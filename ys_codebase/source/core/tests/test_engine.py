"""
Official test suite for core.engine.AtomicEngine.
"""
import os
import time
from dev.testing import YSCBTestCase, require, Requirement
from core.engine import AtomicEngine, _parse_dependencies, _deep_infill_dict, _atomic_swap_dir
from core.uri import ExecutionContext
from core import uri, vfs, events

@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreEngine(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()

    def test_host_config_isolation_from_project_uri(self):
        """Verify host config and snapshot operations succeed even when project:// is undefined (FT-01)."""
        core_cfg = "config://core/config.project.json"
        saved = None
        if vfs.exists(core_cfg):
            saved = vfs.read_json(core_cfg)
            vfs.remove(core_cfg)
            
        try:
            # project:// should fail with ValueError
            with self.assertRaises(ValueError):
                uri.resolve("project://yscb.config.json")
                
            # Engine operations must succeed without relying on project://
            cfg_path, cfg = self.engine._get_config()
            self.assertTrue(os.path.isfile(cfg_path))
            self.assertIn("installed_modules", cfg)
            
            snap_id = self.engine.act_snapshot("isolation_test_snap")
            self.assertTrue(vfs.exists(f"snapshot://{snap_id}/yscb.config.json"))
            self.engine.act_restore_snapshot(snap_id)
            vfs.rmtree(f"snapshot://{snap_id}")
        finally:
            if saved is not None:
                vfs.write_json(core_cfg, saved, indent=2)
        self.mark_passed()

    def test_manifest_dependencies_schema_compatibility(self):
        """Verify _parse_dependencies supports both dict and list schemas (FT-06)."""
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
        """Verify act_solve_deps solves recursive topology and catches circular dependencies (FT-08)."""
        provider_dir = os.path.join(self.sandbox_dir, "mock_provider")
        os.makedirs(provider_dir, exist_ok=True)
        
        # Setup mod_a -> mod_b -> mod_c
        mod_c_dir = os.path.join(provider_dir, "mod_c", "1.0.0")
        os.makedirs(mod_c_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {}})
        
        mod_b_dir = os.path.join(provider_dir, "mod_b", "1.0.0")
        os.makedirs(mod_b_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_b_dir, "manifest.json"), {"name": "mod_b", "version": "1.0.0", "dependencies": {"mod_c": ">=1.0.0"}})
        
        mod_a_dir = os.path.join(provider_dir, "mod_a", "1.0.0")
        os.makedirs(mod_a_dir, exist_ok=True)
        vfs.write_json(os.path.join(mod_a_dir, "manifest.json"), {"name": "mod_a", "version": "1.0.0", "dependencies": {"mod_b": ">=1.0.0"}})
        
        # 1. Topological order should be [mod_c, mod_b, mod_a]
        order = self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        names = [m[0] for m in order]
        self.assertEqual(names, ["mod_c", "mod_b", "mod_a"])
        
        # 2. Setup cycle: mod_c -> mod_a
        vfs.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {"mod_a": ">=1.0.0"}})
        with self.assertRaises(ValueError) as ctx:
            self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        self.assertIn("Circular dependency detected", str(ctx.exception))
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_snapshot_and_restore(self):
        """Verify snapshot creation and disaster recovery rollback."""
        cfg_path, orig_cfg = self.engine._get_config()
        snap_id = self.engine.act_snapshot("unit_test_snap")
        self.assertTrue(vfs.exists(f"snapshot://{snap_id}/yscb.config.json"))
        
        # Verify snapshot content matches
        snap_cfg = vfs.read_json(f"snapshot://{snap_id}/yscb.config.json")
        self.assertEqual(snap_cfg.get("yscb_root"), orig_cfg.get("yscb_root"))
        
        # Test restore
        self.engine.act_restore_snapshot(snap_id)
        _, restored_cfg = self.engine._get_config()
        self.assertEqual(restored_cfg, orig_cfg)
        
        vfs.rmtree(f"snapshot://{snap_id}")
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_inter_process_lock_and_auto_healing(self):
        """Verify process lock exclusivity and 10s auto-healing on stale locks."""
        self.engine.act_unlock("test_op")
        
        # 1. Acquire lock
        self.engine.act_lock("test_op")
        self.assertTrue(vfs.exists("cache://.yscb.lock"))
        
        # 2. Second lock should fail with BlockingIOError
        with self.assertRaises(BlockingIOError):
            self.engine.act_lock("test_op_2", timeout=10.0)
            
        # 3. Unlock
        self.engine.act_unlock("test_op")
        self.assertFalse(vfs.exists("cache://.yscb.lock"))
        
        # 4. Simulate stale lock auto-healing (timeout=0.01s)
        self.engine.act_lock("stale_op")
        time.sleep(0.02)
        # Should auto-heal and acquire
        self.engine.act_lock("new_op", timeout=0.01)
        self.engine.act_unlock("new_op")
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
        
        # 1. First seed
        self.engine._deploy_and_strip_single_module_config("mod_test_cfg", uri.resolve(tpl_dir))
        target_cfg_uri = "config://mod_test_cfg/config.project.json"
        self.assertTrue(vfs.exists(target_cfg_uri))
        self.assertEqual(vfs.read_json(target_cfg_uri), initial_tpl)
        
        # 2. User customizes setting_a and nested.sub_1
        user_mod = {
            "setting_a": "user_custom_value",
            "nested": {
                "sub_1": "user_custom_sub1"
            }
        }
        vfs.write_json(target_cfg_uri, user_mod)
        
        # 3. New template with added setting_b and nested.sub_2
        new_tpl = {
            "setting_a": "default_a",
            "setting_b": "new_default_b",
            "nested": {
                "sub_1": "default_sub1",
                "sub_2": "new_default_sub2"
            }
        }
        vfs.write_json(f"{tpl_dir}/config.project.json", new_tpl)
        
        # 4. Infill update
        self.engine._deploy_and_strip_single_module_config("mod_test_cfg", tpl_dir)
        final_cfg = vfs.read_json(target_cfg_uri)
        
        # User values must be preserved
        self.assertEqual(final_cfg["setting_a"], "user_custom_value")
        self.assertEqual(final_cfg["nested"]["sub_1"], "user_custom_sub1")
        # Missing keys must be infilled
        self.assertEqual(final_cfg["setting_b"], "new_default_b")
        self.assertEqual(final_cfg["nested"]["sub_2"], "new_default_sub2")
        
        vfs.rmtree(f"config://mod_test_cfg")
        self.mark_passed()

    def test_broadcast_event_and_exception_isolation(self):
        """Verify namespaced hook.{emit_mod}.py execution and try-except fault isolation."""
        receiver_dir = f"module://mock_receiver/scripts"
        vfs.makedirs(receiver_dir)
        
        flag_file = f"{self.sandbox_uri}/hook_executed.txt"
        hook_code = f"""
def on_test_event(context):
    with open(r'{uri.resolve(flag_file)}', 'w', encoding='utf-8') as f:
        f.write('EVENT_FIRED:' + context.command)
"""
        vfs.write_text(f"{receiver_dir}/hook.dev.py", hook_code)
        
        # Also create a broken hook in another module
        broken_dir = f"module://mock_broken/scripts"
        vfs.makedirs(broken_dir)
        broken_code = """
def on_test_event(context):
    raise RuntimeError("Deliberate hook failure for testing")
"""
        vfs.write_text(f"{broken_dir}/hook.dev.py", broken_code)
        
        # Broadcast event
        ctx = ExecutionContext("dev", "test_cmd", ["arg1"])
        results = events.broadcast("on_test_event", ctx, emit_module="dev")
        
        # 1. Receiver succeeded
        self.assertEqual(results.get("mock_receiver"), "success")
        self.assertTrue(vfs.exists(flag_file))
        self.assertEqual(vfs.read_text(flag_file), "EVENT_FIRED:test_cmd")
        
        # 2. Broken receiver isolated
        self.assertIn("mock_broken", results)
        self.assertTrue(results["mock_broken"].startswith("warning:"))
        
        # Cleanup
        vfs.rmtree("module://mock_receiver")
        vfs.rmtree("module://mock_broken")
        self.mark_passed()

    def test_download_missing_package_raises_not_found(self):
        """Verify provider missing package raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.engine.act_download("non_existent_pkg_xyz", "9.9.9", "invalid_provider_path")
        self.mark_passed()

    def test_download_build_revision_special_case(self):
        """Verify requesting build revision downloads directly from module.build://."""
        import zipfile
        # Setup mock build package
        build_dir = "module.build://mock_build_pkg"
        vfs.makedirs(build_dir)
        b_zip_uri = f"{build_dir}/1.0.0.build.zip"
        with zipfile.ZipFile(uri.resolve(b_zip_uri), "w") as zf:
            zf.writestr("manifest.json", '{"name": "mock_build_pkg", "version": "1.0.0.build", "entry": "scripts/cli.py"}')
            zf.writestr("scripts/cli.py", 'print("build hello")')

        # Test download with @build
        dl_uri = self.engine.act_download("mock_build_pkg", "build", "non_existent_provider_path")
        self.assertTrue(vfs.exists(dl_uri))
        self.assertTrue(vfs.exists("module.mirror://mock_build_pkg/build.zip"))

        # Cleanup
        vfs.rmtree(build_dir)
        vfs.rmtree("module.mirror://mock_build_pkg")
        self.mark_passed()

    def test_download_build_revision_not_found_raises(self):
        """Verify requesting build revision with missing package raises FileNotFoundError with build guidance."""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.engine.act_download("non_existent_build_mod", "build", "non_existent_prov")
        self.assertIn("Build package not found", str(ctx.exception))
        self.assertIn("dev build", str(ctx.exception))
        self.mark_passed()

    def test_deploy_configurable_templates(self):
        """FT-04: Verify act_deploy_configs_from_modules deploys from configurable/ and cleans up."""
        mod_dir = f"module://mock_deploy_mod"
        cfg_tpl_dir = f"{mod_dir}/configurable"
        vfs.makedirs(cfg_tpl_dir, exist_ok=True)
        vfs.write_json(f"{cfg_tpl_dir}/config.project.json", {"proj_key": "val1"})
        vfs.write_json(f"{cfg_tpl_dir}/config.local.json", {"local_key": "val2"})
        vfs.write_json(f"{cfg_tpl_dir}/contribute.json", {"spaces": {"sp1": {}}})

        # Register mock module
        self.engine.act_register("mock_deploy_mod", "1.0.0.0", "mock_prov")
        self.engine.act_deploy_configs_from_modules()

        # Check deployed to config://
        self.assertTrue(vfs.exists("config://mock_deploy_mod/config.project.json"))
        self.assertTrue(vfs.exists("config://mock_deploy_mod/config.local.json"))
        self.assertTrue(vfs.exists("config://mock_deploy_mod/contribute.json"))
        self.assertEqual(vfs.read_json("config://mock_deploy_mod/config.project.json")["proj_key"], "val1")

        # Check configurable/ was physically purged from module runtime
        self.assertFalse(vfs.exists(cfg_tpl_dir))

        # Cleanup
        self.engine.act_unregister("mock_deploy_mod")
        vfs.rmtree(mod_dir)
        vfs.rmtree("config://mock_deploy_mod")
        self.mark_passed()

    def test_local_config_infill_skips_project_keys(self):
        """FT-17: 驗證 local 層級軟合併時，若 project 已有對應設定則自動跳過。"""
        # 1. 直接測試 _deep_infill_dict 行為
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

        # 2. 測試 act_deploy_configs_from_modules 端到端部署行為
        mod_dir = "module://mock_deploy_infill"
        cfg_tpl_dir = f"{mod_dir}/configurable"
        vfs.makedirs(cfg_tpl_dir, exist_ok=True)
        vfs.write_json(f"{cfg_tpl_dir}/config.project.json", {"shared_key": "proj_val", "override_me": "from_proj"})
        vfs.write_json(f"{cfg_tpl_dir}/config.local.json", {"local_only": "loc_val", "override_me": "from_loc_tpl"})

        self.engine.act_register("mock_deploy_infill", "1.0.0.0", "mock_prov")
        self.engine.act_deploy_configs_from_modules()

        deployed_proj = vfs.read_json("config://mock_deploy_infill/config.project.json")
        deployed_local = vfs.read_json("config://mock_deploy_infill/config.local.json")

        self.assertEqual(deployed_proj.get("override_me"), "from_proj")
        self.assertEqual(deployed_local.get("local_only"), "loc_val")
        self.assertNotIn("override_me", deployed_local)

        # Cleanup
        self.engine.act_unregister("mock_deploy_infill")
        vfs.rmtree(mod_dir)
        vfs.rmtree("config://mock_deploy_infill")
        self.mark_passed()

    def test_dual_layer_snapshot_and_execution_context_immutability(self):
        """Robustness: 驗證雙層快照完整還原與 ExecutionContext 屬性不可變性。"""
        # 1. ExecutionContext 不可變性
        ctx = ExecutionContext("core", "test_cmd", ["arg1"], {"key": "val"})
        self.assertEqual(ctx.module_name, "core")
        self.assertEqual(ctx.command, "test_cmd")
        with self.assertRaises(Exception):
            ctx.module_name = "mutated"

        # 2. 雙層快照與還原
        cfg_p = "config://core/config.project.json"
        orig_p = vfs.read_json(cfg_p) if vfs.exists(cfg_p) else {}
        snap_id = self.engine.act_snapshot("test_dual_snap")
        try:
            vfs.write_json(cfg_p, {"project_root": "mutated_val"})
            self.assertEqual(vfs.read_json(cfg_p).get("project_root"), "mutated_val")
            self.engine.act_restore_snapshot(snap_id)
            restored_p = vfs.read_json(cfg_p)
            self.assertEqual(restored_p.get("project_root"), orig_p.get("project_root"))
        finally:
            if orig_p:
                vfs.write_json(cfg_p, orig_p)
            vfs.rmtree(f"snapshot://{snap_id}")

        self.mark_passed()

    def test_atomic_swap_dir_cleans_stale_old_and_staging_remnants(self):
        """Verify _atomic_swap_dir sweeps and removes stale .old_* and .staging_* directories in parent."""
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
        self.mark_passed()

    def test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback(self):
        """Verify 3-stage directory lock discriminator, in-place atomic file sync, and rollback on genuine errors."""
        import errno
        from unittest.mock import patch

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

        # Genuine permission/IO failure (e.g., ENOSPC or failed write probe) must NOT be swallowed
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
        """FR-01, FR-02, EC-01: Verify cmd_update & reconcile_installed_dependencies auto-install new deps, auto-upgrade intersection deps, and rollback on disjoint conflict."""
        import copy
        import json
        import shutil
        import zipfile
        from core.installer import Installer

        cfg_path, orig_cfg = self.engine._get_config()
        orig_cfg_backup = copy.deepcopy(orig_cfg)
        provider_dir = os.path.join(self.sandbox_dir, "update_deps_provider")
        os.makedirs(provider_dir, exist_ok=True)
        test_mods = ("dep_base", "dep_new", "app_mod", "peer_mod")

        def _make_mod_zip(mod_name: str, ver: str, deps: dict) -> None:
            mod_p = os.path.join(provider_dir, mod_name)
            os.makedirs(mod_p, exist_ok=True)
            zip_p = os.path.join(mod_p, f"{ver}.zip")
            mf = {
                "name": mod_name,
                "version": ver,
                "entry": "scripts/cli.py",
                "dependencies": deps,
            }
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("manifest.json", json.dumps(mf, indent=2))
                zf.writestr("scripts/cli.py", "def noop(cmd_bags):\n    return 0\n")
            idx_p = os.path.join(mod_p, "index.json")
            idx_data = vfs.read_json(idx_p) if os.path.isfile(idx_p) else {"versions": [], "releases": {}}
            if ver not in idx_data["versions"]:
                idx_data["versions"].append(ver)
            idx_data["releases"][ver] = {"status": "active", "dependencies": deps}
            vfs.write_json(idx_p, idx_data, indent=2)

        try:
            # Prepare packages:
            # dep_base: 1.0.0.0 and 1.2.0.0
            # dep_new: 1.0.0.0 (uninstalled initially, added by app_mod 1.1.0.0)
            # app_mod: 1.0.0.0 (requires dep_base >=1.0.0) -> 1.1.0.0 (requires dep_base >=1.2.0 and dep_new >=1.0.0)
            _make_mod_zip("dep_base", "1.0.0.0", {"core": ">=1.0.0"})
            _make_mod_zip("dep_base", "1.2.0.0", {"core": ">=1.0.0"})
            _make_mod_zip("dep_new", "1.0.0.0", {"core": ">=1.0.0"})
            _make_mod_zip("app_mod", "1.0.0.0", {"core": ">=1.0.0", "dep_base": ">=1.0.0"})

            installer = Installer()
            rc_init = installer.cmd_install("app_mod", version="1.0.0.0", provider=provider_dir)
            self.assertEqual(rc_init, 0)
            _, cfg_before = self.engine._get_config()
            inst_before = cfg_before.get("installed_modules", {})
            self.assertEqual(inst_before.get("app_mod", {}).get("version"), "1.0.0.0")
            self.assertEqual(inst_before.get("dep_base", {}).get("version"), "1.2.0.0")
            # Force downgrade dep_base to 1.0.0.0 to test auto-upgrade during app_mod update
            self.engine.act_prepare([("dep_base", "1.0.0.0")], provider_dir, force=True)
            self.engine.act_register("dep_base", "1.0.0.0", provider_dir)
            self.engine.act_reload(clean_stage=True, inject_stage=False)

            # Now publish app_mod 1.1.0.0 which requires dep_base>=1.2.0 and newly introduced dep_new>=1.0.0
            _make_mod_zip("app_mod", "1.1.0.0", {"core": ">=1.0.0", "dep_base": ">=1.2.0", "dep_new": ">=1.0.0"})

            rc_upd = installer.cmd_update("app_mod", provider=provider_dir)
            self.assertEqual(rc_upd, 0)

            _, cfg_after = self.engine._get_config()
            inst_after = cfg_after.get("installed_modules", {})
            self.assertEqual(inst_after.get("app_mod", {}).get("version"), "1.1.0.0")
            self.assertEqual(inst_after.get("dep_base", {}).get("version"), "1.2.0.0")
            self.assertEqual(inst_after.get("dep_new", {}).get("version"), "1.0.0.0")
            self.assertTrue(vfs.is_file("module://dep_new/manifest.json"))

            # Verify FR-02: act_reload Stage 1.5 self-heals when dep_new is unregistered from installed_modules
            self.engine.act_unregister("dep_new")
            self.engine.act_reload(clean_stage=True, inject_stage=False)
            _, cfg_reloaded = self.engine._get_config()
            self.assertEqual(cfg_reloaded.get("installed_modules", {}).get("dep_new", {}).get("version"), "1.0.0.0")

            # Test EC-01: Disjoint dependency conflict blocks update and rolls back snapshot
            # Install peer_mod 1.0.0.0 which pins dep_base ==1.2.0.0
            _make_mod_zip("peer_mod", "1.0.0.0", {"core": ">=1.0.0", "dep_base": "==1.2.0.0"})
            self.assertEqual(installer.cmd_install("peer_mod", version="1.0.0.0", provider=provider_dir), 0)

            # Publish dep_base 1.3.0.0 and app_mod 1.2.0.0 requiring dep_base >=1.3.0.0 (disjoint with peer_mod's ==1.2.0.0!)
            _make_mod_zip("dep_base", "1.3.0.0", {"core": ">=1.0.0"})
            _make_mod_zip("app_mod", "1.2.0.0", {"core": ">=1.0.0", "dep_base": ">=1.3.0.0", "dep_new": ">=1.0.0"})

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





