"""
Official test suite for dev.tester.Tester and dev.testing framework.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
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
    SafeStreamWriter,
    ASCIIReportFormatter,
    get_test_category,
    run_subprocess_with_tree_timeout,
)
from dev.tester import Tester, safe_print, _parse_test_run_config
from dev.testing.sandbox import SandboxProvisioner
from core import uri, vfs
from core.commands import CmdBags, CmdOption


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
        for scheme in ("module.source://", "module.build://", "module.release://"):
            if vfs.exists(scheme):
                root = uri.resolve(scheme)
                if os.path.isdir(root):
                    for item in os.listdir(root):
                        if item.startswith("mock_"):
                            shutil.rmtree(os.path.join(root, item), ignore_errors=True)

    def _mkdtemp(self) -> str:
        d = tempfile.mkdtemp()
        self.temp_dirs.append(d)
        return d

    @require(Requirement.ENV)
    def test_auto_contract_generation(self):
        """Verify dynamic auto contract synthesis and actual execution on compliant and non-compliant mock modules."""
        core_suite = make_contract_suite("core")
        self.assertEqual(core_suite.countTestCases(), 3)
        dev_suite = make_contract_suite("dev")
        self.assertEqual(dev_suite.countTestCases(), 3)

        self.create_mock_source_module("mock_contract_ok", "1.0.0.0")
        ok_suite = make_contract_suite("mock_contract_ok")
        self.assertEqual(ok_suite.countTestCases(), 3)
        res_ok = unittest.TextTestRunner(stream=StringIO(), verbosity=0).run(ok_suite)
        self.assertTrue(res_ok.wasSuccessful(), f"Expected mock_contract_ok to pass: {res_ok.failures} {res_ok.errors}")
        self.assertEqual(res_ok.testsRun, 3)
        self.assertTrue(vfs.exists("module.build://mock_contract_ok/1.0.0.build.zip"))

        self.create_mock_source_module(
            "mock_contract_bad",
            "1.0.0.0",
            files={
                "manifest.json": '{"name": "wrong_name", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}'
            },
        )
        bad_suite = make_contract_suite("mock_contract_bad")
        res_bad = unittest.TextTestRunner(stream=StringIO(), verbosity=0).run(bad_suite)
        self.assertFalse(res_bad.wasSuccessful())
        self.assertGreaterEqual(len(res_bad.failures), 1)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_discovery_and_suite_building(self):
        """Verify TestDiscovery builds 2-phase suite."""
        suite, contract_cnt, custom_cnt = TestDiscovery.build_suite_for_module("core")
        self.assertEqual(contract_cnt, 3)
        self.assertGreaterEqual(custom_cnt, 1)
        self.mark_passed()

    @require(Requirement.ENV)
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
        """Verify _run_test with --all cleans all sandboxes when tests pass."""
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
                    "modules": [
                        {
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
                            "errors": [],
                        }
                    ],
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "unknown": 0,
                    "skipped": 0,
                    "duration": 0.001,
                },
                "sandbox_dir": "",
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
        """Verify _run_test normalizes -k <pat> into --pattern=<pat> and flags."""
        captured_cmd = []

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = list(cmd)
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(
                            {
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
                                "failures_list": [],
                            },
                            f,
                        )
            return MagicMock(returncode=0)

        sb_dir = self._mkdtemp()
        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = sb_dir
        mock_ctx.host_dir = sb_dir
        mock_ctx.engine_dir = sb_dir

        with patch("subprocess.run", side_effect=mock_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"):
            ret = self.tester._run_test(["core", "-k", "test_my_feature", "-q", "-v", "--no-build"])
            self.assertEqual(ret, 0)
            self.assertIn("--pattern=test_my_feature", captured_cmd)
            self.assertNotIn("-k", captured_cmd)
            self.assertIn("--quiet", captured_cmd)
            self.assertIn("--verbose", captured_cmd)
            self.assertIn("core", captured_cmd)
            pos_args = [a for a in captured_cmd[captured_cmd.index("op-test") + 1:] if not a.startswith("-")]
            self.assertEqual(pos_args, ["core"])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_filter_suite_retains_failed_test_and_discovers_network(self):
        """Verify filter_suite retains _FailedTest across all types and includes NETWORK by default."""
        class MockFailedTest(unittest.TestCase):
            pass

        MockFailedTest.__name__ = "_FailedTest"

        class MockNormalTest(YSCBTestCase):
            @require(Requirement.NETWORK)
            def test_net(self):
                self.mark_passed()

        failed_instance = MockFailedTest()
        normal_instance = MockNormalTest("test_net")

        suite = unittest.TestSuite()
        suite.addTest(failed_instance)
        suite.addTest(normal_instance)

        filtered_def = filter_suite(suite)
        test_names = [t.__class__.__name__ for t in filtered_def]
        self.assertIn("_FailedTest", test_names)
        self.assertIn("MockNormalTest", test_names)

        filtered_env = filter_suite(suite, test_type="env")
        test_names_env = [t.__class__.__name__ for t in filtered_env]
        self.assertIn("_FailedTest", test_names_env)
        self.assertNotIn("MockNormalTest", test_names_env)

        with patch("dev.testing.requirement.is_network_available", return_value=False):
            res_net = unittest.TestResult()
            normal_instance.run(res_net)
            self.assertEqual(len(res_net.skipped), 1)
            self.assertIn("requires active Network connection", res_net.skipped[0][1])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_filter_suite_categories_target_and_type_guard(self):
        """Verify filter_suite handles workflow, perf, all, target selectors, and TestDiscovery blocks non-YSCBTestCase classes."""
        class LocalFilterDemoCase(YSCBTestCase):
            @require(Requirement.LOGIC)
            def test_logic_item(self):
                self.mark_passed()

            @require(Requirement.WORKFLOW)
            def test_wf_item(self):
                self.mark_passed()

            @require(Requirement.PERF)
            def test_perf_item(self):
                self.mark_passed()

        raw_suite = unittest.TestSuite(
            [
                LocalFilterDemoCase("test_logic_item"),
                LocalFilterDemoCase("test_wf_item"),
                LocalFilterDemoCase("test_perf_item"),
            ]
        )
        wf_suite = filter_suite(raw_suite, test_type="workflow")
        self.assertEqual([t._testMethodName for t in wf_suite], ["test_wf_item"])

        perf_suite = filter_suite(raw_suite, test_type="perf")
        self.assertEqual([t._testMethodName for t in perf_suite], ["test_perf_item"])

        all_suite = filter_suite(raw_suite, test_type="all-types")
        self.assertEqual(all_suite.countTestCases(), 3)

        target_suite = filter_suite(raw_suite, target="dev:LocalFilterDemoCase.test_wf_item")
        self.assertEqual([t._testMethodName for t in target_suite], ["test_wf_item"])

        self.create_mock_source_module(
            "mock_type_guard_mod",
            files={
                "tests/test_raw.py": (
                    "import unittest\n"
                    "class RawTestCaseViolation(unittest.TestCase):\n"
                    "    def test_bad(self):\n"
                    "        pass\n"
                )
            },
        )
        with self.assertRaises(TypeError) as ctx:
            TestDiscovery.build_suite_for_module("mock_type_guard_mod")
        self.assertIn("Security Guard Blocked", str(ctx.exception))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unknown_fails_tester_and_deducts_custom_passed(self):
        """Verify UNKNOWN > 0 sets all_passed=False, deducts custom_passed, and exits with code 1."""
        mod_name = "mock_unknown_test_mod"
        self.create_mock_source_module(
            mod_name,
            files={
                "tests/test_unmarked.py": (
                    "from dev.testing.case import YSCBTestCase\n"
                    "class TestUnmarked(YSCBTestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.mark_passed()\n"
                    "    def test_missing_mark(self):\n"
                    "        pass\n"
                )
            },
        )
        rep_json_path = os.path.join(self._mkdtemp(), "unknown_report.json")

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
        self.assertEqual(mod_entry["custom_total"], 3)
        self.assertEqual(mod_entry["custom_passed"], 2)

        syn_mod = "mock_syntax_err_mod"
        self.create_mock_source_module(
            syn_mod,
            files={"tests/test_broken_syntax.py": "def broken_syntax(:\n    pass\n"},
        )
        out_syn = StringIO()
        with patch("sys.stdout", out_syn):
            ret_syn = self.tester.run(["op-test", syn_mod, "--type=env"])
        self.assertEqual(ret_syn, 1, "Expected SyntaxError _FailedTest to fail even under --type=env")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_quiet_mode_zero_stderr_leak(self):
        """Verify _run_test in --quiet suppresses subprocess stderr completely."""
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
            "failures_list": [],
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
        """Verify single module test dispatches with --report-json and --quiet-report."""
        captured_cmd = []
        mock_res = MagicMock(returncode=0, stdout="", stderr="")

        def fake_subprocess_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = list(cmd)
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(
                            {
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
                                "failures_list": [],
                            },
                            f,
                        )
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
        """Verify OutputCapturer captures stdout/stderr, supports slice snapshots, and SafeStreamWriter handles encoding errors."""
        capturer = OutputCapturer(enabled=True)
        orig_out = sys.stdout
        with capturer:
            print("hello stdout world")
            snap = capturer.snapshot_offsets()
            print("sliced stdout line")
            print("hello stderr world", file=sys.stderr)
            sliced = capturer.get_slice(snap)
        self.assertEqual(sys.stdout, orig_out)
        out = capturer.get_output()
        self.assertIn("hello stdout world", out)
        self.assertIn("hello stderr world", out)
        self.assertIn("sliced stdout line", sliced)
        self.assertNotIn("hello stdout world", sliced)

        class StrictAsciiStream:
            encoding = "ascii"

            def __init__(self):
                self.chunks = []
                self.flushed = False

            def write(self, s: str):
                s.encode("ascii")
                self.chunks.append(s)

            def flush(self):
                self.flushed = True

        raw_stream = StrictAsciiStream()
        writer = SafeStreamWriter(raw_stream)
        writer.write("ascii and \u6e2c\u8a66")
        writer.flush()
        self.assertEqual(writer.encoding, "ascii")
        self.assertTrue(raw_stream.flushed)
        self.assertIn("ascii and ??", "".join(raw_stream.chunks))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ascii_report_formatter_with_metadata_and_taxonomy(self):
        """Verify ASCIIReportFormatter outputs metadata, timing, taxonomy, notices, and >20-line output truncation."""
        long_output = "\n".join(f"log line {i}" for i in range(1, 26))
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
                    "errors": ["test_fail: AssertionError"],
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
                    "captured_output": long_output,
                }
            ],
            "total": 13,
            "passed": 12,
            "failed": 1,
            "unknown": 0,
            "skipped": 0,
            "duration": 0.45,
        }
        report = ASCIIReportFormatter.format_summary(sample_data, warnings_count=2)
        self.assertIn("Mode: Default (LOGIC + ENV)", report)
        self.assertIn("Target: core", report)
        self.assertIn("Build: No-build (Fast)", report)
        self.assertIn("Notices: 2 sandbox warning(s) captured", report)
        self.assertIn("core (0.45s)", report)
        self.assertIn("[Logic: 6, Env: 3]", report)
        self.assertIn("FAILED / ERROR TEST CASES LIST:", report)
        self.assertIn("Quick Re-run: python yscb.py dev test --target=core:TestCore.test_fail", report)
        self.assertIn("log line 1", report)
        self.assertIn("... [truncated] ...", report)
        self.assertIn("log line 25", report)
        self.assertNotIn("log line 15", report)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_get_test_category_extraction(self):
        """Verify get_test_category correctly identifies taxonomy flags."""
        class MockCatTest(YSCBTestCase):
            @require(Requirement.LOGIC)
            def test_l(self):
                self.mark_passed()

            @require(Requirement.ENV)
            def test_e(self):
                self.mark_passed()

            @require(Requirement.WORKFLOW)
            def test_w(self):
                self.mark_passed()

            @require(Requirement.PERF)
            def test_p(self):
                self.mark_passed()

            def test_default(self):
                self.mark_passed()

        self.assertEqual(get_test_category(MockCatTest("test_l")), "logic")
        self.assertEqual(get_test_category(MockCatTest("test_e")), "env")
        self.assertEqual(get_test_category(MockCatTest("test_w")), "workflow")
        self.assertEqual(get_test_category(MockCatTest("test_p")), "perf")
        self.assertEqual(get_test_category(MockCatTest("test_default")), "logic")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_execute_single_module_in_sandbox_uses_tree_timeout(self):
        """Verify _execute_single_module_in_sandbox delegates to run_subprocess_with_tree_timeout by default."""
        sb_dir = self._mkdtemp()
        mock_ctx = MagicMock(sandbox_dir=sb_dir, host_dir=sb_dir, engine_dir=sb_dir)
        with patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.tester.run_subprocess_with_tree_timeout", return_value=(124, "", "[TimeoutError] Process tree terminated")) as mock_tree:
            rc, rep, out_sb, res_obj = self.tester._execute_single_module_in_sandbox(
                op_test_args=["core"],
                report_filename="rep.json",
                sandbox_idx=1,
                quiet_mode=True,
                timeout_sec=45.0,
            )
            self.assertEqual(rc, 124)
            self.assertIsNone(rep)
            self.assertEqual(out_sb, sb_dir)
            self.assertIsNotNone(res_obj)
            self.assertEqual(res_obj.returncode, 124)
            self.assertIn("[TimeoutError]", res_obj.stderr)
            mock_tree.assert_called_once()
            self.assertEqual(mock_tree.call_args.kwargs.get("timeout_sec"), 45.0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_run_subprocess_with_tree_timeout_normal_and_timeout(self):
        """Verify run_subprocess_with_tree_timeout normal completion and TimeoutExpired tree termination."""
        rc, out, err = run_subprocess_with_tree_timeout(
            [sys.executable, "-c", "import sys; print('stdout_ok'); print('stderr_ok', file=sys.stderr)"],
            timeout_sec=10.0,
        )
        self.assertEqual(rc, 0)
        self.assertIn("stdout_ok", out)
        self.assertIn("stderr_ok", err)

        fake_proc = MagicMock()
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["hang"], timeout=0.5),
            ("partial_out", "partial_err"),
        ]
        fake_proc.stdout = MagicMock()
        fake_proc.stderr = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc), \
             patch("dev.testing.runner.terminate_popen_tree") as mock_kill:
            rc_to, out_to, err_to = run_subprocess_with_tree_timeout(["hang"], timeout_sec=0.5)
            self.assertEqual(rc_to, -1)
            self.assertEqual(out_to, "partial_out")
            self.assertIn("partial_err", err_to)
            self.assertIn("[dev:runner] Process timed out after 0.5s", err_to)
            mock_kill.assert_called_once_with(fake_proc, timeout_sec=2.0)
            fake_proc.stdout.close.assert_called_once()
            fake_proc.stderr.close.assert_called_once()
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_parse_test_run_config_and_cli_guards(self):
        """Verify _parse_test_run_config flag parsing and Tester CLI/op-mksb/op-test guardrails."""
        cfg1 = _parse_test_run_config(["-j4", "--target=core:TestX", "--no-build", "--sequential", "-q"])
        self.assertEqual(cfg1.jobs, 4)
        self.assertEqual(cfg1.target_mod, "core")
        self.assertEqual(cfg1.target_param, "--target=core:TestX")
        self.assertTrue(cfg1.no_build)
        self.assertTrue(cfg1.is_sequential)
        self.assertTrue(cfg1.quiet_mode)

        cfg2 = _parse_test_run_config(["-j", "2", "-a", "-k=my_pat", "-v", "--sync"])
        self.assertEqual(cfg2.jobs, 2)
        self.assertTrue(cfg2.is_all)
        self.assertIn("--pattern=my_pat", cfg2.clean_argv)
        self.assertTrue(cfg2.verbose)
        self.assertTrue(cfg2.sync_requested)

        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(self.tester.run([]), 1)
        self.assertIn("Usage: python yscb.py dev test", buf.getvalue())

        mock_ctx = MagicMock(sandbox_dir="/tmp/fake_sb")
        with patch.object(SandboxProvisioner, "create_sandbox", return_value=mock_ctx) as mock_cs:
            with patch("sys.stdout", StringIO()):
                self.assertEqual(self.tester.run(["op-mksb", "--dir=/tmp/fake_sb"]), 0)
            mock_cs.assert_called_once_with("/tmp/fake_sb")

        with patch.object(SandboxProvisioner, "create_sandbox", side_effect=RuntimeError("disk full")):
            with patch("sys.stdout", StringIO()):
                self.assertEqual(self.tester.run(["op-mksb"]), 1)

        old_sb = os.environ.get("YSCB_TEST_SANDBOX")
        try:
            os.environ["YSCB_TEST_SANDBOX"] = "0"
            with patch("sys.stderr", StringIO()):
                self.assertEqual(self.tester._run_op_test(["core"]), 1)
        finally:
            if old_sb is not None:
                os.environ["YSCB_TEST_SANDBOX"] = old_sb
            else:
                os.environ.pop("YSCB_TEST_SANDBOX", None)

        with patch("sys.stdout", StringIO()):
            self.assertEqual(self.tester._run_op_test(["core", "--type=invalid_xyz"]), 1)
            self.assertEqual(self.tester._run_op_test(["mock_nonexistent_mod_xyz"]), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_run_parallel_test_exception_and_build_failure_handling(self):
        """Verify pre-build failure handling and worker exception resilience in _run_test / _run_parallel_test."""
        with patch("dev.builder.Builder.build_module", return_value=(False, "syntax error")), \
             patch("sys.stderr", StringIO()):
            self.assertEqual(self.tester._run_test(["core"]), 1)

        with patch("dev.builder.Builder.build_all", return_value={"core": (False, "build failed")}), \
             patch("sys.stderr", StringIO()):
            self.assertEqual(self.tester._run_parallel_test(["--all"], ["core", "dev"], no_build=False), 1)

        with patch.object(SandboxProvisioner, "adapt_build_pip_dependencies", return_value=[]), \
             patch.object(SandboxProvisioner, "prune_sandboxes", return_value=0), \
             patch.object(self.tester, "_run_single_module_worker", side_effect=RuntimeError("worker thread exploded")), \
             patch("sys.stdout", StringIO()), \
             patch("sys.stderr", StringIO()):
            rc = self.tester._run_parallel_test(["--all"], ["core", "dev"], no_build=True, quiet_mode=True)
            self.assertEqual(rc, 1)
        self.mark_passed()


@require(Requirement.LOGIC)
class TestDevTesterSync(YSCBTestCase):
    """Consolidated tests for dev.tester --sync and post-test direct install guidance."""

    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_handle_post_test_sync_with_sync_flag(self):
        """Verify sync_requested=True invokes subprocess.run to install <mod>@build."""
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
        """Verify sync_requested=False prints install guidance without invoking subprocess.run."""
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
        """Verify 100% pass outputs single-line summary Pass: {passed}({pct:.1f}%), Fail: 0, Skip: {skipped}."""
        report_data = {
            "total": 50,
            "passed": 50,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
            "failures_list": [],
            "modules": [],
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(output, "Pass: 50(100.0%), Fail: 0, Skip: 0")
        self.mark_passed()

    def test_format_throttled_with_failures(self):
        """Verify failure presence outputs single-line stats followed by FAILED / ERROR TEST CASES LIST details."""
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
                    "captured_output": "Captured stdout line",
                }
            ],
            "modules": [],
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
        """Verify worker-level crash with empty failures_list still outputs module error lines."""
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
                    "errors": ["Execution failed with code 1"],
                }
            ],
        }
        output = ASCIIReportFormatter.format_throttled(report_data)
        self.assertTrue(output.startswith("Pass: 0(0.0%), Fail: 1, Skip: 0"))
        self.assertIn("[!] [dev] ERROR: Execution failed with code 1", output)
        self.mark_passed()

    def test_format_throttled_edge_cases(self):
        """Verify zero-test division safety and all-skipped formatting."""
        report_zero = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
            "failures_list": [],
            "modules": [],
        }
        self.assertEqual(ASCIIReportFormatter.format_throttled(report_zero), "Pass: 0(0.0%), Fail: 0, Skip: 0")

        report_skipped = {
            "total": 10,
            "passed": 0,
            "failed": 0,
            "unknown": 0,
            "skipped": 10,
            "failures_list": [],
            "modules": [],
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
            "modules": [],
        }
        throttled = ASCIIReportFormatter.format_throttled(report_data)
        self.assertEqual(throttled, "Pass: 40(80.0%), Fail: 0, Unknown: 10, Skip: 0")

        summary = ASCIIReportFormatter.format_summary(report_data)
        self.assertIn("Summary : 50 Total, 40 Passed, 0 Failed, 10 Unknown, 0 Skipped (1.234s)", summary)
        self.assertIn("Status  : FAILED", summary)
        self.mark_passed()

    def test_tester_quiet_flag_and_silence_op_test(self):
        """Execute real _run_op_test(['core', '--contract-only', '-q']) and verify throttled output."""
        out_io = StringIO()
        with patch("sys.stdout", out_io):
            ret = self.tester._run_op_test(["core", "--contract-only", "-q"])
        self.assertEqual(ret, 0)
        output = out_io.getvalue().strip()
        self.assertIn("Pass: 3(100.0%), Fail: 0, Skip: 0", output)
        self.assertNotIn("begin test in", output)
        self.mark_passed()

    def test_dev_pep562_lazy_loading_and_cli_test_dispatch(self):
        """Verify dev PEP 562 lazy loading across all __all__ symbols, dir(dev), contributes/core.json contract, and cli.test/op_mksb/op_test."""
        import dev

        saved_attrs = {sym: dev.__dict__.get(sym) for sym in dev.__all__ if sym in dev.__dict__}
        try:
            for sym in dev.__all__:
                dev.__dict__.pop(sym, None)
            dir_entries = dir(dev)
            for sym in dev.__all__:
                self.assertIn(sym, dir_entries)
                loaded = getattr(dev, sym)
                self.assertIsNotNone(loaded)
                self.assertIn(sym, dev.__dict__)
            with self.assertRaises(AttributeError):
                _ = getattr(dev, "NonExistentSymbolXYZ")
        finally:
            dev.__dict__.update(saved_attrs)

        contrib_data = vfs.read_json("module.source://dev/contributes/core.json")
        event_keys = {k for item in contrib_data.get("events", []) if isinstance(item, dict) for k in item}
        self.assertIn("on_test_setup", event_keys)
        self.assertIn("on_test_teardown", event_keys)
        test_opts = contrib_data["commands"]["cmd"]["test"]["options"]
        flat_test_opts = {k for grp in test_opts.values() if isinstance(grp, dict) for k in grp}
        for opt_key in (
            "all",
            "target",
            "pattern",
            "type",
            "contract-only",
            "no-build",
            "jobs",
            "sequential",
            "keep-sandbox",
            "sync",
            "verbose",
            "quiet",
            "report-json",
            "quiet-report",
        ):
            self.assertIn(opt_key, flat_test_opts, f"Missing option '{opt_key}' in dev test contributes")

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
                },
            )
            rc = cli_mod.test(bags)
            self.assertEqual(rc, 0)
            self.assertEqual(captured_argv.count("--pattern=manifest"), 1)
            self.assertNotIn("--k=manifest", captured_argv)
            self.assertEqual(captured_argv.count("--quiet"), 1)
            self.assertNotIn("--q", captured_argv)

            captured_argv.clear()
            self.assertEqual(cli_mod.op_mksb(["--dir=/tmp/mock_sb"]), 0)
            self.assertEqual(captured_argv, ["op-mksb", "--dir=/tmp/mock_sb"])

            captured_argv.clear()
            self.assertEqual(cli_mod.op_test(["core", "--contract-only"]), 0)
            self.assertEqual(captured_argv, ["op-test", "core", "--contract-only"])

        self.mark_passed()
