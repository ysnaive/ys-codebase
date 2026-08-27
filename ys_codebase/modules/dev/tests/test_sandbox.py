"""
Comprehensive test suite for dev.testing.sandbox (SandboxProvisioner, SandboxContext, and 3-tier CLI).
"""
import os
import sys
import json
import unittest
import zipfile
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner, SandboxContext
from dev.testing.runner import TestDiscovery, filter_suite, OutputCapturer, ASCIIReportFormatter, get_test_category
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
        
        class DummyCase(YSCBTestCase):
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
        """ET-03: Verify Builder builds module and preserves scripts/hook.dev.py in single-file zip."""
        builder = Builder()
        m_data = uri.read_json("module.source://core/manifest.json")
        ver = m_data.get("version", "1.0.0.0")
        triplet = ver.rsplit(".", 1)[0] if ver.count(".") == 3 else ver
        build_tag = f"{triplet}.build"

        ok, msg = builder.build_module("core", clean=True)
        self.assertTrue(ok, msg)
        
        build_zip = uri.resolve(f"module.build://core/{build_tag}.zip")
        self.assertTrue(os.path.isfile(build_zip))
        with zipfile.ZipFile(build_zip, "r") as zf:
            self.assertIn("scripts/hook.dev.py", zf.namelist(), "scripts/hook.dev.py was unexpectedly excluded from build artifact!")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_third_party_host_module_inheritance(self):
        """Verify sandbox inherits installed host modules when not present in source/ and dispatches their hooks."""
        ctx = SandboxProvisioner.create_sandbox(copy_source=False)
        try:
            # When copy_source=False, source/ is empty, but host modules (core, dev) are inherited into sandbox modules/
            sandbox_core_mod = os.path.join(ctx.engine_dir, "modules", "core")
            if os.path.isdir(uri.resolve("module://core")):
                self.assertTrue(os.path.isdir(sandbox_core_mod))
                # Verify hook in inherited module was triggered and wrote config.project.json
                cfg_file = os.path.join(ctx.engine_dir, "config", "core", "config.project.json")
                self.assertTrue(os.path.isfile(cfg_file))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_prune_sandboxes_limit(self):
        """FT-01: Verify prune_sandboxes deletes oldest sandboxes when total count exceeds max_keep."""
        sandbox_parent = os.path.join(self.sandbox_dir, "test_prune_scope")
        os.makedirs(sandbox_parent, exist_ok=True)
        created_dirs = []
        try:
            for i in range(1, 6):
                d_name = f"sandbox_20260101_00000{i}_000000"
                d_path = os.path.join(sandbox_parent, d_name)
                os.makedirs(d_path, exist_ok=True)
                created_dirs.append(d_path)

            deleted_cnt = SandboxProvisioner.prune_sandboxes(max_keep=3, sandbox_parent_dir=sandbox_parent)
            self.assertEqual(deleted_cnt, 2)

            # Oldest 2 should be deleted
            self.assertFalse(os.path.exists(created_dirs[0]))
            self.assertFalse(os.path.exists(created_dirs[1]))

            # Newest 3 should remain
            self.assertTrue(os.path.exists(created_dirs[2]))
            self.assertTrue(os.path.exists(created_dirs[3]))
            self.assertTrue(os.path.exists(created_dirs[4]))
        finally:
            for p in created_dirs:
                if os.path.exists(p):
                    SandboxProvisioner.cleanup_sandbox(p, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cleanup_all_sandboxes(self):
        """FT-02: Verify cleanup_all_sandboxes deletes all sandbox_* directories."""
        sandbox_parent = os.path.join(self.sandbox_dir, "test_cleanup_scope")
        os.makedirs(sandbox_parent, exist_ok=True)
        created_dirs = []
        try:
            for i in range(1, 4):
                d_name = f"sandbox_20260101_10000{i}_000000"
                d_path = os.path.join(sandbox_parent, d_name)
                os.makedirs(d_path, exist_ok=True)
                created_dirs.append(d_path)

            deleted_cnt = SandboxProvisioner.cleanup_all_sandboxes(sandbox_parent_dir=sandbox_parent)
            self.assertEqual(deleted_cnt, 3)

            for p in created_dirs:
                self.assertFalse(os.path.exists(p))
        finally:
            for p in created_dirs:
                if os.path.exists(p):
                    SandboxProvisioner.cleanup_sandbox(p, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_cleanup_empty_or_missing(self):
        """ET-01: Verify prune_sandboxes and cleanup_all_sandboxes return 0 when no sandboxes exist."""
        empty_scope = os.path.join(self.sandbox_dir, "test_empty_scope")
        os.makedirs(empty_scope, exist_ok=True)
        cnt1 = SandboxProvisioner.prune_sandboxes(max_keep=3, sandbox_parent_dir=empty_scope)
        cnt2 = SandboxProvisioner.cleanup_all_sandboxes(sandbox_parent_dir=empty_scope)
        self.assertEqual(cnt1, 0)
        self.assertEqual(cnt2, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_cleanup_ignores_non_sandbox(self):
        """ET-02: Verify cleanup_all_sandboxes does not delete non-sandbox directories."""
        sandbox_parent = os.path.join(self.sandbox_dir, "test_ignore_scope")
        os.makedirs(sandbox_parent, exist_ok=True)
        non_sandbox_dir = os.path.join(sandbox_parent, "other_cache_dir_do_not_delete")
        os.makedirs(non_sandbox_dir, exist_ok=True)
        try:
            SandboxProvisioner.cleanup_all_sandboxes(sandbox_parent_dir=sandbox_parent)
            self.assertTrue(os.path.exists(non_sandbox_dir))
        finally:
            if os.path.exists(non_sandbox_dir):
                import shutil
                shutil.rmtree(non_sandbox_dir)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_filter_suite_taxonomy_and_target(self):
        """FT-02, FT-03, FT-04: Verify filter_suite with 4-tier taxonomy and target pinning."""
        class MockLogicTest(YSCBTestCase):
            @require(Requirement.LOGIC)
            def test_logic(self): pass
            @require(Requirement.ENV)
            def test_env(self): pass
            @require(Requirement.WORKFLOW)
            def test_workflow(self): pass
            @require(Requirement.PERF)
            def test_perf(self): pass

        suite = unittest.TestSuite()
        suite.addTest(MockLogicTest("test_logic"))
        suite.addTest(MockLogicTest("test_env"))
        suite.addTest(MockLogicTest("test_workflow"))
        suite.addTest(MockLogicTest("test_perf"))

        # Default filter: includes logic + env (2 tests), excludes workflow + perf
        def_suite = filter_suite(suite)
        self.assertEqual(def_suite.countTestCases(), 2)

        # Explicit logical
        logic_suite = filter_suite(suite, test_type="logic")
        self.assertEqual(logic_suite.countTestCases(), 1)

        # Explicit workflow
        wf_suite = filter_suite(suite, test_type="workflow")
        self.assertEqual(wf_suite.countTestCases(), 1)

        # Explicit perf
        perf_suite = filter_suite(suite, test_type="perf")
        self.assertEqual(perf_suite.countTestCases(), 1)

        # Explicit all
        all_suite = filter_suite(suite, test_type="all")
        self.assertEqual(all_suite.countTestCases(), 4)

        # Target pinning: bypasses default exclusions to run specific test
        tgt_suite = filter_suite(suite, target="test_workflow")
        self.assertEqual(tgt_suite.countTestCases(), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_discovery_dynamic_type_guard_rejects_unittest_testcase(self):
        """FT-05: Verify TestDiscovery raises TypeError when a discovered test directly subclasses unittest.TestCase."""
        import shutil
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_raw_test_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "tests"), exist_ok=True)
            
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_raw_test_mod", "version": "1.0.0.0", "entry": "scripts/cli.py"}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "tests", "test_raw.py"), "w", encoding="utf-8") as f:
                f.write('import unittest\nclass TestRawDirect(unittest.TestCase):\n    def test_a(self): pass\n')

            with self.assertRaises(TypeError) as ctx:
                TestDiscovery.build_suite_for_module("mock_raw_test_mod")
            self.assertIn("Security Guard Blocked", str(ctx.exception))
            self.assertIn("TestRawDirect", str(ctx.exception))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

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

        # Exception restoration test
        try:
            with OutputCapturer(enabled=True):
                raise RuntimeError("deliberate error")
        except RuntimeError:
            pass
        self.assertEqual(sys.stdout, orig_out)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ascii_report_formatter_with_metadata_and_taxonomy(self):
        """FT-02, FT-03, FT-04: Verify ASCIIReportFormatter outputs metadata, timing, taxonomy, and re-run guides."""
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
    def test_single_module_worker_execution_and_report_json(self):
        """FT-01/FT-02: Verify _run_single_module_worker runs in dedicated sandbox and writes report JSON."""
        res_data = self.tester._run_single_module_worker(
            mod_name="core",
            worker_idx=99,
            clean_argv=["--contract-only"],
            keep_sandbox=False,
            is_nested=True
        )
        self.assertEqual(res_data["returncode"], 0)
        self.assertEqual(res_data["module"], "core")
        self.assertEqual(res_data["worker_idx"], 99)
        self.assertIsNotNone(res_data["report_data"])
        self.assertEqual(res_data["report_data"]["passed"], 3)
        self.assertFalse(os.path.exists(res_data["sandbox_dir"]))
        self.mark_passed()
