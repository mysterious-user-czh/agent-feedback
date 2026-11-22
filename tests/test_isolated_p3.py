import json
import tempfile
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.adapters.isolated_hermes import _artifact_source, import_isolated_batch


class IsolatedP3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.batch = self.root / "batch"
        (self.batch / "raw").mkdir(parents=True)
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps({"tasks": [
            {"task_id": "ok", "query": "转换文档"},
            {"task_id": "bad", "query": "开放任务"},
        ]}), encoding="utf-8")
        rows = [
            {"task_id": "ok", "run_id": "run-ok", "selected_skills": ["right"],
             "artifact_pass": True, "artifact_evidence": "file checked", "exit_code": 0},
            {"task_id": "bad", "run_id": "run-bad", "selected_skills": [],
             "artifact_pass": False, "artifact_evidence": "file missing", "exit_code": 2},
        ]
        (self.batch / "results.json").write_text(json.dumps({
            "summary": {"runs": 2}, "results": rows}), encoding="utf-8")
        for index, (row, session) in enumerate(zip(rows, ("s1", "s2"))):
            (self.batch / "raw" / f"{row['run_id']}.json").write_text(json.dumps({
                "run_id": row["run_id"], "case_id": row["task_id"], "session_id": session,
                "config_sha256": "abc", "exit_code": row["exit_code"]}), encoding="utf-8")
            trace = {"type": "tool_result", "name": "terminal", "tool_call_id": f"call-{index}",
                     "is_error": index == 1, "output": json.dumps({"exit_code": index})}
            (self.batch / "raw" / f"{row['run_id']}.stream.jsonl").write_text(
                json.dumps(trace) + "\n", encoding="utf-8")
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def test_import_creates_independent_oracle_and_exit_events(self):
        stats = import_isolated_batch(self.batch, self.spec, self.service)
        self.assertEqual(stats["imported"], 2)
        self.assertEqual(stats["verification_events"], 2)
        self.assertEqual(stats["process_events"], 2)
        self.assertEqual(stats["tool_events"], 2)
        self.assertEqual(stats["tool_failures"], 1)
        items = {i["external_id"]: i for i in json.loads(self.service.report(response_format="json"))["items"]}
        ok = items["isolated:run-ok"]["assessment"]
        bad = items["isolated:run-bad"]["assessment"]
        self.assertEqual(ok["artifact"]["status"], "pass")
        self.assertEqual(ok["artifact"]["reason"], "objective_verification_imported")
        self.assertIn("artifact_source=imported", ok["artifact"]["evidence"])
        self.assertEqual(ok["exit"]["status"], "pass")
        self.assertEqual(ok["execution"]["status"], "pass")
        self.assertEqual(bad["artifact"]["status"], "fail")
        self.assertEqual(bad["exit"]["status"], "fail")
        self.assertEqual(bad["execution"]["status"], "fail")
        self.assertEqual(bad["routing"]["status"], "unknown")

    def test_reimport_has_zero_new_events(self):
        import_isolated_batch(self.batch, self.spec, self.service)
        second = import_isolated_batch(self.batch, self.spec, self.service)
        self.assertEqual(second["already_present"], 2)
        self.assertEqual(second["selection_events"], 0)
        self.assertEqual(second["tool_events"], 0)
        self.assertEqual(second["verification_events"], 0)
        self.assertEqual(second["process_events"], 0)

    def test_cancelled_tool_is_not_counted_as_failure(self):
        path = self.batch / "raw" / "run-ok.stream.jsonl"
        path.write_text(json.dumps({"type": "tool_result", "name": "terminal", "tool_call_id": "cancel",
                                    "output": json.dumps({"exit_code": 130})}) + "\n", encoding="utf-8")
        stats = import_isolated_batch(self.batch, self.spec, self.service)
        self.assertEqual(stats["tool_cancellations"], 1)
        self.assertEqual(stats["tool_failures"], 1)
        item = json.loads(self.service.report(response_format="json"))["items"]
        ok = next(i for i in item if i["external_id"] == "isolated:run-ok")
        self.assertEqual(ok["assessment"]["execution"]["status"], "unknown")

    def test_live_requires_frozen_oracle_provenance(self):
        self.assertEqual(_artifact_source({"artifact_source": "live"}), ("imported", True))
        row = {"artifact_source": "live", "provenance": {"harness_version": "v1",
               "config_sha256": "abc", "skill_tree_sha256": "def"}}
        self.assertEqual(_artifact_source(row), ("live", False))

    def test_raw_result_mismatch_is_rejected(self):
        path = self.batch / "raw" / "run-ok.json"
        row = json.loads(path.read_text(encoding="utf-8"))
        row["exit_code"] = 9
        path.write_text(json.dumps(row), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exit mismatch"):
            import_isolated_batch(self.batch, self.spec, self.service)


if __name__ == "__main__":
    unittest.main()
