"""
Unit tests for Core PipManager SDK exports and dependency parsing utilities.
Covers FT-01 ~ FT-04, ET-01 ~ ET-02, RT-01.
"""

import os
import sys
import tempfile
import shutil
import unittest

from dev.testing.case import YSCBTestCase


class TestPipManagerSDK(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_pip_sdk_")
        self.custom_yscb_dir = os.path.join(self.test_root, "custom_engine")
        os.makedirs(self.custom_yscb_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_ft_01_core_sdk_export(self):
        """FT-01: Verify from core import PipManager, PipInstallError succeeds and exports match."""
        import core
        self.assertIn("PipManager", core.__all__)
        self.assertIn("PipInstallError", core.__all__)
        self.assertIn("pip_manager", core.__all__)

        from core import PipManager, PipInstallError
        self.assertTrue(callable(PipManager))
        self.assertTrue(issubclass(PipInstallError, RuntimeError))

    def test_ft_02_parse_pip_dependencies_dict(self):
        """FT-02: Verify parse_pip_dependencies handles dictionary specifications correctly."""
        from core import PipManager

        deps = {
            "fastembed": ">=0.5.0",
            "tree-sitter": "",
            "pytest": "==7.4.0",
            "flake8": None,
        }
        specs = PipManager.parse_pip_dependencies(deps)
        expected = ["fastembed>=0.5.0", "tree-sitter", "pytest==7.4.0", "flake8"]
        self.assertEqual(specs, expected)

    def test_ft_03_parse_pip_dependencies_list_and_dedup(self):
        """FT-03: Verify parse_pip_dependencies handles list inputs and performs order-preserving deduplication."""
        from core import PipManager

        raw_list = [
            "fastembed>=0.5.0",
            "tree-sitter",
            "fastembed>=0.5.0",
            "pytest==7.4.0",
            "tree-sitter",
        ]
        specs = PipManager.parse_pip_dependencies(raw_list)
        expected = ["fastembed>=0.5.0", "tree-sitter", "pytest==7.4.0"]
        self.assertEqual(specs, expected)

    def test_et_01_parse_pip_dependencies_edge_cases(self):
        """ET-01: Verify parse_pip_dependencies handles None, non-dict/list, and empty inputs gracefully."""
        from core import PipManager

        self.assertEqual(PipManager.parse_pip_dependencies(None), [])
        self.assertEqual(PipManager.parse_pip_dependencies({}), [])
        self.assertEqual(PipManager.parse_pip_dependencies([]), [])
        self.assertEqual(PipManager.parse_pip_dependencies(12345), [])
        self.assertEqual(PipManager.parse_pip_dependencies("invalid_string"), [])

    def test_et_02_parse_pip_dependencies_whitespace_defense(self):
        """ET-02: Verify whitespace stripping and filtering of empty or whitespace-only keys."""
        from core import PipManager

        deps = {
            "  pkg1  ": "  >=1.0.0  ",
            "   ": ">=2.0.0",
            "pkg2": "   ",
        }
        specs = PipManager.parse_pip_dependencies(deps)
        self.assertEqual(specs, ["pkg1>=1.0.0", "pkg2"])

        list_deps = ["  pkgA>=1.0  ", "   ", "pkgB", ""]
        specs_list = PipManager.parse_pip_dependencies(list_deps)
        self.assertEqual(specs_list, ["pkgA>=1.0", "pkgB"])

    def test_ft_04_pip_manager_custom_root_paths(self):
        """FT-04: Verify PipManager paths correctly reflect custom root directory."""
        from core import PipManager

        mgr = PipManager(self.custom_yscb_dir)
        tag = PipManager.get_current_py_tag()
        self.assertTrue(tag.startswith("py3"))

        venv_dir = mgr.get_venv_dir()
        self.assertEqual(venv_dir, os.path.join(self.custom_yscb_dir, ".venv", tag))

        py_exec = mgr.get_python_executable()
        self.assertTrue(py_exec.startswith(venv_dir))

        site_pkg = mgr.get_site_packages_dir()
        self.assertTrue(site_pkg.startswith(venv_dir))
        self.assertTrue(site_pkg.endswith("site-packages"))

    def test_rt_01_installer_sync_pip_dependencies_integration(self):
        """RT-01: Verify Installer.sync_pip_dependencies executes without regression."""
        from core.installer import Installer
        installer = Installer()
        # Ensure invoking sync_pip_dependencies does not crash
        installer.sync_pip_dependencies()


if __name__ == "__main__":
    unittest.main()
