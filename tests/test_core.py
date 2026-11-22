import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.adapters.hermes import import_hermes


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        if hasattr(self, "hermes"):
            self.hermes.close()
        self.tmp.cleanup()

    def start(self, external_id=None):
        return self.service.start("test-agent", "Convert a report", external_id=external_id)["task_id"]

    def make_hermes(self):
        db = self.root / "hermes.db"
        con = sqlite3.connect(db)
        con.executescript("""
            CREATE TABLE sessions(id TEXT, started_at REAL, parent_session_id TEXT);
            CREATE TABLE messages(
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                tool_calls TEXT, tool_name TEXT, timestamp REAL
            );
        """)
        self.hermes = con
        self.now = time.time()
        return db

    def message(self, message_id, session_id, role, content=None, calls=None,
                tool_name=None, timestamp=None):
        self.hermes.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
            (message_id, session_id, role, content, calls, tool_name,
             self.now if timestamp is None else timestamp),
        )
        self.hermes.commit()

    def test_success_requires_latest_objective_verification(self):
        task = self.start()
        with self.assertRaisesRegex(ValueError, "latest_not_success"):
            self.service.label(task, "success")
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.service.event(task, "verification", {"outcome": "success"})
        success = {"outcome": "success", "artifact_source": "live", "evidence": ["artifact checked"]}
        failure = {"outcome": "failure", "artifact_source": "live", "evidence": ["later failure"]}
        self.service.event(task, "verification", success, "verify-success-1")
        self.service.event(task, "verification", failure, "verify-failure-1")
        with self.assertRaisesRegex(ValueError, "latest_not_success"):
            self.service.label(task, "success")
        self.service.event(task, "verification", success, "verify-success-2")
        self.assertTrue(self.service.label(task, "success")["saved"])
        self.assertTrue(self.service.label(task, "success")["duplicate"])
        self.service.event(task, "verification", success, "verify-success-3")
        self.assertTrue(self.service.label(task, "success")["duplicate"])

    def test_self_reported_or_unknown_success_is_rejected(self):
        task = self.start()
        invalid = [
            {"outcome": "success", "evidence": ["agent says done"], "source": "self_reported", "artifact_source": "live"},
            {"outcome": "success", "evidence": ["agent says done"], "source": "observed", "artifact_source": "unknown"},
        ]
        for payload in invalid:
            with self.assertRaisesRegex(ValueError, "success verification"):
                self.service.event(task, "verification", payload)
        # Legacy rows bypass current input validation; the label gate must still reject them.
        self.service.store.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            ("legacy-self-report", task, "verification", json.dumps(invalid[0]), "legacy"),
        )
        with self.assertRaisesRegex(ValueError, "source"):
            self.service.label(task, "success")

    def test_tool_error_is_counted_without_creating_a_finding(self):
        task = self.start()
        self.service.event(task, "tool_result", {"name": "python", "status": "failure", "error_class": "missing_file"})
        report = json.loads(self.service.report(response_format="json"))
        item = report["items"][0]
        self.assertIsNone(item["failure_stage"])
        self.assertEqual(len(item["tool_errors"]), 1)
        self.assertEqual(item["candidates"], [])
        self.assertEqual(item["findings"], [])
        self.assertIsNone(item["priority"])
        self.assertEqual(report["tool_error_count"], 1)

    def test_human_failure_is_p0_but_success_comment_is_not(self):
        failed = self.start("failed")
        self.service.label(failed, "failure", "routing", comment="confirmed wrong skill")
        succeeded = self.start("succeeded")
        self.service.event(succeeded, "verification", {"outcome": "success", "artifact_source": "live", "evidence": ["artifact checked"]})
        self.service.label(succeeded, "success", comment="looks good")
        items = {i["external_id"]: i for i in json.loads(self.service.report(response_format="json"))["items"]}
        self.assertEqual(items["failed"]["priority"], "P0")
        self.assertEqual(items["failed"]["findings"][0]["rule"], "confirmed_routing_issue")
        self.assertIsNone(items["succeeded"]["priority"])
        self.assertEqual(items["succeeded"]["findings"], [])

    def test_idempotent_external_task_and_event(self):
        first = self.service.start("test-agent", "Task", external_id="stable")
        second = self.service.start("test-agent", "Changed duplicate", external_id="stable")
        self.assertEqual(first["task_id"], second["task_id"])
        self.service.event(first["task_id"], "selection", {"kind": "skill", "name": "x", "source": "observed"}, "fixed-event")
        duplicate = self.service.event(first["task_id"], "selection", {"kind": "skill", "name": "x", "source": "observed"}, "fixed-event")
        self.assertTrue(duplicate["duplicate"])

    def test_invalid_input_and_pagination(self):
        task = self.start()
        with self.assertRaises(ValueError):
            self.service.event(task, "selection", {"kind": "skill", "name": "x", "source": "guessed"})
        with self.assertRaises(ValueError):
            self.service.event("missing", "selection", {"kind": "skill", "name": "x"})
        for n in range(4):
            self.service.start("test-agent", f"Task {n}")
        page = json.loads(self.service.report(limit=2, response_format="json"))
        self.assertEqual(page["total"], 5)
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_offset"], 2)

    def test_secret_redaction(self):
        self.service.start("test-agent", "Use sk-abcdefghijklmnop")
        data = json.loads(self.service.report(response_format="json"))
        self.assertNotIn("sk-abcdefghijklmnop", json.dumps(data))
        self.assertIn("[REDACTED]", data["items"][0]["goal"])

    def test_hermes_import_excludes_subagents_by_default(self):
        db = self.make_hermes()
        self.hermes.execute("INSERT INTO sessions VALUES('main',?,NULL)", (self.now,))
        self.hermes.execute("INSERT INTO sessions VALUES('child',?,'main')", (self.now,))
        self.hermes.commit()
        self.message(1, "main", "user", "主会话任务")
        self.message(2, "child", "user", "评测子会话")
        stats = import_hermes(str(db), self.service)
        self.assertEqual(stats["imported"], 1)
        self.assertEqual(stats["excluded_subagents"], 1)
        included = import_hermes(str(db), self.service, include_subagents=True)
        self.assertEqual(included["imported"], 1)
        self.assertEqual(included["total_sessions"], 2)

    def test_hermes_incremental_old_session_and_zero_duplicates(self):
        db = self.make_hermes()
        self.hermes.execute("INSERT INTO sessions VALUES('s1',1,NULL)")
        self.hermes.commit()
        calls = json.dumps([{"function": {"name": "skill_view", "arguments": json.dumps({"name": "microsoft-office"})}}])
        self.message(1, "s1", "user", "Convert this document", timestamp=1)
        first = import_hermes(str(db), self.service, hours=1)
        self.assertEqual(first["imported"], 0)
        self.message(2, "s1", "assistant", calls=calls)
        self.message(3, "s1", "user", "不是用这个技能")
        self.message(4, "s1", "tool", '{"success":true,"text":"error"}', tool_name="demo")
        self.message(5, "s1", "tool", '{"success":false,"error":"failed"}', tool_name="demo")
        second = import_hermes(str(db), self.service, hours=1)
        third = import_hermes(str(db), self.service, hours=1)
        self.assertEqual(second["selection_events"], 1)
        self.assertEqual(second["tool_errors"], 1)
        self.assertEqual(second["correction_candidates"], 1)
        self.assertEqual(third["selection_events"], 0)
        self.assertEqual(third["tool_errors"], 0)
        self.assertEqual(third["correction_candidates"], 0)
        self.message(6, "s1", "assistant", calls=calls)
        fourth = import_hermes(str(db), self.service, hours=1)
        self.assertEqual(fourth["selection_events"], 1)
        self.assertEqual(fourth["correction_candidates"], 0)
        items = {i["external_id"]: i for i in json.loads(self.service.report(response_format="json"))["items"]}
        first_item = items["hermes:s1:segment:1"]
        self.assertEqual(first_item["outcome"], "unknown")
        self.assertEqual(first_item["failure_stage"], "unknown")
        self.assertEqual(first_item["selections"], ["microsoft-office", "microsoft-office"])
        self.assertEqual(len(first_item["tool_errors"]), 1)
        self.assertEqual(first_item["priority"], "P1")
        self.assertEqual(first_item["segment_type"], "task")

    def test_automated_user_envelope_is_not_a_correction(self):
        db = self.make_hermes()
        self.hermes.execute("INSERT INTO sessions VALUES('s1',?,NULL)", (self.now,))
        self.hermes.commit()
        initial = "初始需求：别用doSomething这种命名" + "长" * 2100
        self.message(1, "s1", "user", initial)
        self.message(2, "s1", "user", initial)
        self.message(3, "s1", "user", "[ASYNC DELEGATION BATCH COMPLETE]\\n子任务说：别改这个")
        stats = import_hermes(str(db), self.service)
        self.assertEqual(stats["correction_candidates"], 0)
        self.assertEqual(stats["imported"], 2)
        self.assertEqual(stats["segment_messages"], 3)
        items = json.loads(self.service.report(response_format="json"))["items"]
        self.assertTrue(all(item["outcome"] is None for item in items))
        self.assertEqual({item["goal"] for item in items}, {initial[:2000]})

    def test_hermes_never_overwrites_human_label(self):
        db = self.make_hermes()
        self.hermes.execute("INSERT INTO sessions VALUES('s1',?,NULL)", (self.now,))
        self.hermes.commit()
        self.message(1, "s1", "user", "initial request")
        import_hermes(str(db), self.service)
        task = self.service.store.one("SELECT task_id FROM tasks WHERE external_id='hermes:s1:segment:1'")["task_id"]
        self.service.label(task, "failure", "execution", comment="人工结论")
        self.message(2, "s1", "user", "我说的是另一个文件")
        stats = import_hermes(str(db), self.service)
        self.assertEqual(stats["human_labels_preserved"], 1)
        self.assertEqual(stats["correction_candidates"], 0)
        label = self.service.store.one("SELECT * FROM labels WHERE task_id=?", (task,))
        self.assertEqual(label["source"], "human")
        self.assertEqual(label["comment"], "人工结论")
        self.assertEqual(label["failure_stage"], "execution")


if __name__ == "__main__":
    unittest.main()
