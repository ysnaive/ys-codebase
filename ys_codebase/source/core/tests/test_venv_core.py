"""
Unit tests for YSCB private virtual environment (yscb_venv_core).
"""

import io
import os
import platform
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import yscb
from core import uri, vfs
from core.installer import Installer
from core.pip_manager import PipInstallError, PipManager
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.ENV)
class TestVenvCore(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_venv_core_")
        self.yscb_dir = os.path.join(self.test_root, "ys_codebase")
        os.makedirs(self.yscb_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_uri_resolve_yscb_venv(self):
        """Verify yscb.venv:// resolves to yscb_abs/.venv/."""
        resolved = uri.resolve("yscb.venv://")
        self.assertTrue(resolved.endswith(".venv"))
        self.assertTrue(os.path.isabs(resolved))

        resolved_sub = uri.resolve("yscb.venv://py310/site-packages")
        self.assertTrue(resolved_sub.endswith(os.path.join(".venv", "py310", "site-packages")))
        self.mark_passed()

    def test_pip_manager_paths(self):
        """Verify PipManager paths, cross-platform site-packages dirs, and version partitioning."""
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

        cross_dirs = mgr.get_cross_platform_site_packages_dirs("py311")
        self.assertEqual(len(cross_dirs), 2)
        self.assertTrue(any(d.endswith(os.path.join("Lib", "site-packages")) for d in cross_dirs))
        self.assertTrue(any(d.endswith(os.path.join("lib", "python3.11", "site-packages")) for d in cross_dirs))
        self.assertIsInstance(mgr._can_symlink(self.yscb_dir), bool)
        self.mark_passed()

    @patch("subprocess.run")
    def test_install_packages_flags(self, mock_run):
        """Verify Wheel-Only flags and PipInstallError on failure."""
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

    def test_sys_path_injection(self):
        """Verify _ensure_private_venv_path dynamically injects site-packages."""
        mgr = PipManager(self.yscb_dir)
        site_dir = mgr.get_site_packages_dir()
        os.makedirs(site_dir, exist_ok=True)

        snap = list(sys.path)
        try:
            if site_dir in sys.path:
                sys.path.remove(site_dir)

            yscb._ensure_private_venv_path(self.yscb_dir)
            self.assertIn(site_dir, sys.path)
            self.assertEqual(sys.path[0], site_dir)
        finally:
            sys.path[:] = snap
        self.mark_passed()

    def test_installer_sync_pip_dependencies(self):
        """驗證 Installer.sync_pip_dependencies 實質讀取 manifest 之 pip_dependencies 並發起安裝與廣播 on_env_synced 事件。"""
        installer = Installer()
        mod_name = "mock_pip_mod"
        vfs.makedirs(f"module://{mod_name}", exist_ok=True)
        vfs.write_json(f"module://{mod_name}/manifest.json", {
            "name": mod_name,
            "version": "1.0.0",
            "pip_dependencies": {
                "pkg_alpha": ">=1.2.0",
                "pkg_beta": ""
            }
        })

        cfg_path, cfg = installer.engine._get_config()
        orig_installed = dict(cfg.get("installed_modules", {}))
        cfg["installed_modules"] = {mod_name: {"version": "1.0.0"}}
        installer.engine._save_config(cfg_path, cfg)

        try:
            with patch.object(PipManager, "install_packages") as mock_install:
                with patch("core.events.broadcast") as mock_broadcast:
                    mock_install.return_value = True
                    installer.sync_pip_dependencies()
                    mock_install.assert_called_once_with(["pkg_alpha>=1.2.0", "pkg_beta"])
                    mock_broadcast.assert_called_once()
                    self.assertEqual(mock_broadcast.call_args[0][0], "on_env_synced")
        finally:
            cfg["installed_modules"] = orig_installed
            installer.engine._save_config(cfg_path, cfg)
            if vfs.exists(f"module://{mod_name}"):
                vfs.rmtree(f"module://{mod_name}")

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

    def test_ensure_venv_and_bootstrap_pip_raise_pip_install_error(self):
        """驗證 _bootstrap_pip 與 ensure_venv 失敗時統一拋出 PipInstallError、pyvenv.cfg 加固、預置 wheel 解壓，且 sync_pip_dependencies 降級為 Warning。"""
        mgr = PipManager(self.yscb_dir)
        venv_dir = mgr.get_venv_dir("py999")
        site_pkg = mgr.get_site_packages_dir("py999")
        py_exec = mgr.get_python_executable("py999")

        # 0. _bootstrap_pip 透過 ensurepip _bundled wheel 解壓成功分支
        fake_whl_dir = os.path.join(self.test_root, "fake_ensurepip_bundled")
        os.makedirs(fake_whl_dir, exist_ok=True)
        fake_whl_path = os.path.join(fake_whl_dir, "pip-24.0-py3-none-any.whl")
        with zipfile.ZipFile(fake_whl_path, "w") as zf:
            zf.writestr("pip/__init__.py", "__version__ = '24.0'\n")
        fake_ensurepip = MagicMock()
        fake_ensurepip.__file__ = os.path.join(self.test_root, "__init__.py")
        os.makedirs(os.path.join(self.test_root, "_bundled"), exist_ok=True)
        shutil.copy2(fake_whl_path, os.path.join(self.test_root, "_bundled", "pip-24.0-py3-none-any.whl"))
        with patch("subprocess.run", side_effect=OSError("ensurepip subprocess disabled")):
            with patch.dict("sys.modules", {"ensurepip": fake_ensurepip}):
                mgr._bootstrap_pip(venv_dir, site_pkg, py_exec)
        self.assertTrue(os.path.isdir(os.path.join(site_pkg, "pip")))

        # ensure_venv 已存在 py_exec 時自動加固 pyvenv.cfg (include-system-site-packages = true -> false)
        os.makedirs(os.path.dirname(py_exec), exist_ok=True)
        with open(py_exec, "w", encoding="utf-8") as f:
            f.write("")
        cfg_file = os.path.join(venv_dir, "pyvenv.cfg")
        with open(cfg_file, "w", encoding="utf-8") as f:
            f.write("home = /usr/bin\ninclude-system-site-packages = true\n")
        mgr.ensure_venv("py999")
        with open(cfg_file, "r", encoding="utf-8") as f:
            self.assertIn("include-system-site-packages = false", f.read())
        shutil.rmtree(venv_dir, ignore_errors=True)
        shutil.rmtree(os.path.join(self.test_root, "_bundled"), ignore_errors=True)

        # 1. _bootstrap_pip 失敗應拋出 PipInstallError
        with patch("subprocess.run", side_effect=OSError("ensurepip missing")):
            with patch.dict("sys.modules", {"ensurepip": None}):
                with self.assertRaises(PipInstallError) as ctx:
                    mgr._bootstrap_pip(venv_dir, site_pkg, py_exec)
                self.assertIn("Failed to bootstrap pip", str(ctx.exception))

        # 2. ensure_venv 當 EnvBuilder.create 失敗時亦拋出 PipInstallError
        with patch("venv.EnvBuilder.create", side_effect=OSError("venv creation blocked")):
            with self.assertRaises(PipInstallError) as ctx2:
                mgr.ensure_venv("py999")
            self.assertIn("Failed to create private venv", str(ctx2.exception))

        # 3. Installer.sync_pip_dependencies 攔截 ensure_venv 拋出之 PipInstallError 並降級為 Warning
        installer = Installer()
        mod_name = "mock_no_ensurepip_mod"
        vfs.makedirs(f"module://{mod_name}", exist_ok=True)
        vfs.write_json(f"module://{mod_name}/manifest.json", {
            "name": mod_name,
            "version": "1.0.0",
            "pip_dependencies": {"some_pkg": ">=1.0.0"}
        })
        cfg_path, cfg = installer.engine._get_config()
        orig_installed = dict(cfg.get("installed_modules", {}))
        cfg["installed_modules"] = {mod_name: {"version": "1.0.0"}}
        installer.engine._save_config(cfg_path, cfg)
        try:
            with patch.object(PipManager, "ensure_venv", side_effect=PipInstallError("[PipManager] no ensurepip")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    installer.sync_pip_dependencies()
                self.assertIn("[core:pip] Warning: [PipManager] no ensurepip", buf.getvalue())
        finally:
            cfg["installed_modules"] = orig_installed
            installer.engine._save_config(cfg_path, cfg)
            if vfs.exists(f"module://{mod_name}"):
                vfs.rmtree(f"module://{mod_name}")

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
