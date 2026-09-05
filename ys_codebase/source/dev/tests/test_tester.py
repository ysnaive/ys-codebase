"""
Official test suite for dev.tester.Tester and dev.testing framework.
"""
import os
import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock, mock_open
from dev.testing import YSCBTestCase, require, Requirement
from dev.testing.contract import make_contract_suite
from dev.testing.runner import TestDiscovery, TestRunner
from dev.tester import Tester, safe_print
from core import uri

class TestDevTester(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_auto_contract_generation(self):
        """Verify dynamic auto contract synthesis for core and dev."""
        core_suite = make_contract_suite("core")
        self.assertEqual(core_suite.countTestCases(), 3)
        dev_suite = make_contract_suite("dev")
        self.assertEqual(dev_suite.countTestCases(), 3)
        self.mark_passed()

    def test_discovery_and_suite_building(self):
        """Verify TestDiscovery builds 2-phase suite."""
        suite, contract_cnt, custom_cnt = TestDiscovery.build_suite_for_module("core")
        self.assertEqual(contract_cnt, 3)
        self.assertGreaterEqual(custom_cnt, 1)
        self.mark_passed()

    def test_tester_contract_only_cli(self):
        """Verify Tester CLI runs in --contract-only mode."""
        res = self.tester.run(["op-test", "core", "--contract-only"])
        self.assertEqual(res, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_safe_print_handles_unicode_and_mock_encoding(self):
        """Verify safe_print gracefully handles Unicode characters and encoding issues."""
        class MockEncodingStream:
            def __init__(self):
                self.encoding = "cp950"
                self.buffer = []
            def write(self, s: str):
                # Simulate cp950 failing on \ufffd
                if "\ufffd" in s:
                    raise UnicodeEncodeError("cp950", s, 0, 1, "illegal multibyte sequence")
                self.buffer.append(s)
            def flush(self):
                pass

        mock_stream = MockEncodingStream()
        # Test safe_print with problematic char
        safe_print("test \ufffd unicode", file=mock_stream)
        self.assertTrue(len(mock_stream.buffer) > 0)
        self.assertIn("test ? unicode\n", mock_stream.buffer[0])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_run_test_all_success_cleans_sandboxes(self):
        """FT-03: Verify _run_test with --all cleans all sandboxes when tests pass (Mocked Worker)."""
        from dev.testing.sandbox import SandboxProvisioner
        sandbox_parent = uri.resolve("cache://dev/sandbox/")
        os.makedirs(sandbox_parent, exist_ok=True)
        dummy_sb = os.path.join(sandbox_parent, "sandbox_20260101_200001_000000")
        os.makedirs(dummy_sb, exist_ok=True)
        
        orig_nested = os.environ.get("YSCB_NESTED_TEST")
        os.environ["YSCB_NESTED_TEST"] = "1"
        
        def mock_worker(mod_name, worker_idx, clean_argv, keep_sandbox=False, is_nested=False, **kwargs):
            return {
                "module": mod_name,
                "worker_idx": worker_idx,
                "returncode": 0,
                "report_data": {
                    "modules": [{
                        "name": mod_name,
                        "passed": True,
                        "duration": 0.001,
                        "contract_total": 1,
                        "contract_passed": 1,
                        "custom_total": 0,
                        "custom_passed": 0,
                        "logic_passed": 0,
                        "env_passed": 0,
                        "workflow_passed": 0,
                        "perf_passed": 0,
                        "errors": []
                    }],
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "duration": 0.001
                },
                "sandbox_dir": ""
            }

        try:
            with patch.object(self.tester, "_run_single_module_worker", side_effect=mock_worker):
                ret = self.tester._run_test(["--all", "--contract-only", "--no-build"])
                self.assertEqual(ret, 0)
                self.assertFalse(os.path.exists(dummy_sb))
        finally:
            if orig_nested is not None:
                os.environ["YSCB_NESTED_TEST"] = orig_nested
            else:
                os.environ.pop("YSCB_NESTED_TEST", None)
            if os.path.exists(dummy_sb):
                SandboxProvisioner.cleanup_sandbox(dummy_sb, force=True)
        self.mark_passed()


@require(Requirement.LOGIC)
class TestDevTesterSync(YSCBTestCase):
    """Consolidated tests for dev.tester --sync and post-test direct install guidance."""

    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_handle_post_test_sync_with_sync_flag(self):
        """FT-05: 驗證當 sync_requested=True 時，自動呼叫 subprocess.run 執行 install <mod>@build。"""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data='{"installed_modules": {"dev": {"version": "1.0.0.0"}}}')), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_sub:
            
            output_io = StringIO()
            with patch("sys.stdout", output_io):
                self.tester._handle_post_test_sync(["dev"], sync_requested=True)

            mock_sub.assert_called_once()
            args = mock_sub.call_args[0][0]
            self.assertIn("install", args)
            self.assertIn("dev@build", args)
            self.assertIn("--force", args)
        self.mark_passed()

    def test_handle_post_test_sync_prompt_only(self):
        """FT-05: 驗證當 sync_requested=False 時，不呼叫 install，而是輸出友善提示。"""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data='{"installed_modules": {"dev": {"version": "1.0.0.0"}}}')), \
             patch("subprocess.run") as mock_sub:
            
            output_io = StringIO()
            with patch("sys.stdout", output_io):
                self.tester._handle_post_test_sync(["dev"], sync_requested=False)

            mock_sub.assert_not_called()
            output = output_io.getvalue()
            self.assertIn("install dev@build", output)
        self.mark_passed()


