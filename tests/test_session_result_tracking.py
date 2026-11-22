import json
import tempfile
import unittest
from pathlib import Path

from agent_feedback.adapters.session_result import import_session_result
from agent_feedback.service import FeedbackService
from agent_feedback.tracking import log_skillup_result, sanitize_skillup_result


class SessionResultTests(unittest.TestCase):
    def test_engine_neutral_import_is_idempotent_and_preserves_unknown_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = {
                "engine": "deterministic-reference", "session_id": "reference-1", "exit_code": 0,
                "transcript": [{"role": "user", "content": "copy fixture"},
                               {"role": "tool", "content": json.dumps({"name": "copy", "is_error": False,
                                                                         "output": {"exit_code": 0}})}],
                "artifacts": {"files": [{"name": "artifacts/output.txt", "path": "artifacts/output.txt",
                                          "sha256": "a" * 64}]},
            }
            path = root / "result.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            service = FeedbackService(root / "feedback.db")
            try:
                verification = {"outcome": "success", "evidence": ["Live oracle: exact output"],
                                "source": "observed", "artifact_source": "live"}
                first = import_session_result(path, service, verification=verification, external_id="ref:1")
                second = import_session_result(path, service, verification=verification, external_id="ref:1")
                self.assertTrue(first["created"])
                self.assertFalse(second["created"])
                self.assertEqual(second["tool_events"], 0)
                report = json.loads(service.report(agent="deterministic-reference", response_format="json"))
                assessment = report["items"][0]["assessment"]
                self.assertEqual(assessment["routing"]["status"], "unknown")
                self.assertEqual(assessment["execution"]["status"], "pass")
                self.assertEqual(assessment["artifact"]["status"], "pass")
                self.assertEqual(assessment["exit"]["status"], "pass")
                self.assertEqual(assessment["outcome"]["status"], "pass")
            finally:
                service.close()

    def test_cancelled_tool_is_not_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "result.json"
            path.write_text(json.dumps({"engine": "reference", "exit_code": 0,
                                        "transcript": [{"role": "user", "content": "stop"},
                                                       {"role": "tool", "content": json.dumps({"name": "shell",
                                                                                               "output": {"exit_code": 130}})}]}),
                            encoding="utf-8")
            service = FeedbackService(root / "feedback.db")
            try:
                import_session_result(path, service)
                report = json.loads(service.report(agent="reference", response_format="json"))
                self.assertEqual(report["cancellation_count"], 1)
                self.assertEqual(report["tool_error_count"], 0)
            finally:
                service.close()


class TrackingTests(unittest.TestCase):
    def test_sanitizer_drops_prompts_responses_and_raw_errors(self):
        clean = sanitize_skillup_result({"schema_version": "v1alpha1", "engine_name": "hermes",
            "observed_configuration": {"model": "unknown"}, "case_results": [{
                "case_id": "case-1", "status": "PASS", "duration_ms": 10, "turns": 2,
                "prompt": "SECRET PROMPT", "response": "PRIVATE RESPONSE", "error": "RAW PATH",
                "grading": {"assertion_results": [{"text": "script: C:/private/check.ps1", "passed": True,
                                                    "evidence": "{\"exit_zero\":true}"}]}}]})
        encoded = json.dumps(clean)
        self.assertNotIn("SECRET PROMPT", encoded)
        self.assertNotIn("PRIVATE RESPONSE", encoded)
        self.assertNotIn("RAW PATH", encoded)
        self.assertNotIn("C:/private", encoded)
        self.assertEqual(clean["cases"][0]["checks"][0]["checks"], {"exit_zero": True})

    def test_remote_tracking_uri_is_rejected_before_optional_import(self):
        for uri in ("https://example.invalid", "file://remote-host/share"):
            with self.assertRaisesRegex(ValueError, "local file"):
                log_skillup_result("unused.json", tracking_uri=uri,
                                   experiment_name="x", artifact_root="unused", code_version="x")


if __name__ == "__main__":
    unittest.main()
