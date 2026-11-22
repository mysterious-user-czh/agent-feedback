import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.adapters.hermes import import_hermes


class MessageSegmentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "hermes.db"
        self.hermes = sqlite3.connect(self.db)
        self.hermes.executescript("""
            CREATE TABLE sessions(id TEXT, started_at REAL, parent_session_id TEXT);
            CREATE TABLE messages(
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                tool_calls TEXT, tool_name TEXT, timestamp REAL
            );
        """)
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        self.hermes.close()
        self.tmp.cleanup()

    def message(self, message_id, session_id, role, content=None, calls=None, tool_name=None):
        self.hermes.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
            (message_id, session_id, role, content, calls, tool_name, message_id),
        )
        self.hermes.commit()

    def test_every_message_has_exactly_one_stable_segment(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        calls = json.dumps([{"function": {"name": "skill_view", "arguments": json.dumps({"name": "one"})}}])
        self.message(1, "s", "user", "first task")
        self.message(2, "s", "assistant", calls=calls)
        self.message(3, "s", "tool", '{"success":false}', tool_name="demo")
        self.message(4, "s", "user", "second task")
        self.message(5, "s", "tool", '{"exit_code":130}', tool_name="demo")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 2)
        self.assertEqual(stats["segment_messages"], 5)
        rows = self.service.store.all("SELECT external_id,message_id FROM segment_messages JOIN tasks USING(task_id) ORDER BY message_id")
        self.assertEqual([(row["external_id"], row["message_id"]) for row in rows], [
            ("hermes:s:segment:1", 1), ("hermes:s:segment:1", 2), ("hermes:s:segment:1", 3),
            ("hermes:s:segment:4", 4), ("hermes:s:segment:4", 5),
        ])
        items = {item["external_id"]: item for item in json.loads(self.service.report(response_format="json"))["items"]}
        self.assertEqual(items["hermes:s:segment:1"]["selections"], ["one"])
        self.assertEqual(len(items["hermes:s:segment:1"]["tool_errors"]), 1)
        self.assertEqual(len(items["hermes:s:segment:4"]["cancellations"]), 1)

    def test_automated_envelope_does_not_create_boundary(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "user", "actual task")
        self.message(2, "s", "user", "[ASYNC DELEGATION BATCH COMPLETE] result")
        self.message(3, "s", "assistant", "answer")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        self.assertEqual(stats["segment_messages"], 3)
        automated = self.service.store.one("SELECT is_automated FROM segment_messages WHERE message_id=2")
        self.assertEqual(automated["is_automated"], 1)

    def test_automated_prefix_merges_into_first_human_task(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "user", "[IMPORTANT: system envelope]")
        self.message(2, "s", "assistant", "preface")
        self.message(3, "s", "user", "real request")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        rows = self.service.store.all(
            "SELECT message_id,goal,relation,segment_type FROM segment_messages "
            "JOIN tasks USING(task_id) JOIN task_segments USING(task_id) ORDER BY message_id"
        )
        self.assertEqual([row["goal"] for row in rows], ["real request"] * 3)
        self.assertEqual([row["relation"] for row in rows], ["new_task", "continuation", "continuation"])
        self.assertEqual({row["segment_type"] for row in rows}, {"task"})

    def test_incremental_import_does_not_move_old_messages(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "user", "first")
        self.message(2, "s", "assistant", "one")
        import_hermes(str(self.db), self.service)
        self.message(3, "s", "user", "second")
        self.message(4, "s", "assistant", "two")
        second = import_hermes(str(self.db), self.service)
        third = import_hermes(str(self.db), self.service)
        self.assertEqual(second["imported"], 1)
        self.assertEqual(second["segment_messages"], 2)
        self.assertEqual(third["segment_messages"], 0)
        count = self.service.store.one("SELECT COUNT(*) AS n FROM segment_messages")["n"]
        self.assertEqual(count, 4)

    def test_incremental_automatic_prefix_keeps_task_identity(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "user", "[IMPORTANT: You are running as a scheduled cron job] run")
        first = import_hermes(str(self.db), self.service)
        self.assertEqual(first["imported"], 1)
        self.message(2, "s", "user", "real request after automatic start")
        self.message(3, "s", "assistant", "done")
        second = import_hermes(str(self.db), self.service)
        third = import_hermes(str(self.db), self.service)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["already_present"], 1)
        self.assertEqual(second["segment_messages"], 2)
        self.assertEqual(third["segment_messages"], 0)
        tasks = self.service.store.all("SELECT external_id,goal FROM tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["external_id"], "hermes:s:segment:1")
        self.assertEqual(tasks[0]["goal"], "real request after automatic start")
        rows = self.service.store.all("SELECT message_id,relation FROM segment_messages ORDER BY message_id")
        self.assertEqual([row["relation"] for row in rows], ["new_task", "continuation", "continuation"])

    def test_unsupported_role_has_explicit_ambiguous_reason(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "mystery", "cannot attribute this role")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        segment = self.service.store.one("SELECT segment_type,ambiguous_reason FROM task_segments")
        self.assertEqual(segment["segment_type"], "ambiguous")
        self.assertEqual(segment["ambiguous_reason"], "unsupported_message_role:mystery")

    def test_legacy_session_level_database_is_rejected(self):
        self.hermes.execute("INSERT INTO sessions VALUES('s',1,NULL)")
        self.message(1, "s", "user", "first")
        self.service.start("hermes", "legacy whole session", "s", external_id="s")
        with self.assertRaisesRegex(ValueError, "fresh database"):
            import_hermes(str(self.db), self.service)


if __name__ == "__main__":
    unittest.main()
