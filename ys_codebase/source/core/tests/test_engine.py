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

    def test_snapshot_and_restore(self):
        """Verify snapshot creation and disaster recovery rollback."""
        orig_cfg = uri.read_json("project://yscb.config.json")
        snap_id = self.engine.act_snapshot("unit_test_snap")
        self.assertTrue(uri.exists(f"snapshot://{snap_id}/yscb.config.json"))
        
        # Verify snapshot content matches
        snap_cfg = uri.read_json(f"snapshot://{snap_id}/yscb.config.json")
        self.assertEqual(snap_cfg.get("yscb_root"), orig_cfg.get("yscb_root"))
        
        # Test restore
        self.engine.act_restore_snapshot(snap_id)
        self.assertEqual(uri.read_json("project://yscb.config.json"), orig_cfg)
        
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
