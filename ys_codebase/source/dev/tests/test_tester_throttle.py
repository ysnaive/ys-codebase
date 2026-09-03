import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

from dev.testing.runner import ASCIIReportFormatter
from dev.tester import Tester
from dev.testing.case import YSCBTestCase


class TestTesterThrottleOutput(YSCBTestCase):
    """測試 dev test 輸出格式優化與節流模式 (--quiet / -q)。"""

    def test_format_throttled_all_passed(self):
        """FT-01: 全數通過時僅輸出單行 Pass: {passed}({pct:.1f}%), Fail: 0, Skip: {skipped}。"""
        report_data = {
            "total": 50,
            "passed": 50,
            "failed": 0,
            "skipped": 0,
            "failures_list": [],
            "modules": []
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(output, "Pass: 50(100.0%), Fail: 0, Skip: 0")

    def test_format_throttled_with_failures(self):
        """FT-02: 存在失敗時輸出單行統計及 FAILED / ERROR TEST CASES LIST 詳情。"""
        report_data = {
            "total": 50,
            "passed": 48,
            "failed": 2,
            "skipped": 0,
            "failures_list": [
                {
                    "module": "core",
                    "type": "FAIL",
                    "test": "test_example_failure",
                    "message": "AssertionError: 1 != 2",
                    "location": "source/core/tests/test_foo.py:42",
                    "rerun": "python yscb.py dev test --target=core:test_example_failure",
                    "captured_output": "Captured stdout line"
                }
            ],
            "modules": []
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        lines = output.splitlines()
        self.assertEqual(lines[0], "Pass: 48(96.0%), Fail: 2, Skip: 0")
        self.assertIn("FAILED / ERROR TEST CASES LIST:", output)
        self.assertIn("[core]", output)
        self.assertIn("test_example_failure", output)
        self.assertIn("AssertionError: 1 != 2", output)
        self.assertIn("source/core/tests/test_foo.py:42", output)
        self.assertIn("Quick Re-run: python yscb.py dev test --target=core:test_example_failure", output)

    def test_format_throttled_with_worker_errors(self):
        """FT-02 邊界: worker 級別崩潰無 failures_list 時正確輸出錯誤。"""
        report_data = {
            "total": 1,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "failures_list": [],
            "modules": [
                {
                    "name": "dev",
                    "errors": ["Execution failed with code 1"]
                }
            ]
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertTrue(output.startswith("Pass: 0(0.0%), Fail: 1, Skip: 0"))
        self.assertIn("[!] [dev] ERROR: Execution failed with code 1", output)

    def test_format_throttled_zero_tests_ec_01(self):
        """ET-01: 0 測試或空模組時避免除以零異常。"""
        report_data = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "failures_list": [],
            "modules": []
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(output, "Pass: 0(0.0%), Fail: 0, Skip: 0")

    def test_format_throttled_all_skipped_ec_02(self):
        """ET-02: 所有測試均被 Skip 時輸出 Pass: 0(0.0%), Fail: 0, Skip: 10。"""
        report_data = {
            "total": 10,
            "passed": 0,
            "failed": 0,
            "skipped": 10,
            "failures_list": [],
            "modules": []
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(output, "Pass: 0(0.0%), Fail: 0, Skip: 10")

    def test_tester_quiet_flag_and_silence_op_test(self):
        """FT-03: _run_op_test 支援 --quiet 與 -q，抑制進度文字並調用 format_throttled。"""
        tester = Tester()
        fake_report = {
            "total": 10,
            "passed": 10,
            "failed": 0,
            "skipped": 0,
            "modules": [],
            "failures_list": []
        }
        with patch.object(tester, "_run_op_test") as mock_op_test:
            mock_op_test.return_value = 0
            ret = tester.run(["op-test", "--quiet"])
            self.assertEqual(ret, 0)
            mock_op_test.assert_called_once_with(["--quiet"])

    def test_ai_guidelines_alignment_fr_06(self):
        """FT-05: 驗證 yscb-module-dev、Auto.md、phase_06_test.md 等手冊中 AI 測試指令包含 --quiet。"""
        import os
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        
        # 1. yscb-module-dev SKILL.md
        skill_path = os.path.join(repo_root, "source", "dev", "assets", "skills", "yscb-module-dev", "SKILL.md")
        self.assertTrue(os.path.isfile(skill_path), f"File not found: {skill_path}")
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
        self.assertIn("dev test <mod> --quiet", skill_content)
        self.assertIn("dev test <module> --quiet", skill_content)

        # 2. Auto.md
        auto_path = os.path.join(repo_root, "source", "agents-workflow", "assets", "workflows", "Auto.md")
        self.assertTrue(os.path.isfile(auto_path), f"File not found: {auto_path}")
        with open(auto_path, "r", encoding="utf-8") as f:
            auto_content = f.read()
        self.assertIn("自動化測試", auto_content)

        # 3. phase_06_test.md
        p06_guide_path = os.path.join(repo_root, "source", "agents-workflow", "assets", "skills", "development-sop", "references", "phase_06_test.md")
        self.assertTrue(os.path.isfile(p06_guide_path), f"File not found: {p06_guide_path}")
        with open(p06_guide_path, "r", encoding="utf-8") as f:
            p06_content = f.read()
        self.assertIn("dev test <module> --quiet", p06_content)
        self.assertIn("dev test --all --quiet", p06_content)


if __name__ == "__main__":
    unittest.main()
