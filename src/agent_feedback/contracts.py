"""Deterministic skill-contract checks. Semantic judgments intentionally excluded."""
from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _schema() -> dict[str, Any]:
    schema_path = resources.files("agent_feedback").joinpath("schemas/skill-contract.schema.json")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def load_contracts(path: str | Path) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        Draft202012Validator(_schema()).validate(data)
    except Exception as exc:
        # Keep the public API stable while exposing the exact schema location.
        if exc.__class__.__module__.startswith("jsonschema"):
            location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
            raise ValueError(f"Invalid contract at {location}: {exc.message}") from exc
        raise
    result = {}
    for contract in data:
        name = contract["skill"]
        if name in result:
            raise ValueError(f"Duplicate contract: {name}")
        for group in (contract.get("trigger") or {}).values():
            for rule in group:
                for pattern in rule["patterns"]:
                    try:
                        re.compile(pattern, re.I)
                    except re.error as exc:
                        raise ValueError(f"Invalid regex for {name}/{rule['id']}: {pattern!r}: {exc}") from exc
        result[name] = contract
    return result


def _match(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def evaluate(goal: str, selections: list[str], contracts: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Return evidence-bearing findings; no finding means no defined rule matched, not task success."""
    findings = []
    for skill, contract in contracts.items():
        trigger = contract.get("trigger") or {}
        for rule in trigger.get("required") or []:
            if _match(rule["patterns"], goal) and skill not in selections:
                findings.append({"priority": "P1", "skill": skill, "rule": "required_not_selected",
                                 "rule_id": rule["id"], "evidence": f"Goal matched {rule['id']}; {skill} was not selected"})
        if skill in selections:
            for rule in trigger.get("forbidden") or []:
                if _match(rule["patterns"], goal):
                    findings.append({"priority": "P1", "skill": skill, "rule": "forbidden_selection",
                                     "rule_id": rule["id"], "evidence": f"Goal matched forbidden rule {rule['id']}"})
            maximum = (contract.get("execution") or {}).get("max_selections")
            count = selections.count(skill)
            if maximum and count > maximum:
                findings.append({"priority": "P2", "skill": skill, "rule": "excess_selections",
                                 "rule_id": "max_selections", "evidence": f"Selected {count} times; maximum is {maximum}"})
    return findings