@require(Requirement.LOGIC)
class TestDevTesterThrottle(YSCBTestCase):
    """Consolidated tests for dev test output formatting and throttled mode (--quiet / -q)."""

    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_format_throttled_all_passed(self):
        """FT-01: 全數通過時僅輸出單行 Pass: {passed}({pct:.1f}%), Fail: 0, Skip: {skipped}。"""
        from dev.testing.runner import ASCIIReportFormatter
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
        self.mark_passed()

    def test_format_throttled_with_failures(self):
        """FT-02: 存在失敗時輸出單行統計及 FAILED / ERROR TEST CASES LIST 詳情。"""
        from dev.testing.runner import ASCIIReportFormatter
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
        self.mark_passed()

    def test_format_throttled_with_worker_errors(self):
        """FT-02 邊界: worker 級別崩潰無 failures_list 時正確輸出錯誤。"""
        from dev.testing.runner import ASCIIReportFormatter
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
        self.mark_passed()

    def test_format_throttled_edge_cases(self):
        """ET-01 & ET-02: 0 測試避免除以零異常，全跳過時輸出 Pass: 0(0.0%), Fail: 0, Skip: 10。"""
        from dev.testing.runner import ASCIIReportFormatter
        report_zero = {
            "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "failures_list": [], "modules": []
        }
        self.assertEqual(ASCIIReportFormatter.format_throttled(report_zero), "Pass: 0(0.0%), Fail: 0, Skip: 0")

        report_skipped = {
            "total": 10, "passed": 0, "failed": 0, "skipped": 10,
            "failures_list": [], "modules": []
        }
        self.assertEqual(ASCIIReportFormatter.format_throttled(report_skipped), "Pass: 0(0.0%), Fail: 0, Skip: 10")
        self.mark_passed()

    def test_format_throttled_with_unknown(self):
        """Verify format_throttled and format_summary report Unknown count when unknown > 0."""
        from dev.testing.runner import ASCIIReportFormatter
        report_data = {
            "total": 50,
            "passed": 40,
            "failed": 0,
            "unknown": 10,
            "skipped": 0,
            "duration": 1.234,
            "failures_list": [],
            "modules": []
        }
        throttled = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(throttled, "Pass: 40(80.0%), Fail: 0, Unknown: 10, Skip: 0")

        summary = ASCIIReportFormatter.format_summary(report_data)
        self.assertIn("Summary : 50 Total, 40 Passed, 0 Failed, 10 Unknown, 0 Skipped (1.234s)", summary)
        self.mark_passed()

    def test_tester_quiet_flag_and_silence_op_test(self):
        """FT-03: _run_op_test 支援 --quiet 與 -q，抑制進度文字並調用 format_throttled。"""
        with patch.object(self.tester, "_run_op_test", return_value=0) as mock_op_test:
            ret = self.tester.run(["op-test", "--quiet"])
            self.assertEqual(ret, 0)
            mock_op_test.assert_called_once_with(["--quiet"])
        self.mark_passed()

    def test_ai_guidelines_alignment(self):
        """FT-05: 驗證生態系各指引手冊中測試指令對齊 --quiet。"""
        repo_root = uri.resolve("project://") if uri.exists("project://") else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        
        skill_path = os.path.join(repo_root, "source", "dev", "assets", "skills", "yscb-module-dev", "SKILL.md")
        if not os.path.isfile(skill_path):
            skill_path = os.path.join(repo_root, "ys_codebase", "source", "dev", "assets", "skills", "yscb-module-dev", "SKILL.md")
        if os.path.isfile(skill_path):
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("--quiet", content)
        self.mark_passed()
