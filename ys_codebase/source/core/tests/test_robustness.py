"""
Unit and integration tests for framework robustness, context managers, dual-layer snapshot and strict URI resolution.
"""
import unittest
import os
import tempfile
import shutil
import json
from core import uri
from core.context import ExecutionContext
from core.engine import AtomicEngine
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class FrameworkRobustnessTest(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp()
        self.host_dir = os.path.join(self.tmp_dir, "host")
        self.engine_dir = os.path.join(self.tmp_dir, "engine")
        os.makedirs(self.host_dir, exist_ok=True)
        os.makedirs(os.path.join(self.engine_dir, "config", "core"), exist_ok=True)
        os.makedirs(os.path.join(self.engine_dir, "modules"), exist_ok=True)
        os.makedirs(os.path.join(self.engine_dir, ".mirror"), exist_ok=True)
        os.makedirs(os.path.join(self.engine_dir, ".snapshots"), exist_ok=True)

        # Write host config
        self.host_cfg_path = os.path.join(self.host_dir, "yscb.config.json")
        with open(self.host_cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "yscb_root": self.engine_dir,
                "default_provider": os.path.join(self.tmp_dir, "provider"),
                "installed_modules": {
                    "core": {"version": "1.0.0", "provider": "local"},
                    "dev": {"version": "1.0.0", "provider": "local"}
                }
            }, f, indent=2)

        # Write core config.project.json
        with open(os.path.join(self.engine_dir, "config", "core", "config.project.json"), "w", encoding="utf-8") as f:
            json.dump({"project_root": os.path.join(self.tmp_dir, "project")}, f, indent=2)

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_invalid_uri_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            uri.resolve("relative/path/not/uri")
        with self.assertRaises(ValueError):
            uri.resolve("unknown_scheme://foo")

    def test_context_managers_auto_restore(self):
        # 1. Test module_scope
        orig_mod = uri.get_module_context()
        with uri.module_scope("test_mod"):
            self.assertEqual(uri.get_module_context(), "test_mod")
        self.assertEqual(uri.get_module_context(), orig_mod)

        # 2. Test host_scope
        orig_host = uri.get_host_dir()
        with uri.host_scope(self.host_dir):
            self.assertEqual(uri.get_host_dir(), os.path.normpath(self.host_dir))
        self.assertEqual(uri.get_host_dir(), orig_host)

    def test_context_manager_exception_safety(self):
        orig_mod = uri.get_module_context()
        try:
            with uri.module_scope("temp_error_scope"):
                raise RuntimeError("Intentional error")
        except RuntimeError:
            pass
        self.assertEqual(uri.get_module_context(), orig_mod)

    def test_dual_layer_snapshot_and_restore(self):
        with unittest.mock.patch("core.uri._get_yscb_root", return_value=self.engine_dir):
            with uri.host_scope(self.host_dir):
                engine = AtomicEngine()
                
                # Setup custom module config in config/core/
                cfg_p = uri.resolve("config://core/config.project.json")
                with open(cfg_p, "w", encoding="utf-8") as f:
                    json.dump({"project_root": "original_val"}, f)

                # Create dual-layer snapshot
                snap_id = engine.act_snapshot("test_dual_snap")

                # Mutate both host config and module config
                with open(self.host_cfg_path, "w", encoding="utf-8") as f:
                    json.dump({"mutated": True}, f)
                with open(cfg_p, "w", encoding="utf-8") as f:
                    json.dump({"project_root": "mutated_val"}, f)

                # Restore snapshot
                engine.act_restore_snapshot(snap_id)

                # Verify host config restored
                with open(self.host_cfg_path, "r", encoding="utf-8") as f:
                    h_data = json.load(f)
                self.assertIn("yscb_root", h_data)
                self.assertNotIn("mutated", h_data)

                # Verify module config restored
                with open(cfg_p, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                self.assertEqual(m_data.get("project_root"), "original_val")

    def test_execution_context_ssot_immutability(self):
        ctx = ExecutionContext("core", "test_cmd", ["arg1"], {"key": "val"})
        self.assertEqual(ctx.module_name, "core")
        self.assertEqual(ctx.command, "test_cmd")
        with self.assertRaises(Exception):
            ctx.module_name = "mutated"  # Frozen dataclass check

if __name__ == "__main__":
    unittest.main()
