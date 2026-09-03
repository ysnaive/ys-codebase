"""
Unit tests for modules Git decoupling, restore pipeline, and JIT module synchronization.
Covers FT-01 ~ FT-05, ET-01 ~ ET-02, and PT-01.
"""

import unittest
import tempfile
import os
import shutil
import json
import zipfile
import time
from core import uri
from dev.testing.case import YSCBTestCase
import sys
import importlib.util

# Robustly load yscb host bootstrapper module
_host_d, _ = uri._get_host_config()
_yscb_p = os.path.join(_host_d, "yscb.py")
if not os.path.isfile(_yscb_p):
    _yscb_p = os.path.abspath("yscb.py")
if os.path.isfile(_yscb_p):
    spec = importlib.util.spec_from_file_location("yscb_host", _yscb_p)
    yscb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yscb)
else:
    import yscb


class TestRestoreAndJitModules(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_jit_modules_")
        self.host_dir = os.path.join(self.test_root, "host")
        self.engine_dir = os.path.join(self.host_dir, "engine")
        os.makedirs(self.host_dir, exist_ok=True)
        os.makedirs(self.engine_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_ft_01_gitignore_soft_merge_and_topology_coexistence(self):
        """FT-01: Verify _generate_internal_gitignore performs soft merge and preserves user rules."""
        # 1. New file creation
        gi_path = os.path.join(self.engine_dir, ".gitignore")
        yscb._generate_internal_gitignore(self.engine_dir)
        self.assertTrue(os.path.isfile(gi_path))
        with open(gi_path, "r", encoding="utf-8") as f:
            c1 = f.read()
        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, c1)
        self.assertIn("/.modules/", c1)
        self.assertIn(yscb.INTERNAL_IGNORE_END, c1)

        # 2. Soft merge when yscb:// == project:// (custom user rules + agents-workflow block)
        custom_header = "# Custom User Rules\n*.log\nnode_modules/\n.env\n\n"
        aw_block = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===\n/.agents/temp/\n# === YSCB AGENTS_WORKFLOW IGNORE END ===\n"
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(custom_header + c1 + "\n" + aw_block)

        # Call again
        yscb._generate_internal_gitignore(self.engine_dir)
        with open(gi_path, "r", encoding="utf-8") as f:
            c2 = f.read()

        self.assertIn("# Custom User Rules", c2)
        self.assertIn("node_modules/", c2)
        self.assertIn(".env", c2)
        self.assertIn(aw_block, c2)
        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, c2)
        self.assertIn("/.modules/", c2)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_BEGIN), 1)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_END), 1)

    def test_ft_02_semantic_uri_resolution_to_dot_modules(self):
        """FT-02: Verify module:// resolves to yscb://.modules/."""
        mod_root = uri.resolve("module://")
        self.assertTrue(mod_root.endswith(".modules") or mod_root.endswith(f".modules{os.sep}"))

        core_mod = uri.resolve("module://core")
        self.assertTrue(core_mod.endswith(os.path.join(".modules", "core")) or core_mod.endswith(os.path.join(".modules", "core") + os.sep))

    def test_ft_03_and_04_restore_and_dirty_detection(self):
        """FT-03 & FT-04: Verify _is_modules_dirty and cmd_restore cycle."""
        provider_dir = os.path.join(self.test_root, "provider")
        os.makedirs(provider_dir, exist_ok=True)

        # Create a mock module zip
        mock_mod_name = "testmod"
        mock_ver = "1.0.0"
        pkg_dir = os.path.join(self.test_root, "src_pkg")
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": mock_mod_name, "version": mock_ver}, f)
        os.makedirs(os.path.join(pkg_dir, "scripts"), exist_ok=True)
        with open(os.path.join(pkg_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        mod_prov_dir = os.path.join(provider_dir, mock_mod_name)
        os.makedirs(mod_prov_dir, exist_ok=True)
        zip_p = os.path.join(mod_prov_dir, f"{mock_ver}.zip")
        with zipfile.ZipFile(zip_p, "w") as zf:
            for root, _, files in os.walk(pkg_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    arcname = os.path.relpath(full_p, pkg_dir)
                    zf.write(full_p, arcname)

        # Configure workspace
        installed = {
            mock_mod_name: {
                "version": mock_ver,
                "provider": provider_dir
            }
        }
        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": installed
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        # Verify dirty detection before restore
        is_dirty, dirty_mods = yscb._is_modules_dirty(self.host_dir, "engine", installed)
        self.assertTrue(is_dirty)
        self.assertIn(mock_mod_name, dirty_mods)

        # Execute restore
        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 0)
        finally:
            os.chdir(orig_cwd)

        # Verify materialized in .modules
        mat_mf = os.path.join(self.engine_dir, ".modules", mock_mod_name, "manifest.json")
        self.assertTrue(os.path.isfile(mat_mf))
        with open(mat_mf, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["version"], mock_ver)

        # Verify Clean state
        is_dirty_after, _ = yscb._is_modules_dirty(self.host_dir, "engine", installed)
        self.assertFalse(is_dirty_after)

    def test_et_01_empty_installed_modules_restore(self):
        """ET-01: Verify cmd_restore handles empty installed_modules safely without crashing."""
        cfg_data = {
            "yscb_root": "engine",
            "installed_modules": {}
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 0)
        finally:
            os.chdir(orig_cwd)

    def test_et_02_corrupted_provider_restore_handling(self):
        """ET-02: Verify restore handles unresolvable provider gracefully."""
        cfg_data = {
            "yscb_root": "engine",
            "installed_modules": {
                "nonexistent": {
                    "version": "9.9.9",
                    "provider": "/invalid/nonexistent/path"
                }
            }
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 1)
        finally:
            os.chdir(orig_cwd)

    def test_pt_01_clean_state_jit_sniff_latency(self):
        """PT-01: Benchmark _is_modules_dirty executes in <2ms under clean state."""
        mod_dir = os.path.join(self.engine_dir, ".modules", "mod_perf")
        os.makedirs(mod_dir, exist_ok=True)
        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "mod_perf", "version": "1.0.0"}, f)

        installed = {"mod_perf": {"version": "1.0.0"}}
        
        # Warmup
        yscb._is_modules_dirty(self.host_dir, "engine", installed)

        # 100 runs benchmark
        t0 = time.perf_counter()
        for _ in range(100):
            dirty, _ = yscb._is_modules_dirty(self.host_dir, "engine", installed)
            self.assertFalse(dirty)
        elapsed_avg_ms = ((time.perf_counter() - t0) / 100) * 1000

        self.assertLess(elapsed_avg_ms, 2.0, f"Average JIT sniff took {elapsed_avg_ms:.3f}ms, exceeding 2ms threshold")


if __name__ == "__main__":
    unittest.main()
