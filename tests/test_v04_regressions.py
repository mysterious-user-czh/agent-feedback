import json
import sqlite3
import tempfile
import tomllib
import unittest
from importlib import metadata, resources
from pathlib import Path

import agent_feedback
from agent_feedback import FeedbackService
from agent_feedback.contracts import load_contracts
from agent_feedback.store import Store


ROOT = Path(__file__).resolve().parents[1]


class V04RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def start(self):
        return self.service.start("test", "Test deterministic fixes")["task_id"]

    def test_observed_cannot_overwrite_human_or_add_revision(self):
        task = self.start()
        self.service.label(task, "failure", "execution", comment="人工结论", actor="reviewer")
        before = self.service.store.one("SELECT COUNT(*) AS n FROM label_revisions WHERE task_id=?", (task,))["n"]
        for source in ("observed", "self_reported"):
            result = self.service.label(task, "unknown", source=source)
            self.assertTrue(result["preserved"])
            self.assertFalse(result["saved"])
        current = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (task,))
        after = self.service.store.one("SELECT COUNT(*) AS n FROM label_revisions WHERE task_id=?", (task,))["n"]
        self.assertEqual(current["source"], "human")
        self.assertEqual(current["outcome"], "failure")
        self.assertEqual(after, before)

    def test_human_revision_requires_reason_and_preserves_history(self):
        task = self.start()
        self.service.label(task, "unknown", comment="待复核", actor="reviewer")
        with self.assertRaisesRegex(ValueError, "reason"):
            self.service.label(task, "failure", "routing", comment="确认错选")
        revised = self.service.label(
            task, "failure", "routing", comment="确认错选", actor="reviewer", reason="核对原始轨迹"
        )
        self.assertTrue(revised["saved"])
        rows = self.service.store.all(
            "SELECT outcome,comment,actor,reason FROM label_revisions WHERE task_id=? ORDER BY created_at,revision_id", (task,)
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["outcome"] for row in rows], ["unknown", "failure"])
        self.assertEqual(rows[-1]["reason"], "核对原始轨迹")

    def test_identical_label_does_not_add_revision(self):
        task = self.start()
        self.service.label(task, "unknown", source="observed")
        duplicate = self.service.label(task, "unknown", source="observed")
        self.assertTrue(duplicate["duplicate"])
        count = self.service.store.one("SELECT COUNT(*) AS n FROM label_revisions WHERE task_id=?", (task,))["n"]
        self.assertEqual(count, 1)

    def test_legacy_labels_migrate_once(self):
        path = self.root / "legacy.db"
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE tasks(task_id TEXT PRIMARY KEY,agent TEXT,external_id TEXT,session_id TEXT,
                               goal TEXT,config_hash TEXT,created_at TEXT);
            CREATE TABLE labels(task_id TEXT PRIMARY KEY,outcome TEXT,failure_stage TEXT,
                                expected_selection TEXT,comment TEXT,source TEXT,updated_at TEXT);
            INSERT INTO tasks VALUES('old','test',NULL,NULL,'legacy',NULL,'2026-01-01');
            INSERT INTO labels VALUES('old','failure','routing',NULL,'old label','human','2026-01-02');
        """)
        con.close()
        store = Store(path)
        try:
            migrated = store.one("SELECT * FROM label_revisions WHERE task_id='old'")
            self.assertEqual(migrated["revision_id"], "legacy_old")
            self.assertEqual(migrated["outcome"], "failure")
        finally:
            store.close()
        reopened = Store(path)
        try:
            count = reopened.one("SELECT COUNT(*) AS n FROM label_revisions WHERE task_id='old'")["n"]
            self.assertEqual(count, 1)
        finally:
            reopened.close()

    def test_events_reject_update_and_delete(self):
        task = self.start()
        event = self.service.event(task, "selection", {"kind": "skill", "name": "demo", "source": "observed"})
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.service.store.execute("UPDATE events SET type='artifact' WHERE event_id=?", (event["event_id"],))
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.service.store.execute("DELETE FROM events WHERE event_id=?", (event["event_id"],))

    def test_failure_and_cancellation_are_statistics_not_findings(self):
        task = self.start()
        self.service.event(task, "tool_result", {"name": "one", "status": "failure"})
        self.service.event(task, "tool_result", {"name": "two", "status": "cancelled"})
        report = json.loads(self.service.report(response_format="json"))
        item = report["items"][0]
        self.assertEqual(report["tool_error_count"], 1)
        self.assertEqual(report["cancellation_count"], 1)
        self.assertEqual(item["findings"], [])
        self.assertIsNone(item["priority"])

    def test_schema_is_packaged_and_invalid_contracts_are_rejected(self):
        schema = json.loads(resources.files("agent_feedback").joinpath("schemas/skill-contract.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(len(load_contracts(ROOT / "examples" / "contracts.json")), 10)
        invalid = self.root / "invalid.json"
        invalid.write_text(json.dumps([{"skill": "x"}]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "version"):
            load_contracts(invalid)
        invalid.write_text(json.dumps([{
            "skill": "x", "version": 1,
            "trigger": {"required": [{"id": "bad", "patterns": ["["]}]}
        }]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid regex"):
            load_contracts(invalid)

    def test_version_metadata_is_aligned(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        expected = project["project"]["version"]
        self.assertEqual(expected, "0.12.0")
        self.assertEqual(agent_feedback.__version__, expected)
        self.assertEqual(metadata.version("agent-feedback-local"), expected)


if __name__ == "__main__":
    unittest.main()
