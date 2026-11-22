"""skill-up custom local engine for an isolated Hermes CLI run."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def confined(root: Path, value: str) -> Path:
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if path != root and root not in path.parents:
        raise ValueError("path escapes workspace")
    return path


def parse_stream(path: Path) -> tuple[str | None, str, list[dict]]:
    session_id, final, transcript = None, "", []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id is None:
            match = re.search(r"local-[0-9a-f]{64}", json.dumps(row, ensure_ascii=False))
            if match:
                session_id = match.group(0)
        kind = row.get("type")
        if kind in {"tool_call", "tool.call", "tool_use"} or "tool_call" in row:
            payload = row.get("tool_call", row)
            name = payload.get("name") or payload.get("tool_name") or "unknown"
            args = payload.get("arguments") or payload.get("args") or payload.get("input") or row.get("input") or {}
            transcript.append({"role": "assistant", "content": json.dumps(
                {"tool_call": name, "arguments": args}, ensure_ascii=False)[:4000]})
        elif kind == "tool_result":
            transcript.append({"role": "tool", "content": json.dumps({
                "name": row.get("name"), "is_error": bool(row.get("is_error")),
                "output": row.get("output"), "tool_call_id": row.get("tool_call_id"),
            }, ensure_ascii=False)[:4000]})
        if kind in {"final", "assistant", "message", "result"}:
            final = str(row.get("content") or row.get("text") or final)
    return session_id, final, transcript


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    input_path = Path(args.input).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    workspace = Path(payload["workspace"]).resolve()
    output_path = confined(workspace, args.output)
    started = time.monotonic()
    result = {"engine": "hermes", "exit_code": 1, "final_message": "engine did not run",
              "transcript": payload.get("messages") or [], "artifacts": {"files": []}}
    try:
        template = Path(os.environ["AGENT_FEEDBACK_HERMES_TEMPLATE"]).resolve()
        hermes = Path(os.environ["AGENT_FEEDBACK_HERMES_BIN"]).resolve()
        root = workspace / ".agent-feedback"
        home = root / "hermes-home"
        runtime_home = root / "home"
        temp = root / "temp"
        root.mkdir(exist_ok=True)
        if not home.exists():
            shutil.copytree(template, home, ignore=shutil.ignore_patterns(
                "state.db*", "logs", "cache", "runtime", "kanban.db*", "cron"))
        env_source = Path(os.environ["AGENT_FEEDBACK_HERMES_ENV_FILE"])
        if env_source.exists():
            blocked = ("WEIXIN", "WECHAT", "TELEGRAM", "DISCORD", "SLACK", "WHATSAPP", "MATRIX", "LINE_")
            lines = [line for line in env_source.read_text(encoding="utf-8").splitlines()
                     if not any(token in line.split("=", 1)[0].strip().upper() for token in blocked)]
            (home / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        runtime_home.mkdir(exist_ok=True)
        temp.mkdir(exist_ok=True)
        messages = payload.get("messages") or []
        if not messages or any(not isinstance(m.get("content"), str) for m in messages):
            raise ValueError("SessionInput.messages must contain string content")
        prompt = "\n".join(m["content"] for m in messages if m.get("role") == "user")
        if not prompt:
            raise ValueError("SessionInput contains no user prompt")
        env = os.environ.copy()
        env.update({"HOME": str(runtime_home), "HERMES_HOME": str(home),
                    "TEMP": str(temp), "TMP": str(temp)})
        stream = root / "stream.jsonl"
        received_max_turns = int(payload.get("max_turns") or 8)
        received_timeout = int(payload.get("timeout_seconds") or 300)
        timeout = min(received_timeout, 300)
        controls = {"received_max_turns": received_max_turns, "cli_max_turns": received_max_turns,
                    "received_timeout_seconds": received_timeout, "effective_timeout_seconds": timeout,
                    "skillup_turns_semantics": "reported_by_skillup_not_assumed_to_be_cli_agent_rounds"}
        (root / "engine-controls.json").write_text(json.dumps(controls, indent=2) + "\n", encoding="utf-8")
        command = [str(hermes), "chat", "--cli", "--oneshot", "--format", "stream-json",
                   "--max-turns", str(received_max_turns), "--source", "tool", "-q", prompt]
        try:
            with stream.open("w", encoding="utf-8") as stdout:
                completed = subprocess.run(command, cwd=workspace, env=env, stdout=stdout,
                                           stderr=subprocess.STDOUT, timeout=timeout)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = 124
        session_id, final, tool_transcript = parse_stream(stream)
        artifacts = []
        artifact_root = workspace / "artifacts"
        if artifact_root.exists():
            for path in sorted(p for p in artifact_root.rglob("*") if p.is_file()):
                artifacts.append({"name": str(path.relative_to(workspace)),
                                  "path": str(path.relative_to(workspace))})
        result = {"engine": "hermes", "model": os.environ.get("AGENT_FEEDBACK_MODEL", ""),
                  "session_id": session_id or "", "exit_code": code,
                  "duration_ms": int((time.monotonic() - started) * 1000),
                  "final_message": final,
                  "transcript": messages + tool_transcript + ([{"role": "assistant", "content": final}] if final else []),
                  "artifacts": {"files": artifacts, "generated_files": [a["path"] for a in artifacts]}}
    except Exception as exc:
        result["final_message"] = f"Adapter error: {type(exc).__name__}: {exc}"
        result["exit_code"] = 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=False)
    output_path.write_text(serialized, encoding="utf-8")
    # skill-up consumes --output; retain the exact same SessionResult as a private
    # run artifact so independent validation can re-import the observed engine result.
    raw_artifact = workspace / "artifacts/session-result.json"
    raw_artifact.parent.mkdir(parents=True, exist_ok=True)
    raw_artifact.write_text(serialized, encoding="utf-8")
    # skill-up reliably archives this declared probe artifact. Embed the exact
    # engine result for private independent re-import; public tracking strips it.
    probe_artifact = workspace / "artifacts/probe-result.json"
    if result["exit_code"] == 0 and probe_artifact.is_file():
        probe = json.loads(probe_artifact.read_text(encoding="utf-8"))
        probe["engine_session_result"] = result
        probe_artifact.write_text(json.dumps(probe, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                  encoding="utf-8")


if __name__ == "__main__":
    main()
