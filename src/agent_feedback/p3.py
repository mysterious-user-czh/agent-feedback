"""P3 deterministic three-state assessment, abstention and labeled confusion metrics."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .contracts import evaluate

STATUSES = ("pass", "fail", "unknown")
DIMENSIONS = ("routing", "execution", "artifact", "exit", "outcome")


def _decision(status: str, reason: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence": evidence or []}


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def assess(goal: str, selections: list[str], events: list[dict[str, Any]],
           contracts: dict[str, dict[str, Any]], label: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive independent dimensions. Missing evidence always remains unknown."""
    label = label or {}
    route_findings = [f for f in evaluate(goal, selections, contracts)
                      if f["rule"] in {"required_not_selected", "forbidden_selection"}]
    expected = label.get("expected_selection") if label.get("source") == "human" else None
    if route_findings:
        routing = _decision("fail", "deterministic_contract_violation",
                            [f["evidence"] for f in route_findings])
    elif expected:
        routing = (_decision("pass", "human_expected_selection_matched", [f"Expected {expected}"])
                   if expected in selections else
                   _decision("fail", "human_expected_selection_not_matched", [f"Expected {expected}"]))
    elif label.get("source") == "human" and label.get("failure_stage") == "routing":
        routing = _decision("fail", "human_confirmed_routing_failure",
                            [label.get("comment") or "Human routing label"])
    else:
        satisfied = []
        for skill, contract in contracts.items():
            if skill not in selections:
                continue
            for rule in (contract.get("trigger") or {}).get("required") or []:
                if _matches(rule["patterns"], goal):
                    satisfied.append(f"{skill}:{rule['id']}")
        routing = (_decision("pass", "required_contract_satisfied", satisfied) if satisfied
                   else _decision("unknown", "no_reliable_routing_truth"))

    tools = [e["payload"] for e in events if e["type"] == "tool_result"]
    failures = [t for t in tools if t["status"] == "failure" and not t.get("recovered")]
    cancellations = [t for t in tools if t["status"] == "cancelled"]
    if failures:
        execution = _decision("fail", "tool_failure_observed",
                              [f"{t['name']}:{t.get('error_class') or 'failure'}" for t in failures])
    elif tools and not (cancellations and len(cancellations) == len(tools)):
        execution = _decision("pass", "tool_results_successful_or_recovered")
    elif cancellations:
        execution = _decision("unknown", "cancelled_without_execution_result")
    else:
        execution = _decision("unknown", "no_tool_result_evidence")

    verifications = [e["payload"] for e in events if e["type"] == "verification"
                     and e["payload"]["outcome"] in {"success", "failure"}]
    if verifications:
        latest = verifications[-1]
        artifact_source = latest.get("artifact_source", "unknown")
        verification_source = latest.get("source", "unknown")
        evidence = [f"artifact_source={artifact_source}", f"verification_source={verification_source}"]
        evidence += latest.get("evidence") or []
        if verification_source not in {"observed", "human"} or artifact_source not in {"live", "imported"}:
            artifact = _decision("unknown", "verification_provenance_not_objective", evidence)
        else:
            artifact = _decision("pass" if latest["outcome"] == "success" else "fail",
                                 f"objective_verification_{artifact_source}", evidence)
    else:
        artifact = _decision("unknown", "no_objective_verification")

    processes = [e["payload"] for e in events if e["type"] == "process_result"]
    if processes:
        code = processes[-1]["exit_code"]
        exit_result = _decision("pass" if code == 0 else "fail", "process_exit_code", [f"exit_code={code}"])
    else:
        exit_result = _decision("unknown", "no_process_result")

    if label.get("source") == "human" and label.get("outcome") in {"success", "failure"}:
        outcome = _decision("pass" if label["outcome"] == "success" else "fail",
                            "human_outcome_label", [label.get("comment") or "Human outcome label"])
    elif artifact["status"] == "fail" or exit_result["status"] == "fail":
        outcome = _decision("fail", "deterministic_completion_failed",
                            [f"artifact={artifact['status']}", f"exit={exit_result['status']}"])
    elif artifact["status"] == "pass" and exit_result["status"] == "pass":
        outcome = _decision("pass", "deterministic_artifact_exit_rollup",
                            ["artifact=pass", "exit=pass"])
    else:
        outcome = _decision("unknown", "incomplete_completion_evidence",
                            [f"artifact={artifact['status']}", f"exit={exit_result['status']}"])
    return {"routing": routing, "execution": execution, "artifact": artifact,
            "exit": exit_result, "outcome": outcome}


def confusion(records: list[dict[str, str]]) -> dict[str, Any]:
    """Build per-type actual pass/fail × predicted pass/fail/unknown matrices."""
    valid = [r for r in records if r.get("actual") in {"pass", "fail"}
             and r.get("predicted") in STATUSES and r.get("kind")]
    kinds = sorted({r["kind"] for r in valid})
    matrices = {}
    for kind in kinds + (["overall"] if kinds else []):
        rows = valid if kind == "overall" else [r for r in valid if r["kind"] == kind]
        counts = {actual: {predicted: 0 for predicted in STATUSES} for actual in ("pass", "fail")}
        for row in rows:
            counts[row["actual"]][row["predicted"]] += 1
        judged = sum(counts[a][p] for a in counts for p in ("pass", "fail"))
        correct = sum(counts[a][a] for a in ("pass", "fail"))
        abstained = sum(counts[a]["unknown"] for a in counts)
        matrices[kind] = {
            "matrix": counts, "labeled": len(rows), "judged": judged, "abstained": abstained,
            "correct_when_judged": correct,
            "accuracy_when_judged": correct / judged if judged else None,
            "coverage": judged / len(rows) if rows else None,
        }
    return matrices


def summarize(assessments: list[dict[str, Any]], truth: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Aggregate all dimensions; unknown reason coverage is not root-cause accuracy."""
    dimensions = {}
    for name in DIMENSIONS:
        counts = Counter(a[name]["status"] for a in assessments)
        unknowns = [a[name] for a in assessments if a[name]["status"] == "unknown"]
        reasoned = sum(bool(a.get("reason")) for a in unknowns)
        dimensions[name] = {
            **{status: counts[status] for status in STATUSES},
            "total": len(assessments),
            "abstention_rate": counts["unknown"] / len(assessments) if assessments else None,
            "unknown_reason_coverage": reasoned / len(unknowns) if unknowns else None,
        }
    return {"dimensions": dimensions, "confusion": confusion(truth or [])}
