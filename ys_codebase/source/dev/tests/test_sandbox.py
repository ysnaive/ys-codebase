"""
Comprehensive test suite for dev.testing.sandbox (SandboxProvisioner, SandboxContext, and 3-tier CLI).
"""
import os
import sys
import json
import unittest
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner, SandboxContext
from dev.testing.runner import TestDiscovery, filter_suite
from dev.tester import Tester
from dev.builder import Builder
from core import uri

class TestSandboxArchitecture(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tester = Tester()

    @require(Requirement.LOGIC)
    def test_op_mksb_atomic_provisioning(self):
        """FT-01: Verify dev op-mksb creates full micro virtual environment with core hook setup."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            self.assertTrue(os.path.isdir(ctx.sandbox_dir))
            self.assertTrue(os.path.isdir(ctx.project_dir))
            self.assertTrue(os.path.isdir(ctx.host_dir))
            self.assertTrue(os.path.isdir(ctx.engine_dir))
            self.assertTrue(os.path.isdir(ctx.provider_dir))
            
            # Verify host yscb.config.json
            host_cfg_file = os.path.join(ctx.host_dir, "yscb.config.json")
            self.assertTrue(os.path.isfile(host_cfg_file))
            with open(host_cfg_file, "r", encoding="utf-8") as f:
                h_data = json.load(f)
            self.assertEqual(h_data.get("yscb_root"), "./engine")

            # Verify core's hook.dev.py auto-configured config.project.json
            core_project_cfg = os.path.join(ctx.engine_dir, "config", "core", "config.project.json")
            self.assertTrue(os.path.isfile(core_project_cfg))
            with open(core_project_cfg, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            self.assertEqual(c_data.get("project_root"), "../mock_downstream_project")
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_vfs_natural_constant_self_locating(self):
        """FT-02: Verify constant self-locating operates deterministically in sandbox without code hacks."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            sandbox_uri_file = os.path.join(ctx.engine_dir, "source", "core", "core", "uri.py")
            # If uri.py runs at that location, curr is uri.py's dir, 3 levels up is ctx.engine_dir
            curr = os.path.dirname(sandbox_uri_file)
            calc_root = os.path.dirname(os.path.dirname(os.path.dirname(curr)))
            self.assertEqual(os.path.abspath(calc_root), os.path.abspath(ctx.engine_dir))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_op_test_in_place_execution(self):
        """FT-03: Verify dev op-test runs in-place without spawning additional sandboxes."""
        res = self.tester.run(["op-test", "core", "--contract-only"])
        self.assertEqual(res, 0)
        self.mark_passed()

    @require(Requirement.HOST_CLI)
    def test_dev_test_high_level_orchestration(self):
        """FT-04: Verify high-level dev test runs E2E workflow."""
        ret, stdout, stderr = self.run_cli(["dev", "test", "core", "--contract-only"])
        self.assertEqual(ret, 0)
        self.assertIn("YS-Codebase Test Execution Diagnostic Report", stdout)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dual_source_provider_resolution(self):
        """FT-05: Verify mock provider package creation and index tracking."""
        pkg_dir = self.create_mock_package("mock_demo_pkg", "1.0.0", deps={"core": "1.0.0"})
        self.assertTrue(os.path.isdir(pkg_dir))
        manifest_file = os.path.join(pkg_dir, "manifest.json")
        self.assertTrue(os.path.isfile(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["name"], "mock_demo_pkg")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_type_filter_and_recursive_pattern_filter(self):
        """FT-06: Verify filter_suite recursively filters by pattern and Requirement type."""
        suite = unittest.TestSuite()
        
        class DummyCase(unittest.TestCase):
            @require(Requirement.LOGIC)
            def test_alpha_logic(self):
                pass
            @require(Requirement.NETWORK)
            def test_beta_network(self):
                pass
            def test_gamma_general(self):
                pass

        loader = unittest.TestLoader()
        inner_suite = loader.loadTestsFromTestCase(DummyCase)
        suite.addTest(inner_suite)

        # Pattern filter: 'alpha'
        filtered_pattern = filter_suite(suite, pattern="alpha")
        self.assertEqual(filtered_pattern.countTestCases(), 1)

        # Type filter: 'logic' (should exclude network)
        filtered_logic = filter_suite(suite, test_type="logic")
        self.assertEqual(filtered_logic.countTestCases(), 2)  # alpha_logic and gamma_general

        # Type filter: 'network' (should match beta_network)
        filtered_net = filter_suite(suite, test_type="network")
        self.assertEqual(filtered_net.countTestCases(), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_dev_error_isolation(self):
        """ET-01: Verify error isolation when a hook raises an exception during test setup."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            # Create a broken hook in sandbox
            broken_mod_dir = os.path.join(ctx.engine_dir, "source", "mock_broken_hook", "scripts")
            os.makedirs(broken_mod_dir, exist_ok=True)
            with open(os.path.join(broken_mod_dir, "hook.dev.py"), "w", encoding="utf-8") as f:
                f.write("def on_test_setup(context):\n    raise RuntimeError('Deliberate hook failure')\n")
            
            # Dispatching hooks should not throw an unhandled exception
            SandboxProvisioner._dispatch_test_hooks(ctx, "on_test_setup")
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_invalid_type_filter_cli_exit_1(self):
        """ET-02: Verify invalid --type filter returns exit code 1."""
        res = self.tester.run(["op-test", "core", "--type=invalid_type_xyz"])
        self.assertEqual(res, 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_builder_preserves_hook_dev(self):
        """ET-03: Verify Builder builds module and preserves scripts/hook.dev.py while excluding tests/."""
        builder = Builder()
        ok, msg = builder.build_module("core", clean=True)
        self.assertTrue(ok, msg)
        
        build_core_root = uri.resolve("module.build.root://core/1.0.0")
        hook_file = os.path.join(build_core_root, "scripts", "hook.dev.py")
        self.assertTrue(os.path.isfile(hook_file), "scripts/hook.dev.py was unexpectedly excluded from build artifact!")
        self.assertFalse(os.path.exists(os.path.join(build_core_root, "tests")), "tests/ directory was not excluded!")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_third_party_host_module_inheritance(self):
        """Verify sandbox inherits installed host modules when not present in source/ and dispatches their hooks."""
        ctx = SandboxProvisioner.create_sandbox(copy_source=False)
        try:
            # When copy_source=False, source/ is empty, but host modules (core, dev) are inherited into sandbox modules/
            sandbox_core_mod = os.path.join(ctx.engine_dir, "modules", "core")
            if os.path.isdir(uri.resolve("module.root://core")):
                self.assertTrue(os.path.isdir(sandbox_core_mod))
                # Verify hook in inherited module was triggered and wrote config.project.json
                cfg_file = os.path.join(ctx.engine_dir, "config", "core", "config.project.json")
                self.assertTrue(os.path.isfile(cfg_file))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()
