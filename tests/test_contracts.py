import json
import tempfile
import unittest
from pathlib import Path

from agent_feedback import FeedbackService
from agent_feedback.contracts import evaluate, load_contracts


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = load_contracts(ROOT / "examples" / "contracts.json")
        cls.cases = json.loads((ROOT / "tests" / "golden_cases.json").read_text(encoding="utf-8"))

    def test_all_golden_cases(self):
        failures = []
        for case in self.cases:
            findings = evaluate(case["goal"], case["selections"], self.contracts)
            actual = [
                f"{f['skill']}:{f['rule']}" +
                (f":{f['rule_id']}" if f["rule"] != "excess_selections" else "")
                for f in findings
            ]
            if actual != case["expected"]:
                failures.append(f"{case['id']}: expected {case['expected']}, got {actual}")
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertEqual(len(self.cases), 34)

    def test_every_contract_has_positive_and_clean_cases(self):
        expected_skills = {finding.split(":", 1)[0] for case in self.cases for finding in case["expected"]}
        clean_selections = {skill for case in self.cases if not case["expected"] for skill in case["selections"]}
        contract_skills = set(self.contracts)
        self.assertEqual(contract_skills - expected_skills, set(), "Contract lacks a positive detection case")
        self.assertEqual(contract_skills - clean_selections, set(), "Contract lacks a clean routing case")
        self.assertEqual(len(contract_skills), 10)

    def test_duplicate_contract_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contracts.json"
            path.write_text(json.dumps([{"skill": "x", "version": 1}, {"skill": "x", "version": 1}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_contracts(path)

    def test_report_priorities_and_markdown_disclaimer(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = FeedbackService(Path(tmp) / "feedback.db", ROOT / "examples" / "contracts.json")
            try:
                missed = service.start("test", "把这个 Word 转成 PDF", external_id="missed")["task_id"]
                self.assertIsNotNone(missed)
                forbidden = service.start("test", "这份 docx 里的截图帮我压一下", external_id="forbidden")["task_id"]
                service.event(forbidden, "selection", {"kind": "skill", "name": "docx-editing", "source": "observed"})
                report = json.loads(service.report(response_format="json"))
                self.assertEqual(report["priority_counts"], {"P0": 0, "P1": 2, "P2": 0})
                self.assertTrue(all(item["priority"] == "P1" for item in report["items"]))
                markdown = service.report()
                self.assertIn("P0＝人工确认失败", markdown)
                self.assertIn("未发现已定义规则的异常不代表成功", markdown)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
