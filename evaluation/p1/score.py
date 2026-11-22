"""Reproduce P1 development-set scores using only the standard library.

Usage: python evaluation/p1/score.py
Optional: --golden PATH --predictions PATH --output-dir PATH
"""
import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path


def wilson(successes, total, z=1.959963984540054):
    if not total:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"method": "Wilson score, 95%", "successes": successes, "total": total,
            "lower": max(0.0, centre - margin), "upper": min(1.0, centre + margin)}


def f1_for_rows(rows):
    counts = Counter(row["confusion"] for row in rows)
    tp, fp, fn = counts["TP"], counts["FP"], counts["FN"]
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0


def cluster_bootstrap_f1(rows, sessions, seed=20261115, iterations=10000):
    """Percentile CI resampling whole sessions; fixed seed makes it reproducible."""
    rng = random.Random(seed)
    by_session = {session: [row for row in rows if row["session_id"] == session] for session in sessions}
    values = []
    session_list = list(sessions)
    for _ in range(iterations):
        sampled = [row for session in (rng.choice(session_list) for _ in session_list)
                   for row in by_session[session]]
        values.append(f1_for_rows(sampled))
    values.sort()
    return {"method": f"session-cluster bootstrap percentile, 95%; 10,000 iterations; seed {seed}",
            "iterations": iterations, "seed": seed,
            "lower": values[math.floor(0.025 * (iterations - 1))],
            "upper": values[math.floor(0.975 * (iterations - 1))]}


