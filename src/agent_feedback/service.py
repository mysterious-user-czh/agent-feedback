"""Application service shared by MCP, CLI, and platform adapters."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import evaluate, load_contracts
from .models import FAILURE_STAGES, OUTCOMES, SOURCES, choice, clean_text, validate_event
from .p3 import assess, summarize
from .store import Store


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class FeedbackService:
    def __init__(self, db_path: str | Path, contracts_path: str | Path | None = None):
        self.store = Store(db_path)
        self.contracts = load_contracts(contracts_path) if contracts_path else {}

    def close(self) -> None:
        self.store.close()

    def start(self, agent: str, goal: str, session_id: str | None = None,
              config_hash: str | None = None, external_id: str | None = None) -> dict[str, Any]:
        agent = clean_text(agent, "agent", required=True, limit=100)
        goal = clean_text(goal, "goal", required=True, limit=2000)
        session_id = clean_text(session_id, "session_id", limit=200) or None
        config_hash = clean_text(config_hash, "config_hash", limit=128) or None
        external_id = clean_text(external_id, "external_id", limit=200) or None
        if external_id:
            old = self.store.one("SELECT task_id FROM tasks WHERE agent=? AND external_id=?", (agent, external_id))
            if old:
                return {"task_id": old["task_id"], "created": False}
        task_id = "task_" + uuid.uuid4().hex
        self.store.execute(
            "INSERT INTO tasks(task_id,agent,external_id,session_id,goal,config_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (task_id, agent, external_id, session_id, goal, config_hash, utcnow()),
        )
        return {"task_id": task_id, "created": True}

    def event(self, task_id: str, type: str, payload: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
        task_id = clean_text(task_id, "task_id", required=True, limit=200)
        if not self.store.one("SELECT task_id FROM tasks WHERE task_id=?", (task_id,)):
            raise ValueError("Unknown task_id; call feedback_start first")
        payload = validate_event(type, payload)
        type = payload.pop("_type", type)
        event_id = clean_text(event_id, "event_id", limit=300) or "evt_" + uuid.uuid4().hex
        if self.store.one("SELECT event_id FROM events WHERE event_id=?", (event_id,)):
            return {"event_id": event_id, "created": False, "duplicate": True}
        self.store.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)", (event_id, task_id, type, json.dumps(payload, ensure_ascii=False, sort_keys=True), utcnow())
        )
        return {"event_id": event_id, "created": True, "duplicate": False}

    def label(self, task_id: str, outcome: str = "unknown", failure_stage: str = "unknown",
              expected_selection: str | None = None, comment: str | None = None,
              source: str = "human", actor: str | None = None, reason: str | None = None) -> dict[str, Any]:
        task_id = clean_text(task_id, "task_id", required=True, limit=200)
        if not self.store.one("SELECT task_id FROM tasks WHERE task_id=?", (task_id,)):
            raise ValueError("Unknown task_id; call feedback_start first")
        outcome = choice(outcome, OUTCOMES, "outcome")
        failure_stage = choice(failure_stage, FAILURE_STAGES, "failure_stage")
        source = choice(source, SOURCES, "source")
        actor = clean_text(actor or source, "actor", required=True, limit=200)
        reason = clean_text(reason, "reason", limit=2000)
        expected_selection = clean_text(expected_selection, "expected_selection", limit=200) or None
        comment = clean_text(comment, "comment", limit=2000) or None
        if outcome == "success" and failure_stage != "unknown":
            raise ValueError("Successful tasks must use failure_stage='unknown'")
        if outcome == "success":
            latest = self.store.one(
                "SELECT event_id,payload FROM events WHERE task_id=? AND type='verification' "
                "ORDER BY rowid DESC LIMIT 1", (task_id,),
            )
            reason = None
            payload = json.loads(latest["payload"]) if latest else {}
            if not latest or payload.get("outcome") != "success":
                reason = "latest_not_success"
            elif payload.get("source") not in {"observed", "human"}:
                reason = "source"
            elif payload.get("artifact_source") not in {"live", "imported"}:
                reason = "artifact_source"
            elif not payload.get("evidence"):
                reason = "evidence_empty"
            if reason:
                raise ValueError(f"Cannot label success: {reason}; latest objective live/imported verification is required")
        with self.store.transaction():
            current = self.store.one("SELECT * FROM labels WHERE task_id=?", (task_id,))
            if current and current["source"] == "human" and source != "human":
                return {"task_id": task_id, "saved": False, "preserved": True,
                        "outcome": current["outcome"], "failure_stage": current["failure_stage"]}
            values = (outcome, failure_stage, expected_selection, comment, source)
            old_values = tuple(current[k] for k in ("outcome", "failure_stage", "expected_selection", "comment", "source")) if current else None
            if current and values == old_values:
                return {"task_id": task_id, "outcome": outcome, "failure_stage": failure_stage,
                        "saved": False, "duplicate": True}
            if current and current["source"] == "human" and not reason:
                raise ValueError("Revising a human label requires a reason")
            now = utcnow()
            revision_id = "rev_" + uuid.uuid4().hex
            self.store.execute(
                "INSERT INTO label_revisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (revision_id, task_id, outcome, failure_stage, expected_selection, comment,
                 source, actor, reason or "Initial label", now),
            )
            self.store.execute(
                "INSERT INTO labels VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                "outcome=excluded.outcome,failure_stage=excluded.failure_stage,expected_selection=excluded.expected_selection,"
                "comment=excluded.comment,source=excluded.source,updated_at=excluded.updated_at",
                (task_id, outcome, failure_stage, expected_selection, comment, source, now),
            )
        return {"task_id": task_id, "outcome": outcome, "failure_stage": failure_stage,
                "saved": True, "revision_id": revision_id}

    def report(self, agent: str | None = None, selection: str | None = None,
               review_status: str = "all", limit: int = 20, offset: int = 0,
               response_format: str = "markdown", priority: str | None = None,
               execution: str | None = None, has_tool_errors: bool | None = None,
               has_observed_label: bool | None = None, sort: str = "priority",
               search: str | None = None) -> dict[str, Any] | str:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be >= 0")
        if review_status not in {"all", "pending", "reviewed"}:
            raise ValueError("review_status must be all, pending, or reviewed")
        if priority not in {None, "P0", "P1", "P2", "none"}:
            raise ValueError("priority must be P0, P1, P2, none, or omitted")
        if execution not in {None, "pass", "fail", "unknown"}:
            raise ValueError("execution must be pass, fail, unknown, or omitted")
        if sort not in {"priority", "source_time", "tool_errors"}:
            raise ValueError("sort must be priority, source_time, or tool_errors")
        if response_format not in {"markdown", "json"}:
            raise ValueError("response_format must be markdown or json")
        search = clean_text(search, "search", limit=200) or None
        where, params = [], []
        if agent:
            where.append("t.agent=?")
            params.append(agent)
        if review_status == "pending":
            where.append("(l.task_id IS NULL OR l.source != 'human')")
        elif review_status == "reviewed":
            where.append("l.source = 'human'")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        tasks = self.store.all(
            f"SELECT t.*,l.outcome,l.failure_stage,l.expected_selection,l.comment,l.source AS label_source,ts.segment_type "
            f"FROM tasks t LEFT JOIN labels l USING(task_id) LEFT JOIN task_segments ts USING(task_id) {clause} ORDER BY t.created_at DESC", tuple(params)
        )
        items = []
        for task in tasks:
            events = [self.store.payload(e) for e in self.store.all("SELECT rowid AS sequence,* FROM events WHERE task_id=? ORDER BY rowid", (task["task_id"],))]
            selections = [e["payload"]["name"] for e in events if e["type"] == "selection"]
            if selection and selection not in selections:
                continue
            errors = [e["payload"] for e in events if e["type"] == "tool_result" and e["payload"]["status"] == "failure"]
            cancellations = [e["payload"] for e in events if e["type"] == "tool_result" and e["payload"]["status"] == "cancelled"]
            findings = []
            candidates = []
            human_failure = task.get("label_source") == "human" and (
                task.get("failure_stage") == "routing" or task.get("outcome") == "failure"
            )
            if human_failure:
                candidates.append("human_feedback")
                findings.append({"priority": "P0", "rule": "confirmed_routing_issue" if task.get("failure_stage") == "routing" else "confirmed_task_failure",
                                 "evidence": task.get("comment") or "Human label confirms failure"})
            verification_events = [e for e in events if e["type"] == "verification"]
            latest_verification = verification_events[-1] if verification_events else None
            verification_payload = latest_verification["payload"] if latest_verification else {}
            conflict_reason = None
            if task.get("label_source") == "human" and task.get("outcome") == "success":
                if not latest_verification or verification_payload.get("outcome") != "success":
                    conflict_reason = "latest_not_success" if latest_verification else "verification_missing"
                elif verification_payload.get("source") not in {"observed", "human"}:
                    conflict_reason = "source"
                elif verification_payload.get("artifact_source") not in {"live", "imported"}:
                    conflict_reason = "artifact_source"
                elif not verification_payload.get("evidence"):
                    conflict_reason = "evidence_empty"
                if conflict_reason:
                    revision = self.store.one(
                        "SELECT revision_id FROM label_revisions WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
                        (task["task_id"],),
                    )
                    evidence = json.dumps({
                        "reason": conflict_reason,
                        "label_revision_id": revision["revision_id"] if revision else None,
                        "verification_event_id": latest_verification["event_id"] if latest_verification else None,
                    }, ensure_ascii=False, sort_keys=True)
                    candidates.append("label_evidence_conflict")
                    findings.append({"priority": "P1", "rule": "label_evidence_conflict", "evidence": evidence})
            if task.get("label_source") == "observed" and task.get("comment"):
                candidates.append("user_correction_candidate")
                findings.append({"priority": "P1", "rule": "user_correction_candidate", "evidence": task["comment"]})
            if len(set(selections)) > 1:
                candidates.append("multiple_selections_review_needed")
                findings.append({"priority": "P1", "rule": "multiple_selections_review_needed",
                                 "evidence": "Multiple distinct skills selected; review whether each was necessary"})
            contract_findings = evaluate(task["goal"], selections, self.contracts)
            findings.extend(contract_findings)
            candidates.extend(f["rule"] for f in contract_findings)
            priorities = {f["priority"] for f in findings}
            task_priority = next((p for p in ("P0", "P1", "P2") if p in priorities), None)
            label = {"source": task.get("label_source"), "outcome": task.get("outcome"),
                     "failure_stage": task.get("failure_stage"),
                     "expected_selection": task.get("expected_selection"),
                     "comment": task.get("comment")}
            assessment = assess(task["goal"], selections, events, self.contracts, label)
            items.append({**task, "selections": selections, "tool_errors": errors,
                          "cancellations": cancellations,
                          "verification": [e["payload"] for e in verification_events],
                          "candidates": candidates, "findings": findings, "priority": task_priority,
                          "label_verification_conflict": conflict_reason is not None,
                          "execution_status": assessment["execution"]["status"],
                          "tool_error_count": len(errors), "cancellation_count": len(cancellations),
                          "selection_count": len(selections),
                          "assessment": assessment, "event_count": len(events)})
        if search:
            needle = search.casefold()
            items = [item for item in items if needle in " ".join(
                [item["goal"], item["task_id"], *item["selections"]]).casefold()]
        total = len(items)
        filtered = [item for item in items if (
            (priority is None or (item["priority"] is None if priority == "none" else item["priority"] == priority))
            and (execution is None or item["execution_status"] == execution)
            and (has_tool_errors is None or bool(item["tool_errors"]) is has_tool_errors)
            and (has_observed_label is None or (item.get("label_source") == "observed") is has_observed_label)
        )]
        filtered_total = len(filtered)
        filtered.sort(key=lambda item: item.get("source_started_at") or item["created_at"], reverse=True)
        if sort == "tool_errors":
            filtered.sort(key=lambda item: item["tool_error_count"], reverse=True)
        elif sort == "priority":
            filtered.sort(key=lambda item: item["tool_error_count"], reverse=True)
            filtered.sort(key=lambda item: {"P0": 0, "P1": 1, "P2": 2}.get(item["priority"], 3))
        page = filtered[offset:offset + limit]
        truth = []
        for item in filtered:
            if item.get("label_source") == "human" and item.get("outcome") in {"success", "failure"}:
                truth.append({"kind": "outcome", "actual": "pass" if item["outcome"] == "success" else "fail",
                              "predicted": item["assessment"]["outcome"]["status"]})
                if item.get("failure_stage") == "routing":
                    truth.append({"kind": "routing", "actual": "fail", "predicted": item["assessment"]["routing"]["status"]})
                elif item["outcome"] == "success" and item.get("expected_selection"):
                    truth.append({"kind": "routing", "actual": "pass", "predicted": item["assessment"]["routing"]["status"]})
        priority_counts = {p: sum(f["priority"] == p for item in filtered for f in item["findings"])
                           for p in ("P0", "P1", "P2")}
        result = {"total": total, "filtered_total": filtered_total, "count": len(page), "offset": offset,
                  "has_more": offset + len(page) < filtered_total,
                  "next_offset": offset + limit if offset + len(page) < filtered_total else None,
                  "tool_error_count": sum(len(item["tool_errors"]) for item in filtered),
                  "cancellation_count": sum(len(item["cancellations"]) for item in filtered),
                  "priority_counts": priority_counts,
                  "filters": {"agent": agent, "selection": selection, "review_status": review_status,
                              "priority": priority, "execution": execution,
                              "has_tool_errors": has_tool_errors, "has_observed_label": has_observed_label,
                              "sort": sort, "search": search},
                  "p3": summarize([item["assessment"] for item in filtered], truth), "items": page}
        return json.dumps(result, ensure_ascii=False, indent=2) if response_format == "json" else self._markdown(result)

    @staticmethod
    def _markdown(result: dict[str, Any]) -> str:
        counts = result["priority_counts"]
        lines = ["# Agent Feedback Report", "",
                 f"共 {result['total']} 个任务；筛选后 {result['filtered_total']} 个；当前显示 {result['count']} 个。",
                 f"发现计数：P0 {counts['P0']}；P1 {counts['P1']}；P2 {counts['P2']}。",
                 f"执行统计：工具失败 {result['tool_error_count']}；用户取消 {result['cancellation_count']}（均不自动生成优先级发现）。", "",
                 "P0＝人工确认失败；P1＝触发/纠正候选，需复核；P2＝已定义执行规则的候选。",
                 "工具失败与取消仅作统计，不证明路由或任务失败。",
                 "P3 各维度独立判定；unknown 表示证据不足，不计作成功或失败。",
                 "未发现已定义规则的异常不代表成功。", ""]
        for name, stats in result["p3"]["dimensions"].items():
            rate = "—" if stats["abstention_rate"] is None else f"{stats['abstention_rate']:.1%}"
            lines.append(f"P3 {name}：pass {stats['pass']}；fail {stats['fail']}；unknown {stats['unknown']}；拒判率 {rate}。")
        lines.append("")
        for item in result["items"]:
            states = "；".join(f"{name}={decision['status']}" for name, decision in item["assessment"].items())
            lines += [f"## [{item['priority'] or '无发现'}] {item['goal']}", "",
                      f"- 任务：`{item['task_id']}`；Agent：`{item['agent']}`",
                      f"- 选择：{', '.join(item['selections']) or '无'}",
                      f"- P3：{states}",
                      f"- 结果：{item.get('outcome') or 'unknown'}；归因：{item.get('failure_stage') or 'unknown'}",
                      f"- 工具失败：{len(item['tool_errors'])}；取消：{len(item['cancellations'])}；候选信号：{', '.join(item['candidates']) or '无'}"]
            for finding in item["findings"]:
                lines.append(f"- **{finding['priority']} {finding['rule']}**：{finding['evidence']}")
            if item.get("comment"):
                lines.append(f"- 反馈原文：{item['comment']}")
            lines.append("")
        return "\n".join(lines)
