"""
Unit tests for FileSpaceManager dual-track aggregation, geometry resolution, and file iteration.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from file_space.exceptions import InvalidFileSpaceConfigError, FileSpaceNotFoundError
from file_space.manager import FileSpaceManager
from file_space.schema import HashPolicy, FileSpaceConfig, FileSpaceOrigin


class TestFileSpaceManager(YSCBTestCase):
    """Tests for FileSpaceManager configuration aggregation, path safety, and file discovery."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_space_mgr_"))
        self.proj_root = self.tmp_dir / "project"
        self.storage_root = self.tmp_dir / "storage"
        self.src_dir = self.proj_root / "src"
        self.docs_dir = self.proj_root / "docs"
        self.extra_docs_dir = self.proj_root / "extra_docs"
        self.src_dir.mkdir(parents=True)
        self.docs_dir.mkdir(parents=True)
        self.extra_docs_dir.mkdir(parents=True)

        (self.src_dir / "app.py").write_text("print('app')\n", encoding="utf-8")
        (self.src_dir / "ignore.pyc").write_bytes(b"\x00\x01")
        git_dir = self.src_dir / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("gitcfg", encoding="utf-8")

        (self.docs_dir / "arch.md").write_text("# Arch\n", encoding="utf-8")
        (self.extra_docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (self.extra_docs_dir / "draft.tmp").write_text("tmp\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft01_dual_track_aggregation_and_override(self) -> None:
        """FT-01: Verify list append deduplication and host scalar override across module & project tracks."""
        contributed = {
            "docs": {
                "description": "Module default docs",
                "include": [self.docs_dir.as_posix()],
                "exclude": [".git", "archive"],
                "file_patterns": ["*.md"],
                "hash_policy": "adaptive",
                "large_file_threshold_mb": 10,
                "watch": True,
                "weight": 1.0,
                "owner_modules": ["agents-workflow"],
            }
        }
        project_spaces = {
            "docs": {
                "description": "Host overridden docs",
                "include": [self.extra_docs_dir.as_posix()],
                "exclude": ["archive", "secret"],
                "file_patterns": ["*.md", "*.txt"],
                "hash_policy": "full_hash",
                "large_file_threshold_mb": 25,
                "watch": False,
                "weight": 1.5,
            },
            "source": {
                "description": "Host source",
                "include": [self.src_dir.as_posix()],
                "exclude": [".git", "__pycache__"],
                "file_patterns": ["*.py"],
            },
        }

        mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config=project_spaces,
            contributed_spaces=contributed,
        )

        spaces = mgr.list_spaces()
        self.assertIn("docs", spaces)
        self.assertIn("source", spaces)

        docs_cfg = mgr.get_space("docs")
        self.assertEqual(docs_cfg.origin, FileSpaceOrigin.MERGED)
        self.assertEqual(docs_cfg.description, "Host overridden docs")
        self.assertEqual(docs_cfg.hash_policy, HashPolicy.FULL_HASH)
        self.assertEqual(docs_cfg.large_file_threshold_mb, 25)
        self.assertFalse(docs_cfg.watch)
        self.assertEqual(docs_cfg.weight, 1.5)

        resolved_inc = [p.as_posix() for p in docs_cfg.resolved_include_paths]
        self.assertIn(self.docs_dir.resolve().as_posix(), resolved_inc)
        self.assertIn(self.extra_docs_dir.resolve().as_posix(), resolved_inc)
        self.assertEqual(docs_cfg.exclude, [".git", "archive", "secret"])
        self.assertEqual(docs_cfg.file_patterns, ["*.md", "*.txt"])
        self.assertIn("agents-workflow", docs_cfg.owner_modules)
        self.assertIn("project", docs_cfg.owner_modules)

        src_cfg = mgr.get_space("source")
        self.assertEqual(src_cfg.origin, FileSpaceOrigin.PROJECT)
        self.assertEqual(src_cfg.hash_policy, HashPolicy.ADAPTIVE)

        # Verify __providers__ based origin resolution (pure project vs multi-module vs merged)
        mgr_providers = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={},
            contributed_spaces={
                "pure_proj": {
                    "include": [self.src_dir.as_posix()],
                    "__provider__": "project",
                    "__providers__": ["project"],
                },
                "multi_mod": {
                    "include": [self.docs_dir.as_posix()],
                    "__provider__": "knowledge-db",
                    "__providers__": ["agents-workflow", "knowledge-db"],
                },
                "mod_and_proj": {
                    "include": [self.docs_dir.as_posix(), self.extra_docs_dir.as_posix()],
                    "__provider__": "project",
                    "__providers__": ["agents-workflow", "project"],
                },
            },
        )
        self.assertEqual(mgr_providers.get_space("pure_proj").origin, FileSpaceOrigin.PROJECT)
        self.assertEqual(mgr_providers.get_space("pure_proj").owner_modules, ["project"])
        self.assertEqual(mgr_providers.get_space("pure_proj").origin_display, "origin(project)")
        self.assertEqual(mgr_providers.get_space("multi_mod").origin, FileSpaceOrigin.MODULE)
        self.assertEqual(
            mgr_providers.get_space("multi_mod").owner_modules,
            ["agents-workflow", "knowledge-db"],
        )
        self.assertEqual(
            mgr_providers.get_space("multi_mod").origin_display,
            "merged(agents-workflow, knowledge-db)",
        )
        self.assertEqual(mgr_providers.get_space("mod_and_proj").origin, FileSpaceOrigin.MERGED)
        self.assertEqual(
            mgr_providers.get_space("mod_and_proj").owner_modules,
            ["agents-workflow", "project"],
        )
        self.assertEqual(
            mgr_providers.get_space("mod_and_proj").origin_display,
            "merged(agents-workflow, project)",
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft02_ephemeral_space_and_iteration(self) -> None:
        """FT-02: Verify define_ephemeral_space, iter_space_files filtering, and resolve_file_path."""
        mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "include": [self.src_dir.as_posix()],
                    "exclude": [".git"],
                    "file_patterns": ["*.py"],
                }
            },
            contributed_spaces={},
        )

        ephemeral_dir = self.tmp_dir / "sandbox_space"
        ephemeral_dir.mkdir()
        (ephemeral_dir / "sandbox_mod.py").write_text("x = 1\n", encoding="utf-8")

        eph_cfg = mgr.define_ephemeral_space(
            "sandbox",
            {
                "include": [ephemeral_dir.as_posix()],
                "file_patterns": ["*.py"],
                "hash_policy": "stat_only",
            },
        )
        self.assertEqual(eph_cfg.origin, FileSpaceOrigin.EPHEMERAL)
        self.assertEqual(eph_cfg.hash_policy, HashPolicy.STAT_ONLY)

        src_files = list(mgr.iter_space_files("source"))
        self.assertEqual(len(src_files), 1)
        self.assertEqual(src_files[0][0], "app.py")

        resolved = mgr.resolve_file_path("app.py", space_name="source")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved, (self.src_dir / "app.py").resolve())

        self.assertTrue(
            mgr.file_belongs_to_space(self.src_dir / "app.py", "source")
        )
        self.assertFalse(
            mgr.file_belongs_to_space(self.src_dir / "ignore.pyc", "source")
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et01_path_traversal_and_invalid_space_errors(self) -> None:
        """ET-01: Verify FileSpaceNotFoundError, InvalidFileSpaceConfigError, and path traversal protection."""
        outside_file = self.tmp_dir / "secret.py"
        outside_file.write_text("SECRET = 1\n", encoding="utf-8")

        mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "include": [self.src_dir.as_posix()],
                    "file_patterns": ["*.py"],
                }
            },
            contributed_spaces={},
        )

        with self.assertRaises(FileSpaceNotFoundError):
            mgr.get_space("non_existent_space")

        with self.assertRaises(InvalidFileSpaceConfigError):
            mgr.define_ephemeral_space("bad_empty", {"include": []})

        with self.assertRaises(InvalidFileSpaceConfigError):
            FileSpaceConfig(
                name="bad_policy",
                include=[self.src_dir],
                hash_policy="unknown_hash_mode",
            )

        traversed = mgr.resolve_file_path("../../secret.py", space_name="source")
        self.assertIsNone(traversed)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft03_load_spaces_caching_project_root_and_symlinks(self) -> None:
        """FR-02, EC-02: Verify load_spaces(force=False) caching, project_root caching, and follow_symlinks subdirectory behavior."""
        from unittest.mock import patch

        resolve_calls = 0

        def counting_resolver(raw: str) -> str:
            nonlocal resolve_calls
            if raw == "project://":
                resolve_calls += 1
                return self.proj_root.as_posix()
            return ""

        mgr = FileSpaceManager(
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "include": [self.src_dir.as_posix()],
                    "file_patterns": ["*.py"],
                }
            },
            contributed_spaces={},
            uri_resolver=counting_resolver,
        )

        # 1. project_root is cached after first resolution
        root1 = mgr.project_root
        root2 = mgr.project_root
        self.assertEqual(root1, self.proj_root.resolve())
        self.assertEqual(root2, self.proj_root.resolve())
        self.assertEqual(resolve_calls, 1)

        # 2. load_spaces(force=False) returns cached map without re-discovering; force=True reloads
        with patch.object(mgr, "_discover_module_contributed_spaces", wraps=mgr._discover_module_contributed_spaces) as mock_disc:
            cached_map = mgr.load_spaces(force=False)
            self.assertEqual(mock_disc.call_count, 0)
            self.assertIn("source", cached_map)

            reloaded_map = mgr.load_spaces(force=True)
            self.assertEqual(mock_disc.call_count, 1)
            self.assertIn("source", reloaded_map)

        # 3. EC-02: follow_symlinks=True with symlinked subdirectory resolves paths consistently
        ext_target_dir = self.tmp_dir / "ext_linked_pkg"
        ext_target_dir.mkdir(parents=True)
        (ext_target_dir / "linked_mod.py").write_text("LINKED = True\n", encoding="utf-8")

        symlink_sub = self.src_dir / "linked_sub"
        symlink_supported = True
        try:
            os.symlink(ext_target_dir, symlink_sub, target_is_directory=True)
        except (OSError, NotImplementedError):
            symlink_supported = False

        if symlink_supported:
            # When follow_symlinks=False (default), symlink_sub is ignored
            files_no_follow = [rel for rel, _, _ in mgr.iter_space_files("source")]
            self.assertEqual(files_no_follow, ["app.py"])

            # When follow_symlinks=True, symlink_sub is traversed and its file is included
            mgr.define_ephemeral_space(
                "sym_space",
                {
                    "include": [self.src_dir.as_posix()],
                    "file_patterns": ["*.py"],
                    "follow_symlinks": True,
                },
            )
            files_follow = [rel for rel, _, _ in mgr.iter_space_files("sym_space")]
            self.assertIn("app.py", files_follow)
            self.assertTrue(any("linked_mod.py" in f for f in files_follow))

        self.mark_passed()

