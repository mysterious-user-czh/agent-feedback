import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicExampleTests(unittest.TestCase):
    def test_basic_usage_runs_and_reports_current_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "basic_usage.py"
            shutil.copy2(ROOT / "examples" / "basic_usage.py", script)
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            result = subprocess.run(
                [sys.executable, str(script)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("筛选后 1 个", result.stdout)
            self.assertIn("routing=unknown", result.stdout)
            self.assertIn("execution=pass", result.stdout)
            self.assertIn("artifact=pass", result.stdout)
            self.assertIn("exit=pass", result.stdout)
            self.assertIn("outcome=pass", result.stdout)
            self.assertIn("结果：success", result.stdout)


if __name__ == "__main__":
    unittest.main()
