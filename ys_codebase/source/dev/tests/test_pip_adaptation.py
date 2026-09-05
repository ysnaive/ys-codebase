"""
Test suite for pip adaptation and 3-tier virtual environment projection in dev toolchain.
Covers FT-01, FT-02, FT-03, ET-01, ET-02, and FT-04.
"""
import os
import sys
import json
import shutil
import tempfile
import zipfile
import unittest
from unittest.mock import patch, MagicMock

from dev.testing import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner, SandboxContext
from dev.checker import Checker, CheckSeverity, CheckReport
from core import uri, PipManager


class TestPipAdaptationAndProjection(YSCBTestCase):

    def setUp(self):
        super().setUp()
        self.temp_dirs = []

    def tearDown(self):
        super().tearDown()
        for d in self.temp_dirs:
            if os.path.lexists(d):
                try:
                    if os.path.islink(d):
                        os.unlink(d)
                    else:
                        shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

    def _mkdtemp(self) -> str:
        d = tempfile.mkdtemp()
        self.temp_dirs.append(d)
        return d

    @require(Requirement.LOGIC)
    def test_adapt_build_pip_dependencies(self):
        """FT-01: Verify adapt_build_pip_dependencies extracts specs from build zip and manifest."""
        temp_dir = self._mkdtemp()
        mod_name = "test_pip_mod"
        build_mod_dir = os.path.join(temp_dir, mod_name)
        os.makedirs(build_mod_dir, exist_ok=True)

        manifest_data = {
            "name": mod_name,
            "version": "1.0.0",
            "entry": "scripts/cli.py",
            "dependencies": ["core"],
            "pip_dependencies": {
                "mock-pkg-a": ">=1.0.0",
                "mock-pkg-b": ""
            }
        }
        zip_path = os.path.join(build_mod_dir, "1.0.0.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))

        orig_exists = uri.exists
        orig_resolve = uri.resolve

        def mock_exists(u: str) -> bool:
            if u == "module.build://":
                return True
            return orig_exists(u)

        def mock_resolve(u: str) -> str:
            if u == "module.build://":
                return temp_dir
            return orig_resolve(u)

        with patch("core.uri.exists", side_effect=mock_exists), \
             patch("core.uri.resolve", side_effect=mock_resolve), \
             patch.object(PipManager, "install_packages") as mock_install:

            specs = SandboxProvisioner.adapt_build_pip_dependencies(target_modules=[mod_name], quiet=True)
            self.assertEqual(specs, ["mock-pkg-a>=1.0.0", "mock-pkg-b"])
            mock_install.assert_called_once_with(["mock-pkg-a>=1.0.0", "mock-pkg-b"])

            # Test non-existent module has no specs
            empty_specs = SandboxProvisioner.adapt_build_pip_dependencies(target_modules=["non_existent"], quiet=True)
            self.assertEqual(empty_specs, [])

        self.mark_passed()

    @require(Requirement.ENV)
    def test_sandbox_venv_projection(self):
        """FT-02: Verify _project_venv creates cross-platform venv projection into sandbox engine/.venv."""
        host_dir = self._mkdtemp()
        sb_engine_dir = self._mkdtemp()

        host_venv = os.path.join(host_dir, ".venv")
        os.makedirs(host_venv, exist_ok=True)
        canary_file = os.path.join(host_venv, "canary.txt")
        with open(canary_file, "w", encoding="utf-8") as f:
            f.write("canary_content")

        res = SandboxProvisioner._project_venv(host_dir, sb_engine_dir)
        self.assertTrue(res)

        sb_venv = os.path.join(sb_engine_dir, ".venv")
        self.assertTrue(os.path.exists(sb_venv))
        sb_canary = os.path.join(sb_venv, "canary.txt")
        self.assertTrue(os.path.isfile(sb_canary))
        with open(sb_canary, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "canary_content")

        SandboxProvisioner._unlink_projected_venv(sb_engine_dir)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_sandbox_import_from_projected_venv(self):
        """FT-03: Verify sandbox environment can resolve package files from projected venv."""
        host_dir = self._mkdtemp()
        sb_engine_dir = self._mkdtemp()

        pm_host = PipManager(host_dir)
        site_pkg = pm_host.get_site_packages_dir()
        mock_pkg_dir = os.path.join(site_pkg, "dummy_projected_mod")
        os.makedirs(mock_pkg_dir, exist_ok=True)
        init_py = os.path.join(mock_pkg_dir, "__init__.py")
        with open(init_py, "w", encoding="utf-8") as f:
            f.write("FLAG = 'PROJECTED_SUCCESS'\n")

        res = SandboxProvisioner._project_venv(host_dir, sb_engine_dir)
        self.assertTrue(res)

        pm_sb = PipManager(sb_engine_dir)
        sb_site_pkg = pm_sb.get_site_packages_dir()
        sb_mod_init = os.path.join(sb_site_pkg, "dummy_projected_mod", "__init__.py")
        self.assertTrue(os.path.isfile(sb_mod_init))
        with open(sb_mod_init, "r", encoding="utf-8") as f:
            self.assertIn("PROJECTED_SUCCESS", f.read())

        SandboxProvisioner._unlink_projected_venv(sb_engine_dir)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sandbox_venv_pth_fallback(self):
        """ET-01: Verify venv projection falls back to .pth when junction/symlink fails."""
        host_dir = self._mkdtemp()
        sb_engine_dir = self._mkdtemp()

        host_venv = os.path.join(host_dir, ".venv")
        os.makedirs(host_venv, exist_ok=True)
        pm_host = PipManager(host_dir)
        host_site_pkg = pm_host.get_site_packages_dir()
        os.makedirs(host_site_pkg, exist_ok=True)

        def mock_create_junction(*args, **kwargs):
            raise OSError("Access denied")

        def mock_symlink(*args, **kwargs):
            raise OSError("Not supported")

        patches = [patch("os.symlink", side_effect=mock_symlink)]
        try:
            import _winapi
            patches.append(patch("_winapi.CreateJunction", side_effect=mock_create_junction))
        except ImportError:
            pass

        for p in patches:
            p.start()

        try:
            res = SandboxProvisioner._project_venv(host_dir, sb_engine_dir)
            self.assertTrue(res)

            pm_sb = PipManager(sb_engine_dir)
            sb_site_pkg = pm_sb.get_site_packages_dir()
            pth_file = os.path.join(sb_site_pkg, "host_venv.pth")
            self.assertTrue(os.path.isfile(pth_file))
            with open(pth_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertEqual(content, host_site_pkg)
        finally:
            for p in patches:
                p.stop()

        self.mark_passed()

    @require(Requirement.ENV)
    def test_cleanup_sandbox_protects_host_venv(self):
        """ET-02: Verify cleanup_sandbox unlinks projected venv without deleting host venv contents."""
        host_dir = self._mkdtemp()
        host_venv = os.path.join(host_dir, ".venv")
        os.makedirs(host_venv, exist_ok=True)
        canary_file = os.path.join(host_venv, "canary_host.txt")
        with open(canary_file, "w", encoding="utf-8") as f:
            f.write("host_data_alive")

        sb_dir = self._mkdtemp()
        sb_host = os.path.join(sb_dir, "host_env")
        sb_engine = os.path.join(sb_host, "engine")
        os.makedirs(sb_engine, exist_ok=True)

        res = SandboxProvisioner._project_venv(host_dir, sb_engine)
        self.assertTrue(res)

        cleaned = SandboxProvisioner.cleanup_sandbox(sb_dir, force=True)
        self.assertTrue(cleaned)
        self.assertFalse(os.path.exists(sb_dir))

        self.assertTrue(os.path.isdir(host_venv))
        self.assertTrue(os.path.isfile(canary_file))
        with open(canary_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "host_data_alive")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_checker_pip_dependencies_validation(self):
        """FT-04: Verify Checker correctly validates pip_dependencies structure."""
        checker = Checker()

        # 1. Valid pip_dependencies
        valid_m = {
            "name": "mod_valid",
            "version": "1.0.0.0",
            "entry": "scripts/cli.py",
            "dependencies": ["core"],
            "pip_dependencies": {
                "package-a": ">=1.0.0",
                "package-b": None,
                "package-c": ""
            }
        }
        report = CheckReport(module="mod_valid")
        checker._check_pip_dependencies("mod_valid", valid_m, report)
        self.assertFalse(report.has_fails)
        self.assertEqual(len(report.errors), 0)

        # 2. Invalid: pip_dependencies is not a dict (e.g. list)
        invalid_list = {
            "name": "mod_list",
            "pip_dependencies": ["package-a"]
        }
        report_list = CheckReport(module="mod_list")
        checker._check_pip_dependencies("mod_list", invalid_list, report_list)
        self.assertTrue(report_list.has_fails)
        self.assertTrue(any("must be an object" in e for e in report_list.errors))

        # 3. Invalid: package name is empty or whitespace
        invalid_pkg = {
            "name": "mod_pkg",
            "pip_dependencies": {
                "": ">=1.0.0"
            }
        }
        report_pkg = CheckReport(module="mod_pkg")
        checker._check_pip_dependencies("mod_pkg", invalid_pkg, report_pkg)
        self.assertTrue(report_pkg.has_fails)
        self.assertTrue(any("Invalid package name" in e for e in report_pkg.errors))

        # 4. Invalid: constraint is non-string (e.g. int)
        invalid_spec = {
            "name": "mod_spec",
            "pip_dependencies": {
                "package-a": 123
            }
        }
        report_spec = CheckReport(module="mod_spec")
        checker._check_pip_dependencies("mod_spec", invalid_spec, report_spec)
        self.assertTrue(report_spec.has_fails)
        self.assertTrue(any("Invalid version specification" in e for e in report_spec.errors))

        self.mark_passed()
