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
from dev.testing.requirement import require, Requirement


class TestPipManagerSDK(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_pip_sdk_")
        self.custom_yscb_dir = os.path.join(self.test_root, "custom_engine")
        os.makedirs(self.custom_yscb_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_core_sdk_export(self):
        """FT-01: Verify from core import PipManager, PipInstallError succeeds and exports match."""
        import core
        self.assertIn("PipManager", core.__all__)
        self.assertIn("PipInstallError", core.__all__)
        self.assertIn("pip_manager", core.__all__)

        from core import PipManager, PipInstallError
        self.assertTrue(callable(PipManager))
        self.assertTrue(issubclass(PipInstallError, RuntimeError))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_parse_pip_dependencies_dict_and_list_dedup(self):
        """FT-02 & FT-03: Verify parse_pip_dependencies handles dict specifications and list dedup."""
        from core import PipManager

        # 1. Dict parsing
        deps_dict = {
            "fastembed": ">=0.5.0",
            "tree-sitter": "",
            "pytest": "==7.4.0",
            "flake8": None,
        }
        specs_dict = PipManager.parse_pip_dependencies(deps_dict)
        self.assertEqual(specs_dict, ["fastembed>=0.5.0", "tree-sitter", "pytest==7.4.0", "flake8"])

        # 2. List parsing with order-preserving deduplication
        raw_list = [
            "fastembed>=0.5.0",
            "tree-sitter",
            "fastembed>=0.5.0",
            "pytest==7.4.0",
            "tree-sitter",
        ]
        specs_list = PipManager.parse_pip_dependencies(raw_list)
        self.assertEqual(specs_list, ["fastembed>=0.5.0", "tree-sitter", "pytest==7.4.0"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_parse_pip_dependencies_edge_cases_and_whitespace(self):
        """ET-01 & ET-02: Verify invalid types, empty inputs, and whitespace defense."""
        from core import PipManager

        # Edge cases: None, empty, invalid types
        self.assertEqual(PipManager.parse_pip_dependencies(None), [])
        self.assertEqual(PipManager.parse_pip_dependencies({}), [])
        self.assertEqual(PipManager.parse_pip_dependencies([]), [])
        self.assertEqual(PipManager.parse_pip_dependencies(12345), [])
        self.assertEqual(PipManager.parse_pip_dependencies("invalid_string"), [])

        # Whitespace stripping & filtering
        deps = {
            "  pkg1  ": "  >=1.0.0  ",
            "   ": ">=2.0.0",
            "pkg2": "   ",
        }
        self.assertEqual(PipManager.parse_pip_dependencies(deps), ["pkg1>=1.0.0", "pkg2"])

        list_deps = ["  pkgA>=1.0  ", "   ", "pkgB", ""]
        self.assertEqual(PipManager.parse_pip_dependencies(list_deps), ["pkgA>=1.0", "pkgB"])
        self.mark_passed()

    @require(Requirement.LOGIC)
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
        self.mark_passed()

    @require(Requirement.ENV)
    def test_rt_01_installer_sync_pip_dependencies_integration(self):
        """RT-01: Verify Installer.sync_pip_dependencies executes without regression."""
        from core.installer import Installer
        installer = Installer()
        # Ensure invoking sync_pip_dependencies does not crash
        installer.sync_pip_dependencies()
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
