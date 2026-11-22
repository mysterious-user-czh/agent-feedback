import tempfile
import unittest
from pathlib import Path

from agent_feedback.routing_policy import denied_skills, explain, missing_referenced_inputs


class RoutingPolicyTests(unittest.TestCase):
    def test_legacy_doc_excludes_ooxml_editors(self):
        self.assertEqual(denied_skills("旧版 legacy .doc 直接填模板"), ["docx", "docx-editing"])

    def test_docx_is_not_legacy_doc(self):
        self.assertNotIn("docx", denied_skills("读取 fixture.docx 并统计字数"))

    def test_review_excludes_conversion_and_body_edit(self):
        self.assertEqual(denied_skills("添加批注并开启修订"), ["docx-editing", "microsoft-office"])

    def test_image_compression_excludes_body_editor(self):
        self.assertEqual(denied_skills("压缩文档里的所有截图"), ["docx-editing"])

    def test_body_edit_excludes_office_conversion(self):
        self.assertEqual(denied_skills("把正文 ABC 改为 DEF，其他内容不变"), ["docx", "microsoft-office"])

    def test_unrelated_task_has_no_invented_deny(self):
        self.assertEqual(denied_skills("合并两个文本文件"), [])

    def test_decision_does_not_use_case_id(self):
        evidence = explain("添加批注并开启修订")
        self.assertFalse(evidence["case_id_used"])
        self.assertEqual(evidence["basis"], "capability_rules")

    def test_missing_explicit_input_blocks_managed_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            query = "把 fixtures/not-present.docx 转成 artifacts/missing.pdf"
            self.assertEqual(missing_referenced_inputs(query, tmp), ["fixtures/not-present.docx"])
            self.assertEqual(denied_skills(query, base_dir=tmp), ["docx", "docx-editing", "microsoft-office"])

    def test_existing_explicit_input_applies_pdf_boundary_without_missing_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            fixtures.mkdir()
            (fixtures / "present.docx").write_bytes(b"fixture")
            query = "把 fixtures/present.docx 转成 artifacts/output.pdf"
            self.assertEqual(missing_referenced_inputs(query, tmp), [])
            self.assertEqual(denied_skills(query, base_dir=tmp), ["docx-editing"])

    def test_export_pdf_path_excludes_body_editor(self):
        self.assertEqual(denied_skills("导出 artifacts/output.pdf"), ["docx-editing"])


if __name__ == "__main__":
    unittest.main()
