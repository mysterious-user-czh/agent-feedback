"""Single-source Hermes v2.2 event and message-segment rules.

These are deterministic provenance rules, not semantic task-success inference.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

CORRECTION_RULES_VERSION = "hermes-corrections-v2-contextual"
STRONG_CORRECTION = re.compile(
    r"你(?:理解|听|看)错|我(?:说|指)的是|别改这个|重新来|wrong skill|don't use|"
    r"还是错|没有改成功|撤回|事实错误|需要修正|理解错方向",
    re.I,
)
WEAK_CORRECTION = re.compile(r"不是用|用错|别用|应该.{0,12}(?:用|走)|不对", re.I)
# Kept for callers that only need a lexical prefilter; build_segments uses is_correction.
CORRECTION = re.compile(STRONG_CORRECTION.pattern + "|" + WEAK_CORRECTION.pattern, re.I)
CRON_ENVELOPE = re.compile(r"\[IMPORTANT:[^\n]*cron job", re.I)
KNOWN_ROLES = {"user", "assistant", "tool", "system"}


def is_correction(content: str) -> bool:
    """Recognize direct corrections without indicting later teaching examples.

    Strong, explicit assessments may occur anywhere in a detailed review. Weak
    phrases such as ``别用`` are restricted to the opening context because they
    are common in naming advice, design rules and quoted examples.
    """
    if not content:
        return False
    return bool(STRONG_CORRECTION.search(content) or WEAK_CORRECTION.search(content[:240]))


def event_source(message: Mapping[str, Any]) -> tuple[str, bool]:
    """Classify cron before generic IMPORTANT envelopes."""
    content = (message["content"] or "").lstrip()
    if message["role"] != "user":
        return "background", False
    if content.startswith("[ASYNC DELEGATION"):
        return "delegation", True
    if content.startswith("[CURRENT RUN TIME:") or CRON_ENVELOPE.match(content):
        return "cron", True
    if content.startswith("[IMPORTANT:"):
        return "background", True
    return "user", False


def _segment(session_id: str, external_message_id: Any, kind: str, goal: str | None,
             segment_type: str = "task", ambiguous_reason: str | None = None) -> dict[str, Any]:
    return {
        "external_id": f"hermes:{session_id}:segment:{external_message_id}",
        "session_id": session_id,
        "kind": kind,
        "segment_type": segment_type,
        "ambiguous_reason": ambiguous_reason,
        "goal": goal if goal is not None else f"Hermes automated session {session_id}",
        "goal_source": goal,
        "messages": [],
        "message_ids": [],
    }


def build_segments(session_id: str, messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build stable segments, including incremental automatic-to-human sessions.

    An automatic-prefixed segment always takes its first message ID. Its goal may
    later change from the automatic placeholder to the first human request, but
    its identity and existing event ownership remain stable.
    """
    materialized = list(messages)
    if not materialized:
        return []
    unsupported = sorted({str(message["role"]) for message in materialized if message["role"] not in KNOWN_ROLES})
    # Metadata roles such as session_meta can safely continue a known segment.
    # Ambiguity is reserved for sessions with no known role to anchor attribution.
    if unsupported and not any(message["role"] in KNOWN_ROLES for message in materialized):
        segment = _segment(
            session_id, materialized[0]["id"], "unsupported", None,
            "ambiguous", "unsupported_message_role:" + ",".join(unsupported),
        )
        for index, message in enumerate(materialized):
            source, automated = event_source(message)
            relation = "child_event" if source == "delegation" else ("new_task" if index == 0 else "continuation")
            segment["messages"].append((message, source, relation, automated))
            segment["message_ids"].append(message["id"])
        return [segment]

    sources = {message["id"]: event_source(message) for message in materialized}
    has_human = any(
        sources[message["id"]][0] == "user" and bool(message["content"])
        for message in materialized
    )
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pending_prefix: list[tuple[Mapping[str, Any], str, str, bool]] = []

    for message in materialized:
        source, automated = sources[message["id"]]
        human = source == "user" and bool(message["content"])
        repeated_initial = bool(human and current and message["content"] == current["goal_source"])
        correction = bool(
            human and current is not None and current["kind"] == "human"
            and not repeated_initial and is_correction(message["content"] or "")
        )
        if correction:
            relation = "correction"
        elif human:
            prefix_id = pending_prefix[0][0]["id"] if pending_prefix else message["id"]
            current = _segment(session_id, prefix_id, "human", message["content"])
            current["goal"] = message["content"][:2000]
            segments.append(current)
            if pending_prefix:
                for index, (prefix, prefix_source, _, prefix_automated) in enumerate(pending_prefix):
                    prefix_relation = (
                        "child_event" if index == 0 and prefix_source == "delegation"
                        else "new_task" if index == 0
                        else "child_event" if prefix_source == "delegation"
                        else "continuation"
                    )
                    current["messages"].append((prefix, prefix_source, prefix_relation, prefix_automated))
                    current["message_ids"].append(prefix["id"])
                pending_prefix = []
                relation = "continuation"
            else:
                relation = "new_task"
        elif current is None and has_human:
            pending_prefix.append((message, source, "continuation", automated))
            continue
        else:
            if current is None:
                current = _segment(session_id, message["id"], "automated", None)
                segments.append(current)
                relation = "child_event" if source == "delegation" else "new_task"
            else:
                relation = "child_event" if source == "delegation" else "continuation"
        current["messages"].append((message, source, relation, automated))
        current["message_ids"].append(message["id"])
    return segments
