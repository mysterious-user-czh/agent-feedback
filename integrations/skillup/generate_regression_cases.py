"""Freeze skill-up cases from observed failures, never from a synthetic success story."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "integrations/skillup/evals"
SOURCE = ROOT / "validation/p2-clean/results.json"
NORMAL_SPEC = ROOT / "evaluation/p2/real-tasks-01.json"
BEFORE_HOME = ROOT / "validation/p2-clean/hermes-home"
AFTER_HOME = ROOT / "validation/candidate-11-shared-home"
FROZEN_BEFORE = ROOT / "validation/p4-regression-before-home"
CASE_ID = "p2-04-confusable-image-compression"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def freeze_before_home() -> None:
    if FROZEN_BEFORE.exists():
        shutil.rmtree(FROZEN_BEFORE)
    ignored = shutil.ignore_patterns(
        "state.db*", "logs", "cache", "runtime", "kanban.db*", "cron",
        "environments", "installs", ".env", "auth.json", "auth.lock",
        "projects.db", "spawn-ledger.json*", "gateway*", "*.lock",
        "models_dev_cache*", "plugin-update-checks",
    )
    shutil.copytree(BEFORE_HOME, FROZEN_BEFORE, ignore=ignored)


def main() -> None:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))["results"]
    failures = [row for row in rows if row["case_id"] == CASE_ID]
    assert len(failures) == 3, "the frozen source case must have exactly three observations"
    assert all(row["artifact_pass"] is False for row in failures), "source is not a stable artifact failure"
    assert all("missing" in row["artifact_evidence"].lower() or "not found" in row["artifact_evidence"].lower()
               for row in failures), "source failure signature is not missing artifact"
    fixture_hashes = {row["fixture_sha256"]["word-image.docx"] for row in failures}
    assert len(fixture_hashes) == 1, "source fixture changed between observations"

    first_work = SOURCE.parent / "work" / failures[0]["run_id"]
    fixture_source = first_work / "fixtures/word-image.docx"
    assert sha256(fixture_source) == fixture_hashes.pop(), "fixture does not match source evidence"
    fixture_dir = EVALS / "fixtures/image-compression/workspace/fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_source, fixture_dir / "word-image.docx")

    # Use the same original goal; only the run-specific output filename is made reusable.
    query = failures[0]["query"]
    original_output = f"artifacts/{failures[0]['run_id']}.docx"
    assert original_output in query, "unexpected source query; refusing to invent a goal"
    query = query.replace(original_output, "artifacts/compressed.docx")
    case = f"""id: p2-04-image-compression-regression
title: Observed missing-artifact failure from the frozen p2-clean batch
input:
  prompt: |
    {query}
context:
  repo_fixture: evals/fixtures/image-compression/workspace
expect:
  files_exist:
    - artifacts/compressed.docx
judge:
  type: script
  script_path: evals/scripts/check_image_compression.ps1
  timeout_seconds: 30
"""
    (EVALS / "cases/image-compression.yaml").write_text(case, encoding="utf-8")

    # The enhanced judge is maintained as a standalone reviewable artifact, not overwritten here.
    judge_path = EVALS / "scripts/check_image_compression.ps1"
    judge_text = judge_path.read_text(encoding="utf-8")
    assert sha256(fixture_dir / "word-image.docx") in judge_text, "judge fixture hash is stale"
    for required_check in ("images_decode", "dimensions_preserved_or_scaled", "alpha_preserved"):
        assert required_check in judge_text, f"judge lacks {required_check}"

    normal_tasks = json.loads(NORMAL_SPEC.read_text(encoding="utf-8"))["tasks"]
    normal = next(task for task in normal_tasks if task["task_id"] == "real-05-body-edit")
    normal_fixture = ROOT / "validation/real-tasks-07-final/fixtures/body.docx"
    if not normal_fixture.exists():
        candidates = list((ROOT / "validation/real-tasks-07-final/work").glob("*/fixtures/body.docx"))
        assert len(candidates) >= 1, "normal-control fixture is missing"
        normal_fixture = candidates[0]
    normal_dir = EVALS / "fixtures/body-edit/workspace/fixtures"
    normal_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(normal_fixture, normal_dir / "body.docx")
    normal_case = f"""id: real-05-normal-body-edit-control
