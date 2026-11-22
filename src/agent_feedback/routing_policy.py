"""Deterministic, capability-based deny rules for isolated skill routing."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_rules() -> list[dict[str, Any]]:
    return json.loads(Path(__file__).with_name("routing-policy.json").read_text(encoding="utf-8"))["rules"]


def missing_referenced_inputs(query: str, base_dir: str | Path) -> list[str]:
    """Return explicit fixture references that do not exist; never infer unspecified inputs."""
    root = Path(base_dir)
    references = re.findall(r"fixtures[/\\][^\s，。；;\"'`]+", query)
    return sorted({reference for reference in references if not (root / reference).is_file()})


def denied_skills(query: str, rules: list[dict[str, Any]] | None = None,
                  base_dir: str | Path | None = None,
                  managed_skills: set[str] | None = None) -> list[str]:
    """Return capability exclusions and hard missing-input preconditions, never a Top1 choice."""
    if base_dir is not None and missing_referenced_inputs(query, base_dir):
        return sorted(managed_skills or {"microsoft-office", "docx", "docx-editing"})
    denied: set[str] = set()
    matched: list[str] = []
    for rule in rules or load_rules():
        if any(re.search(pattern, query, re.I) for pattern in rule["any"]):
            if rule.get("none") and any(re.search(pattern, query, re.I) for pattern in rule["none"]):
                continue
            denied.update(rule["deny"])
            matched.append(rule["id"])
    return sorted(denied)


def explain(query: str) -> dict[str, Any]:
    """Public evidence helper; the deny result is deliberately independent of task/case IDs."""
    denied = denied_skills(query)
    return {"deny": denied, "basis": "capability_rules", "case_id_used": False}
