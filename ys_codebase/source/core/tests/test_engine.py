"""
Official test suite for core.engine.AtomicEngine.
"""
import os
import time
from dev.testing import YSCBTestCase
from core.engine import AtomicEngine
from core.uri import ExecutionContext
from core import uri

class TestCoreEngine(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()

    def test_host_config_isolation_from_project_uri(self):
        """Verify host config and snapshot operations succeed even when project:// is undefined (FT-01)."""
        core_cfg = "config.root://core/config.project.json"
        saved = None
        if uri.exists(core_cfg):
            saved = uri.read_json(core_cfg)
            uri.remove(core_cfg)
            
        try:
            # project:// should fail with ValueError
            with self.assertRaises(ValueError):
                uri.resolve("project://yscb.config.json")
                
            # Engine operations must succeed without relying on project://
            cfg_path, cfg = self.engine._get_config()
            self.assertTrue(os.path.isfile(cfg_path))
            self.assertIn("installed_modules", cfg)
            
            snap_id = self.engine.act_snapshot("isolation_test_snap")
            self.assertTrue(uri.exists(f"snapshot://{snap_id}/yscb.config.json"))
            self.engine.act_restore_snapshot(snap_id)
            uri.rmtree(f"snapshot://{snap_id}")
        finally:
            if saved is not None:
                uri.write_json(core_cfg, saved, indent=2)
        self.mark_passed()

    def test_manifest_dependencies_schema_compatibility(self):
        """Verify _parse_dependencies supports both dict and list schemas (FT-06)."""
        dict_deps = {"core": ">=1.0.0", "dev": "^1.2.0"}
        parsed_dict = self.engine._parse_dependencies(dict_deps)
        self.assertEqual(parsed_dict["core"], ">=1.0.0")
        self.assertEqual(parsed_dict["dev"], "^1.2.0")
        
        list_deps = ["core >=1.0.0", "helper ^0.5.0", "standalone"]
        parsed_list = self.engine._parse_dependencies(list_deps)
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
        uri.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {}})
        
        mod_b_dir = os.path.join(provider_dir, "mod_b", "1.0.0")
        os.makedirs(mod_b_dir, exist_ok=True)
        uri.write_json(os.path.join(mod_b_dir, "manifest.json"), {"name": "mod_b", "version": "1.0.0", "dependencies": {"mod_c": ">=1.0.0"}})
        
        mod_a_dir = os.path.join(provider_dir, "mod_a", "1.0.0")
        os.makedirs(mod_a_dir, exist_ok=True)
        uri.write_json(os.path.join(mod_a_dir, "manifest.json"), {"name": "mod_a", "version": "1.0.0", "dependencies": {"mod_b": ">=1.0.0"}})
        
        # 1. Topological order should be [mod_c, mod_b, mod_a]
        order = self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        names = [m[0] for m in order]
        self.assertEqual(names, ["mod_c", "mod_b", "mod_a"])
        
        # 2. Setup cycle: mod_c -> mod_a
        uri.write_json(os.path.join(mod_c_dir, "manifest.json"), {"name": "mod_c", "version": "1.0.0", "dependencies": {"mod_a": ">=1.0.0"}})
        with self.assertRaises(ValueError) as ctx:
            self.engine.act_solve_deps("mod_a", "1.0.0", provider_dir)
        self.assertIn("Circular dependency detected", str(ctx.exception))
        self.mark_passed()

    def test_snapshot_and_restore(self):
        """Verify snapshot creation and disaster recovery rollback."""
        cfg_path, orig_cfg = self.engine._get_config()
        snap_id = self.engine.act_snapshot("unit_test_snap")
        self.assertTrue(uri.exists(f"snapshot://{snap_id}/yscb.config.json"))
        
        # Verify snapshot content matches
        snap_cfg = uri.read_json(f"snapshot://{snap_id}/yscb.config.json")
        self.assertEqual(snap_cfg.get("yscb_root"), orig_cfg.get("yscb_root"))
        
        # Test restore
        self.engine.act_restore_snapshot(snap_id)
        _, restored_cfg = self.engine._get_config()
        self.assertEqual(restored_cfg, orig_cfg)
        
        uri.rmtree(f"snapshot://{snap_id}")
        self.mark_passed()

    def test_inter_process_lock_and_auto_healing(self):
        """Verify process lock exclusivity and 10s auto-healing on stale locks."""
        self.engine.act_unlock("test_op")
        
        # 1. Acquire lock
        self.engine.act_lock("test_op")
        self.assertTrue(uri.exists("temp://.yscb.lock"))
        
        # 2. Second lock should fail with BlockingIOError
        with self.assertRaises(BlockingIOError):
            self.engine.act_lock("test_op_2", timeout=10.0)
            
        # 3. Unlock
        self.engine.act_unlock("test_op")
        self.assertFalse(uri.exists("temp://.yscb.lock"))
        
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
        uri.makedirs(tpl_dir)
        initial_tpl = {
            "setting_a": "default_a",
            "nested": {
                "sub_1": "default_sub1"
            }
        }
        uri.write_json(f"{tpl_dir}/config.project.json", initial_tpl)
        
        # 1. First seed
        self.engine._seed_or_update_config("mod_test_cfg", tpl_dir)
        target_cfg_uri = "config.root://mod_test_cfg/config.project.json"
        self.assertTrue(uri.exists(target_cfg_uri))
        self.assertEqual(uri.read_json(target_cfg_uri), initial_tpl)
        
        # 2. User customizes setting_a and nested.sub_1
        user_mod = {
            "setting_a": "user_custom_value",
            "nested": {
                "sub_1": "user_custom_sub1"
            }
        }
        uri.write_json(target_cfg_uri, user_mod)
        
        # 3. New template with added setting_b and nested.sub_2
        new_tpl = {
            "setting_a": "default_a",
            "setting_b": "new_default_b",
            "nested": {
                "sub_1": "default_sub1",
                "sub_2": "new_default_sub2"
            }
        }
        uri.write_json(f"{tpl_dir}/config.project.json", new_tpl)
        
        # 4. Infill update
        self.engine._seed_or_update_config("mod_test_cfg", tpl_dir)
        final_cfg = uri.read_json(target_cfg_uri)
        
        # User values must be preserved
        self.assertEqual(final_cfg["setting_a"], "user_custom_value")
        self.assertEqual(final_cfg["nested"]["sub_1"], "user_custom_sub1")
        # Missing keys must be infilled
        self.assertEqual(final_cfg["setting_b"], "new_default_b")
        self.assertEqual(final_cfg["nested"]["sub_2"], "new_default_sub2")
        
        uri.rmtree(f"config.root://mod_test_cfg")
        self.mark_passed()

    def test_broadcast_event_and_exception_isolation(self):
        """Verify namespaced hook.{emit_mod}.py execution and try-except fault isolation."""
        receiver_dir = f"module.root://mock_receiver/scripts"
        uri.makedirs(receiver_dir)
        
        flag_file = f"{self.sandbox_uri}/hook_executed.txt"
        hook_code = f"""
def on_test_event(context):
    with open(r'{uri.resolve(flag_file)}', 'w', encoding='utf-8') as f:
        f.write('EVENT_FIRED:' + context.command)
"""
        uri.write_text(f"{receiver_dir}/hook.dev.py", hook_code)
        
        # Also create a broken hook in another module
        broken_dir = f"module.root://mock_broken/scripts"
        uri.makedirs(broken_dir)
        broken_code = """
def on_test_event(context):
    raise RuntimeError("Deliberate hook failure for testing")
"""
        uri.write_text(f"{broken_dir}/hook.dev.py", broken_code)
        
        # Broadcast event
        ctx = ExecutionContext("dev", "test_cmd", ["arg1"])
        results = self.engine.act_broadcast_event("dev", "on_test_event", ctx)
        
        # 1. Receiver succeeded
        self.assertEqual(results.get("mock_receiver"), "success")
        self.assertTrue(uri.exists(flag_file))
        self.assertEqual(uri.read_text(flag_file), "EVENT_FIRED:test_cmd")
        
        # 2. Broken receiver isolated
        self.assertIn("mock_broken", results)
        self.assertTrue(results["mock_broken"].startswith("warning:"))
        
        # Cleanup
        uri.rmtree("module.root://mock_receiver")
        uri.rmtree("module.root://mock_broken")
        self.mark_passed()

    def test_download_missing_package_raises_not_found(self):
        """Verify provider missing package raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.engine.act_download("non_existent_pkg_xyz", "9.9.9", "invalid_provider_path")
        self.mark_passed()