title: Normal Word body edit must not regress after the compression instruction fix
input:
  prompt: |
    {normal['query']}
context:
  repo_fixture: evals/fixtures/body-edit/workspace
expect:
  files_exist:
    - artifacts/body-edited.docx
judge:
  type: script
  script_path: evals/scripts/check_body_edit.ps1
  timeout_seconds: 30
"""
    (EVALS / "cases/normal-body-edit.yaml").write_text(normal_case, encoding="utf-8")
    normal_judge = r'''$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$checks = [ordered]@{
  exit_zero = ($env:EVAL_EXIT_CODE -eq '0')
  input_unchanged = ((Get-FileHash 'fixtures/body.docx' -Algorithm SHA256).Hash.ToLower() -eq '__FIXTURE_HASH__')
}
if (Test-Path 'artifacts/body-edited.docx') {
  try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path 'artifacts/body-edited.docx'))
    try {
      $entry = $zip.GetEntry('word/document.xml')
      $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
      try { $xml = $reader.ReadToEnd() } finally { $reader.Dispose() }
      $checks['new_marker_present'] = $xml.Contains('NEW_BODY_VALUE')
      $checks['old_marker_absent'] = -not $xml.Contains('OLD_BODY_VALUE')
      $checks['table_preserved'] = $xml.Contains('TABLE_KEEP_OK')
    } finally { $zip.Dispose() }
  } catch { $checks['docx_opens'] = $false }
} else { $checks['docx_opens'] = $false }
$checks | ConvertTo-Json -Compress
if ($checks.Values -contains $false) { exit 1 }
exit 0
'''.replace("__FIXTURE_HASH__", sha256(normal_dir / "body.docx"))
    (EVALS / "scripts/check_body_edit.ps1").write_text(normal_judge, encoding="utf-8")

    freeze_before_home()
    manifest = {
        "schema_version": 1,
        "source": {
            "batch": "p2-clean", "case_id": CASE_ID, "observations": 3,
            "failure_signature": "artifact_missing",
            "observed_missing_artifacts": 3,
            "source_results_sha256": sha256(SOURCE),
            "fixture_sha256": sha256(fixture_dir / "word-image.docx"),
        },
        "before": {"template": "p4-regression-before-home", "skill_tree_sha256": tree_hash(FROZEN_BEFORE / "skills")},
        "after": {"template": "candidate-11-shared-home", "skill_tree_sha256": tree_hash(AFTER_HOME / "skills"),
                  "change": "Existing candidate-10 fix plus quality-85 alignment, alpha preservation and decode/dimension self-checks"},
        "promotion_rule": "Two fresh before runs must both have the same missing-artifact signature; otherwise classify as flaky and do not claim a stable before/after regression.",
        "required_runs": {"before": 2, "after": 3, "normal_after": 1},
        "budget_per_run": {"max_turns_regression": 12, "max_turns_normal": 16,
                            "timeout_seconds": 240, "token_budget": None, "cost_budget": None,
                            "unavailable_budget_fields": "token_and_cost_unknown",
                            "actual_controls_evidence": "validation/BATCH/**/.agent-feedback/engine-controls.json",
                            "skillup_turns_semantics": "reported by skill-up; not assumed to equal CLI agent rounds or used as budget-enforcement evidence"},
        "normal_control": {"task_id": normal["task_id"], "fixture_sha256": sha256(normal_dir / "body.docx")},
        "privacy": "No raw transcript, final response, session ID, credential, or live database is included in generated cases.",
    }
    output = ROOT / "evaluation/p4/regression-case-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
