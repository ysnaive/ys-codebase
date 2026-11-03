"""
Comprehensive test suite for dev.testing.sandbox (SandboxProvisioner, SandboxContext, and VFS projection).
"""
import os
import sys
import json
import shutil
import tempfile
import zipfile
import unittest
from unittest.mock import patch

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner, SandboxContext
from core import uri, vfs, PipManager


class TestSandboxArchitecture(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dirs = []

    def tearDown(self):
        super().tearDown()
        for d in self.temp_dirs:
            if os.path.lexists(d):
                try:
                    if os.path.islink(d):
                        os.unlink(d)
                    else:
                        shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

    def _mkdtemp(self) -> str:
        d = tempfile.mkdtemp()
        self.temp_dirs.append(d)
        return d

    @require(Requirement.WORKFLOW)
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

    @require(Requirement.ENV)
    def test_sandbox_vfs_natural_constant_self_locating(self):
        """FT-02: Verify constant self-locating operates deterministically in sandbox without code hacks."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            sandbox_uri_file = os.path.join(ctx.engine_dir, "source", "core", "core", "uri.py")
            curr = os.path.dirname(sandbox_uri_file)
            calc_root = os.path.dirname(os.path.dirname(os.path.dirname(curr)))
            self.assertEqual(os.path.abspath(calc_root), os.path.abspath(ctx.engine_dir))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dual_source_provider_resolution(self):
        """FT-05: Verify mock provider package creation, CmdBags entrypoint, and index tracking."""
        pkg_dir = self.create_mock_package("mock_demo_pkg", "1.0.0.0", deps={"core": ">=1.0.0.0"})
        try:
            self.assertTrue(os.path.isdir(pkg_dir))
            manifest_file = os.path.join(pkg_dir, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_file))
            with open(manifest_file, "r", encoding="utf-8") as f:
                m = json.load(f)
            self.assertEqual(m["name"], "mock_demo_pkg")
            cli_file = os.path.join(pkg_dir, "scripts", "cli.py")
            with open(cli_file, "r", encoding="utf-8") as f:
                cli_content = f.read()
            self.assertIn("def hello(cmd_bags", cli_content)
            self.assertNotIn("def process(args", cli_content)
        finally:
            rel_mod = os.path.dirname(pkg_dir)
            if os.path.isdir(rel_mod):
                shutil.rmtree(rel_mod, ignore_errors=True)
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_dev_sandbox_hook_convergence(self):
        """FT-06: Verify SandboxProvisioner dispatches on_test_setup via core.events.broadcast."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            flag_file = os.path.join(ctx.sandbox_dir, "setup_fired.flag")
            flag_file_escaped = flag_file.replace("\\", "/")
            mod_dir = os.path.join(ctx.engine_dir, "source", "mock_hook_mod", "scripts")
            os.makedirs(mod_dir, exist_ok=True)
            with open(os.path.join(mod_dir, "hook.dev.py"), "w", encoding="utf-8") as f:
                f.write(f"def on_test_setup(context):\n    with open('{flag_file_escaped}', 'w') as f: f.write('OK')\n    return 'OK'\n")
            
            from core import events, uri
            scanned_roots = [
                os.path.join(ctx.engine_dir, "source"),
                os.path.join(ctx.engine_dir, ".modules")
            ]
            with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):
                res = events.broadcast("on_test_setup", context=ctx, emit_module="dev", search_roots=scanned_roots)
            self.assertEqual(res.get("mock_hook_mod"), "OK")
            self.assertTrue(os.path.isfile(flag_file))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_third_party_host_module_inheritance(self):
        """Verify sandbox inherits installed host modules when not present in source/ and dispatches their hooks."""
        ctx = SandboxProvisioner.create_sandbox(copy_source=False)
        try:
            sandbox_core_mod = os.path.join(ctx.engine_dir, ".modules", "core")
            self.assertTrue(os.path.isdir(sandbox_core_mod))
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

            self.assertFalse(os.path.exists(created_dirs[0]))
            self.assertFalse(os.path.exists(created_dirs[1]))
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
                shutil.rmtree(non_sandbox_dir)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_adapt_build_pip_dependencies(self):
        """FT-07: Verify adapt_build_pip_dependencies extracts specs from build zip and manifest."""
        temp_dir = self._mkdtemp()
        mod_name = "test_pip_mod"
        build_mod_dir = os.path.join(temp_dir, mod_name)
        os.makedirs(build_mod_dir, exist_ok=True)

        manifest_data = {
            "name": mod_name,
            "version": "1.0.0.0",
            "entry": "scripts/cli.py",
            "dependencies": ["core"],
            "pip_dependencies": {
                "mock-pkg-a": ">=1.0.0",
                "mock-pkg-b": ""
            }
        }
        zip_path = os.path.join(build_mod_dir, "1.0.0.build.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))

        orig_exists = vfs.exists
        orig_resolve = uri.resolve

        def mock_exists(u: str) -> bool:
            if u == "module.build://":
                return True
            return orig_exists(u)

        def mock_resolve(u: str) -> str:
            if u == "module.build://":
                return temp_dir
            return orig_resolve(u)

        saved_adapted = set(SandboxProvisioner._ADAPTED_SPECS)
        try:
            SandboxProvisioner._ADAPTED_SPECS.clear()
            with patch("core.vfs.exists", side_effect=mock_exists), \
                 patch("core.uri.resolve", side_effect=mock_resolve), \
                 patch.object(PipManager, "install_packages") as mock_install:

                specs = SandboxProvisioner.adapt_build_pip_dependencies(target_modules=[mod_name])
                self.assertEqual(specs, ["mock-pkg-a>=1.0.0", "mock-pkg-b"])
                mock_install.assert_called_once_with(["mock-pkg-a>=1.0.0", "mock-pkg-b"])

                empty_specs = SandboxProvisioner.adapt_build_pip_dependencies(target_modules=["non_existent"])
                self.assertEqual(empty_specs, [])
        finally:
            SandboxProvisioner._ADAPTED_SPECS = saved_adapted

        self.mark_passed()

    @require(Requirement.ENV)
    def test_sandbox_venv_projection_and_cleanup(self):
        """FT-08: Verify _project_venv creates projection and cleanup_sandbox protects host venv."""
        host_dir = self._mkdtemp()
        host_venv = os.path.join(host_dir, ".venv")
        os.makedirs(host_venv, exist_ok=True)
        canary_file = os.path.join(host_venv, "canary_host.txt")
        with open(canary_file, "w", encoding="utf-8") as f:
            f.write("host_data_alive")

        sb_dir = self._mkdtemp()
        sb_host = os.path.join(sb_dir, "host_env")
        sb_engine = os.path.join(sb_host, "engine")
        os.makedirs(sb_engine, exist_ok=True)

        res = SandboxProvisioner._project_venv(host_dir, sb_engine)
        self.assertTrue(res)

        sb_venv = os.path.join(sb_engine, ".venv")
        self.assertTrue(os.path.exists(sb_venv))

        cleaned = SandboxProvisioner.cleanup_sandbox(sb_dir, force=True)
        self.assertTrue(cleaned)
        self.assertFalse(os.path.exists(sb_dir))

        self.assertTrue(os.path.isdir(host_venv))
        self.assertTrue(os.path.isfile(canary_file))
        with open(canary_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "host_data_alive")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sort_zip_filenames_by_semver_and_bad_zip(self):
        """FR-06, EC-07: Verify _sort_zip_filenames_by_semver sorts multi-digit versions and handles bad zips."""
        filenames = [
            "1.2.0.build.zip",
            "1.10.0.build.zip",
            "1.9.0.build.zip",
            "1.10.1.build.zip",
            "0.9.9.build.zip"
        ]
        sorted_fns = SandboxProvisioner._sort_zip_filenames_by_semver(filenames)
        expected = [
            "0.9.9.build.zip",
            "1.2.0.build.zip",
            "1.9.0.build.zip",
            "1.10.0.build.zip",
            "1.10.1.build.zip"
        ]
        self.assertEqual(sorted_fns, expected)
        self.assertEqual(sorted_fns[-1], "1.10.1.build.zip")

        # Test corrupt zip handling during sandbox extraction
        temp_dir = self._mkdtemp()
        bad_zip = os.path.join(temp_dir, "corrupt.build.zip")
        with open(bad_zip, "w") as f:
            f.write("not a zip file content")

        with self.assertRaises(zipfile.BadZipFile):
            with zipfile.ZipFile(bad_zip, "r") as zf:
                zf.namelist()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_deploy_modules_build_zip_skips_copytree_and_falls_back_on_corrupt_zip(self):
        """FR-07, EC-06: Verify valid .build.zip skips host copytree, and corrupt .build.zip falls back to host copytree."""
        fake_root = self._mkdtemp()
        fake_host_modules = os.path.join(fake_root, ".modules")
        fake_build_root = os.path.join(fake_root, ".build")
        os.makedirs(fake_host_modules, exist_ok=True)
        os.makedirs(fake_build_root, exist_ok=True)

        # Module 'mod_valid' has both host .modules/mod_valid and valid .build/mod_valid/1.0.0.build.zip
        host_mod_valid = os.path.join(fake_host_modules, "mod_valid")
        os.makedirs(host_mod_valid, exist_ok=True)
        with open(os.path.join(host_mod_valid, "from_host.txt"), "w", encoding="utf-8") as f:
            f.write("host_version")

        build_mod_valid = os.path.join(fake_build_root, "mod_valid")
        os.makedirs(build_mod_valid, exist_ok=True)
        valid_zip = os.path.join(build_mod_valid, "1.0.0.build.zip")
        with zipfile.ZipFile(valid_zip, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "mod_valid", "version": "1.0.0.1"}))
            zf.writestr("from_build.txt", "build_version")

        # Module 'mod_corrupt' has both host .modules/mod_corrupt and a corrupted .build/mod_corrupt/1.0.0.build.zip
        host_mod_corrupt = os.path.join(fake_host_modules, "mod_corrupt")
        os.makedirs(host_mod_corrupt, exist_ok=True)
        with open(os.path.join(host_mod_corrupt, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "mod_corrupt", "version": "1.0.0.0"}, f)
        with open(os.path.join(host_mod_corrupt, "fallback_ok.txt"), "w", encoding="utf-8") as f:
            f.write("recovered_from_host")

        build_mod_corrupt = os.path.join(fake_build_root, "mod_corrupt")
        os.makedirs(build_mod_corrupt, exist_ok=True)
        corrupt_zip = os.path.join(build_mod_corrupt, "1.0.0.build.zip")
        with open(corrupt_zip, "w", encoding="utf-8") as f:
            f.write("CORRUPT_ZIP_PAYLOAD")

        sb_dir = self._mkdtemp()
        ctx = SandboxContext(sb_dir)
        for d in (ctx.sandbox_dir, ctx.project_dir, ctx.host_dir, ctx.engine_dir, ctx.provider_dir):
            os.makedirs(d, exist_ok=True)

        def mock_exists(u: str) -> bool:
            if u in ("module://", "module.build://"):
                return True
            if u == "module.source://":
                return False
            return False

        def mock_resolve(u: str) -> str:
            if u == "module://":
                return fake_host_modules
            if u == "module.build://":
                return fake_build_root
            if u == "yscb://":
                return fake_root
            return fake_root

        orig_copytree = shutil.copytree
        copied_srcs = []

        def tracking_copytree(src, dst, *args, **kwargs):
            copied_srcs.append(os.path.basename(src))
            return orig_copytree(src, dst, *args, **kwargs)

        with patch("core.vfs.exists", side_effect=mock_exists), \
             patch("core.uri.resolve", side_effect=mock_resolve), \
             patch("shutil.copytree", side_effect=tracking_copytree):
            host_cfg = SandboxProvisioner._deploy_target_and_dependency_modules(ctx, copy_source=False)

        # 1. 'mod_valid' was extracted from .build.zip and NEVER passed to shutil.copytree
        self.assertNotIn("mod_valid", copied_srcs)
        sb_valid_dir = os.path.join(ctx.engine_dir, ".modules", "mod_valid")
        self.assertTrue(os.path.isfile(os.path.join(sb_valid_dir, "from_build.txt")))
        self.assertFalse(os.path.exists(os.path.join(sb_valid_dir, "from_host.txt")))
        self.assertEqual(host_cfg["installed_modules"]["mod_valid"]["version"], "1.0.0.1")

        # 2. EC-06: 'mod_corrupt' failed zip extraction, cleaned up empty dir, and fell back to shutil.copytree
        self.assertIn("mod_corrupt", copied_srcs)
        sb_corrupt_dir = os.path.join(ctx.engine_dir, ".modules", "mod_corrupt")
        self.assertTrue(os.path.isfile(os.path.join(sb_corrupt_dir, "fallback_ok.txt")))
        self.assertEqual(host_cfg["installed_modules"]["mod_corrupt"]["version"], "1.0.0.0")
        self.mark_passed()

