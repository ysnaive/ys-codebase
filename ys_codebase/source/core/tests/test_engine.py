"""
Official test suite for core.engine.AtomicEngine.
"""
import os
import time
from dev.testing import YSCBTestCase
from core.engine import AtomicEngine
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
        # Clean any lock
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

    def test_download_missing_package_raises_not_found(self):
        """Verify provider missing package raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.engine.act_download("non_existent_pkg_xyz", "9.9.9", "invalid_provider_path")
        self.mark_passed()
