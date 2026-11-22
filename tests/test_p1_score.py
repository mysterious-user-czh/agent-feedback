import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P1 = ROOT / "evaluation" / "p1"
spec = importlib.util.spec_from_file_location("p1_score", P1 / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


class P1ScoreTests(unittest.TestCase):
    def test_frozen_metrics_and_intervals(self):
        result = score.score(P1 / "golden.json", P1 / "predictions.json")
        self.assertEqual(result["annotated_cases"], 40)
        self.assertEqual(result["gold_positive_boundaries"], 10)
        self.assertEqual(result["predicted_unable_to_determine_count"], 0)
        self.assertEqual(result["difference_count"], 8)
        self.assertEqual(result["confidence_intervals"]["boundary_f1"]["lower"], 0.375)

    def test_unable_rate_is_measured_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            rows = json.loads((P1 / "predictions.json").read_text(encoding="utf-8"))
            rows[0]["predicted_relation"] = "unknown"
            rows[0]["predicted_segment"] = None
            path.write_text(json.dumps(rows), encoding="utf-8")
            result = score.score(P1 / "golden.json", path)
            self.assertEqual(result["predicted_unable_to_determine_count"], 1)
            self.assertEqual(result["predicted_unable_to_determine_rate"], 1 / 40)


if __name__ == "__main__":
    unittest.main()
