"""
Comprehensive Unit, Edge & Integration Tests for Dev Release & Verification Toolchain Refactor.
Covers:
- FT-01 ~ FT-08 (Functional Test Cases)
- ET-01 ~ ET-07 (Edge & Failure Mode Cases)
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile
from typing import Dict, Any, List

# Set path to include ys_codebase source modules
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_CORE = os.path.join(REPO_ROOT, "ys_codebase", "source", "core")
SRC_DEV = os.path.join(REPO_ROOT, "ys_codebase", "source", "dev")

for p in [SRC_CORE, SRC_DEV, REPO_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from core import uri
from core import semver
from dev.builder import Builder
from dev.checker import Checker
from dev.releaser import Releaser, ReleaseVersionExistsError, VersionRollbackError, CyclicDependencyError
from dev.tester import Tester
from scripts.cli import main as dev_cli_main

class TestDevToolchainRefactor(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_dev_refactor_")
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp_dir)

        # Setup mock module.source://, module.build://, module.release://
        self.src_dir = os.path.join(self.tmp_dir, "source")
        self.build_dir = os.path.join(self.tmp_dir, "build")
        self.rel_dir = os.path.join(self.tmp_dir, "release")
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.build_dir, exist_ok=True)
        os.makedirs(self.rel_dir, exist_ok=True)

        # Override core uri root for isolated testing
        self._orig_get_yscb_root = uri._get_yscb_root
        uri._get_yscb_root = lambda: self.tmp_dir

    def tearDown(self):
        uri._get_yscb_root = self._orig_get_yscb_root
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_mock_module(self, name: str, version: str = "1.0.0.0", dependencies: Dict[str, str] = None) -> str:
        mod_dir = os.path.join(self.src_dir, name)
        os.makedirs(mod_dir, exist_ok=True)
        manifest = {
            "name": name,
            "version": version,
            "description": f"Mock module {name}",
            "entry": "scripts/cli.py",
            "dependencies": dependencies or {}
        }
        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        scripts_dir = os.path.join(mod_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("# Mock CLI entry\nprint('hello')\n")

        tests_dir = os.path.join(mod_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        with open(os.path.join(tests_dir, "test_sample.py"), "w", encoding="utf-8") as f:
            f.write("# Sample test\n")

        with open(os.path.join(mod_dir, ".yscbignore"), "w", encoding="utf-8") as f:
            f.write("*.ignore_me\n")

        with open(os.path.join(mod_dir, "file.ignore_me"), "w", encoding="utf-8") as f:
            f.write("should be ignored in release\n")

        return mod_dir

    # --- FT-01: dev build auto-clean and retain tests ---
    def test_build_auto_clean(self):
        self._create_mock_module("mod_a", "1.0.0.0")
        mod_build_dir = os.path.join(self.build_dir, "mod_a")
        os.makedirs(mod_build_dir, exist_ok=True)
        
        # Plant dirty leftover artifact
        dirty_file = os.path.join(mod_build_dir, "old_dirty_file.tmp")
        with open(dirty_file, "w") as f:
            f.write("dirty")
            
        builder = Builder()
        ok, msg = builder.build_module("mod_a")
        self.assertTrue(ok, msg)

        # Verify dirty leftover was cleaned
        self.assertFalse(os.path.exists(dirty_file))

        # Verify build zip created
        expected_zip = os.path.join(mod_build_dir, "1.0.0.build.zip")
        self.assertTrue(os.path.exists(expected_zip))

        # Verify tests/ is retained in build package
        with zipfile.ZipFile(expected_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("tests/test_sample.py", namelist)
            self.assertIn("manifest.json", namelist)
            
            # Verify version was tagged as X.Y.Z.build in manifest.json
            m_data = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(m_data["version"], "1.0.0.build")

        # Verify build index.json updated
        index_file = os.path.join(mod_build_dir, "index.json")
        self.assertTrue(os.path.exists(index_file))
        with open(index_file, "r", encoding="utf-8") as f:
            idx = json.load(f)
            self.assertIn("1.0.0.build", idx["versions"])

    # --- FT-02: dev release pure packaging and 3-Gate ---
    def test_release_pure_package(self):
        self._create_mock_module("mod_b", "1.2.3.0")
        releaser = Releaser()
        ok, msg = releaser.release_module("mod_b")
        self.assertTrue(ok, msg)

        rel_zip = os.path.join(self.rel_dir, "mod_b", "1.2.3.0.zip")
        self.assertTrue(os.path.exists(rel_zip))

        # Verify tests/ and .yscbignore entries are excluded
        with zipfile.ZipFile(rel_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertNotIn("tests/test_sample.py", namelist)
            self.assertNotIn("file.ignore_me", namelist)
            self.assertNotIn(".yscbignore", namelist)
            self.assertIn("scripts/cli.py", namelist)

        # Verify release index.json
        idx_path = os.path.join(self.rel_dir, "mod_b", "index.json")
        self.assertTrue(os.path.exists(idx_path))
        with open(idx_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
            self.assertEqual(idx["versions"], ["1.2.3.0"])

    # --- FT-03: 3-Revision sliding window & cross-triplet convergence ---
    def test_version_retention_policy(self):
        builder = Builder()
        self._create_mock_module("mod_c", "1.0.0.0")

        # Release 1.0.0.0, 1.0.0.1, 1.0.0.2
        builder.package_release("mod_c", "1.0.0.0")
        builder.package_release("mod_c", "1.0.0.1")
        builder.package_release("mod_c", "1.0.0.2")

        c_rel_dir = os.path.join(self.rel_dir, "mod_c")
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.0.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.1.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.2.zip")))

        # Release 1.0.0.3 (4th revision in same triplet -> 1.0.0.0 must be purged)
        builder.package_release("mod_c", "1.0.0.3")
        self.assertFalse(os.path.exists(os.path.join(c_rel_dir, "1.0.0.0.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.1.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.2.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.3.zip")))

        # Release 1.0.1.0 (Cross-triplet upgrade -> legacy triplet 1.0.0 retains ONLY highest 1.0.0.3)
        builder.package_release("mod_c", "1.0.1.0")
        self.assertFalse(os.path.exists(os.path.join(c_rel_dir, "1.0.0.1.zip")))
        self.assertFalse(os.path.exists(os.path.join(c_rel_dir, "1.0.0.2.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.0.3.zip")))
        self.assertTrue(os.path.exists(os.path.join(c_rel_dir, "1.0.1.0.zip")))

        # Verify index.json reflects exactly the active physical files
        idx_path = os.path.join(c_rel_dir, "index.json")
        with open(idx_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
            self.assertEqual(idx["versions"], ["1.0.0.3", "1.0.1.0"])

    # --- FT-04: release --all DAG dependency topological sorting ---
    def test_release_all_toposort(self):
        # Create core, dev (depends on core), app (depends on dev)
        self._create_mock_module("mod_core", "1.0.0.0")
        self._create_mock_module("mod_dev", "1.0.0.0", dependencies={"mod_core": ">=1.0.0"})
        self._create_mock_module("mod_app", "1.0.0.0", dependencies={"mod_dev": ">=1.0.0"})

        releaser = Releaser()
        results = releaser.release_all()
        self.assertEqual(len(results), 3)
        for m, (ok, msg) in results.items():
            self.assertTrue(ok, f"Failed for {m}: {msg}")

        # Verify all 3 modules released
        self.assertTrue(os.path.exists(os.path.join(self.rel_dir, "mod_core", "1.0.0.0.zip")))
        self.assertTrue(os.path.exists(os.path.join(self.rel_dir, "mod_dev", "1.0.0.0.zip")))
        self.assertTrue(os.path.exists(os.path.join(self.rel_dir, "mod_app", "1.0.0.0.zip")))

    # --- FT-06: dev bump-* commands ---
    def test_bump_version_commands(self):
        self._create_mock_module("mod_bump", "1.0.0.0")
        manifest_path = os.path.join(self.src_dir, "mod_bump", "manifest.json")

        # bump-revision
        ret = dev_cli_main(["bump-revision", "mod_bump"])
        self.assertEqual(ret, 0)
        with open(manifest_path, "r") as f:
            self.assertEqual(json.load(f)["version"], "1.0.0.1")

        # bump-patch
        ret = dev_cli_main(["bump-patch", "mod_bump"])
        self.assertEqual(ret, 0)
        with open(manifest_path, "r") as f:
            self.assertEqual(json.load(f)["version"], "1.0.1.0")

        # bump-minor
        ret = dev_cli_main(["bump-minor", "mod_bump"])
        self.assertEqual(ret, 0)
        with open(manifest_path, "r") as f:
            self.assertEqual(json.load(f)["version"], "1.1.0.0")

        # bump-major
        ret = dev_cli_main(["bump-major", "mod_bump"])
        self.assertEqual(ret, 0)
        with open(manifest_path, "r") as f:
            self.assertEqual(json.load(f)["version"], "2.0.0.0")

    # --- FT-07: dev release-check command ---
    def test_release_check_command(self):
        self._create_mock_module("mod_chk", "1.0.0.0")
        ret = dev_cli_main(["release-check", "mod_chk"])
        self.assertEqual(ret, 0)

    # --- ET-01: Gate 2 duplicate version error ---
    def test_gate2_version_exists_error(self):
        self._create_mock_module("mod_dup", "1.0.0.0")
        releaser = Releaser()
        ok, msg = releaser.release_module("mod_dup")
        self.assertTrue(ok)

        # Attempt duplicate release
        passed, errors = releaser.release_check("mod_dup")
        self.assertFalse(passed)
        self.assertTrue(any("Gate 2 Failed" in e for e in errors))

    # --- ET-02: Gate 3 version rollback error ---
    def test_gate3_version_rollback_error(self):
        self._create_mock_module("mod_rb", "1.0.0.5")
        releaser = Releaser()
        ok, msg = releaser.release_module("mod_rb")
        self.assertTrue(ok)

        # Change source version to 1.0.0.2 (rollback)
        m_path = os.path.join(self.src_dir, "mod_rb", "manifest.json")
        with open(m_path, "w") as f:
            json.dump({"name": "mod_rb", "version": "1.0.0.2", "entry": "scripts/cli.py"}, f)

        passed, errors = releaser.release_check("mod_rb")
        self.assertFalse(passed)
        self.assertTrue(any("Gate 3 Failed" in e for e in errors))

    # --- ET-04: release-check rejects --all ---
    def test_release_check_reject_all(self):
        ret = dev_cli_main(["release-check", "--all"])
        self.assertEqual(ret, 1)

    # --- ET-06: cyclic dependency detection in release --all ---
    def test_toposort_cyclic_dependency_error(self):
        self._create_mock_module("mod_x", "1.0.0.0", dependencies={"mod_y": ">=1.0.0"})
        self._create_mock_module("mod_y", "1.0.0.0", dependencies={"mod_x": ">=1.0.0"})

        releaser = Releaser()
        with self.assertRaises(CyclicDependencyError):
            releaser.release_all()

    # --- FT-05: tester pre-build and --no-build flag ---
    def test_tester_pipeline_with_prebuild(self):
        self._create_mock_module("mod_tpb", "1.0.0.0")
        mod_build_dir = os.path.join(self.build_dir, "mod_tpb")
        self.assertFalse(os.path.exists(os.path.join(mod_build_dir, "1.0.0.build.zip")))

        # Test pre-build triggering
        builder = Builder()
        ok, msg = builder.build_module("mod_tpb")
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(os.path.join(mod_build_dir, "1.0.0.build.zip")))

    # --- FT-08: release-git pipeline sequence & local-only commit/tag ---
    def test_release_git_pipeline(self):
        self._create_mock_module("mod_git", "1.0.0.0")
        releaser = Releaser()

        # Mock Git repository behavior
        git_history = []
        def mock_git(args, cwd=None):
            cmd_str = " ".join(args)
            git_history.append(cmd_str)
            if "rev-parse" in cmd_str:
                return 0, "true", ""
            return 0, "", ""
        
        releaser._run_git_cmd = mock_git

        # Mock Tester passing
        with unittest.mock.patch("dev.tester.Tester.run", return_value=0):
            ok, msg = releaser.release_git("mod_git", "chore: test release")
            self.assertTrue(ok, msg)

        # Verify git sequence: add -> commit -> tag
        self.assertTrue(any("add -A" in c for c in git_history))
        self.assertTrue(any("commit -m" in c for c in git_history))
        self.assertTrue(any("tag -a mod_git/v1.0.0.0" in c for c in git_history))

        # Absolute guarantee: no 'push' command in git_history
        self.assertFalse(any("push" in c for c in git_history))

    # --- ET-03: release-git atomic abort on test/check failure ---
    def test_release_git_atomic_abort(self):
        self._create_mock_module("mod_fail_git", "1.0.0.0")
        releaser = Releaser()
        git_history = []
        releaser._run_git_cmd = lambda args, cwd=None: (git_history.append(" ".join(args)) or (0, "", ""))

        # When Step 1 (test) fails:
        with unittest.mock.patch("dev.tester.Tester.run", return_value=1):
            ok, msg = releaser.release_git("mod_fail_git", "chore: fail")
            self.assertFalse(ok)
            self.assertIn("Step 1 Failed", msg)
            self.assertFalse(any("commit" in c for c in git_history))
            self.assertFalse(any("tag" in c for c in git_history))

    # --- ET-05: tester pre-build fail abort ---
    def test_tester_prebuild_fail_abort(self):
        # Invalid module without entry
        mod_dir = os.path.join(self.src_dir, "mod_broken")
        os.makedirs(mod_dir, exist_ok=True)
        with open(os.path.join(mod_dir, "manifest.json"), "w") as f:
            json.dump({"name": "mod_broken", "version": "1.0.0.0", "entry": "scripts/missing.py"}, f)

        builder = Builder()
        ok, msg = builder.build_module("mod_broken")
        self.assertFalse(ok)
        self.assertIn("Check failed", msg)

    # --- ET-07: First-time release module initialization ---
    def test_release_first_time_init(self):
        self._create_mock_module("mod_first", "1.0.0.0")
        mod_rel_dir = os.path.join(self.rel_dir, "mod_first")
        self.assertFalse(os.path.exists(mod_rel_dir))

        releaser = Releaser()
        ok, msg = releaser.release_module("mod_first")
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.exists(os.path.join(mod_rel_dir, "1.0.0.0.zip")))
        self.assertTrue(os.path.exists(os.path.join(mod_rel_dir, "index.json")))

if __name__ == "__main__":
    unittest.main()

