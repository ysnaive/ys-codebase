"""
Unit tests for FingerprintScanner and top-level file_space SDK facade delegating to core.space.
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

import file_space
from file_space.exceptions import (
    FingerprintCorruptedError,
    InvalidFileSpaceConfigError,
)
from file_space.manager import FileSpaceManager
from file_space.scanner import BinarySnapshotManager, FingerprintScanner


class TestScannerAndCursors(YSCBTestCase):
    """Tests for FingerprintScanner forwarding to core.space.SpaceScanner and top-level SDK facade."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_space_scanner_"))
        self.proj_root = self.tmp_dir / "project"
        self.storage_root = self.tmp_dir / "storage"
        self.src_dir = self.proj_root / "src"
        self.src_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    def _build_scanner(
        self,
        hash_policy: str = "adaptive",
        threshold_mb: int = 1,
    ) -> FingerprintScanner:
        mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "include": [self.src_dir.as_posix()],
                    "exclude": [".git"],
                    "file_patterns": ["*.py", "*.bin", "*.txt"],
                    "hash_policy": hash_policy,
                    "large_file_threshold_mb": threshold_mb,
                }
            },
            contributed_spaces={},
        )
        return FingerprintScanner(
            space_manager=mgr, storage_root=self.storage_root
        )

    @require(Requirement.LOGIC)
    def test_hash_policies_and_delegation(self) -> None:
        """Verify FingerprintScanner delegates hash policies and sparse sampling to core.space.SpaceScanner."""
        small_file = self.src_dir / "small.py"
        small_file.write_text("x = 42\n", encoding="utf-8")

        large_file = self.src_dir / "large.bin"
        size = 1024 * 1024 + 128 * 1024
        large_file.write_bytes(b"A" * size)

        scanner_adaptive = self._build_scanner(hash_policy="adaptive", threshold_mb=1)
        scanner_adaptive.refresh("source")
        snap_ad = scanner_adaptive.snapshot("source")
        self.assertEqual(len(snap_ad["src/small.py"].content_hash), 32)
        self.assertTrue(snap_ad["src/large.bin"].content_hash.startswith("sample2b:"))

        scanner_stat = self._build_scanner(hash_policy="stat_only", threshold_mb=1)
        scanner_stat.refresh("source", force=True)
        snap_stat = scanner_stat.snapshot("source")
        self.assertTrue(snap_stat["src/small.py"].content_hash.startswith("stat:"))

        with self.assertRaises(InvalidFileSpaceConfigError):
            scanner_adaptive.compute_file_hash(
                small_file,
                size=small_file.stat().st_size,
                mtime_ns=small_file.stat().st_mtime_ns,
                policy="invalid_policy",
            )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_multi_consumer_cursors_and_corruption_healing(self) -> None:
        """Verify multi-consumer cursors, consume_diff rollback, and YFP2 self-healing via core.space."""
        f1 = self.src_dir / "base.py"
        f1.write_text("v1\n", encoding="utf-8")

        scanner = self._build_scanner()
        scanner.refresh("source")
        scanner.ack("source", consumer_id="consumer_A")
        scanner.ack("source", consumer_id="consumer_B")

        f_temp = self.src_dir / "temp.py"
        f_temp.write_text("temp\n", encoding="utf-8")
        f1.write_text("v2_modified\n", encoding="utf-8")
        scanner.refresh("source")

        with scanner.consume_diff("source", consumer_id="consumer_A") as diff_a1:
            self.assertIn("src/temp.py", diff_a1.added)
            self.assertIn("src/base.py", diff_a1.modified)

        f_temp.unlink()
        scanner.refresh("source")

        diff_a2 = scanner.diff("source", consumer_id="consumer_A")
        self.assertEqual(diff_a2.deleted, ["src/temp.py"])
        diff_b = scanner.diff("source", consumer_id="consumer_B")
        self.assertEqual(diff_b.modified, ["src/base.py"])
        self.assertNotIn("src/temp.py", diff_b.added)

        snap_path = scanner.get_snapshot_path("source")
        snap_path.write_bytes(b"BAD_MAGIC_CORRUPTED_BYTES")
        empty_state = BinarySnapshotManager().load_state(snap_path)
        self.assertEqual(empty_state.head_generation, 0)

        recovered_snap = scanner.snapshot("source")
        self.assertIn("src/base.py", recovered_snap)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_top_level_sdk_facade(self) -> None:
        """Verify top-level file_space module facade functions delegate to core.space."""
        (self.src_dir / "facade_mod.py").write_text("v = 1\n", encoding="utf-8")
        eph_dir = self.tmp_dir / "eph_facade"
        eph_dir.mkdir(parents=True, exist_ok=True)
        (eph_dir / "eph.py").write_text("e = 1\n", encoding="utf-8")

        try:
            mgr, scanner = file_space.configure_default_file_space(
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
            self.assertIsNotNone(mgr)
            self.assertIsNotNone(scanner)
            self.assertEqual(file_space.list_spaces(), ["source"])
            self.assertEqual(file_space.get_space("source").name, "source")

            eph_cfg = file_space.define_ephemeral_space(
                "eph",
                {
                    "include": [eph_dir.as_posix()],
                    "file_patterns": ["*.py"],
                },
            )
            self.assertEqual(eph_cfg.name, "eph")
            self.assertIn("eph", file_space.list_spaces())

            resolved = file_space.resolve_file_path(
                "facade_mod.py", space_name="source"
            )
            self.assertEqual(resolved, (self.src_dir / "facade_mod.py").resolve())

            iter_rels = [
                rel for rel, _, _ in file_space.iter_space_files("source")
            ]
            self.assertEqual(iter_rels, ["facade_mod.py"])

            ref_res = file_space.refresh("source")
            self.assertEqual(ref_res.to_generation, 1)

            snap = file_space.snapshot("source")
            self.assertIn("src/facade_mod.py", snap)

            m_root = file_space.merkle_root("source")
            self.assertEqual(len(m_root), 32)

            d_res = file_space.diff("source", consumer_id="sdk_user", auto_refresh=False)
            self.assertIn("src/facade_mod.py", d_res.added)

            acked_gen = file_space.ack(
                None,
                consumer_id="sdk_user",
                space_generations={"source": 1, "eph": 0},
            )
            self.assertIsInstance(acked_gen, int)
            self.assertGreaterEqual(acked_gen, 1)

            file_space.reset_cursor("source", consumer_id="sdk_user")
            with file_space.consume_diff(
                "source", consumer_id="sdk_user", auto_refresh=False
            ) as c_diff:
                self.assertIn("src/facade_mod.py", c_diff.added)

            after_diff = file_space.diff(
                "source", consumer_id="sdk_user", auto_refresh=False
            )
            self.assertEqual(after_diff.added, [])
        finally:
            file_space._DEFAULT_MANAGER = None
            file_space._DEFAULT_SCANNER = None

        self.mark_passed()
