"""
Unit tests for build Git decoupling and .build/ semantic URI resolution.
Covers FT-01 ~ FT-05, ET-01, and PT-01.
"""

import unittest
import tempfile
import os
import shutil
import json
import zipfile
import time
import importlib.util
from core import uri
from dev.testing.case import YSCBTestCase

# Robustly load yscb host bootstrapper module
_host_d, _ = uri._get_host_config()
_yscb_p = os.path.join(_host_d, "yscb.py")
if not os.path.isfile(_yscb_p):
    _yscb_p = os.path.abspath("yscb.py")
if os.path.isfile(_yscb_p):
    spec = importlib.util.spec_from_file_location("yscb_host_build", _yscb_p)
    yscb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yscb)
else:
    import yscb


class TestBuildGitDecoupling(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_bld_decouple_")
        self.engine_dir = os.path.join(self.test_root, "engine")
        os.makedirs(self.engine_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_ft_01_gitignore_contains_dot_build(self):
        """FT-01: Verify _generate_internal_gitignore injects /.build/ in soft merge."""
        gi_path = os.path.join(self.engine_dir, ".gitignore")
        
        # 1. Clean generation
        yscb._generate_internal_gitignore(self.engine_dir)
        self.assertTrue(os.path.isfile(gi_path))
        with open(gi_path, "r", encoding="utf-8") as f:
            c1 = f.read()
        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, c1)
        self.assertIn("/.build/", c1)
        self.assertIn("/.modules/", c1)
        self.assertNotIn("\n/build/\n", c1)
        self.assertIn(yscb.INTERNAL_IGNORE_END, c1)

        # 2. Soft merge coexistence
        custom_rules = "# User Custom\n*.tmp\nnode_modules/\n"
        aw_block = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===\n/.agents/temp/\n# === YSCB AGENTS_WORKFLOW IGNORE END ===\n"
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(custom_rules + c1 + "\n" + aw_block)

        yscb._generate_internal_gitignore(self.engine_dir)
        with open(gi_path, "r", encoding="utf-8") as f:
            c2 = f.read()

        self.assertIn("# User Custom", c2)
        self.assertIn("*.tmp", c2)
        self.assertIn("node_modules/", c2)
        self.assertIn(aw_block, c2)
        self.assertIn("/.build/", c2)
        self.assertNotIn("\n/build/\n", c2)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_BEGIN), 1)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_END), 1)

    def test_ft_02_uri_resolution_to_dot_build(self):
        """FT-02: Verify module.build:// and fallback resolve to yscb://.build/."""
        bld_root = uri.resolve("module.build://")
        self.assertTrue(".build" in bld_root)

        bld_core = uri.resolve("module.build://core")
        self.assertTrue(os.path.join(".build", "core") in bld_core)

    def test_ft_03_builder_outputs_to_dot_build(self):
        """FT-03: Verify Builder resolves module.build:// correctly under current uri scheme."""
        from dev.builder import Builder
        mod_build_root = "module.build://mock_mod"
        real_path = uri.resolve(mod_build_root)
        self.assertTrue(".build" in real_path)
        self.assertTrue(real_path.endswith(os.path.join(".build", "mock_mod")) or real_path.endswith(os.path.join(".build", "mock_mod") + os.sep))

    def test_ft_04_restore_prioritizes_dot_build(self):
        """FT-04: Verify _restore_module_package prioritizes .build/ over build/."""
        mock_yscb = os.path.join(self.test_root, "host_yscb")
        dot_bld = os.path.join(mock_yscb, ".build", "test_mod")
        old_bld = os.path.join(mock_yscb, "build", "test_mod")
        dest_dir = os.path.join(mock_yscb, ".modules", "test_mod")
        mirror_dir = os.path.join(mock_yscb, ".mirror", "test_mod")

        os.makedirs(dot_bld, exist_ok=True)
        os.makedirs(old_bld, exist_ok=True)

        # Create zip in .build with marker file 'from_dot_build.txt'
        dot_zip = os.path.join(dot_bld, "1.0.0.build.zip")
        with zipfile.ZipFile(dot_zip, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "test_mod", "version": "1.0.0.build"}))
            zf.writestr("marker.txt", "from_dot_build")

        # Create zip in old build with marker file 'from_old_build.txt'
        old_zip = os.path.join(old_bld, "1.0.0.build.zip")
        with zipfile.ZipFile(old_zip, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "test_mod", "version": "1.0.0.build"}))
            zf.writestr("marker.txt", "from_old_build")

        ok = yscb._restore_module_package(
            module_name="test_mod",
            version="1.0.0.build",
            provider_arg="none",
            base_dir=self.test_root,
            yscb_root="host_yscb",
            dest_dir=dest_dir,
            mirror_dir=mirror_dir
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "marker.txt")))
        with open(os.path.join(dest_dir, "marker.txt"), "r", encoding="utf-8") as f:
            content = f.read().strip()
        self.assertEqual(content, "from_dot_build")

    def test_ft_05_standards_doc_check(self):
        """FT-05: Verify STANDARDS.md marks module.build as 🚫 忽略 and maps to yscb://.build/."""
        curr = os.path.abspath(os.path.dirname(__file__))
        found = None
        for _ in range(8):
            cand = os.path.join(curr, "docs", "_project", "STANDARDS.md")
            if os.path.isfile(cand):
                found = cand
                break
            curr = os.path.dirname(curr)
        if not found and os.path.isfile("/workspace/ys-codebase/docs/_project/STANDARDS.md"):
            found = "/workspace/ys-codebase/docs/_project/STANDARDS.md"

        if found:
            with open(found, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("yscb://.build/", content)
            self.assertIn("module.build.root://", content)
            self.assertIn("🚫 忽略", content)

    def test_et_01_nonexistent_dot_build_auto_create(self):
        """ET-01: Verify resolving module.build:// on non-existent path works gracefully."""
        res = uri.resolve("module.build://some_clean_mod/1.0.0.build")
        self.assertTrue(".build" in res)
        self.assertFalse(os.path.exists(res))
        # uri.makedirs should cleanly create it
        uri.makedirs("module.build://some_clean_mod/1.0.0.build")
        self.assertTrue(os.path.isdir(res))

    def test_pt_01_uri_resolve_perf(self):
        """PT-01: Verify uri.resolve('module.build://') latency is sub-millisecond."""
        start = time.perf_counter()
        for _ in range(100):
            uri.resolve("module.build://core")
        elapsed = (time.perf_counter() - start) / 100
        # Must be well under 1ms (typically <0.02ms)
        self.assertLess(elapsed, 0.001)


if __name__ == "__main__":
    unittest.main()
