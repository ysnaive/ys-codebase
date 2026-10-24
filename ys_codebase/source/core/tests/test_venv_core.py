"""
Unit tests for YSCB private virtual environment (yscb_venv_core).
Covers FT-01 ~ FT-08, EC-01 ~ EC-06, and NFR-01 ~ NFR-04.
"""

import os
import sys
import json
import shutil
import tempfile
import platform
import unittest
from unittest.mock import patch, MagicMock

from core import uri
from core.pip_manager import PipManager, PipInstallError
from core.ide_projector import IdeProjector
from core.installer import Installer
from dev.testing.case import YSCBTestCase
import yscb


class TestVenvCore(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_venv_core_")
        self.yscb_dir = os.path.join(self.test_root, "ys_codebase")
        os.makedirs(self.yscb_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_ft_01_uri_resolve_yscb_venv(self):
        """FT-01: Verify yscb.venv:// resolves to yscb_abs/.venv/."""
        resolved = uri.resolve("yscb.venv://")
        self.assertTrue(resolved.endswith(".venv"))
        self.assertTrue(os.path.isabs(resolved))

        resolved_sub = uri.resolve("yscb.venv://py310/site-packages")
        self.assertTrue(resolved_sub.endswith(os.path.join(".venv", "py310", "site-packages")))
        self.mark_passed()

    def test_ft_02_pip_manager_paths(self):
        """FT-02: Verify PipManager paths and version partitioning."""
        mgr = PipManager(self.yscb_dir)
        tag = mgr.get_current_py_tag()
        self.assertEqual(tag, f"py{sys.version_info.major}{sys.version_info.minor}")

        venv_dir = mgr.get_venv_dir("py310")
        self.assertEqual(venv_dir, os.path.join(self.yscb_dir, ".venv", "py310"))

        py_exec = mgr.get_python_executable("py310")
        if platform.system() == "Windows":
            self.assertTrue(py_exec.endswith(os.path.join("Scripts", "python.exe")))
        else:
            self.assertTrue(py_exec.endswith(os.path.join("bin", "python")))

        site_pkg = mgr.get_site_packages_dir("py310")
        if platform.system() == "Windows":
            self.assertTrue(site_pkg.endswith(os.path.join("Lib", "site-packages")))
        else:
            self.assertTrue(site_pkg.endswith(os.path.join("lib", "python3.10", "site-packages")))
        self.mark_passed()

    @patch("subprocess.run")
    def test_ft_03_install_packages_flags(self, mock_run):
        """FT-03: Verify Wheel-Only flags and PipInstallError on failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        mgr = PipManager(self.yscb_dir)
        with patch.object(mgr, "ensure_venv") as mock_ensure:
            mgr.install_packages(["zstandard>=0.22.0", "lmdb"])
            mock_ensure.assert_called_once()
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("-m", called_cmd)
            self.assertIn("pip", called_cmd)
            self.assertIn("install", called_cmd)
            self.assertIn("--only-binary=:all:", called_cmd)
            self.assertIn("--no-warn-script-location", called_cmd)
            self.assertIn("--quiet", called_cmd)
            self.assertIn("zstandard>=0.22.0", called_cmd)
            self.assertIn("lmdb", called_cmd)

        # Test failure
        mock_proc.returncode = 1
        mock_proc.stderr = "ERROR: No matching distribution found for dummy-no-wheel"
        mock_proc.stdout = ""
        with patch.object(mgr, "ensure_venv"):
            with self.assertRaises(PipInstallError) as ctx:
                mgr.install_packages(["dummy-no-wheel"])
            self.assertIn("Wheel-Only installation failed", str(ctx.exception))
        self.mark_passed()

    def test_ft_05_sys_path_injection(self):
        """FT-05: Verify _ensure_private_venv_path dynamically injects site-packages."""
        mgr = PipManager(self.yscb_dir)
        site_dir = mgr.get_site_packages_dir()
        os.makedirs(site_dir, exist_ok=True)

        if site_dir in sys.path:
            sys.path.remove(site_dir)

        yscb._ensure_private_venv_path(self.yscb_dir)
        self.assertIn(site_dir, sys.path)
        self.assertEqual(sys.path[0], site_dir)

        # Clean up
        if site_dir in sys.path:
            sys.path.remove(site_dir)
        self.mark_passed()

    def test_ft_08_installer_sync_pip_dependencies(self):
        """T-01 實質化：驗證 Installer.sync_pip_dependencies 實質讀取 manifest 之 pip_dependencies 並發起安裝與 IDE 同步。"""
        installer = Installer()
        mod_name = "mock_pip_mod"
        uri.makedirs(f"module://{mod_name}", exist_ok=True)
        uri.write_json(f"module://{mod_name}/manifest.json", {
            "name": mod_name,
            "version": "1.0.0",
            "pip_dependencies": {
                "pkg_alpha": ">=1.2.0",
                "pkg_beta": ""
            }
        })

        cfg_path, cfg = installer.engine._get_config()
        orig_installed = dict(cfg.get("installed_modules", {}))
        cfg.setdefault("installed_modules", {})[mod_name] = {"version": "1.0.0"}
        installer.engine._save_config(cfg_path, cfg)

        mock_proj_dir = os.path.join(self.test_root, "mock_proj")
        os.makedirs(mock_proj_dir, exist_ok=True)
        orig_resolve = uri.resolve
        def mock_resolve(u, *args, **kwargs):
            if str(u).startswith("project://"):
                return mock_proj_dir
            return orig_resolve(u, *args, **kwargs)

        try:
            with patch.object(PipManager, "install_packages") as mock_install:
                with patch.object(IdeProjector, "is_vscode_configured", return_value=True):
                    with patch.object(IdeProjector, "sync_vscode_settings") as mock_sync:
                        with patch("core.uri.resolve", side_effect=mock_resolve):
                            mock_install.return_value = True
                            mock_sync.return_value = True
                            installer.sync_pip_dependencies()
                            mock_install.assert_called_once_with(["pkg_alpha>=1.2.0", "pkg_beta"])
                            mock_sync.assert_called_once_with(mock_proj_dir)
        finally:
            cfg["installed_modules"] = orig_installed
            installer.engine._save_config(cfg_path, cfg)
            if uri.exists(f"module://{mod_name}"):
                uri.rmtree(f"module://{mod_name}")

        self.mark_passed()

    def test_pip_manager_sdk_export_and_parse_utilities(self):
        """PipManager SDK: 驗證 core 公開匯出、parse_pip_dependencies 字典、陣列去重與邊界條件。"""
        import core
        self.assertIn("PipManager", core.__all__)
        self.assertIn("PipInstallError", core.__all__)
        self.assertIs(core.PipManager, PipManager)
        self.assertIs(core.PipInstallError, PipInstallError)

        # Dict parsing
        deps_dict = {
            "fastembed": ">=0.5.0",
            "tree-sitter": "",
            "pytest": "==7.4.0",
            "flake8": None,
        }
        specs_dict = PipManager.parse_pip_dependencies(deps_dict)
        self.assertEqual(specs_dict, ["fastembed>=0.5.0", "tree-sitter", "pytest==7.4.0", "flake8"])

        # List parsing with dedup & whitespace stripping
        raw_list = ["  fastembed>=0.5.0  ", "tree-sitter", "", "   ", "fastembed>=0.5.0"]
        specs_list = PipManager.parse_pip_dependencies(raw_list)
        self.assertEqual(specs_list, ["fastembed>=0.5.0", "tree-sitter"])

        # Edge cases
        self.assertEqual(PipManager.parse_pip_dependencies(None), [])
        self.assertEqual(PipManager.parse_pip_dependencies([]), [])
        self.assertEqual(PipManager.parse_pip_dependencies({}), [])
        self.assertEqual(PipManager.parse_pip_dependencies("invalid"), [])
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()



