"""
Comprehensive test suite for dev.testing.sandbox (SandboxProvisioner, SandboxContext, and VFS projection).
"""
import json
import os
import shutil
import tempfile
import threading
import zipfile
from unittest.mock import patch

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner, SandboxContext
from core import uri, vfs, events, PipManager


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
        """Verify dev op-mksb creates full micro virtual environment with core hook setup."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            self.assertTrue(os.path.isdir(ctx.sandbox_dir))
            self.assertTrue(os.path.isdir(ctx.project_dir))
            self.assertTrue(os.path.isdir(ctx.host_dir))
            self.assertTrue(os.path.isdir(ctx.engine_dir))
            self.assertTrue(os.path.isdir(ctx.provider_dir))

            host_cfg_file = os.path.join(ctx.host_dir, "yscb.config.json")
            self.assertTrue(os.path.isfile(host_cfg_file))
            with open(host_cfg_file, "r", encoding="utf-8") as f:
                h_data = json.load(f)
            self.assertEqual(h_data.get("yscb_root"), "./engine")

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
        """Verify VFS and URI resolution inside sandbox host_scope and yscb_scope."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):
                self.assertEqual(os.path.abspath(uri.resolve("yscb.host://")), os.path.abspath(ctx.host_dir))
                self.assertEqual(os.path.abspath(uri.resolve("yscb://")), os.path.abspath(ctx.engine_dir))
                self.assertEqual(
                    os.path.abspath(uri.resolve("module.source://core")),
                    os.path.abspath(os.path.join(ctx.engine_dir, "source", "core")),
                )
                self.assertEqual(
                    os.path.abspath(uri.resolve("module://core")),
                    os.path.abspath(os.path.join(ctx.engine_dir, ".modules", "core")),
                )
                self.assertTrue(vfs.exists("module.source://core/manifest.json"))
        finally:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_context_set_module_config(self):
        """Verify SandboxContext.set_module_config routes project vs local config files accurately."""
        sb_dir = self._mkdtemp()
        ctx = SandboxContext(sb_dir)
        proj_cfg_path = ctx.set_module_config("core", "config.project.json", {"project_root": "../proj"})
        local_cfg_path = ctx.set_module_config("core", "config.local.json", {"debug": True})
        named_local_path = ctx.set_module_config("server", "config.dev.local.json", {"port": 9000})

        self.assertEqual(
            os.path.abspath(proj_cfg_path),
            os.path.abspath(os.path.join(ctx.engine_dir, "config", "core", "config.project.json")),
        )
        self.assertEqual(
            os.path.abspath(local_cfg_path),
            os.path.abspath(os.path.join(ctx.engine_dir, ".config.local", "core", "config.local.json")),
        )
        self.assertEqual(
            os.path.abspath(named_local_path),
            os.path.abspath(os.path.join(ctx.engine_dir, ".config.local", "server", "config.dev.local.json")),
        )
        with open(proj_cfg_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"project_root": "../proj"})
        with open(local_cfg_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"debug": True})
        with open(named_local_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"port": 9000})
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dual_source_provider_resolution(self):
        """Verify mock provider package creation, CmdBags entrypoint, and multi-version index sorting."""
        pkg_dir_1 = self.create_mock_package("mock_demo_pkg", "1.0.0.0", deps={"core": ">=1.0.0.0"})
        pkg_dir_2 = self.create_mock_package("mock_demo_pkg", "1.2.0.0", deps={"core": ">=1.0.0.0"})
        try:
            self.assertTrue(os.path.isdir(pkg_dir_1))
            self.assertTrue(os.path.isdir(pkg_dir_2))
            manifest_file = os.path.join(pkg_dir_1, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_file))
            with open(manifest_file, "r", encoding="utf-8") as f:
                m = json.load(f)
            self.assertEqual(m["name"], "mock_demo_pkg")
            cli_file = os.path.join(pkg_dir_1, "scripts", "cli.py")
            with open(cli_file, "r", encoding="utf-8") as f:
                cli_content = f.read()
            self.assertIn("def hello(cmd_bags", cli_content)
            self.assertNotIn("def process(args", cli_content)

            idx_file = os.path.join(os.path.dirname(pkg_dir_1), "index.json")
            with open(idx_file, "r", encoding="utf-8") as f:
                idx_data = json.load(f)
            self.assertEqual(idx_data.get("versions"), ["1.0.0.0", "1.2.0.0"])
        finally:
            rel_mod = os.path.dirname(pkg_dir_1)
            if os.path.isdir(rel_mod):
                shutil.rmtree(rel_mod, ignore_errors=True)
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_dev_sandbox_hook_convergence(self):
        """Verify SandboxProvisioner dispatches on_test_setup via core.events.broadcast."""
        ctx = SandboxProvisioner.create_sandbox()
        try:
            flag_file = os.path.join(ctx.sandbox_dir, "setup_fired.flag")
            flag_file_escaped = flag_file.replace("\\", "/")
            mod_dir = os.path.join(ctx.engine_dir, "source", "mock_hook_mod", "scripts")
            os.makedirs(mod_dir, exist_ok=True)
            with open(os.path.join(mod_dir, "hook.dev.py"), "w", encoding="utf-8") as f:
                f.write(
                    f"def on_test_setup(context):\n"
                    f"    with open('{flag_file_escaped}', 'w') as f: f.write('OK')\n"
                    f"    return 'OK'\n"
                )

            scanned_roots = [
                os.path.join(ctx.engine_dir, "source"),
                os.path.join(ctx.engine_dir, ".modules"),
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
    def test_create_sandbox_rollback_on_failure_and_active_guard(self):
        """Verify create_sandbox rolls back allocated directory on failure and cleanup_sandbox guards active sandbox."""
        target_sb = os.path.join(self._mkdtemp(), "sandbox_rollback_test")
        with patch.object(
            SandboxProvisioner,
            "_provision_core_and_config",
            side_effect=RuntimeError("simulated provisioning error"),
        ):
            with self.assertRaises(RuntimeError):
                SandboxProvisioner.create_sandbox(target_dir=target_sb, copy_source=False)

        self.assertFalse(os.path.exists(target_sb))
        self.assertNotIn(os.path.abspath(target_sb), SandboxProvisioner._ACTIVE_SANDBOXES)

        # Active sandbox guardrail: when YSCB_SANDBOX_DIR matches target and is_harness_cleanup=False, do not delete
        guard_sb = os.path.join(self._mkdtemp(), "sandbox_active_guard")
        os.makedirs(os.path.join(guard_sb, "host_env", "engine"), exist_ok=True)
        old_sb_env = os.environ.get("YSCB_SANDBOX_DIR")
        try:
            os.environ["YSCB_SANDBOX_DIR"] = guard_sb
            res_guarded = SandboxProvisioner.cleanup_sandbox(guard_sb, force=True, is_harness_cleanup=False)
            self.assertTrue(res_guarded)
            self.assertTrue(os.path.isdir(guard_sb), "Active sandbox must not be deleted when is_harness_cleanup=False")

            res_harness = SandboxProvisioner.cleanup_sandbox(guard_sb, force=True, is_harness_cleanup=True)
            self.assertTrue(res_harness)
            self.assertFalse(os.path.exists(guard_sb), "Sandbox must be deleted when is_harness_cleanup=True")
        finally:
            if old_sb_env is not None:
                os.environ["YSCB_SANDBOX_DIR"] = old_sb_env
            else:
                os.environ.pop("YSCB_SANDBOX_DIR", None)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_prune_sandboxes_limit(self):
        """Verify prune_sandboxes deletes oldest sandboxes when total count exceeds max_keep."""
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
        """Verify cleanup_all_sandboxes deletes all sandbox_* directories."""
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
        """Verify prune_sandboxes and cleanup_all_sandboxes return 0 when no sandboxes exist."""
        empty_scope = os.path.join(self.sandbox_dir, "test_empty_scope")
        os.makedirs(empty_scope, exist_ok=True)
        cnt1 = SandboxProvisioner.prune_sandboxes(max_keep=3, sandbox_parent_dir=empty_scope)
        cnt2 = SandboxProvisioner.cleanup_all_sandboxes(sandbox_parent_dir=empty_scope)
        self.assertEqual(cnt1, 0)
        self.assertEqual(cnt2, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_cleanup_ignores_non_sandbox(self):
        """Verify cleanup_all_sandboxes does not delete non-sandbox directories."""
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
        """Verify adapt_build_pip_dependencies extracts specs from build zip and manifest."""
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
                "mock-pkg-b": "",
            },
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
        """Verify _project_venv symlink/junction projection, .pth fallback when symlink fails, and host venv protection."""
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

        cleaned = SandboxProvisioner.cleanup_sandbox(sb_dir, force=True, is_harness_cleanup=True)
        self.assertTrue(cleaned)
        self.assertFalse(os.path.exists(sb_dir))

        self.assertTrue(os.path.isdir(host_venv))
        self.assertTrue(os.path.isfile(canary_file))
        with open(canary_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "host_data_alive")

        # Verify .pth fallback when os.symlink / CreateJunction raises OSError
        sb_dir_pth = self._mkdtemp()
        sb_engine_pth = os.path.join(sb_dir_pth, "host_env", "engine")
        os.makedirs(sb_engine_pth, exist_ok=True)
        with patch("os.symlink", side_effect=OSError("symlink disabled")), \
             patch("platform.system", return_value="Linux"):
            res_pth = SandboxProvisioner._project_venv(host_dir, sb_engine_pth)
            self.assertTrue(res_pth)
            sb_site_pkg = PipManager(sb_engine_pth).get_site_packages_dir()
            pth_file = os.path.join(sb_site_pkg, "host_venv.pth")
            self.assertTrue(os.path.isfile(pth_file))
            with open(pth_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), PipManager(host_dir).get_site_packages_dir())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sort_zip_filenames_and_find_latest_build_zip(self):
        """Verify _sort_zip_filenames_by_semver handles invalid version fallback, tie-breaking, and _find_latest_build_zip."""
        filenames = [
            "invalid_ver.zip",
            "alpha.build.zip",
            "1.2.0.build.zip",
            "1.10.0.build.zip",
            "1.9.0.build.zip",
            "1.10.1.build.zip",
            "0.9.9.build.zip",
        ]
        sorted_fns = SandboxProvisioner._sort_zip_filenames_by_semver(filenames)
        expected = [
            "alpha.build.zip",
            "invalid_ver.zip",
            "0.9.9.build.zip",
            "1.2.0.build.zip",
            "1.9.0.build.zip",
            "1.10.0.build.zip",
            "1.10.1.build.zip",
        ]
        self.assertEqual(sorted_fns, expected)

        temp_build_root = self._mkdtemp()
        mod_build_dir = os.path.join(temp_build_root, "mock_ver_mod")
        os.makedirs(mod_build_dir, exist_ok=True)
        for fname in ("1.2.0.build.zip", "1.10.0.build.zip", "bad_ver.build.zip"):
            with open(os.path.join(mod_build_dir, fname), "wb") as f:
                f.write(b"PK")

        orig_exists = vfs.exists
        orig_resolve = uri.resolve
        with patch("core.vfs.exists", side_effect=lambda u: True if u == "module.build://" else orig_exists(u)), \
             patch("core.uri.resolve", side_effect=lambda u: temp_build_root if u == "module.build://" else orig_resolve(u)):
            latest = SandboxProvisioner._find_latest_build_zip("mock_ver_mod")
            self.assertIsNotNone(latest)
            self.assertEqual(os.path.basename(latest), "1.10.0.build.zip")
            self.assertIsNone(SandboxProvisioner._find_latest_build_zip("nonexistent_mod"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_deploy_modules_build_zip_skips_copytree_and_falls_back_on_corrupt_zip(self):
        """Verify valid .build.zip skips host copytree, and corrupt .build.zip falls back to host copytree."""
        fake_root = self._mkdtemp()
        fake_host_modules = os.path.join(fake_root, ".modules")
        fake_build_root = os.path.join(fake_root, ".build")
        os.makedirs(fake_host_modules, exist_ok=True)
        os.makedirs(fake_build_root, exist_ok=True)

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
            return False

        def mock_resolve(u: str) -> str:
            if u == "module://":
                return fake_host_modules
            if u == "module.build://":
                return fake_build_root
            return fake_root

        orig_copytree = shutil.copytree
        copied_srcs = []

        def tracking_copytree(src, dst, *args, **kwargs):
            copied_srcs.append(os.path.basename(src))
            return orig_copytree(src, dst, *args, **kwargs)

        with patch("core.vfs.exists", side_effect=mock_exists), \
             patch("core.uri.resolve", side_effect=mock_resolve), \
             patch("shutil.copytree", side_effect=tracking_copytree), \
             patch.dict(os.environ, {"YSCB_TEST_TARGET_MODULES": ""}):
            host_cfg = SandboxProvisioner._deploy_target_and_dependency_modules(ctx, copy_source=False)

        self.assertNotIn("mod_valid", copied_srcs)
        sb_valid_dir = os.path.join(ctx.engine_dir, ".modules", "mod_valid")
        self.assertTrue(os.path.isfile(os.path.join(sb_valid_dir, "from_build.txt")))
        self.assertFalse(os.path.exists(os.path.join(sb_valid_dir, "from_host.txt")))
        self.assertEqual(host_cfg["installed_modules"]["mod_valid"]["version"], "1.0.0.1")

        self.assertIn("mod_corrupt", copied_srcs)
        sb_corrupt_dir = os.path.join(ctx.engine_dir, ".modules", "mod_corrupt")
        self.assertTrue(os.path.isfile(os.path.join(sb_corrupt_dir, "fallback_ok.txt")))
        self.assertEqual(host_cfg["installed_modules"]["mod_corrupt"]["version"], "1.0.0.0")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cleanup_sandbox_releases_lock_before_teardown_and_rmtree(self):
        """Verify cleanup_sandbox does not hold _SANDBOX_LOCK during on_test_teardown broadcast or robust_rmtree."""
        sb_dir = self._mkdtemp()
        ctx = SandboxContext(sb_dir)
        for d in (ctx.sandbox_dir, ctx.project_dir, ctx.host_dir, ctx.engine_dir, ctx.provider_dir):
            os.makedirs(d, exist_ok=True)
        SandboxProvisioner._ACTIVE_SANDBOXES.add(os.path.abspath(sb_dir))

        lock_held_states = []

        def _is_lock_held_by_another_thread() -> bool:
            holder = []

            def _probe():
                acquired = SandboxProvisioner._SANDBOX_LOCK.acquire(blocking=False)
                if acquired:
                    SandboxProvisioner._SANDBOX_LOCK.release()
                holder.append(not acquired)

            t = threading.Thread(target=_probe)
            t.start()
            t.join(timeout=2.0)
            return holder[0] if holder else True

        def spy_broadcast(event_name, **kwargs):
            lock_held_states.append(("broadcast", _is_lock_held_by_another_thread()))
            return {}

        orig_rmtree = vfs.robust_rmtree

        def spy_rmtree(target_p, **kwargs):
            lock_held_states.append(("rmtree", _is_lock_held_by_another_thread()))
            return orig_rmtree(target_p, **kwargs)

        with patch("core.events.broadcast", side_effect=spy_broadcast), \
             patch("core.vfs.robust_rmtree", side_effect=spy_rmtree):
            ok = SandboxProvisioner.cleanup_sandbox(sb_dir, force=True, is_harness_cleanup=True)

        self.assertTrue(ok)
        self.assertNotIn(os.path.abspath(sb_dir), SandboxProvisioner._ACTIVE_SANDBOXES)
        self.assertEqual(lock_held_states, [("broadcast", False), ("rmtree", False)])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_deploy_modules_prunes_to_transitive_dependency_closure(self):
        """Verify _deploy_target_and_dependency_modules only deploys core, dev, target_modules, and their recursive dependencies."""
        fake_root = self._mkdtemp()
        fake_host_modules = os.path.join(fake_root, ".modules")
        fake_build_root = os.path.join(fake_root, ".build")
        os.makedirs(fake_host_modules, exist_ok=True)
        os.makedirs(fake_build_root, exist_ok=True)

        modules_spec = {
            "core": {"version": "1.0.0.0", "dependencies": {}},
            "dev": {"version": "1.0.0.0", "dependencies": {"core": ">=1.0.0"}},
            "mod_leaf": {"version": "1.0.0.0", "dependencies": {"core": ">=1.0.0"}},
            "mod_mid": {"version": "1.0.0.0", "dependencies": {"core": ">=1.0.0", "mod_leaf": ">=1.0.0"}},
            "mod_top": {"version": "1.0.0.0", "dependencies": ["core", "mod_mid"]},
            "mod_unrelated": {"version": "1.0.0.0", "dependencies": {"core": ">=1.0.0"}},
        }
        for m_name, mf in modules_spec.items():
            m_dir = os.path.join(fake_host_modules, m_name)
            os.makedirs(m_dir, exist_ok=True)
            with open(os.path.join(m_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": m_name, **mf}, f)

        for b_name in ("mod_top", "mod_unrelated"):
            b_dir = os.path.join(fake_build_root, b_name)
            os.makedirs(b_dir, exist_ok=True)
            with zipfile.ZipFile(os.path.join(b_dir, "1.0.0.build.zip"), "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": b_name, **modules_spec[b_name]}))

        def mock_exists(u: str) -> bool:
            return u in ("module://", "module.build://")

        def mock_resolve(u: str) -> str:
            if u == "module://":
                return fake_host_modules
            if u == "module.build://":
                return fake_build_root
            return fake_root

        sb_pruned = self._mkdtemp()
        ctx_pruned = SandboxContext(sb_pruned)
        for d in (ctx_pruned.sandbox_dir, ctx_pruned.project_dir, ctx_pruned.host_dir, ctx_pruned.engine_dir, ctx_pruned.provider_dir):
            os.makedirs(d, exist_ok=True)

        sb_env_inherited = self._mkdtemp()
        ctx_env = SandboxContext(sb_env_inherited)
        for d in (ctx_env.sandbox_dir, ctx_env.project_dir, ctx_env.host_dir, ctx_env.engine_dir, ctx_env.provider_dir):
            os.makedirs(d, exist_ok=True)

        with patch("core.vfs.exists", side_effect=mock_exists), \
             patch("core.uri.resolve", side_effect=mock_resolve):
            cfg_pruned = SandboxProvisioner._deploy_target_and_dependency_modules(
                ctx_pruned,
                copy_source=False,
                target_modules=["mod_top"],
            )
            with patch.dict(os.environ, {"YSCB_TEST_TARGET_MODULES": "mod_mid"}):
                cfg_env = SandboxProvisioner._deploy_target_and_dependency_modules(
                    ctx_env,
                    copy_source=False,
                    target_modules=None,
                )

        self.assertEqual(
            set(cfg_pruned["installed_modules"].keys()),
            {"core", "dev", "mod_top", "mod_mid", "mod_leaf"},
        )
        self.assertFalse(os.path.exists(os.path.join(ctx_pruned.engine_dir, ".modules", "mod_unrelated")))

        self.assertEqual(
            set(cfg_env["installed_modules"].keys()),
            {"core", "dev", "mod_mid", "mod_leaf"},
        )
        self.assertFalse(os.path.exists(os.path.join(ctx_env.engine_dir, ".modules", "mod_top")))
        self.assertFalse(os.path.exists(os.path.join(ctx_env.engine_dir, ".modules", "mod_unrelated")))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_cross_session_grandchild_and_sandbox_process_reaping(self):
        """Verify terminate_popen_tree and reap_sandbox_processes reap grandchildren across setsid() boundaries."""
        import subprocess
        import sys
        import time
        from core.platform.process import (
            is_process_alive,
            reap_sandbox_processes,
            terminate_popen_tree,
        )

        sb_dir = self._mkdtemp()
        pid_file = os.path.join(sb_dir, "grandchild.pid")
        code = (
            "import os, subprocess, sys, time; "
            "kw = {'start_new_session': True} if sys.platform != 'win32' else {}; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kw); "
            f"open({pid_file!r}, 'w').write(str(p.pid)); "
            "time.sleep(60)"
        )
        popen_kw = {"start_new_session": True} if sys.platform != "win32" else {}
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=sb_dir, **popen_kw)
        grandchild_pid = 0
        try:
            for _ in range(40):
                if os.path.isfile(pid_file):
                    raw = open(pid_file, "r", encoding="utf-8").read().strip()
                    if raw.isdigit():
                        grandchild_pid = int(raw)
                        break
                time.sleep(0.05)
            self.assertGreater(grandchild_pid, 0)
            self.assertTrue(is_process_alive(grandchild_pid))

            terminate_popen_tree(proc, timeout_sec=1.5)
            reap_sandbox_processes(sb_dir, timeout_sec=1.0)
            for _ in range(20):
                if not is_process_alive(grandchild_pid):
                    break
                time.sleep(0.05)
            self.assertFalse(
                is_process_alive(grandchild_pid),
                "Grandchild in new session must be reaped by terminate_popen_tree / reap_sandbox_processes",
            )
        finally:
            if proc.poll() is None:
                terminate_popen_tree(proc, timeout_sec=1.0)
        self.mark_passed()
