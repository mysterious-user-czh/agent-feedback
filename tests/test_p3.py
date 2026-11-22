import json
import tempfile
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.p3 import assess, confusion, summarize


CONTRACTS = {
    "right": {"skill": "right", "trigger": {"required": [{"id": "convert", "patterns": ["转换"]}]}},
    "wrong": {"skill": "wrong", "trigger": {"forbidden": [{"id": "convert", "patterns": ["转换"]}]}},
}


def verification(outcome="success", evidence=None, source="observed", artifact_source="live"):
    return {"type": "verification", "payload": {"outcome": outcome,
            "evidence": evidence or ["checked"], "source": source, "artifact_source": artifact_source}}


class P3Tests(unittest.TestCase):
    def test_missing_evidence_is_unknown_with_reason(self):
        result = assess("未定义任务", [], [], {})
        self.assertTrue(all(v["status"] == "unknown" for v in result.values()))
        self.assertTrue(all(v["reason"] for v in result.values()))
        stats = summarize([result])["dimensions"]["routing"]
        self.assertEqual(stats["abstention_rate"], 1)
        self.assertEqual(stats["unknown_reason_coverage"], 1)

    def test_required_contract_pass_and_fail(self):
        self.assertEqual(assess("转换文档", ["right"], [], CONTRACTS)["routing"]["status"], "pass")
        self.assertEqual(assess("转换文档", [], [], CONTRACTS)["routing"]["status"], "fail")
        self.assertEqual(assess("转换文档", ["wrong"], [], CONTRACTS)["routing"]["status"], "fail")

    def test_expected_selection_is_used_only_as_explicit_truth(self):
        label = {"source": "human", "expected_selection": "right"}
        self.assertEqual(assess("开放任务", ["right"], [], {}, label)["routing"]["status"], "pass")
        self.assertEqual(assess("开放任务", ["other"], [], {}, label)["routing"]["status"], "fail")

    def test_route_artifact_exit_and_execution_stay_independent(self):
        events = [
            {"type": "tool_result", "payload": {"name": "python", "status": "failure", "recovered": False}},
            verification(evidence=["PDF checked"]),
            {"type": "process_result", "payload": {"exit_code": 1}},
        ]
        result = assess("转换文档", ["right"], events, CONTRACTS)
        self.assertEqual(result["routing"]["status"], "pass")
        self.assertEqual(result["execution"]["status"], "fail")
        self.assertEqual(result["artifact"]["status"], "pass")
        self.assertEqual(result["exit"]["status"], "fail")

    def test_latest_objective_verification_and_recovered_failure(self):
        events = [
            {"type": "tool_result", "payload": {"name": "python", "status": "failure", "recovered": True}},
            verification("failure", ["missing"], artifact_source="imported"),
            verification("success", ["now exists"]),
        ]
        result = assess("开放任务", [], events, {})
        self.assertEqual(result["execution"]["status"], "pass")
        self.assertEqual(result["artifact"]["status"], "pass")

    def test_unknown_or_self_reported_verification_cannot_pass(self):
        for event in (verification(source="self_reported"), verification(artifact_source="unknown")):
            result = assess("开放任务", [], [event, {"type": "process_result", "payload": {"exit_code": 0}}], {})
            self.assertEqual(result["artifact"]["status"], "unknown")
            self.assertEqual(result["artifact"]["reason"], "verification_provenance_not_objective")
            self.assertEqual(result["outcome"]["status"], "unknown")

    def test_confusion_excludes_unknown_from_accuracy_but_not_coverage(self):
        matrix = confusion([
            {"kind": "routing", "actual": "pass", "predicted": "pass"},
            {"kind": "routing", "actual": "pass", "predicted": "unknown"},
            {"kind": "outcome", "actual": "fail", "predicted": "fail"},
        ])
        self.assertEqual(matrix["routing"]["abstained"], 1)
        self.assertEqual(matrix["routing"]["accuracy_when_judged"], 1)
        self.assertEqual(matrix["routing"]["coverage"], 0.5)
        self.assertEqual(matrix["overall"]["labeled"], 3)

    def test_process_result_validation_and_report_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = FeedbackService(Path(tmp) / "feedback.db")
            try:
                task = service.start("test", "开放任务")["task_id"]
                with self.assertRaisesRegex(ValueError, "integer"):
                    service.event(task, "process_result", {"exit_code": "0"})
                service.event(task, "process_result", {"exit_code": 0})
                report = json.loads(service.report(response_format="json"))
                self.assertEqual(report["items"][0]["assessment"]["exit"]["status"], "pass")
                self.assertEqual(report["p3"]["dimensions"]["routing"]["unknown"], 1)
                self.assertEqual(report["p3"]["confusion"], {})
                self.assertIn("unknown 表示证据不足", service.report())
            finally:
                service.close()

    def test_tool_failure_does_not_create_routing_truth(self):
        events = [{"type": "tool_result", "payload": {"name": "python", "status": "failure"}}]
        result = assess("开放任务", ["any"], events, {})
        self.assertEqual(result["execution"]["status"], "fail")
        self.assertEqual(result["routing"]["status"], "unknown")

    def test_outcome_is_artifact_exit_rollup_not_artifact_copy(self):
        events = [verification(evidence=["live checked"]),
                  {"type": "process_result", "payload": {"exit_code": 1}}]
        result = assess("开放任务", [], events, {})
        self.assertEqual(result["artifact"]["status"], "pass")
        self.assertEqual(result["outcome"]["status"], "fail")
        self.assertEqual(result["outcome"]["reason"], "deterministic_completion_failed")
        self.assertIn("artifact_source=live", result["artifact"]["evidence"])

    def test_outcome_waits_for_exit_and_human_label_can_supply_semantic_truth(self):
        events = [verification()]
        result = assess("开放任务", [], events, {})
        self.assertEqual(result["outcome"]["status"], "unknown")
        labeled = assess("开放任务", [], events, {},
                         {"source": "human", "outcome": "failure", "comment": "wrong deliverable"})
        self.assertEqual(labeled["outcome"]["status"], "fail")
        self.assertEqual(labeled["outcome"]["reason"], "human_outcome_label")


if __name__ == "__main__":
    unittest.main()
