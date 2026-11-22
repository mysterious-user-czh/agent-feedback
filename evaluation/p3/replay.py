"""Reproduce P3 routing replay from all 34 public golden cases; standard library + project."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from agent_feedback.contracts import load_contracts
from agent_feedback.p3 import assess, confusion


def main() -> None:
    cases = json.loads((ROOT / "tests/golden_cases.json").read_text(encoding="utf-8"))
    contracts = load_contracts(ROOT / "examples/contracts.json")
    truth = []
    rows = []
    for case in cases:
        predicted = assess(case["goal"], case["selections"], [], contracts)["routing"]
        actual = "fail" if any("required_not_selected" in f or "forbidden_selection" in f
                               for f in case["expected"]) else "pass"
        truth.append({"kind": "routing", "actual": actual, "predicted": predicted["status"]})
        rows.append({"id": case["id"], "actual": actual, "predicted": predicted["status"],
                     "reason": predicted["reason"]})
    metrics = confusion(truth)["routing"]
    result = {"schema": "agent-feedback-p3-replay-v1", "cases": len(cases),
              "coverage_check": {"covered": len(rows), "baseline": len(cases), "missing": []},
              "top1_scored": False,
              "top1_note": "Golden cases define contract outcomes, not reliable Top1 labels.",
              "metrics": metrics, "rows": rows}
    out = Path(__file__).parent
    (out / "replay-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    accuracy = "—" if metrics["accuracy_when_judged"] is None else f"{metrics['accuracy_when_judged']:.1%}"
    coverage = "—" if metrics["coverage"] is None else f"{metrics['coverage']:.1%}"
    lines = ["# P3 黄金集回放", "", f"已覆盖 **{len(rows)}/{len(cases)}**，差集 0。",
             "Top-1 未评分：这些案例只有合约结果，没有可靠唯一最佳选择标签。", "",
             f"- labeled：{metrics['labeled']}", f"- judged：{metrics['judged']}",
             f"- unknown／abstained：{metrics['abstained']}",
             f"- 判定后准确率：{accuracy}", f"- 非拒判覆盖率：{coverage}", "",
             "| actual | predicted pass | predicted fail | predicted unknown |", "|---|---:|---:|---:|"]
    for actual in ("pass", "fail"):
        row = metrics["matrix"][actual]
        lines.append(f"| {actual} | {row['pass']} | {row['fail']} | {row['unknown']} |")
    lines += ["", "unknown 不计入准确率分子或分母，但计入拒判数和覆盖率分母。",
              "该回放只验证确定性路由合约，不证明产物、执行、退出或通用任务效果。", ""]
    (out / "replay-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
