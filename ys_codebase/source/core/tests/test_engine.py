"""
Official test suite for core.engine.AtomicEngine.
"""
import copy
import errno
import io
import json
import os
import shutil
import sys
import time
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from dev.testing import YSCBTestCase, require, Requirement
from core.engine import AtomicEngine, _parse_dependencies, _deep_infill_dict, _atomic_swap_dir
from core.installer import Installer
from core.uri import ExecutionContext, CyclicURIDependencyError
from core import uri, vfs, gitignore
from core.context import bind_runtime_context, bind_cell_context, get_runtime_context
from core.service_contract import BaseServiceWorkerContract, touch_activity
from core.validator import ContributesValidator
from core.platform.lock import InterProcessLock
from core.commands import dispatcher
from core.commands.bags import CmdBags, CmdOption
from core.commands.contributes_cmd import check_contributes
from core.space.registry import SpaceRegistry
from core.space.scanner import SpaceScanner
from tests import create_provider_release_zip, load_core_cli_module


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreEngine(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()

    def test_host_config_isolation_from_project_uri(self):
        """Verify host config and snapshot operations succeed even when project:// is undefined."""
        core_cfg = "config://core/config.project.json"
        saved = None
        if vfs.exists(core_cfg):
            saved = vfs.read_json(core_cfg)
            vfs.remove(core_cfg)

        snap_id = None
        try:
            with self.assertRaises(ValueError):
                uri.resolve("project://yscb.config.json")

            cfg_path, cfg = self.engine._get_config()
            self.assertTrue(os.path.isfile(cfg_path))
            self.assertIn("installed_modules", cfg)

            snap_id = self.engine.act_snapshot("isolation_test_snap")
            self.assertTrue(vfs.exists(f"snapshot://{snap_id}/yscb.config.json"))
            self.engine.act_restore_snapshot(snap_id)
        finally:
            if snap_id and vfs.exists(f"snapshot://{snap_id}"):
                vfs.rmtree(f"snapshot://{snap_id}", ignore_errors=True)
            if saved is not None:
                vfs.write_json(core_cfg, saved, indent=2)
        self.mark_passed()

    def test_manifest_dependencies_schema_compatibility(self):
        """Verify _parse_dependencies supports both dict and list schemas."""
        dict_deps = {"core": ">=1.0.0", "dev": "^1.2.0"}
        parsed_dict = _parse_dependencies(dict_deps)
        self.assertEqual(parsed_dict["core"], ">=1.0.0")
        self.assertEqual(parsed_dict["dev"], "^1.2.0")

        list_deps = ["core >=1.0.0", "helper ^0.5.0", "standalone"]
        parsed_list = _parse_dependencies(list_deps)
        self.assertEqual(parsed_list["core"], ">=1.0.0")
        self.assertEqual(parsed_list["helper"], "^0.5.0")
        self.assertEqual(parsed_list["standalone"], "*")
        self.mark_passed()

    def test_act_solve_deps_recursive_and_cycle_guard(self):
        """Verify act_solve_deps solves recursive topology and catches circular dependencies."""
        provider_dir = os.path.join(self.sandbox_dir, "mock_provider")
        os.makedirs(provider_dir, exist_ok=True)

        mod_c_dir = os.path.join(provider_dir, "mod_c", "1.0.0")
        os.makedirs(mod_c_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {}})

        mod_b_dir = os.path.join(provider_dir, "mod_b", "1.0.0")
        os.makedirs(mod_b_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_b_dir, "manifest.json"), {"name": "mod_b", "version": "1.0.0", "dependencies": {"mod_c": ">=1.0.0"}})

        mod_a_dir = os.path.join(provider_dir, "mod_a", "1.0.0")
        os.makedirs(mod_a_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_a_dir, "manifest.json"), {"name": "mod_a", "version": "1.0.0", "dependencies": {"mod_b": ">=1.0.0"}})

        order = self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        names = [m[0] for m in order]
        self.assertEqual(names, ["mod_c", "mod_b", "mod_a"])

        vfs.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {"mod_a": ">=1.0.0"}})
        with self.assertRaises(ValueError) as ctx:
            self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        self.assertIn("Circular dependency detected", str(ctx.exception))
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_snapshot_and_restore(self):
        """Verify snapshot creation and disaster recovery rollback."""
        _, orig_cfg = self.engine._get_config()
        snap_id = self.engine.act_snapshot("unit_test_snap")
        try:
            self.assertTrue(vfs.exists(f"snapshot://{snap_id}/yscb.config.json"))

            snap_cfg = vfs.read_json(f"snapshot://{snap_id}/yscb.config.json")
            self.assertEqual(snap_cfg.get("yscb_root"), orig_cfg.get("yscb_root"))

            self.engine.act_restore_snapshot(snap_id)
            _, restored_cfg = self.engine._get_config()
            self.assertEqual(restored_cfg, orig_cfg)
        finally:
            if vfs.exists(f"snapshot://{snap_id}"):
                vfs.rmtree(f"snapshot://{snap_id}", ignore_errors=True)
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_inter_process_lock_and_auto_healing(self):
        """Verify process lock exclusivity, Inode preservation on unlock, and stale lock auto-healing."""
        self.engine.act_unlock("test_op")
        try:
            self.engine.act_lock("test_op")
            self.assertTrue(vfs.exists("cache://.yscb.lock"))
            lock_p = uri.resolve("cache://.yscb.lock")
            inode_before = os.stat(lock_p).st_ino

            with self.assertRaises(BlockingIOError):
                self.engine.act_lock("test_op_2", timeout=10.0)

            self.engine.act_unlock("test_op")
            self.assertTrue(vfs.exists("cache://.yscb.lock"))
            self.assertEqual(os.stat(lock_p).st_ino, inode_before)
            probe_lk = InterProcessLock(lock_p, reentrant=False)
            self.assertTrue(probe_lk.acquire(blocking=False, reentrant=False))
            probe_lk.release()

            self.engine.act_lock("stale_op")
            past_ts = time.time() - 30.0
            os.utime(lock_p, (past_ts, past_ts))
            self.engine.act_lock("new_op", timeout=10.0)
            self.engine.act_unlock("new_op")
        finally:
            for op_name in ("test_op", "stale_op", "new_op"):
                self.engine.act_unlock(op_name)
        self.mark_passed()

    def test_seed_and_infill_config(self):
        """Verify default config seeding and recursive in-fill preserving user values."""
        tpl_dir = f"{self.sandbox_uri}/tpl_mod"
        vfs.makedirs(tpl_dir)
        initial_tpl = {
            "setting_a": "default_a",
            "nested": {
                "sub_1": "default_sub1"
            }
        }
        vfs.write_json(f"{tpl_dir}/config.project.json", initial_tpl)

        target_cfg_uri = "config://mod_test_cfg/config.project.json"
        try:
            self.engine._deploy_and_strip_single_module_config("mod_test_cfg", uri.resolve(tpl_dir))
            self.assertTrue(vfs.exists(target_cfg_uri))
            self.assertEqual(vfs.read_json(target_cfg_uri), initial_tpl)

            user_mod = {
                "setting_a": "user_custom_value",
                "nested": {
                    "sub_1": "user_custom_sub1"
                }
            }
            vfs.write_json(target_cfg_uri, user_mod)

            new_tpl = {
                "setting_a": "default_a",
                "setting_b": "new_default_b",
                "nested": {
                    "sub_1": "default_sub1",
                    "sub_2": "new_default_sub2"
                }
            }
            vfs.write_json(f"{tpl_dir}/config.project.json", new_tpl)

            self.engine._deploy_and_strip_single_module_config("mod_test_cfg", tpl_dir)
            final_cfg = vfs.read_json(target_cfg_uri)

            self.assertEqual(final_cfg["setting_a"], "user_custom_value")
            self.assertEqual(final_cfg["nested"]["sub_1"], "user_custom_sub1")
            self.assertEqual(final_cfg["setting_b"], "new_default_b")
            self.assertEqual(final_cfg["nested"]["sub_2"], "new_default_sub2")
        finally:
            if vfs.exists("config://mod_test_cfg"):
                vfs.rmtree("config://mod_test_cfg", ignore_errors=True)
        self.mark_passed()

    def test_download_missing_package_raises_not_found(self):
        """Verify provider missing package raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.engine.act_download("non_existent_pkg_xyz", "9.9.9", "invalid_provider_path")
        self.mark_passed()

    def test_download_build_revision_special_case(self):
        """Verify requesting build revision downloads directly from module.build://."""
        build_dir = "module.build://mock_build_pkg"
        try:
            vfs.makedirs(build_dir)
            b_zip_uri = f"{build_dir}/1.0.0.build.zip"
            with zipfile.ZipFile(uri.resolve(b_zip_uri), "w") as zf:
                zf.writestr("manifest.json", '{"name": "mock_build_pkg", "version": "1.0.0.build", "entry": "scripts/cli.py"}')
                zf.writestr("scripts/cli.py", 'print("build hello")')

            dl_uri = self.engine.act_download("mock_build_pkg", "build", "non_existent_provider_path")
            self.assertTrue(vfs.exists(dl_uri))
            self.assertTrue(vfs.exists("module.mirror://mock_build_pkg/build.zip"))
        finally:
            if vfs.exists(build_dir):
                vfs.rmtree(build_dir, ignore_errors=True)
            if vfs.exists("module.mirror://mock_build_pkg"):
                vfs.rmtree("module.mirror://mock_build_pkg", ignore_errors=True)
        self.mark_passed()

    def test_download_build_revision_not_found_raises(self):
        """Verify requesting build revision with missing package raises FileNotFoundError with build guidance."""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.engine.act_download("non_existent_build_mod", "build", "non_existent_prov")
        self.assertIn("Build package not found", str(ctx.exception))
        self.assertIn("dev build", str(ctx.exception))
        self.mark_passed()

    def test_deploy_configurable_templates(self):
        """Verify act_deploy_configs_from_modules deploys from configurable/ and cleans up."""
        mod_dir = "module://mock_deploy_mod"
        cfg_tpl_dir = f"{mod_dir}/configurable"
        try:
            vfs.makedirs(cfg_tpl_dir, exist_ok=True)
            vfs.write_json(f"{cfg_tpl_dir}/config.project.json", {"proj_key": "val1"})
            vfs.write_json(f"{cfg_tpl_dir}/config.local.json", {"local_key": "val2"})
            vfs.write_json(f"{cfg_tpl_dir}/contribute.json", {"spaces": {"sp1": {}}})

            self.engine.act_register("mock_deploy_mod", "1.0.0.0", "mock_prov")
            self.engine.act_deploy_configs_from_modules()

            self.assertTrue(vfs.exists("config://mock_deploy_mod/config.project.json"))
            self.assertTrue(vfs.exists("config.local://mock_deploy_mod/config.local.json"))
            self.assertTrue(vfs.exists("config://mock_deploy_mod/contribute.json"))
            self.assertEqual(vfs.read_json("config://mock_deploy_mod/config.project.json")["proj_key"], "val1")

            self.assertFalse(vfs.exists(cfg_tpl_dir))
        finally:
            self.engine.act_unregister("mock_deploy_mod")
            for u in (mod_dir, "config://mock_deploy_mod", "config.local://mock_deploy_mod"):
                if vfs.exists(u):
                    vfs.rmtree(u, ignore_errors=True)
        self.mark_passed()

    def test_local_config_infill_skips_project_keys(self):
        """驗證 local 層級軟合併時，若 project 已有對應設定則自動跳過。"""
        base = {"existing_local": "val_local"}
        template = {
            "existing_local": "def_local",
            "in_proj": "def_in_proj",
            "only_local": "def_only_local",
            "nested": {
                "sub_proj": 1,
                "sub_local": 2,
            },
        }
        project_data = {
            "in_proj": "custom_proj",
            "nested": {
                "sub_proj": 99,
            },
        }

        result, changed = _deep_infill_dict(base, template, project_data=project_data)
        self.assertTrue(changed)
        self.assertEqual(result["existing_local"], "val_local")
        self.assertNotIn("in_proj", result)
        self.assertEqual(result["only_local"], "def_only_local")
        self.assertNotIn("sub_proj", result["nested"])
        self.assertEqual(result["nested"]["sub_local"], 2)

        mod_dir = "module://mock_deploy_infill"
        cfg_tpl_dir = f"{mod_dir}/configurable"
        try:
            vfs.makedirs(cfg_tpl_dir, exist_ok=True)
            vfs.write_json(f"{cfg_tpl_dir}/config.project.json", {"shared_key": "proj_val", "override_me": "from_proj"})
            vfs.write_json(f"{cfg_tpl_dir}/config.local.json", {"local_only": "loc_val", "override_me": "from_loc_tpl"})

            self.engine.act_register("mock_deploy_infill", "1.0.0.0", "mock_prov")
            self.engine.act_deploy_configs_from_modules()

            deployed_proj = vfs.read_json("config://mock_deploy_infill/config.project.json")
            deployed_local = vfs.read_json("config.local://mock_deploy_infill/config.local.json")

            self.assertEqual(deployed_proj.get("override_me"), "from_proj")
            self.assertEqual(deployed_local.get("local_only"), "loc_val")
            self.assertNotIn("override_me", deployed_local)
        finally:
            self.engine.act_unregister("mock_deploy_infill")
            for u in (mod_dir, "config://mock_deploy_infill", "config.local://mock_deploy_infill"):
                if vfs.exists(u):
                    vfs.rmtree(u, ignore_errors=True)
        self.mark_passed()

    def test_dual_layer_snapshot_and_execution_context_immutability(self):
        """驗證雙層快照完整還原（含 storage.local:// 備份與殘留清除）與 ExecutionContext 屬性不可變性。"""
        ctx = ExecutionContext("core", "test_cmd", ["arg1"], {"key": "val"})
        self.assertEqual(ctx.module_name, "core")
        self.assertEqual(ctx.command, "test_cmd")
        with self.assertRaises(Exception):
            ctx.module_name = "mutated"

        cfg_p = "config://core/config.project.json"
        cfg_loc_test = "config.local://test_snap_mod/config.local.json"
        stg_loc_test = "storage.local://test_snap_mod/heavy_index.bin"
        cache_test = "cache://test_snap_mod/ephemeral.tmp"
        vfs.makedirs("config.local://test_snap_mod", exist_ok=True)
        vfs.makedirs("storage.local://test_snap_mod", exist_ok=True)
        vfs.makedirs("cache://test_snap_mod", exist_ok=True)
        vfs.write_json(cfg_loc_test, {"local_secret": "orig_secret"})
        vfs.write_text(stg_loc_test, "PERSISTENT_LOCAL_MODEL")
        vfs.write_text(cache_test, "EPHEMERAL_CACHE")

        orig_p = vfs.read_json(cfg_p) if vfs.exists(cfg_p) else {}
        snap_id = self.engine.act_snapshot("test_dual_snap")
        try:
            self.assertTrue(vfs.exists(f"snapshot://{snap_id}/config.local/test_snap_mod/config.local.json"))
            self.assertTrue(vfs.exists(f"snapshot://{snap_id}/storage.local/test_snap_mod/heavy_index.bin"))
            self.assertFalse(vfs.exists(f"snapshot://{snap_id}/cache"))

            vfs.write_json(cfg_p, {"project_root": "mutated_val"})
            vfs.write_json(cfg_loc_test, {"local_secret": "mutated_secret"})
            vfs.write_text(stg_loc_test, "MUTATED_LOCAL_MODEL")
            self.assertEqual(vfs.read_json(cfg_p).get("project_root"), "mutated_val")
            self.assertEqual(vfs.read_json(cfg_loc_test).get("local_secret"), "mutated_secret")
            self.engine.act_restore_snapshot(snap_id)
            restored_p = vfs.read_json(cfg_p)
            self.assertEqual(restored_p.get("project_root"), orig_p.get("project_root"))
            self.assertEqual(vfs.read_json(cfg_loc_test).get("local_secret"), "orig_secret")
            self.assertEqual(vfs.read_text(stg_loc_test), "PERSISTENT_LOCAL_MODEL")

            vfs.rmtree(f"snapshot://{snap_id}/config.local", ignore_errors=True)
            vfs.rmtree(f"snapshot://{snap_id}/storage.local", ignore_errors=True)
            vfs.write_json("config.local://test_snap_mod/dirty_after_snap.json", {"dirty": True})
            vfs.write_text("storage.local://test_snap_mod/dirty_after_snap.bin", "dirty")
            self.engine.act_restore_snapshot(snap_id)
            self.assertTrue(vfs.is_dir("config.local://"))
            self.assertFalse(vfs.exists("config.local://test_snap_mod/dirty_after_snap.json"))
            self.assertTrue(vfs.is_dir("storage.local://"))
            self.assertFalse(vfs.exists("storage.local://test_snap_mod/dirty_after_snap.bin"))
        finally:
            if orig_p:
                vfs.write_json(cfg_p, orig_p)
            vfs.rmtree("config.local://test_snap_mod", ignore_errors=True)
            vfs.rmtree("storage.local://test_snap_mod", ignore_errors=True)
            vfs.rmtree("cache://test_snap_mod", ignore_errors=True)
            vfs.rmtree(f"snapshot://{snap_id}", ignore_errors=True)

        self.mark_passed()

    def test_act_delete_purge_and_multi_segment_act_migrate(self):
        """驗證 act_delete(purge=True) 物理清理四大持久化空間，以及 act_migrate 多維度遷移階梯 (minor/patch/revision)。"""
        mod = "test_purge_mig_mod"
        for scheme in ("storage", "storage.local", "config", "config.local", "cache"):
            vfs.makedirs(f"{scheme}://{mod}", exist_ok=True)
            vfs.write_text(f"{scheme}://{mod}/marker.txt", scheme)

        self.engine.act_delete(mod, clean_mirror=False, purge=False)
        self.assertFalse(vfs.exists(f"cache://{mod}/marker.txt"))
        for scheme in ("storage", "storage.local", "config", "config.local"):
            self.assertTrue(vfs.exists(f"{scheme}://{mod}/marker.txt"))

        self.engine.act_delete(mod, clean_mirror=False, purge=True)
        for scheme in ("storage", "storage.local", "config", "config.local"):
            self.assertFalse(vfs.exists(f"{scheme}://{mod}"))

        mig_dir = f"module://{mod}/scripts/migrations"
        vfs.makedirs(mig_dir, exist_ok=True)
        log_uri = f"storage.local://{mod}/mig_order.json"
        for script_name, tag in (
            ("1.2.x.py", "1.2.x"),
            ("1.2.6.x.py", "1.2.6.x"),
            ("1.2.7.x.py", "1.2.7.x"),
            ("1.2.7.1.py", "1.2.7.1"),
            ("1.3.x.py", "1.3.x"),
        ):
            code = (
                "import json, os\n"
                "def migrate(context):\n"
                "    d = context['storage_local_dir']\n"
                "    os.makedirs(d, exist_ok=True)\n"
                "    p = os.path.join(d, 'mig_order.json')\n"
                "    if os.path.exists(p):\n"
                "        with open(p, 'r', encoding='utf-8') as f:\n"
                "            arr = json.load(f)\n"
                "    else:\n"
                "        arr = []\n"
                f"    arr.append('{tag}')\n"
                "    with open(p, 'w', encoding='utf-8') as f:\n"
                "        json.dump(arr, f)\n"
                "    return True\n"
            )
            vfs.write_text(f"{mig_dir}/{script_name}", code)

        try:
            self.assertTrue(self.engine.act_migrate(mod, "1.2.6.build", "1.2.6.build"))
            self.assertTrue(self.engine.act_migrate(mod, "1.2.7.build", "1.2.7.0"))
            self.assertFalse(vfs.exists(log_uri))

            self.assertTrue(self.engine.act_migrate(mod, "1.2.6.build", "1.2.7.build"))
            self.assertEqual(vfs.read_json(log_uri), ["1.2.7.x"])
            vfs.remove(log_uri)

            self.assertTrue(self.engine.act_migrate(mod, "1.2.6.build", "1.2.7.0"))
            self.assertEqual(vfs.read_json(log_uri), ["1.2.7.x"])
            vfs.remove(log_uri)

            ok = self.engine.act_migrate(mod, "1.2.6.0", "1.2.7.1")
            self.assertTrue(ok)
            self.assertEqual(vfs.read_json(log_uri), ["1.2.7.x", "1.2.7.1"])
        finally:
            vfs.rmtree(f"module://{mod}", ignore_errors=True)
            vfs.rmtree(f"storage.local://{mod}", ignore_errors=True)
        self.mark_passed()

    def test_atomic_swap_dir_cleans_stale_old_and_staging_remnants(self):
        """Verify _atomic_swap_dir sweeps stale remnants and rolls back .old to target on Stage 2 failure."""
        parent = os.path.join(self.sandbox_dir, "swap_parent")
        target = os.path.join(parent, "target_mod")
        staging = os.path.join(parent, ".staging_target_mod_999")
        stale_old = os.path.join(parent, ".old_other_mod_111_222")
        stale_staging = os.path.join(parent, ".staging_other_mod_111_222")

        os.makedirs(target, exist_ok=True)
        os.makedirs(staging, exist_ok=True)
        os.makedirs(stale_old, exist_ok=True)
        os.makedirs(stale_staging, exist_ok=True)

        with open(os.path.join(target, "v.txt"), "w", encoding="utf-8") as f:
            f.write("old")
        with open(os.path.join(staging, "v.txt"), "w", encoding="utf-8") as f:
            f.write("new")
        with open(os.path.join(stale_old, "remnant.txt"), "w", encoding="utf-8") as f:
            f.write("stale")

        _atomic_swap_dir(staging, target)
        self.assertTrue(os.path.isdir(target))
        with open(os.path.join(target, "v.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "new")
        self.assertFalse(os.path.exists(staging))
        self.assertFalse(os.path.exists(stale_old))
        self.assertFalse(os.path.exists(stale_staging))

        # Verify Stage 2 failure automatically rolls back .old -> target without leaving dot-directories
        bad_staging = os.path.join(parent, ".staging_nonexistent")
        with self.assertRaises(OSError):
            _atomic_swap_dir(bad_staging, target, retries=1)
        self.assertTrue(os.path.isdir(target))
        with open(os.path.join(target, "v.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "new")
        leftovers = [e for e in os.listdir(parent) if e.startswith(".")]
        self.assertEqual(leftovers, [])

        self.mark_passed()

    def test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback(self):
        """Verify 3-stage directory lock discriminator, in-place atomic file sync, and rollback on genuine errors."""
        parent = os.path.join(self.sandbox_dir, "virtiofs_swap")
        target = os.path.join(parent, "locked_mod")
        staging = os.path.join(parent, ".staging_locked_mod")
        os.makedirs(os.path.join(target, "sub"), exist_ok=True)
        os.makedirs(os.path.join(staging, "sub"), exist_ok=True)

        with open(os.path.join(target, "keep.txt"), "w", encoding="utf-8") as f:
            f.write("v1")
        with open(os.path.join(target, "obsolete.txt"), "w", encoding="utf-8") as f:
            f.write("remove_me")
        with open(os.path.join(staging, "keep.txt"), "w", encoding="utf-8") as f:
            f.write("v2")
        with open(os.path.join(staging, "sub", "new.txt"), "w", encoding="utf-8") as f:
            f.write("added")

        real_replace = os.replace

        def _mock_dir_locked_replace(src, dst):
            if os.path.abspath(src) == os.path.abspath(target):
                raise PermissionError(errno.EACCES, "Directory handle locked by virtiofs", src)
            return real_replace(src, dst)

        with patch("os.replace", side_effect=_mock_dir_locked_replace):
            _atomic_swap_dir(staging, target, retries=1)

        with open(os.path.join(target, "keep.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "v2")
        with open(os.path.join(target, "sub", "new.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "added")
        self.assertFalse(os.path.exists(os.path.join(target, "obsolete.txt")))

        staging2 = os.path.join(parent, ".staging_locked_mod_2")
        os.makedirs(staging2, exist_ok=True)
        with open(os.path.join(staging2, "keep.txt"), "w", encoding="utf-8") as f:
            f.write("v3_fail")

        def _mock_genuine_error_replace(src, dst):
            if os.path.abspath(src) == os.path.abspath(target):
                raise OSError(errno.ENOSPC, "No space left on device", src)
            return real_replace(src, dst)

        with patch("os.replace", side_effect=_mock_genuine_error_replace):
            with self.assertRaises(OSError) as ctx:
                _atomic_swap_dir(staging2, target, retries=1)
            self.assertEqual(ctx.exception.errno, errno.ENOSPC)

        with open(os.path.join(target, "keep.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "v2")
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_update_and_reconcile_dependencies_self_heal_and_conflict_rollback(self):
        """Verify cmd_update and reconcile_installed_dependencies auto-install new deps, auto-upgrade intersection deps, and rollback on disjoint conflict."""
        cfg_path, orig_cfg = self.engine._get_config()
        orig_cfg_backup = copy.deepcopy(orig_cfg)
        provider_dir = os.path.join(self.sandbox_dir, "update_deps_provider")
        os.makedirs(provider_dir, exist_ok=True)
        test_mods = ("dep_base", "dep_new", "app_mod", "peer_mod")

        try:
            create_provider_release_zip(provider_dir, "dep_base", "1.0.0.0", dependencies={"core": ">=1.0.0"})
            create_provider_release_zip(provider_dir, "dep_base", "1.2.0.0", dependencies={"core": ">=1.0.0"})
            create_provider_release_zip(provider_dir, "dep_new", "1.0.0.0", dependencies={"core": ">=1.0.0"})
            create_provider_release_zip(provider_dir, "app_mod", "1.0.0.0", dependencies={"core": ">=1.0.0", "dep_base": ">=1.0.0"})

            installer = Installer()
            rc_init = installer.cmd_install("app_mod", version="1.0.0.0", provider=provider_dir)
            self.assertEqual(rc_init, 0)
            _, cfg_before = self.engine._get_config()
            inst_before = cfg_before.get("installed_modules", {})
            self.assertEqual(inst_before.get("app_mod", {}).get("version"), "1.0.0.0")
            self.assertEqual(inst_before.get("dep_base", {}).get("version"), "1.2.0.0")
            self.engine.act_prepare([("dep_base", "1.0.0.0")], provider_dir, force=True)
            self.engine.act_register("dep_base", "1.0.0.0", provider_dir)
            self.engine.act_reload(clean_stage=True, inject_stage=False)

            create_provider_release_zip(
                provider_dir,
                "app_mod",
                "1.1.0.0",
                dependencies={"core": ">=1.0.0", "dep_base": ">=1.2.0", "dep_new": ">=1.0.0"},
            )

            rc_upd = installer.cmd_update("app_mod", provider=provider_dir)
            self.assertEqual(rc_upd, 0)

            _, cfg_after = self.engine._get_config()
            inst_after = cfg_after.get("installed_modules", {})
            self.assertEqual(inst_after.get("app_mod", {}).get("version"), "1.1.0.0")
            self.assertEqual(inst_after.get("dep_base", {}).get("version"), "1.2.0.0")
            self.assertEqual(inst_after.get("dep_new", {}).get("version"), "1.0.0.0")
            self.assertTrue(vfs.is_file("module://dep_new/manifest.json"))

            self.engine.act_unregister("dep_new")
            self.engine.act_reload(clean_stage=True, inject_stage=False)
            _, cfg_reloaded = self.engine._get_config()
            self.assertEqual(cfg_reloaded.get("installed_modules", {}).get("dep_new", {}).get("version"), "1.0.0.0")

            create_provider_release_zip(provider_dir, "peer_mod", "1.0.0.0", dependencies={"core": ">=1.0.0", "dep_base": "==1.2.0.0"})
            self.assertEqual(installer.cmd_install("peer_mod", version="1.0.0.0", provider=provider_dir), 0)

            create_provider_release_zip(provider_dir, "dep_base", "1.3.0.0", dependencies={"core": ">=1.0.0"})
            create_provider_release_zip(
                provider_dir,
                "app_mod",
                "1.2.0.0",
                dependencies={"core": ">=1.0.0", "dep_base": ">=1.3.0.0", "dep_new": ">=1.0.0"},
            )

            rc_conflict = installer.cmd_update("app_mod", provider=provider_dir)
            self.assertEqual(rc_conflict, 1)

            _, cfg_rolled_back = self.engine._get_config()
            inst_rb = cfg_rolled_back.get("installed_modules", {})
            self.assertEqual(inst_rb.get("app_mod", {}).get("version"), "1.1.0.0")
            self.assertEqual(inst_rb.get("dep_base", {}).get("version"), "1.2.0.0")
            self.mark_passed()
        finally:
            self.engine._save_config(cfg_path, orig_cfg_backup)
            for m_name in test_mods:
                self.engine.act_delete(m_name, clean_mirror=True, purge=True)
                if vfs.exists(f"module://{m_name}"):
                    vfs.rmtree(f"module://{m_name}", ignore_errors=True)
            shutil.rmtree(provider_dir, ignore_errors=True)
            self.engine.act_reload(clean_stage=True, inject_stage=True, reconcile_deps=False)

    def test_snapshot_collision_cleanup_and_lock_reentrancy(self):
        """驗證 act_snapshot 覆寫同名舊快照時清除殘留檔案，以及 act_lock / act_unlock 同操作重入計數與 Inode 保留。"""
        snap_uri = "snapshot://snap_collision_test"
        try:
            vfs.makedirs(f"{snap_uri}/modules/GhostMod", exist_ok=True)
            vfs.write_text(f"{snap_uri}/modules/GhostMod/stale.txt", "stale")
            self.engine.act_snapshot("snap_collision_test")
            self.assertFalse(vfs.exists(f"{snap_uri}/modules/GhostMod/stale.txt"))
        finally:
            if vfs.exists(snap_uri):
                vfs.rmtree(snap_uri, ignore_errors=True)

        self.engine.act_lock("test_reentrant_op")
        lock_p = uri.resolve("cache://.yscb.lock")
        try:
            self.engine.act_lock("test_reentrant_op")
            self.engine.act_unlock("test_reentrant_op")
            self.assertTrue(vfs.exists("cache://.yscb.lock"))
            probe_held = InterProcessLock(lock_p, reentrant=False)
            self.assertFalse(probe_held.acquire(blocking=False, reentrant=False))
        finally:
            self.engine.act_unlock("test_reentrant_op")
        self.assertTrue(vfs.exists("cache://.yscb.lock"))
        probe_free = InterProcessLock(lock_p, reentrant=False)
        self.assertTrue(probe_free.acquire(blocking=False, reentrant=False))
        probe_free.release()
        self.mark_passed()

    def test_uri_cycle_detection_and_tls_context_restoration(self):
        """驗證 URI const/config 循環依賴防護、TLS 狀態快照還原與 symlink 子路徑安全邊界。"""
        # 1. Self-referencing const/project scheme raises CyclicURIDependencyError
        core_cfg = "config://core/config.project.json"
        saved_cfg = vfs.read_json(core_cfg) if vfs.exists(core_cfg) else None
        try:
            vfs.write_json(core_cfg, {"project_root": "project://recursive_self"})
            with self.assertRaises(CyclicURIDependencyError):
                uri.resolve("project://file.txt", interactive=False)
        finally:
            if saved_cfg is not None:
                vfs.write_json(core_cfg, saved_cfg)

        # 2. bind_runtime_context restores uri_tls fields and host_scope restores active_yscb_dir
        orig_host = uri.get_host_dir()
        orig_yscb = uri.get_yscb_root()
        orig_mod = uri.get_module_context()
        temp_host = os.path.join(self.sandbox_dir, "tls_host")
        temp_yscb = os.path.join(self.sandbox_dir, "tls_yscb")
        os.makedirs(temp_host, exist_ok=True)
        os.makedirs(temp_yscb, exist_ok=True)
        with bind_runtime_context(host_dir=temp_host, yscb_dir=temp_yscb):
            uri.set_host_dir(temp_host)
            uri.set_yscb_root(temp_yscb)
            uri.set_module_context("tls_mod")
            self.assertEqual(uri.get_host_dir(), os.path.normpath(os.path.abspath(temp_host)))
            self.assertEqual(uri.get_yscb_root(), os.path.normpath(os.path.abspath(temp_yscb)))
            self.assertEqual(uri.get_module_context(), "tls_mod")
            with uri.host_scope(temp_host, None):
                uri.set_yscb_root(temp_host)
            self.assertEqual(uri.get_yscb_root(), os.path.normpath(os.path.abspath(temp_yscb)))
        self.assertEqual(uri.get_host_dir(), orig_host)
        self.assertEqual(uri.get_yscb_root(), orig_yscb)
        self.assertEqual(uri.get_module_context(), orig_mod)

        # 3. _ensure_safe_subpath blocks symlink escape outside base_dir
        base_d = os.path.join(self.sandbox_dir, "safe_base")
        outside_d = os.path.join(self.sandbox_dir, "outside_secret")
        os.makedirs(base_d, exist_ok=True)
        os.makedirs(outside_d, exist_ok=True)
        secret_f = os.path.join(outside_d, "secret.txt")
        with open(secret_f, "w", encoding="utf-8") as f:
            f.write("secret")
        esc_link = os.path.join(base_d, "esc_link")
        try:
            os.symlink(outside_d, esc_link)
            has_symlink = True
        except (OSError, NotImplementedError):
            has_symlink = False
        if has_symlink:
            with self.assertRaises(PermissionError):
                uri._ensure_safe_subpath(base_d, "esc_link/secret.txt", "test://esc_link/secret.txt")
        self.mark_passed()

    def test_service_contract_vcwd_busy_and_ipc_touch_activity(self):
        """驗證 BaseServiceWorkerContract.bind_worker_context vcwd 優先序、set_state busy 欄位與 IPC touch_activity。"""
        from core.context import get_virtual_cwd

        class _DummyWorker(BaseServiceWorkerContract):
            @property
            def name(self) -> str:
                return "dummy_svc"

            def start(self, context):
                pass

            def stop(self) -> None:
                pass

            def health_check(self) -> bool:
                return True

        w = _DummyWorker()
        pkts = []
        mock_sink = MagicMock()
        mock_sink.emit_packet_fn = lambda pkt: pkts.append(pkt)
        w._log_sink = mock_sink

        w.set_state(w.STATE_UPDATING)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0]["type"], "service_status")
        self.assertTrue(pkts[0]["busy"])

        self.assertTrue(w.touch_activity())
        self.assertEqual(pkts[-1]["type"], "touch_activity")
        self.assertEqual(pkts[-1]["source"], "dummy_svc")

        host_p = os.path.join(self.sandbox_dir, "svc_host")
        yscb_p = os.path.join(host_p, "ys_codebase")
        os.makedirs(yscb_p, exist_ok=True)
        with w.bind_worker_context({"host_dir": host_p, "yscb_dir": yscb_p}):
            self.assertEqual(os.path.normpath(str(get_virtual_cwd())), os.path.normpath(os.path.abspath(host_p)))
        self.mark_passed()

    def test_gitignore_cqs_status_and_cross_process_dynamic_persistence(self):
        """驗證 gitignore.status() 唯讀不刪檔，且新進程可從 .gitignore 現有受控區塊還原已安裝模組之動態規則。"""
        proj_d = os.path.join(self.sandbox_dir, "gi_cqs_proj")
        yscb_d = os.path.join(proj_d, "ys_codebase")
        os.makedirs(os.path.join(yscb_d, ".modules", "dyn_mod"), exist_ok=True)
        with open(os.path.join(proj_d, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump({"yscb_root": "./ys_codebase", "installed_modules": {"dyn_mod": {"version": "1.0.0.0"}}}, f)

        gitignore.register("dyn_mod", ["/.dyn_generated/"], sync_now=True, proj_root=proj_d, yscb_root=yscb_d)
        gi_file = os.path.join(proj_d, ".gitignore")
        self.assertIn("# [dyn_mod]\n/.dyn_generated/", vfs.read_text(gi_file))

        # Simulate a fresh process where in-memory _CUSTOM_ROOT_DYNAMIC_STORE is empty
        gitignore._CUSTOM_ROOT_DYNAMIC_STORE.clear()
        st = gitignore.status(proj_root=proj_d, yscb_root=yscb_d)
        self.assertTrue(st["in_sync"])
        self.assertIn("dyn_mod", st["groups"])

        res_sync = gitignore.sync(proj_root=proj_d, yscb_root=yscb_d)
        self.assertIn("dyn_mod", res_sync["groups"])
        self.assertIn("# [dyn_mod]\n/.dyn_generated/", vfs.read_text(gi_file))
        self.mark_passed()

    def test_validator_type_signature_and_interprocess_lock_reentrancy(self):
        """驗證 ContributesValidator.parse_type_signature 引號/括號感知切分與 InterProcessLock 同執行緒跨實例重入保護。"""
        parsed = ContributesValidator.parse_type_signature('str? = "a,b|c=d" | replace')
        self.assertEqual(parsed["type"], "str")
        self.assertFalse(parsed["required"])
        self.assertEqual(parsed["default"], "a,b|c=d")
        self.assertEqual(parsed["merge_strategy"], "replace")

        parsed_enum = ContributesValidator.parse_type_signature("enum(a=1, b|2, c)!")
        self.assertEqual(parsed_enum["type"], "enum")
        self.assertTrue(parsed_enum["required"])
        self.assertEqual(parsed_enum["enum_values"], ["a=1", "b|2", "c"])

        lock_file = os.path.join(self.sandbox_dir, "reentrant_test.lock")
        lock1 = InterProcessLock(lock_file)
        lock2 = InterProcessLock(lock_file)
        self.assertTrue(lock1.acquire(blocking=False))
        try:
            # Default non-reentrant across instances blocks same-thread duplicate acquire
            self.assertFalse(lock2.acquire(blocking=False))
            # Explicit reentrant=True allows same-thread re-entry
            self.assertTrue(lock2.acquire(blocking=False, reentrant=True))
            lock2.release()
        finally:
            lock1.release()
        self.mark_passed()

    def test_space_positive_filename_rule_and_status_owner_isolation(self):
        """驗證 CompiledRuleSet 正向純檔名規則不誤匹配同名父目錄，以及 SpaceScanner.status() 不誤套用其他 owner 的同名合成快照。"""
        proj_d = Path(self.sandbox_dir) / "sp_fix_proj"
        yscb_d = proj_d / "ys_codebase"
        (proj_d / "SKILL.md").mkdir(parents=True, exist_ok=True)
        (proj_d / "SKILL.md" / "unrelated.txt").write_text("nope\n", encoding="utf-8")
        (proj_d / "docs").mkdir(parents=True, exist_ok=True)
        (proj_d / "docs" / "SKILL.md").write_text("yes\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=proj_d,
            yscb_dir=yscb_d,
            raw_spaces={
                "mod_a/skills": {
                    "entries": ["project://"],
                    "include": ["SKILL.md"],
                },
                "mod_b/skills": {
                    "entries": ["project://docs"],
                    "include": ["SKILL.md"],
                },
            },
        )
        matched_files = [f.rel_path for f in reg.iter_space_files("mod_a/skills")]
        self.assertEqual(matched_files, ["docs/SKILL.md"])

        scanner = SpaceScanner(registry=reg, storage_root=yscb_d / ".storage.local" / "core" / "spaces")
        scanner.scan("mod_a/skills")
        st_payload = scanner.status("mod_b/skills")
        self.assertEqual(len(st_payload["spaces"]), 1)
        self.assertEqual(st_payload["spaces"][0]["head_generation"], 0)
        self.mark_passed()

    def test_dispatcher_reentrant_argv_and_contributes_check_commands_alias(self):
        """驗證 dispatch_local 重入時 sys.argv 完整還原、純分支群組 Help 路由，以及 contributes check commands 映射。"""
        orig_argv = list(sys.argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_group = dispatcher.dispatch(["core", "uri"])
        self.assertEqual(rc_group, 0)
        self.assertIn("AVAILABLE SUBCOMMANDS:", buf.getvalue())
        self.assertEqual(sys.argv, orig_argv)

        buf_chk = io.StringIO()
        with redirect_stdout(buf_chk):
            rc_chk = check_contributes("module.source://core/contributes/core.json")
        self.assertEqual(rc_chk, 0)
        self.mark_passed()
