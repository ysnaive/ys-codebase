"""
Unit tests for FileSpaceManager compatibility forwarding shell delegating to core.space.SpaceRegistry.
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

from file_space.exceptions import FileSpaceNotFoundError, InvalidFileSpaceConfigError
from file_space.manager import FileSpaceManager
from file_space.schema import FileSpaceConfig, FileSpaceOrigin, HashPolicy


class TestFileSpaceManager(YSCBTestCase):
    """Tests for FileSpaceManager forwarding to core.space.SpaceRegistry."""

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
    def test_dual_track_aggregation_and_override(self) -> None:
        """Verify legacy dict normalization and dual-track aggregation via core.space.SpaceRegistry."""
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
        self.assertIn("agents-workflow", docs_cfg.owner_modules)
        self.assertIn("project", docs_cfg.owner_modules)

        src_cfg = mgr.get_space("source")
        self.assertEqual(src_cfg.origin, FileSpaceOrigin.PROJECT)
        self.assertEqual(src_cfg.hash_policy, HashPolicy.ADAPTIVE)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ephemeral_space_and_iteration(self) -> None:
        """Verify define_ephemeral_space, iter_space_files, resolve_file_path, and file_belongs_to_space."""
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
        sandbox_file = ephemeral_dir / "sandbox_mod.py"
        sandbox_file.write_text("x = 1\n", encoding="utf-8")

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

        eph_cfg_instance = mgr.define_ephemeral_space(
            "sandbox_instance",
            FileSpaceConfig(
                name="sandbox_instance",
                include=[ephemeral_dir],
                file_patterns=["*.py"],
                hash_policy=HashPolicy.FULL_HASH,
            ),
        )
        self.assertEqual(eph_cfg_instance.origin, FileSpaceOrigin.EPHEMERAL)
        self.assertEqual(eph_cfg_instance.hash_policy, HashPolicy.FULL_HASH)

        sandbox_files = list(mgr.iter_space_files("sandbox"))
        self.assertEqual(len(sandbox_files), 1)
        self.assertEqual(sandbox_files[0][0], "sandbox_mod.py")
        self.assertEqual(
            mgr.resolve_file_path("sandbox_mod.py", space_name="sandbox"),
            sandbox_file.resolve(),
        )
        self.assertTrue(mgr.file_belongs_to_space(sandbox_file, "sandbox"))

        src_files = list(mgr.iter_space_files("source"))
        self.assertEqual(len(src_files), 1)
        self.assertEqual(src_files[0][0], "app.py")

        resolved = mgr.resolve_file_path("app.py", space_name="source")
        self.assertEqual(resolved, (self.src_dir / "app.py").resolve())

        self.assertTrue(mgr.file_belongs_to_space(self.src_dir / "app.py", "source"))
        self.assertFalse(mgr.file_belongs_to_space(self.src_dir / "ignore.pyc", "source"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_path_traversal_and_invalid_space_errors(self) -> None:
        """Verify FileSpaceNotFoundError, InvalidFileSpaceConfigError, and path traversal protection."""
        outside_file = self.tmp_dir / "secret.py"
        outside_file.write_text("SECRET = 1\n", encoding="utf-8")

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

        with self.assertRaises(FileSpaceNotFoundError):
            mgr.get_space("non_existent_space")

        with self.assertRaises(InvalidFileSpaceConfigError):
            mgr.define_ephemeral_space("", {"include": [self.src_dir.as_posix()]})

        with self.assertRaises(InvalidFileSpaceConfigError):
            mgr.define_ephemeral_space("bad_type", 123)  # type: ignore[arg-type]

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
    def test_schema_serialization_and_iter_with_stat(self) -> None:
        """Verify FileSpaceConfig to_dict/from_dict roundtrip and iter_space_files_with_stat delegation."""
        cfg = FileSpaceConfig(
            name="filter_check",
            include=[self.proj_root],
            exclude=[".git", "*.pyc"],
            file_patterns=["*.py", "*.md"],
        )
        serialized = cfg.to_dict()
        restored = FileSpaceConfig.from_dict(cfg.name, serialized)
        self.assertEqual(restored.to_dict(), serialized)
        self.assertTrue(cfg.is_file_included("src/app.py"))
        self.assertFalse(cfg.is_file_included("src/app.pyc"))
        self.assertTrue(cfg.is_dir_excluded(".git", ".git"))

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
        stat_entries = list(mgr.iter_space_files_with_stat("source"))
        self.assertEqual(len(stat_entries), 1)
        rel_p, abs_p, _src_r, mtime_ns, ctime_ns, size = stat_entries[0]
        self.assertEqual(rel_p, "app.py")
        self.assertTrue(abs_p.is_file())
        self.assertGreater(mtime_ns, 0)
        self.assertGreater(ctime_ns, 0)
        self.assertEqual(size, abs_p.stat().st_size)
        self.mark_passed()
