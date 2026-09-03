"""
Official test suite for dev.tester.Tester and dev.testing framework.
"""
import os
import sys
from io import StringIO
from unittest.mock import patch
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