def score(golden_path, predictions_path):
    golden_bytes = golden_path.read_bytes()
    golden = json.loads(golden_bytes)
    predictions = {(row["session_id"], row["message_id"]): row
                   for row in json.loads(predictions_path.read_text(encoding="utf-8"))}
    rows, differences = [], []
    for case in golden["cases"]:
        key = (case["session_id"], case["message_id"])
        if key not in predictions:
            raise ValueError(f"Missing prediction: {key}")
        pred = predictions[key]
        relation = pred.get("predicted_relation")
        segment = pred.get("predicted_segment")
        unable = bool(pred.get("predicted_ambiguous")) or relation in {"unknown", "ambiguous"} or segment is None
        pred_boundary = relation == "new_task"
        gold_boundary = case["gold_is_boundary"]
        confusion = ("TP" if pred_boundary and gold_boundary else "FP" if pred_boundary and not gold_boundary
                     else "FN" if not pred_boundary and gold_boundary else "TN")
        owner = int(segment.rsplit(":", 1)[1]) if segment is not None else None
        relation_ok = relation == case["gold_relation"]
        owner_ok = owner == case["gold_segment_start_message_id"]
        row = {"session_id": key[0], "message_id": key[1], "confusion": confusion,
               "relation_ok": relation_ok, "owner_ok": owner_ok, "unable": unable}
        rows.append(row)
        if not relation_ok or not owner_ok or pred_boundary != gold_boundary:
            differences.append({"case_id": case["case_id"], "session_id": key[0], "message_id": key[1],
                                "predicted_relation": relation, "gold_relation": case["gold_relation"],
                                "predicted_owner": owner, "gold_owner": case["gold_segment_start_message_id"],
                                "note": case["annotation_note"]})
    counts = Counter(row["confusion"] for row in rows)
    tp, fp, fn, tn = (counts[key] for key in ("TP", "FP", "FN", "TN"))
    total = len(rows)
    positives = tp + fn
    relation_correct = sum(row["relation_ok"] for row in rows)
    owner_correct = sum(row["owner_ok"] for row in rows)
    unable_count = sum(row["unable"] for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else 0.0
    f1 = f1_for_rows(rows)
    selected = set(golden["selected_sessions"])
    covered = {row["session_id"] for row in rows}
    strata = Counter(case["stratum"] for case in golden["cases"])
    return {
        "rules_version": "hermes-message-segments-v2.2-three-fields",
        "golden_sha256": hashlib.sha256(golden_bytes).hexdigest(),
        "selected_sessions": len(selected), "annotated_cases": total, "covered_sessions": len(covered),
        "missing_selected_sessions": sorted(selected - covered), "unexpected_case_sessions": sorted(covered - selected),
        "strata_counts": dict(strata), "gold_positive_boundaries": positives, "predicted_positive_boundaries": tp + fp,
        "boundary_confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "boundary_precision": precision, "boundary_recall": recall, "boundary_f1": f1,
        "relation_accuracy": relation_correct / total, "ownership_accuracy": owner_correct / total,
        "predicted_unable_to_determine_count": unable_count,
        "predicted_unable_to_determine_rate": unable_count / total,
        "gold_ambiguous_cases": sum(bool(case["gold_ambiguous"]) for case in golden["cases"]),
        "unknown_metric_limit": "Measured from predictions; no ambiguous gold examples, so this is not ambiguity-detection effectiveness evidence",
        "confidence_intervals": {
            "boundary_precision": wilson(tp, tp + fp), "boundary_recall": wilson(tp, positives),
            "boundary_f1": cluster_bootstrap_f1(rows, sorted(selected), seed=golden.get("seed", 20261115)),
            "relation_accuracy": wilson(relation_correct, total), "ownership_accuracy": wilson(owner_correct, total),
        },
        "difference_count": len(differences), "differences": differences,
        "review_limit": "Development/diagnostic set only; no human blind review, inter-annotator agreement, or independent test-set evidence",
    }


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=here / "golden.json")
    parser.add_argument("--predictions", type=Path, default=here / "predictions.json")
    parser.add_argument("--output-dir", type=Path, default=here)
    args = parser.parse_args()
    result = score(args.golden, args.predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c = result["confidence_intervals"]
    pct = lambda key: f"{100 * c[key]['lower']:.1f}%–{100 * c[key]['upper']:.1f}%"
    metadata = json.loads(args.golden.read_text(encoding="utf-8"))
    is_validation = "validation" in metadata.get("dataset_role", "")
    dataset_label = "会话隔离验证集" if is_validation else "开发／诊断集"
    review_line = ("- 会话与开发集交集为 0；标签由主 Agent 阅读完整上下文完成，尚无独立人员复核。"
                   if is_validation else "- 已加入独立只读复核；仍不是隔周盲标、人际一致性或独立测试集。")
    lines = ["# P1 分层黄金集指标", "",
             f"- {dataset_label}：{result['annotated_cases']} 点、{result['covered_sessions']} 个会话；黄金正边界 {result['gold_positive_boundaries']} 个（TP+FN），预测正边界 {result['predicted_positive_boundaries']} 个。",
             f"- 实际分层：{json.dumps(result['strata_counts'], ensure_ascii=False)}；这是分层样本，不是全库随机样本。", 
             f"- 边界：TP {result['boundary_confusion']['TP']}、FP {result['boundary_confusion']['FP']}、FN {result['boundary_confusion']['FN']}、TN {result['boundary_confusion']['TN']}。",
             f"- Precision：{result['boundary_precision']:.1%}（95% CI {pct('boundary_precision')}）；Recall：{result['boundary_recall']:.1%}（95% CI {pct('boundary_recall')}）。",
             f"- F1：{result['boundary_f1']:.1%}（95% CI {pct('boundary_f1')}）。",
             f"- 关系准确率：{round(result['relation_accuracy'] * result['annotated_cases'])}/{result['annotated_cases']}（{result['relation_accuracy']:.1%}；95% CI {pct('relation_accuracy')}）。",
             f"- 任务归属准确率：{round(result['ownership_accuracy'] * result['annotated_cases'])}/{result['annotated_cases']}（{result['ownership_accuracy']:.1%}；95% CI {pct('ownership_accuracy')}）。",
             f"- 无法判定比例：实测 {result['predicted_unable_to_determine_count']}/{result['annotated_cases']}（{result['predicted_unable_to_determine_rate']:.1%}）；本批没有歧义黄金例，不能证明歧义检测有效。",
             f"- Precision／Recall／准确率区间使用 Wilson score；F1 使用按会话整组 bootstrap（10,000 次、固定种子 {c['boundary_f1']['seed']}）。区间只反映有限抽样不确定性，不含标注偏差或会话选择偏差。",
             review_line, "", "## 差异清单", ""]
    for item in result["differences"]:
        lines.append(f"- {item['case_id']}／消息 {item['message_id']}：预测 {item['predicted_relation']}→{item['predicted_owner']}，黄金 {item['gold_relation']}→{item['gold_owner']}。{item['note']}。")
    (args.output_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
