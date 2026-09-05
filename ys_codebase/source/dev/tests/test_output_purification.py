"""
Unit and Integration Test Suite for Output Purification, Information Aggregation, and Security Guardrails.
Covers: FT-01, FT-02, FT-03, FT-04, ET-01, ET-02.
"""
import os
import sys
import json
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

from dev.testing import YSCBTestCase, require, Requirement
from dev.testing.case import SecurityError
from dev.testing.runner import ASCIIReportFormatter
from dev.tester import Tester


@require(Requirement.LOGIC)
class TestOutputPurification(YSCBTestCase):
    """Verifies output purification, IPC JSON reporting, warning folding, and host security guardrails."""

    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_quiet_mode_zero_stderr_leak(self):
        """FT-01: Verify _run_test in --quiet suppresses subprocess stderr completely with clean stats."""
        dummy_report = {
            "filter_mode": "Default (LOGIC + ENV)",
            "target_scope": "dev",
            "no_build": True,
            "modules": [],
            "total": 10,
            "passed": 10,
            "failed": 0,
            "skipped": 0,
            "duration": 1.23,
            "failures_list": []
        }

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Subprocess stdout noise\n"
        mock_res.stderr = (
            "[compiler:warning] Failed to resolve project URI 'workflow.docs://' in 'SKILL.md'\n"
            "[compiler:warning] Unresolved semantic URI tag\n"
            "Warning: something non-critical happened\n"
        )

        def fake_subprocess_run(cmd, **kwargs):
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(dummy_report, f)
            return mock_res

        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = tempfile.mkdtemp()
        mock_ctx.host_dir = mock_ctx.sandbox_dir
        mock_ctx.engine_dir = mock_ctx.sandbox_dir

        out_io = StringIO()
        err_io = StringIO()

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"), \
             patch("sys.stdout", out_io), \
             patch("sys.stderr", err_io):
            ret = self.tester._run_test(["dev", "--quiet", "--no-build"])

        self.assertEqual(ret, 0)
        # Verify 0 stderr leak
        self.assertEqual(err_io.getvalue(), "", "Expected zero stderr output in quiet mode!")
        # Verify single line stats in stdout
        stdout_val = out_io.getvalue().strip()
        self.assertEqual(stdout_val, "Pass: 10(100.0%), Fail: 0, Skip: 0")
        self.mark_passed()

    def test_single_module_json_ipc_pipeline(self):
        """FT-02: Verify single module test dispatches with --report-json and --quiet-report."""
        captured_cmd = []

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = ""
        mock_res.stderr = ""

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
                            "skipped": 0,
                            "duration": 0.5,
                            "failures_list": []
                        }, f)
            return mock_res

        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = tempfile.mkdtemp()
        mock_ctx.host_dir = mock_ctx.sandbox_dir
        mock_ctx.engine_dir = mock_ctx.sandbox_dir

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"), \
             patch("sys.stdout", StringIO()), \
             patch("sys.stderr", StringIO()):
            ret = self.tester._run_test(["dev", "--no-build"])

        self.assertEqual(ret, 0)
        self.assertTrue(any(a.startswith("--report-json=") for a in captured_cmd), "Expected --report-json argument")
        self.assertIn("--quiet-report", captured_cmd, "Expected --quiet-report argument")
        self.mark_passed()

    def test_normal_mode_warning_collation(self):
        """FT-03: Verify normal mode folds captured warnings into a single notice summary."""
        dummy_report = {
            "filter_mode": "Default (LOGIC + ENV)",
            "target_scope": "dev",
            "no_build": True,
            "modules": [{
                "name": "dev",
                "duration": 2.5,
                "contract_total": 3,
                "contract_passed": 3,
                "custom_total": 10,
                "custom_passed": 10,
                "logic_passed": 5,
                "env_passed": 5,
                "workflow_passed": 0,
                "perf_passed": 0,
                "failures_count": 0,
                "skipped_count": 0,
                "passed": True
            }],
            "total": 13,
            "passed": 13,
            "failed": 0,
            "skipped": 0,
            "duration": 2.5,
            "failures_list": []
        }

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = ""
        mock_res.stderr = (
            "[compiler:warning] Line 1\n"
            "[compiler:warning] Line 2\n"
            "[compiler:warning] Line 3\n"
        )

        def fake_subprocess_run(cmd, **kwargs):
            for arg in cmd:
                if arg.startswith("--report-json="):
                    p = arg.split("=", 1)[1]
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(dummy_report, f)
            return mock_res

        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = tempfile.mkdtemp()
        mock_ctx.host_dir = mock_ctx.sandbox_dir
        mock_ctx.engine_dir = mock_ctx.sandbox_dir

        out_io = StringIO()
        err_io = StringIO()

        orig_quiet = os.environ.get("YSCB_TEST_QUIET")
        if "YSCB_TEST_QUIET" in os.environ:
            del os.environ["YSCB_TEST_QUIET"]
        try:
            with patch("subprocess.run", side_effect=fake_subprocess_run), \
                 patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
                 patch("dev.testing.sandbox.SandboxProvisioner.cleanup_sandbox"), \
                 patch("sys.stdout", out_io), \
                 patch("sys.stderr", err_io):
                ret = self.tester._run_test(["dev", "--no-build"])
        finally:
            if orig_quiet is not None:
                os.environ["YSCB_TEST_QUIET"] = orig_quiet

        self.assertEqual(ret, 0)
        out_str = out_io.getvalue()
        # Verify warning summary notice exists
        self.assertIn("[*] Notices: 3 sandbox warning(s) captured (suppressed, run with --verbose to inspect)", out_str)
        # Verify raw warning lines are not printed to stdout or stderr
        self.assertNotIn("[compiler:warning] Line 1", out_str)
        self.assertNotIn("[compiler:warning] Line 1", err_io.getvalue())
        self.mark_passed()

    def test_op_test_host_guard(self):
        """FT-04: Verify dev op-test is blocked on host environment."""
        err_io = StringIO()
        orig_sb = os.environ.get("YSCB_TEST_SANDBOX")
        try:
            # Clear sandbox environment flag
            if "YSCB_TEST_SANDBOX" in os.environ:
                del os.environ["YSCB_TEST_SANDBOX"]
            with patch("sys.stderr", err_io):
                code = self.tester._run_op_test(["dev"])
            self.assertEqual(code, 1)
            err_str = err_io.getvalue()
            self.assertIn("Security Guard Blocked", err_str)
            self.assertIn("'dev op-test' is an internal in-place runner", err_str)
        finally:
            if orig_sb is not None:
                os.environ["YSCB_TEST_SANDBOX"] = orig_sb
        self.mark_passed()

    def test_sandbox_path_validation_blocks_leak(self):
        """ET-01: Verify YSCBTestCase.setUp raises SecurityError when sandbox dir is invalid."""
        orig_sb = os.environ.get("YSCB_TEST_SANDBOX")
        orig_dir = os.environ.get("YSCB_SANDBOX_DIR")
        orig_shared = YSCBTestCase._shared_sandbox_ctx
        try:
            # Case A: YSCB_TEST_SANDBOX not set
            if "YSCB_TEST_SANDBOX" in os.environ:
                del os.environ["YSCB_TEST_SANDBOX"]
            tc = YSCBTestCase()
            with self.assertRaises(SecurityError):
                tc.setUp()

            # Case B: YSCB_TEST_SANDBOX is 1, but points to nonexistent sandbox and cwd has no host_env
            os.environ["YSCB_TEST_SANDBOX"] = "1"
            os.environ["YSCB_SANDBOX_DIR"] = "/nonexistent/fake/sandbox/dir"
            YSCBTestCase._shared_sandbox_ctx = None
            with patch("os.getcwd", return_value="d:/repos/ys_codebase"):
                with self.assertRaises(SecurityError):
                    tc.setUp()
        finally:
            if orig_sb is not None:
                os.environ["YSCB_TEST_SANDBOX"] = orig_sb
            elif "YSCB_TEST_SANDBOX" in os.environ:
                del os.environ["YSCB_TEST_SANDBOX"]
            if orig_dir is not None:
                os.environ["YSCB_SANDBOX_DIR"] = orig_dir
            elif "YSCB_SANDBOX_DIR" in os.environ:
                del os.environ["YSCB_SANDBOX_DIR"]
            YSCBTestCase._shared_sandbox_ctx = orig_shared
        self.mark_passed()

    def test_sandbox_crash_stderr_tail_fallback(self):
        """ET-02: Verify crash diagnosis extracts stderr tail when sandbox unexpectedly fails."""
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        # 30 lines of error trace
        mock_res.stderr = "\n".join([f"Traceback line {i}" for i in range(1, 31)])

        mock_ctx = MagicMock()
        mock_ctx.sandbox_dir = tempfile.mkdtemp()
        mock_ctx.host_dir = mock_ctx.sandbox_dir
        mock_ctx.engine_dir = mock_ctx.sandbox_dir

        err_io = StringIO()
        with patch("subprocess.run", return_value=mock_res), \
             patch("dev.testing.sandbox.SandboxProvisioner.create_sandbox", return_value=mock_ctx), \
             patch("dev.testing.sandbox.SandboxProvisioner.prune_sandboxes"), \
             patch("sys.stdout", StringIO()), \
             patch("sys.stderr", err_io):
            ret = self.tester._run_test(["dev", "--no-build"])

        self.assertEqual(ret, 1)
        err_str = err_io.getvalue()
        self.assertIn("Subprocess execution failed with code 1", err_str)
        # Must contain tail (e.g. line 30)
        self.assertIn("Traceback line 30", err_str)
        # Should not contain head lines beyond 20 lines (e.g. line 1)
        self.assertNotIn("Traceback line 1\n", err_str)
        self.mark_passed()
