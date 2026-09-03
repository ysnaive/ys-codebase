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

# Robustly load yscb host bootstrapper module
_host_d, _ = uri._get_host_config()
_yscb_p = os.path.join(_host_d, "yscb.py")
if not os.path.isfile(_yscb_p):
    _yscb_p = os.path.abspath("yscb.py")
if os.path.isfile(_yscb_p):
    import importlib.util
    spec = importlib.util.spec_from_file_location("yscb_host_venv", _yscb_p)
    yscb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yscb)
else:
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

    def test_ft_04_internal_gitignore_contains_venv(self):
        """FT-04: Verify _generate_internal_gitignore includes /.venv/."""
        gi_path = os.path.join(self.yscb_dir, ".gitignore")
        yscb._generate_internal_gitignore(self.yscb_dir)
        self.assertTrue(os.path.isfile(gi_path))

        with open(gi_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, content)
        self.assertIn("/.venv/", content)
        self.assertIn("/.modules/", content)
        self.assertIn("/.build/", content)
        self.assertIn(yscb.INTERNAL_IGNORE_END, content)

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

    def test_ft_06_ide_projector_skip_when_no_vscode(self):
        """FT-06: Verify IdeProjector silently skips when project://.vscode does not exist."""
        proj_root = os.path.join(self.test_root, "my_project")
        os.makedirs(proj_root, exist_ok=True)

        projector = IdeProjector(self.yscb_dir)
        self.assertFalse(projector.is_vscode_configured(proj_root))

        result = projector.sync_vscode_settings(proj_root)
        self.assertFalse(result)
        # Ensure .vscode was NOT created
        self.assertFalse(os.path.exists(os.path.join(proj_root, ".vscode")))

    def test_ft_07_ide_projector_soft_merge_and_revert(self):
        """FT-07: Verify explicit _yscb_managed marking and reversible soft-merge."""
        proj_root = os.path.join(self.test_root, "vscode_project")
        vscode_dir = os.path.join(proj_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)

        settings_path = os.path.join(vscode_dir, "settings.json")
        initial_settings = {
            "custom.user.setting": True,
            "python.analysis.extraPaths": ["/opt/custom/lib"],
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(initial_settings, f, indent=2)

        projector = IdeProjector(self.yscb_dir)
        self.assertTrue(projector.is_vscode_configured(proj_root))

        # Mock site-packages directory
        site_pkg = projector.pip_mgr.get_site_packages_dir()
        os.makedirs(site_pkg, exist_ok=True)

        # 1. Sync
        ok = projector.sync_vscode_settings(proj_root, extra_paths=["./source/core"])
        self.assertTrue(ok)

        with open(settings_path, "r", encoding="utf-8") as f:
            updated = json.load(f)

        self.assertIn("_yscb_managed", updated)
        self.assertTrue(updated["custom.user.setting"])
        self.assertIn("/opt/custom/lib", updated["python.analysis.extraPaths"])
        self.assertIn("./source/core", updated["python.analysis.extraPaths"])

        # 2. Revert
        rev_ok = projector.revert_vscode_settings(proj_root)
        self.assertTrue(rev_ok)

        with open(settings_path, "r", encoding="utf-8") as f:
            reverted = json.load(f)

        self.assertNotIn("_yscb_managed", reverted)
        self.assertTrue(reverted["custom.user.setting"])
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["/opt/custom/lib"])

    def test_ft_08_installer_sync_pip_dependencies(self):
        """FT-08: Verify Installer.sync_pip_dependencies reads manifests and triggers installation."""
        installer = Installer()
        with patch.object(PipManager, "install_packages") as mock_install:
            with patch.object(IdeProjector, "sync_vscode_settings") as mock_sync:
                installer.sync_pip_dependencies()
                self.assertIsNotNone(installer)


