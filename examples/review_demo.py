"""Create an isolated, deterministic review-site demonstration database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_feedback.service import FeedbackService


def create_demo(path: str | Path, contracts_path: str | Path, *, replace: bool = False) -> dict[str, int]:
    path = Path(path).resolve()
    if path.exists():
        if not replace:
            raise FileExistsError(f"Demonstration database already exists: {path}")
        path.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    service = FeedbackService(path, contracts_path)
    external = 0

    def task(goal: str, selections: list[str], *, tools: list[dict] | None = None,
             verification: dict | None = None, exit_code: int | None = None,
             label: dict | None = None) -> str:
        nonlocal external
        external += 1
        task_id = service.start("review-demo", goal, external_id=f"demo-{external}")["task_id"]
        for name in selections:
            service.event(task_id, "selection", {"kind": "skill", "name": name, "source": "observed"})
        for tool in tools or []:
            service.event(task_id, "tool_result", tool)
        if exit_code is not None:
            service.event(task_id, "process_result", {"exit_code": exit_code, "source": "observed"})
        if verification:
            service.event(task_id, "verification", verification)
        if label:
            service.label(task_id, **label)
        return task_id

    task(
        "修改正文并重新编号公式，交付可打开的 Word 文档",
        ["docx-editing"],
        tools=[{"name": "word_save", "status": "failure", "error_class": "ValidationError", "source": "observed"}],
        verification={"outcome": "failure", "evidence": ["文档重新打开校验失败：公式编号未更新"],
                      "source": "observed", "artifact_source": "live"},
        exit_code=1,
        label={"outcome": "failure", "failure_stage": "routing", "source": "human",
               "actor": "demo-reviewer", "comment": "审核结论：确认问题\n正文任务进入了不完整的处理路径，已人工复现。"},
    )
    task(
        "整理这份会议纪要，保留原有语气",
        ["docx-editing"],
        tools=[{"name": "terminal", "status": "success", "source": "observed"}],
        label={"outcome": "unknown", "failure_stage": "unknown", "source": "observed",
               "actor": "user", "comment": "不是这个，我需要的是纪要压缩而不是排版。"},
    )
    task(
        "分析表格数据并修改正文中的结论",
        ["docx-editing", "microsoft-office"],
        tools=[{"name": "terminal", "status": "success", "source": "observed"}],
        exit_code=0,
    )
    task(
        "修改正文并统一标题格式",
        ["docx-editing", "docx-editing", "docx-editing"],
        tools=[{"name": "terminal", "status": "success", "source": "observed"}],
        exit_code=0,
    )
    task(
        "将 Word 文档导出为 PDF",
        ["microsoft-office"],
        tools=[{"name": "terminal", "status": "success", "source": "observed"}],
        verification={"outcome": "success", "evidence": ["PDF 可解析，共 3 页；页数与源文档一致"],
                      "source": "observed", "artifact_source": "live"},
        exit_code=0,
        label={"outcome": "success", "failure_stage": "unknown", "source": "human",
               "actor": "demo-reviewer", "comment": "人工抽查产物可打开，页数正确。"},
    )
    report = json.loads(service.report(limit=100, response_format="json"))
    reviewed = json.loads(service.report(review_status="reviewed", limit=1, response_format="json"))["total"]
    service.close()
    return {"total": report["total"], "reviewed": reviewed, "pending": report["total"] - reviewed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--contracts", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(json.dumps(create_demo(args.output, args.contracts, replace=args.replace), ensure_ascii=False))


if __name__ == "__main__":
    main()
