import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_feedback.adapters.hermes import import_hermes
from agent_feedback.service import FeedbackService


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def start(self, external_id):
        return self.service.start("test", f"goal {external_id}", external_id=external_id)["task_id"]

    def failure(self, task, event_id):
        self.service.event(task, "tool_result", {"name": "tool", "status": "failure"}, event_id)

    def test_filters_counts_and_stable_triage_sort(self):
        p0 = self.start("p0")
        self.failure(p0, "p0-error-1")
        self.failure(p0, "p0-error-2")
        self.service.label(p0, "failure", "routing", comment="confirmed")
        p1 = self.start("p1")
        self.failure(p1, "p1-error-1")
        self.service.label(p1, "unknown", comment="不是用这个", source="observed")
        plain_failure = self.start("plain-failure")
        self.failure(plain_failure, "plain-error")
        self.start("clean")

        report = json.loads(self.service.report(response_format="json", limit=100))
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["filtered_total"], 4)
        self.assertEqual([item["external_id"] for item in report["items"]],
                         ["p0", "p1", "plain-failure", "clean"])
        self.assertEqual(report["items"][0]["tool_error_count"], 2)
        self.assertEqual(report["items"][1]["selection_count"], 0)
        self.assertEqual(report["items"][2]["execution_status"], "fail")

        only_p1 = json.loads(self.service.report(response_format="json", priority="P1"))
        self.assertEqual((only_p1["total"], only_p1["filtered_total"]), (4, 1))
        self.assertEqual(only_p1["priority_counts"]["P1"], 1)
        failures = json.loads(self.service.report(
            response_format="json", execution="fail", has_tool_errors=True, limit=100))
        self.assertEqual(failures["filtered_total"], 3)
        observed = json.loads(self.service.report(response_format="json", has_observed_label=True))
        self.assertEqual([item["external_id"] for item in observed["items"]], ["p1"])
        without_errors = json.loads(self.service.report(response_format="json", has_tool_errors=False))
        self.assertEqual([item["external_id"] for item in without_errors["items"]], ["clean"])

    def test_p1_items_precede_unflagged_tasks_on_first_page(self):
        for index in range(30):
            self.start(f"plain-{index}")
        flagged = self.start("flagged")
        self.service.label(flagged, "unknown", comment="用错了", source="observed")
        page = json.loads(self.service.report(response_format="json", priority="P1", limit=100))
        self.assertEqual(page["filtered_total"], 1)
        default = json.loads(self.service.report(response_format="json", limit=100))
        self.assertEqual(default["items"][0]["external_id"], "flagged")

    def test_legacy_success_with_later_failure_is_p1_conflict(self):
        task = self.start("legacy-conflict")
        self.service.event(task, "verification", {
            "outcome": "success", "artifact_source": "live", "evidence": ["checked"]
        }, "verification-success")
        self.service.label(task, "success")
        self.service.event(task, "verification", {
            "outcome": "failure", "artifact_source": "live", "evidence": ["later oracle failure"]
        }, "verification-failure")
        item = json.loads(self.service.report(response_format="json"))["items"][0]
        self.assertTrue(item["label_verification_conflict"])
        finding = next(f for f in item["findings"] if f["rule"] == "label_evidence_conflict")
        evidence = json.loads(finding["evidence"])
        self.assertEqual(evidence["reason"], "latest_not_success")
        self.assertEqual(evidence["verification_event_id"], "verification-failure")
        self.assertTrue(evidence["label_revision_id"].startswith("rev_"))
        self.assertEqual(item["priority"], "P1")

    def test_legacy_success_without_valid_provenance_is_conflict(self):
        task = self.start("legacy-source")
        self.service.store.execute(
            "INSERT INTO events VALUES(?,?,?,?,?)",
            ("legacy-verification", task, "verification", json.dumps({
                "outcome": "success", "source": "self_reported", "artifact_source": "live",
                "evidence": ["old self report"]
            }), "legacy"),
        )
        self.service.store.execute(
            "INSERT INTO labels VALUES(?,?,?,?,?,?,?)",
            (task, "success", "unknown", None, "legacy", "human", "legacy"),
        )
        item = json.loads(self.service.report(response_format="json"))["items"][0]
        self.assertTrue(item["label_verification_conflict"])
        finding = next(f for f in item["findings"] if f["rule"] == "label_evidence_conflict")
        self.assertEqual(json.loads(finding["evidence"])["reason"], "source")

    def test_source_time_is_set_and_backfilled_on_unchanged_import(self):
        source = self.root / "state.db"
        con = sqlite3.connect(source)
        con.executescript(
            "CREATE TABLE sessions(id TEXT PRIMARY KEY,started_at REAL,parent_session_id TEXT);"
            "CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,"
            "tool_calls TEXT,tool_name TEXT,timestamp REAL);"
            "INSERT INTO sessions VALUES('main',1234,NULL);"
            "INSERT INTO messages VALUES(1,'main','user','task',NULL,NULL,1234);"
        )
        con.commit()
        con.close()
        import_hermes(str(source), self.service)
        row = self.service.store.one("SELECT task_id,source_started_at,created_at FROM tasks")
        self.assertIn("1970-01-01T00:20:34", row["source_started_at"])
        original_created = row["created_at"]
        self.service.store.execute("UPDATE tasks SET source_started_at=NULL WHERE task_id=?", (row["task_id"],))
        stats = import_hermes(str(source), self.service)
        self.assertEqual(stats["skipped_unchanged"], 1)
        restored = self.service.store.one("SELECT source_started_at,created_at FROM tasks WHERE task_id=?", (row["task_id"],))
        self.assertIn("1970-01-01T00:20:34", restored["source_started_at"])
        self.assertEqual(restored["created_at"], original_created)


if __name__ == "__main__":
    unittest.main()
