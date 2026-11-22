import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "integrations/skillup/hermes_engine.py"
SPEC = importlib.util.spec_from_file_location("hermes_engine", MODULE)
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class SkillupEngineTests(unittest.TestCase):
    def test_confined_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertEqual(engine.confined(root, "outputs/result.json"), root / "outputs/result.json")
            with self.assertRaisesRegex(ValueError, "escapes"):
                engine.confined(root, "../outside")

    def test_parse_stream_preserves_tool_transcript_and_exit_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stream.jsonl"
            rows = [
                {"type": "tool_use", "name": "skill_view", "input": {"name": "docx"}},
                {"type": "tool_result", "name": "terminal", "tool_call_id": "t1", "output": "{}"},
                {"type": "result", "session_id": "local-" + "a" * 64, "content": "done", "exit_code": 0},
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            session, final, transcript = engine.parse_stream(path)
            self.assertEqual(session, "local-" + "a" * 64)
            self.assertEqual(final, "done")
            self.assertEqual([m["role"] for m in transcript], ["assistant", "tool"])
            self.assertIn("skill_view", transcript[0]["content"])


if __name__ == "__main__":
    unittest.main()
