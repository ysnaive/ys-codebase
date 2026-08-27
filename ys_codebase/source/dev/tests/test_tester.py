"""
Official test suite for dev.tester.Tester and dev.testing framework.
"""
from dev.testing import YSCBTestCase, require, Requirement
from dev.testing.contract import make_contract_suite
from dev.testing.runner import TestDiscovery, TestRunner
from dev.tester import Tester
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
    def test_run_test_all_success_cleans_sandboxes(self):
        """FT-03: Verify _run_test with --all cleans all sandboxes when tests pass."""
        import os
        from dev.testing.sandbox import SandboxProvisioner
        sandbox_parent = uri.resolve("cache://dev/sandbox/")
        os.makedirs(sandbox_parent, exist_ok=True)
        dummy_sb = os.path.join(sandbox_parent, "sandbox_20260101_200001_000000")
        os.makedirs(dummy_sb, exist_ok=True)
        try:
            ret = self.tester._run_test(["--all", "--contract-only", "--no-build"])
            self.assertEqual(ret, 0)
            self.assertFalse(os.path.exists(dummy_sb))
        finally:
            if os.path.exists(dummy_sb):
                SandboxProvisioner.cleanup_sandbox(dummy_sb, force=True)
        self.mark_passed()
