"""Deterministic reference engine for SessionInput/SessionResult contract tests only.

This is not an LLM agent and must never be reported as a second real-agent validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path


def confined(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise ValueError("path escapes workspace")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.monotonic()
    input_path = Path(args.input).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    workspace = Path(payload["workspace"]).resolve()
    output = confined(workspace, args.output)
    messages = payload.get("messages") or []
    prompt = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    session_id = "reference-" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]
    result = {"engine": "deterministic-reference", "model": "reference-copy-v1",
              "session_id": session_id, "exit_code": 1, "duration_ms": 0,
              "final_message": "Unsupported reference fixture", "transcript": messages,
              "artifacts": {"files": [], "generated_files": []}}
    try:
        if "fixtures/input.txt" not in prompt or "artifacts/output.txt" not in prompt:
            raise ValueError("reference engine only supports the frozen text-copy contract fixture")
        source = confined(workspace, "fixtures/input.txt")
        target = confined(workspace, "artifacts/output.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        tool = {"role": "tool", "content": json.dumps({"name": "reference_copy", "is_error": False,
                                                       "output": {"exit_code": 0}})}
        result.update({"exit_code": 0, "final_message": "REFERENCE_COPY_OK",
                       "transcript": messages + [tool, {"role": "assistant", "content": "REFERENCE_COPY_OK"}],
                       "artifacts": {"files": [{"name": "artifacts/output.txt", "path": "artifacts/output.txt",
                                                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
                                     "generated_files": ["artifacts/output.txt"]}})
    except Exception as exc:
        result["final_message"] = f"Reference error: {type(exc).__name__}: {exc}"
    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
