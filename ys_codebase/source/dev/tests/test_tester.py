"""
Official test suite for dev.tester.Tester and dev.testing framework.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

from dev.testing import YSCBTestCase, require, Requirement
from dev.testing.contract import make_contract_suite
from dev.testing.runner import (
    TestDiscovery,
    TestRunner,
    filter_suite,
    OutputCapturer,
    ASCIIReportFormatter,
    get_test_category,
)
from dev.tester import Tester, safe_print
from dev.testing.sandbox import SandboxProvisioner
from core import uri, vfs


class TestDevTester(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tester = Tester()
        self.temp_dirs = []

    def tearDown(self):
        super().tearDown()
        for d in self.temp_dirs:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)

    def _mkdtemp(self) -> str:
        d = tempfile.mkdtemp()
        self.temp_dirs.append(d)
        return d

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
                if "\ufffd" in s:
                    raise UnicodeEncodeError("cp950", s, 0, 1, "illegal multibyte sequence")
                self.buffer.append(s)
            def flush(self):
                pass

        mock_stream = MockEncodingStream()
        safe_print("test \ufffd unicode", file=mock_stream)
        self.assertTrue(len(mock_stream.buffer) > 0)
        self.assertIn("test ? unicode\n", mock_stream.buffer[0])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_run_test_all_success_cleans_sandboxes(self):
        """FT-03: Verify _run_test with --all cleans all sandboxes when tests pass (Mocked Worker)."""
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
                        "unknown": 0,
                        "errors": []
                    }],
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "unknown": 0,
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
    def test_op_test_single_token_normalization(self):
        """FR-01, EC-01: Verify _run_test normalizes -k <pat> into --pattern=<pat> and flags."""
        captured_cmd = []

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = list(cmd)
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump({
                            "filter_mode": "Default",
                            "target_scope": "core",
                            "no_build": True,
                            "modules": [],
                            "total": 1,
                            "passed": 1,
                            "failed": 0,
                            "unknown": 0,
                            "skipped": 0,
                            "duration": 0.1,
                            "failures_list": []
                        }, f)
            return MagicMock(returncode=0)

        sb_dir = self._mkdtemp()
        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = sb_dir
        mock_ctx.host_dir = sb_dir
        mock_ctx.engine_dir = sb_dir

        with patch("subprocess.run", side_effect=mock_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"):
            
            # Call _run_test with separated -k token and flags
            ret = self.tester._run_test(["core", "-k", "test_my_feature", "-q", "-v", "--no-build"])
            self.assertEqual(ret, 0)
            
            # Verify child process op-test args
            self.assertIn("--pattern=test_my_feature", captured_cmd)
            self.assertNotIn("-k", captured_cmd)
            self.assertIn("--quiet", captured_cmd)
            self.assertIn("--verbose", captured_cmd)
            self.assertIn("core", captured_cmd)
            # Verify target module is not overwritten by the pattern
            pos_args = [a for a in captured_cmd[captured_cmd.index("op-test")+1:] if not a.startswith("-")]
            self.assertEqual(pos_args, ["core"])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_filter_suite_retains_failed_test_and_discovers_network(self):
        """FR-03, EC-05: filter_suite retains _FailedTest across all types and includes NETWORK by default."""
        class MockFailedTest(unittest.TestCase):
            pass
        # Name the class _FailedTest to simulate unittest import/syntax failure
        MockFailedTest.__name__ = "_FailedTest"

        class MockNormalTest(YSCBTestCase):
            @require(Requirement.NETWORK)
            def test_net(self):
                pass

        failed_instance = MockFailedTest()
        normal_instance = MockNormalTest("test_net")

        suite = unittest.TestSuite()
        suite.addTest(failed_instance)
        suite.addTest(normal_instance)

        # 1. Default filter should retain both _FailedTest and NETWORK test
        filtered_def = filter_suite(suite)
        test_names = [t.__class__.__name__ for t in filtered_def]
        self.assertIn("_FailedTest", test_names)
        self.assertIn("MockNormalTest", test_names)

        # 2. Type-restricted filter (--type=env) MUST STILL retain _FailedTest
        filtered_env = filter_suite(suite, test_type="env")
        test_names_env = [t.__class__.__name__ for t in filtered_env]
        self.assertIn("_FailedTest", test_names_env)
        self.assertNotIn("MockNormalTest", test_names_env)

        # 3. Offline network execution triggers SkipTest and increments skipped count
        with patch("dev.testing.requirement.is_network_available", return_value=False):
            res_net = unittest.TestResult()
            normal_instance.run(res_net)
            self.assertEqual(len(res_net.skipped), 1)
            self.assertIn("requires active Network connection", res_net.skipped[0][1])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unknown_fails_tester_and_deducts_custom_passed(self):
        """FR-03, EC-05, [P00:DR-03]: UNKNOWN > 0 sets all_passed=False, deducts custom_passed, exits 1."""
        # Follow [P00:DR-03]: write mock module to disk, never define un-marked test class in AST
        mod_name = "mock_unknown_test_mod"
        src_path = self.create_mock_source_module(
            mod_name,
            files={
                "tests/test_unmarked.py": (
                    "from dev.testing.case import YSCBTestCase\n"
                    "class TestUnmarked(YSCBTestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.mark_passed()\n"
                    "    def test_missing_mark(self):\n"
                    "        pass\n"  # missing self.mark_passed() -> UNKNOWN
                )
            }
        )
        rep_json_path = os.path.join(self._mkdtemp(), "unknown_report.json")

        try:
            # Run op-test directly inside sandbox context
            out_io = StringIO()
            with patch("sys.stdout", out_io):
                ret = self.tester.run(["op-test", mod_name, f"--report-json={rep_json_path}"])
            self.assertEqual(ret, 1, "Expected UNKNOWN > 0 to result in exit code 1")
            self.assertIn("Status  : FAILED", out_io.getvalue())
            self.assertTrue(os.path.isfile(rep_json_path))
            with open(rep_json_path, "r", encoding="utf-8") as f:
                rep_data = json.load(f)
            self.assertEqual(rep_data["unknown"], 1)
            mod_entry = rep_data["modules"][0]
            self.assertFalse(mod_entry["passed"])
            # 1 default test_basic + 2 in test_unmarked = 3 custom tests, 2 passed, 1 unknown
            self.assertEqual(mod_entry["custom_total"], 3)
            self.assertEqual(mod_entry["custom_passed"], 2)
        finally:
            if os.path.exists(src_path):
                shutil.rmtree(src_path, ignore_errors=True)
            for scheme in ("module.build://", "module.release://"):
                u = f"{scheme}{mod_name}"
                if vfs.exists(u):
                    shutil.rmtree(uri.resolve(u), ignore_errors=True)

        # Also verify SyntaxError in test file produces _FailedTest and fails even under --type=env
        syn_mod = "mock_syntax_err_mod"
        syn_path = self.create_mock_source_module(
            syn_mod,
            files={
                "tests/test_broken_syntax.py": "def broken_syntax(:\n    pass\n"
            }
        )
        try:
            out_syn = StringIO()
            with patch("sys.stdout", out_syn):
                ret_syn = self.tester.run(["op-test", syn_mod, "--type=env"])
            self.assertEqual(ret_syn, 1, "Expected SyntaxError _FailedTest to fail even under --type=env")
        finally:
            if os.path.exists(syn_path):
                shutil.rmtree(syn_path, ignore_errors=True)
            for scheme in ("module.build://", "module.release://"):
                u = f"{scheme}{syn_mod}"
                if vfs.exists(u):
                    shutil.rmtree(uri.resolve(u), ignore_errors=True)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_quiet_mode_zero_stderr_leak(self):
        """FT-01 (Purification): Verify _run_test in --quiet suppresses subprocess stderr completely."""
        dummy_report = {
            "filter_mode": "Default (LOGIC + ENV)",
            "target_scope": "dev",
            "no_build": True,
            "modules": [],
            "total": 10,
            "passed": 10,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
            "duration": 1.23,
            "failures_list": []
        }

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Subprocess stdout noise\n"
        mock_res.stderr = (
            "[compiler:warning] Failed to resolve project URI\n"
            "Warning: something non-critical happened\n"
        )

        def fake_subprocess_run(cmd, **kwargs):
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(dummy_report, f)
            return mock_res

        sb_dir = self._mkdtemp()
        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = sb_dir
        mock_ctx.host_dir = sb_dir
        mock_ctx.engine_dir = sb_dir

        out_io = StringIO()
        err_io = StringIO()

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"), \
             patch("sys.stdout", out_io), \
             patch("sys.stderr", err_io):
            ret = self.tester._run_test(["dev", "--quiet", "--no-build"])

        self.assertEqual(ret, 0)
        self.assertEqual(err_io.getvalue(), "", "Expected zero stderr output in quiet mode!")
        self.assertEqual(out_io.getvalue().strip(), "Pass: 10(100.0%), Fail: 0, Skip: 0")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_single_module_json_ipc_pipeline(self):
        """FT-02 (Purification): Verify single module test dispatches with --report-json and --quiet-report."""
        captured_cmd = []
        mock_res = MagicMock(returncode=0, stdout="", stderr="")

        def fake_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = list(cmd)
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump({
                            "filter_mode": "Default",
                            "target_scope": "dev",
                            "no_build": True,
                            "modules": [],
                            "total": 5,
                            "passed": 5,
                            "failed": 0,
                            "unknown": 0,
                            "skipped": 0,
                            "duration": 0.5,
                            "failures_list": []
                        }, f)
            return mock_res

        sb_dir = self._mkdtemp()
        mock_ctx = MagicMock(sandbox_dir=sb_dir, host_dir=sb_dir, engine_dir=sb_dir)

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"):
            ret = self.tester._run_test(["dev", "--no-build"])
            self.assertEqual(ret, 0)
            self.assertIn("--quiet-report", captured_cmd)
            self.assertTrue(any(a.startswith("--report-json=") for a in captured_cmd))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_output_capturer_buffers_and_restores(self):
        """FT-01: Verify OutputCapturer captures stdout and stderr and safely restores original streams."""
        capturer = OutputCapturer(enabled=True)
        orig_out = sys.stdout
        with capturer:
            print("hello stdout world")
            print("hello stderr world", file=sys.stderr)
        self.assertEqual(sys.stdout, orig_out)
        out = capturer.get_output()
        self.assertIn("hello stdout world", out)
        self.assertIn("hello stderr world", out)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ascii_report_formatter_with_metadata_and_taxonomy(self):
        """FT-02: Verify ASCIIReportFormatter outputs metadata, timing, taxonomy, and re-run guides."""
        sample_data = {
            "filter_mode": "Default (LOGIC + ENV)",
            "target_scope": "core",
            "no_build": True,
            "modules": [
                {
                    "name": "core",
                    "passed": False,
                    "duration": 0.45,
                    "contract_total": 3,
                    "contract_passed": 3,
                    "custom_total": 10,
                    "custom_passed": 9,
                    "logic_passed": 6,
                    "env_passed": 3,
                    "workflow_passed": 0,
                    "perf_passed": 0,
                    "unknown": 0,
                    "errors": ["test_fail: AssertionError"]
                }
            ],
            "failures_list": [
                {
                    "module": "core",
                    "test": "TestCore.test_fail",
                    "type": "FAIL",
                    "message": "AssertionError: 1 != 2",
                    "location": "tests/test_core.py:10",
                    "rerun": "python yscb.py dev test --target=core:TestCore.test_fail",
                    "captured_output": "debug print line"
                }
            ],
            "total": 13,
            "passed": 12,
            "failed": 1,
            "unknown": 0,
            "skipped": 0,
            "duration": 0.45
        }
        report = ASCIIReportFormatter.format_summary(sample_data)
        self.assertIn("Mode: Default (LOGIC + ENV)", report)
        self.assertIn("Target: core", report)
        self.assertIn("Build: No-build (Fast)", report)
        self.assertIn("core (0.45s)", report)
        self.assertIn("[Logic: 6, Env: 3]", report)
        self.assertIn("FAILED / ERROR TEST CASES LIST:", report)
        self.assertIn("Quick Re-run: python yscb.py dev test --target=core:TestCore.test_fail", report)
        self.assertIn("debug print line", report)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_get_test_category_extraction(self):
        """Verify get_test_category correctly identifies taxonomy flags."""
        class MockCatTest(YSCBTestCase):
            @require(Requirement.LOGIC)
            def test_l(self): pass
            @require(Requirement.ENV)
            def test_e(self): pass
            @require(Requirement.WORKFLOW)
            def test_w(self): pass
            @require(Requirement.PERF)
            def test_p(self): pass
            def test_default(self): pass

        self.assertEqual(get_test_category(MockCatTest("test_l")), "logic")
        self.assertEqual(get_test_category(MockCatTest("test_e")), "env")
        self.assertEqual(get_test_category(MockCatTest("test_w")), "workflow")
        self.assertEqual(get_test_category(MockCatTest("test_p")), "perf")
        self.assertEqual(get_test_category(MockCatTest("test_default")), "logic")
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
        report_data = {
            "total": 50,
            "passed": 50,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
            "failures_list": [],
            "modules": []
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(output, "Pass: 50(100.0%), Fail: 0, Skip: 0")
        self.mark_passed()

    def test_format_throttled_with_failures(self):
        """FT-02: 存在失敗時輸出單行統計及 FAILED / ERROR TEST CASES LIST 詳情。"""
        report_data = {
            "total": 50,
            "passed": 48,
            "failed": 2,
            "unknown": 0,
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
        report_data = {
            "total": 1,
            "passed": 0,
            "failed": 1,
            "unknown": 0,
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
        report_zero = {
            "total": 0, "passed": 0, "failed": 0, "unknown": 0, "skipped": 0,
            "failures_list": [], "modules": []
        }
        self.assertEqual(ASCIIReportFormatter.format_throttled(report_zero), "Pass: 0(0.0%), Fail: 0, Skip: 0")

        report_skipped = {
            "total": 10, "passed": 0, "failed": 0, "unknown": 0, "skipped": 10,
            "failures_list": [], "modules": []
        }
        self.assertEqual(ASCIIReportFormatter.format_throttled(report_skipped), "Pass: 0(0.0%), Fail: 0, Skip: 10")
        self.mark_passed()

    def test_format_throttled_with_unknown(self):
        """Verify format_throttled and format_summary report Unknown count when unknown > 0."""
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
        self.assertIn("Status  : FAILED", summary)
        self.mark_passed()

    def test_tester_quiet_flag_and_silence_op_test(self):
        """DT-01: Execute real _run_op_test(['core', '--contract-only', '-q']) and verify throttled output."""
        out_io = StringIO()
        with patch("sys.stdout", out_io):
            ret = self.tester._run_op_test(["core", "--contract-only", "-q"])
        self.assertEqual(ret, 0)
        output = out_io.getvalue().strip()
        self.assertIn("Pass: 3(100.0%), Fail: 0, Skip: 0", output)
        self.assertNotIn("begin test in", output)
        self.mark_passed()

    def test_dev_pep562_lazy_loading_and_cli_test_dispatch(self):
        """D-01, D-08, DT-05: Verify dev PEP 562 lazy loading, contributes/core.json contract, and cli.test."""
        import dev
        import importlib.util
        from core.commands import CmdBags, CmdOption

        self.assertIn("Releaser", dev.__all__)
        self.assertIsNotNone(getattr(dev, "Releaser"))
        with self.assertRaises(AttributeError):
            _ = getattr(dev, "NonExistentSymbolXYZ")

        # Verify contributes/core.json declares events and options
        contrib_data = vfs.read_json("module.source://dev/contributes/core.json")
        event_keys = {k for item in contrib_data.get("events", []) if isinstance(item, dict) for k in item}
        self.assertIn("on_test_setup", event_keys)
        self.assertIn("on_test_teardown", event_keys)
        test_opts = contrib_data["commands"]["cmd"]["test"]["options"]
        flat_test_opts = {k for grp in test_opts.values() if isinstance(grp, dict) for k in grp}
        for opt_key in ("all", "target", "pattern", "type", "contract-only", "no-build", "jobs", "sequential", "keep-sandbox", "sync", "verbose", "quiet", "report-json", "quiet-report"):
            self.assertIn(opt_key, flat_test_opts, f"Missing option '{opt_key}' in dev test contributes")

        # Verify scripts/cli.py test() accepts both CmdBags and legacy list without duplicate flag emission
        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_tester_check", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        captured_argv = []
        with patch("dev.tester.Tester.run", side_effect=lambda argv: (captured_argv.extend(argv), 0)[1]):
            bags = CmdBags(
                raw_cmd="dev test",
                args=["core"],
                options={
                    "pattern": CmdOption("pattern", "manifest"),
                    "k": CmdOption("k", "manifest"),
                    "quiet": CmdOption("quiet", True),
                    "q": CmdOption("q", True),
                }
            )
            rc = cli_mod.test(bags)
            self.assertEqual(rc, 0)
            self.assertEqual(captured_argv.count("--pattern=manifest"), 1)
            self.assertNotIn("--k=manifest", captured_argv)
            self.assertEqual(captured_argv.count("--quiet"), 1)
            self.assertNotIn("--q", captured_argv)

        self.mark_passed()
