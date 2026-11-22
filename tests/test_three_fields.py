import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.adapters.hermes import RULES_VERSION, import_hermes


class ThreeFieldSegmentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "hermes.db"
        self.hermes = sqlite3.connect(self.db)
        self.hermes.executescript("""
            CREATE TABLE sessions(id TEXT, started_at REAL, parent_session_id TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,
                                  tool_calls TEXT,tool_name TEXT,timestamp REAL);
            INSERT INTO sessions VALUES('s',1,NULL);
        """)
        self.service = FeedbackService(self.root / "feedback.db")

    def tearDown(self):
        self.service.close()
        self.hermes.close()
        self.tmp.cleanup()

    def message(self, message_id, role, content):
        self.hermes.execute("INSERT INTO messages VALUES(?,'s',?,?,NULL,NULL,?)", (message_id, role, content, message_id))
        self.hermes.commit()

    def test_correction_stays_in_current_task(self):
        self.message(1, "user", "convert this document")
        self.message(2, "assistant", "working")
        self.message(3, "user", "我说的是另一个文件")
        self.message(4, "assistant", "corrected")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        self.assertEqual(stats["correction_candidates"], 1)
        rows = self.service.store.all("SELECT message_id,event_source,relation FROM segment_messages ORDER BY message_id")
        self.assertEqual([row["relation"] for row in rows], ["new_task", "continuation", "correction", "continuation"])
        task = self.service.store.one("SELECT task_id,goal FROM tasks")
        self.assertEqual(task["goal"], "convert this document")
        label = self.service.store.one("SELECT task_id,source FROM labels")
        self.assertEqual(label["task_id"], task["task_id"])
        self.assertEqual(label["source"], "observed")

    def test_delegation_and_cron_sources_are_not_task_types(self):
        self.message(1, "user", "[IMPORTANT: You are running as a scheduled cron job] run")
        self.message(2, "user", "actual task")
        self.message(3, "user", "[ASYNC DELEGATION BATCH COMPLETE] child")
        self.message(4, "user", "[CURRENT RUN TIME: now] cron")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        rows = self.service.store.all("SELECT event_source,relation FROM segment_messages ORDER BY message_id")
        self.assertEqual([(row["event_source"], row["relation"]) for row in rows], [
            ("cron", "new_task"), ("user", "continuation"),
            ("delegation", "child_event"), ("cron", "continuation")
        ])
        self.assertEqual(self.service.store.one("SELECT segment_type FROM task_segments")["segment_type"], "task")

    def test_late_teaching_example_is_not_a_correction(self):
        self.message(1, "user", "分析技能命中率下降的原因")
        self.message(2, "assistant", "请补充具体建议")
        self.message(3, "user", "我认为应规范描述、增加负例并分层路由。" + "背景" * 150 +
                       "工具名要语义化，别用doSomething这种模糊命名。请据此审查并给方案。")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["correction_candidates"], 0)
        rows = self.service.store.all("SELECT relation FROM segment_messages ORDER BY message_id")
        self.assertEqual([row["relation"] for row in rows], ["new_task", "continuation", "new_task"])

    def test_explicit_assessment_later_in_review_remains_a_correction(self):
        self.message(1, "user", "审查这份提案")
        self.message(2, "assistant", "已给出结论")
        self.message(3, "user", "先肯定方向。" + "分析" * 150 + "但这里有两条事实错误，需要修正。")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["correction_candidates"], 1)

    def test_first_user_message_with_correction_word_starts_task(self):
        self.message(1, "user", "别用doSomething；这是我遇到的命中率问题")
        stats = import_hermes(str(self.db), self.service)
        self.assertEqual(stats["imported"], 1)
        self.assertEqual(stats["correction_candidates"], 0)
        row = self.service.store.one(
            "SELECT relation,event_source,segment_type FROM segment_messages "
            "JOIN task_segments USING(task_id)"
        )
        self.assertEqual((row["relation"], row["event_source"], row["segment_type"]),
                         ("new_task", "user", "task"))

    def test_v1_segmented_database_is_rejected(self):
        self.service.start("hermes", "old correction segment", "s", external_id="hermes:s:segment:3")
        self.service.store.execute(
            "INSERT INTO schema_metadata VALUES('hermes_segment_rules','hermes-message-segments-v2-three-fields')"
        )
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            import_hermes(str(self.db), self.service)

    def test_rules_version_is_explicit(self):
        self.message(1, "user", "actual task")
        import_hermes(str(self.db), self.service)
        rules = self.service.store.one("SELECT value FROM schema_metadata WHERE key='hermes_segment_rules'")
        self.assertEqual(rules["value"], RULES_VERSION)


if __name__ == "__main__":
    unittest.main()
