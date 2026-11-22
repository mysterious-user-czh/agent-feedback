import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_feedback.auto_collect import audit_hermes_import, collect_once, watch_hermes
from agent_feedback.service import FeedbackService


class AutoCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "state.db"
        self.con = sqlite3.connect(self.source)
        self.con.executescript(
            "CREATE TABLE sessions(id TEXT PRIMARY KEY,started_at REAL,parent_session_id TEXT);"
            "CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,"
            "tool_calls TEXT,tool_name TEXT,timestamp REAL);"
            "INSERT INTO sessions VALUES('main',1,NULL);"
            "INSERT INTO sessions VALUES('child',1,'main');"
            "INSERT INTO sessions VALUES('empty',1,NULL);"
        )
        self.feedback = self.root / "feedback.db"
        self.service = FeedbackService(self.feedback)

    def tearDown(self):
        self.service.close()
        self.con.close()
        self.tmp.cleanup()

    def message(self, mid, session="main", role="user", content="task", calls=None, tool_name=None):
        self.con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                         (mid, session, role, content, calls, tool_name, mid))
        self.con.commit()

    def test_collect_once_has_full_coverage_and_zero_duplicate_increment(self):
        calls = json.dumps([{"function": {"name": "skill_view", "arguments": json.dumps({"name": "docx"})}}])
        self.message(1)
        self.message(2, role="assistant", calls=calls)
        self.message(3, role="tool", content='{"success":false,"error":"bad"}', tool_name="demo")
        self.message(4, role="tool", content='{"exit_code":"130"}', tool_name="demo")
        self.message(5, session="child")
        first = collect_once(str(self.source), str(self.feedback))
        self.assertTrue(first["success"])
        coverage = first["coverage"]
        self.assertEqual((coverage["covered_sessions"], coverage["source_sessions"]), (1, 1))
        self.assertEqual((coverage["covered_messages"], coverage["source_messages"]), (4, 4))
        self.assertEqual((coverage["covered_skill_selections"], coverage["source_skill_selections"]), (1, 1))
        self.assertEqual((coverage["covered_tool_failures"], coverage["source_tool_failures"]), (1, 1))
        self.assertEqual((coverage["covered_tool_cancellations"], coverage["source_tool_cancellations"]), (1, 1))
        self.assertEqual((coverage["covered_tool_error_or_cancel_events"],
                          coverage["source_tool_error_or_cancel_events"]), (2, 2))
        self.assertEqual((coverage["covered_tool_errors"], coverage["source_tool_errors"]), (1, 1))
        self.assertEqual(coverage["excluded_subagents"], 1)
        self.assertEqual(first["import"]["tool_failures"], 1)
        self.assertEqual(first["import"]["tool_cancellations"], 1)
        self.assertEqual(first["import"]["tool_error_or_cancel_events"], 2)
        second = collect_once(str(self.source), str(self.feedback))
        self.assertTrue(second["success"])
        self.assertEqual(second["import"]["selection_events"], 0)
        self.assertEqual(second["import"]["tool_errors"], 0)
        self.assertEqual(second["import"]["tool_failures"], 0)
        self.assertEqual(second["import"]["tool_cancellations"], 0)
        self.assertEqual(second["import"]["tool_error_or_cancel_events"], 0)
        self.assertEqual(second["import"]["segment_messages"], 0)
        self.message(6, content="new message in old session")
        third = collect_once(str(self.source), str(self.feedback))
        self.assertEqual(third["coverage"]["covered_messages"], 5)
        self.assertEqual(third["import"]["segment_messages"], 1)
        status = json.loads((self.root / "collector-status.json").read_text(encoding="utf-8"))
        self.assertTrue(status["success"])
        self.assertEqual(len((self.root / "collector-history.jsonl").read_text(encoding="utf-8").splitlines()), 3)

    def test_audit_exposes_missing_message_instead_of_trusting_cursor(self):
        self.message(1)
        self.message(2, role="assistant")
        collect_once(str(self.source), str(self.feedback))
        self.service.store.execute("DELETE FROM segment_messages WHERE session_id='main' AND message_id=2")
        coverage = audit_hermes_import(str(self.source), self.service)
        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["missing_messages"], [{"session_id": "main", "message_id": 2}])
        self.assertEqual((coverage["covered_sessions"], coverage["source_sessions"]), (0, 1))

    def test_non_hermes_selection_is_not_an_unexpected_hermes_event(self):
        self.message(1)
        collect_once(str(self.source), str(self.feedback))
        task = self.service.start("other", "other task", external_id="other:1")["task_id"]
        self.service.event(task, "selection", {"kind": "skill", "name": "x", "source": "observed"}, "other:event")
        coverage = audit_hermes_import(str(self.source), self.service)
        self.assertTrue(coverage["coverage_complete"])

    def test_audit_rejects_unexpected_previously_imported_subagent(self):
        self.message(1)
        self.message(2, session="child")
        collect_once(str(self.source), str(self.feedback), include_subagents=True)
        coverage = audit_hermes_import(str(self.source), self.service)
        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["unexpected_sessions"], ["child"])

    def test_watch_rejects_tight_polling(self):
        with self.assertRaisesRegex(ValueError, "at least 5"):
            watch_hermes(str(self.source), str(self.feedback), interval_seconds=1, cycles=1)


if __name__ == "__main__":
    unittest.main()
