"""
Unit tests for FingerprintScanner, 4 HashPolicy modes, 192KB sparse sampling,
10ms Racy-Clean guard, YFP2 atomic snapshots, multi-consumer cursors, and top-level SDK facade.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

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
from file_space.schema import HashPolicy


class TestScannerAndCursors(YSCBTestCase):
    """Tests for two-stage scanning, YFP2 binary persistence, multi-consumer cursors, and SDK facade."""

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
    def test_four_hash_policies_and_sparse_sampling(self) -> None:
        """Verify adaptive (with 192KB sparse sampling boundaries), full_hash, stat_only, lazy_stabilized, and invalid policy."""
        small_file = self.src_dir / "small.py"
        small_file.write_text("x = 42\n", encoding="utf-8")

        large_file = self.src_dir / "large.bin"
        size = 1024 * 1024 + 128 * 1024  # 1,179,648 bytes
        large_bytes = b"A" * size
        large_file.write_bytes(large_bytes)

        # 1. adaptive policy (threshold = 1MB)
        scanner_adaptive = self._build_scanner(
            hash_policy="adaptive", threshold_mb=1
        )
        scanner_adaptive.refresh("source")
        snap_ad = scanner_adaptive.snapshot("source")
        self.assertEqual(len(snap_ad["small.py"].content_hash), 40)
        self.assertFalse(
            snap_ad["small.py"].content_hash.startswith("sample2b:")
        )
        base_sample_hash = snap_ad["large.bin"].content_hash
        self.assertTrue(base_sample_hash.startswith("sample2b:"))
        self.assertEqual(len(base_sample_hash), 49)

        # Verify 192KB sparse sampling boundaries on large.bin (size = 1,179,648 bytes):
        # Unsampled regions at offset 200KB and 800KB must produce identical sample hash
        buf_unsampled = bytearray(large_bytes)
        buf_unsampled[200 * 1024] = ord("Z")
        buf_unsampled[800 * 1024] = ord("Z")
        large_file.write_bytes(bytes(buf_unsampled))
        self.assertEqual(
            FingerprintScanner._compute_sparse_sample_hash(large_file, size),
            base_sample_hash,
        )

        # Sampled head (offset 100), middle (offset size // 2), and tail (offset size - 1) must alter hash
        for mutated_offset in (100, size // 2, size - 1):
            buf_mut = bytearray(large_bytes)
            buf_mut[mutated_offset] = ord("Z")
            large_file.write_bytes(bytes(buf_mut))
            self.assertNotEqual(
                FingerprintScanner._compute_sparse_sample_hash(large_file, size),
                base_sample_hash,
            )

        # File <= 192KB (128KB) reads entire content in _compute_sparse_sample_hash
        medium_file = self.src_dir / "medium_128k.bin"
        med_size = 128 * 1024
        med_bytes = b"M" * med_size
        medium_file.write_bytes(med_bytes)
        med_base_hash = FingerprintScanner._compute_sparse_sample_hash(
            medium_file, med_size
        )
        med_mut = bytearray(med_bytes)
        med_mut[70 * 1024] = ord("Q")
        medium_file.write_bytes(bytes(med_mut))
        self.assertNotEqual(
            FingerprintScanner._compute_sparse_sample_hash(medium_file, med_size),
            med_base_hash,
        )
        medium_file.unlink()
        large_file.write_bytes(large_bytes)

        # 2. full_hash policy
        scanner_full = self._build_scanner(
            hash_policy="full_hash", threshold_mb=1
        )
        scanner_full.refresh("source", force=True)
        snap_full = scanner_full.snapshot("source")
        self.assertEqual(len(snap_full["large.bin"].content_hash), 40)
        self.assertFalse(
            snap_full["large.bin"].content_hash.startswith("sample2b:")
        )

        # 3. stat_only policy
        scanner_stat = self._build_scanner(
            hash_policy="stat_only", threshold_mb=1
        )
        scanner_stat.refresh("source", force=True)
        snap_stat = scanner_stat.snapshot("source")
        self.assertTrue(snap_stat["small.py"].content_hash.startswith("stat:"))

        # 4. lazy_stabilized policy (background=True with freshly written large file)
        now_ns = time.time_ns()
        os.utime(large_file, ns=(now_ns, now_ns))
        scanner_lazy = self._build_scanner(
            hash_policy="lazy_stabilized", threshold_mb=1
        )
        scanner_lazy.refresh("source", background=True, force=True)
        snap_lazy = scanner_lazy.snapshot("source")
        self.assertTrue(snap_lazy["large.bin"].pending_stabilization)
        self.assertTrue(
            snap_lazy["large.bin"].content_hash.startswith("pending:")
        )

        # Backdate mtime by 3 seconds (> 2.0s stabilization window) and refresh again
        old_ns = now_ns - 3_000_000_000
        os.utime(large_file, ns=(old_ns, old_ns))
        scanner_lazy.refresh("source", background=True)
        snap_stabilized = scanner_lazy.snapshot("source")
        self.assertFalse(snap_stabilized["large.bin"].pending_stabilization)
        self.assertTrue(
            snap_stabilized["large.bin"].content_hash.startswith("sample2b:")
        )

        # 5. Invalid policy raises InvalidFileSpaceConfigError
        with self.assertRaises(InvalidFileSpaceConfigError):
            scanner_adaptive.compute_file_hash(
                small_file,
                size=small_file.stat().st_size,
                mtime_ns=small_file.stat().st_mtime_ns,
                policy="invalid_policy",
            )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_racy_clean_guard(self) -> None:
        """Verify 10ms Racy-Clean guard skips re-hash outside window and forces re-hash within 5ms window."""
        target = self.src_dir / "racy.py"
        target.write_text("AAAA\n", encoding="utf-8")
        st1 = target.stat()
        orig_mtime_ns = st1.st_mtime_ns
        scan1_ns = max(st1.st_mtime_ns, st1.st_ctime_ns) + 50_000_000

        scanner = self._build_scanner(hash_policy="full_hash")
        with patch("file_space.scanner.time.time_ns", return_value=scan1_ns):
            scanner.refresh("source")
        first_hash = scanner.snapshot("source")["racy.py"].content_hash

        # Overwrite with same byte length and lock mtime_ns to orig_mtime_ns
        target.write_text("BBBB\n", encoding="utf-8")
        os.utime(target, ns=(orig_mtime_ns, orig_mtime_ns))
        st2 = target.stat()

        # Outside 10ms racy window (+50ms after max(mtime_ns, ctime_ns)): stat gate hits cache (0 hash calls)
        outside_window_ns = max(st2.st_mtime_ns, st2.st_ctime_ns) + 50_000_000
        with patch(
            "file_space.scanner.time.time_ns", return_value=outside_window_ns
        ), patch.object(
            scanner, "compute_file_hash", wraps=scanner.compute_file_hash
        ) as mock_hash:
            cached_diff = scanner.refresh("source")
            self.assertEqual(mock_hash.call_count, 0)
            self.assertEqual(cached_diff.modified, [])

        # Inside 10ms racy window (orig_mtime_ns + 5ms): Racy-Clean guard forces re-hash and detects modification
        inside_window_ns = orig_mtime_ns + 5_000_000
        with patch(
            "file_space.scanner.time.time_ns", return_value=inside_window_ns
        ):
            diff_res = scanner.refresh("source")

        second_hash = scanner.snapshot("source")["racy.py"].content_hash
        self.assertNotEqual(first_hash, second_hash)
        self.assertIn("racy.py", diff_res.modified)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_multi_consumer_cursors_and_ephemeral_cancellation(self) -> None:
        """Verify independent consumer_A and consumer_B watermarks, diff detail helpers, and transient cancellation."""
        f1 = self.src_dir / "base.py"
        f1.write_text("v1\n", encoding="utf-8")

        scanner = self._build_scanner()
        scanner.refresh("source")
        scanner.ack("source", consumer_id="consumer_A")
        scanner.ack("source", consumer_id="consumer_B")

        # Gen 2: Add temp.py and modify base.py
        f_temp = self.src_dir / "temp.py"
        f_temp.write_text("temp\n", encoding="utf-8")
        f1.write_text("v2_modified\n", encoding="utf-8")
        scanner.refresh("source")

        # consumer_A consumes Gen 2 immediately
        with scanner.consume_diff("source", consumer_id="consumer_A") as diff_a1:
            self.assertIn("temp.py", diff_a1.added)
            self.assertIn("base.py", diff_a1.modified)
            self.assertEqual(diff_a1.detail.dirty_files, {"temp.py", "base.py"})
            detail_dict = diff_a1.detail.to_dict()
            self.assertEqual(detail_dict["added"], ["temp.py"])
            self.assertEqual(detail_dict["modified"], ["base.py"])
            self.assertTrue(detail_dict["has_changes"])
            self.assertEqual(diff_a1.total_changed, 2)

        # Gen 3: Delete temp.py before consumer_B ever wakes up
        f_temp.unlink()
        scanner.refresh("source")

        # consumer_A sees only temp.py deleted in Gen 3
        diff_a2 = scanner.diff("source", consumer_id="consumer_A")
        self.assertEqual(diff_a2.deleted, ["temp.py"])
        self.assertEqual(diff_a2.added, [])

        # consumer_B was at Gen 1: temp.py was created in Gen 2 and deleted in Gen 3,
        # so for consumer_B it cancels out (neither in added nor in deleted)!
        diff_b = scanner.diff("source", consumer_id="consumer_B")
        self.assertEqual(diff_b.modified, ["base.py"])
        self.assertNotIn("temp.py", diff_b.added)
        self.assertNotIn("temp.py", diff_b.deleted)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_consume_diff_exception_rollback_and_yfp2_corruption_healing(
        self,
    ) -> None:
        """Verify consume_diff preserves cursor on exception and corrupted YFP2 triggers self-healing."""
        f1 = self.src_dir / "mod.py"
        f1.write_text("init\n", encoding="utf-8")

        scanner = self._build_scanner()
        scanner.refresh("source")

        with self.assertRaises(RuntimeError):
            with scanner.consume_diff(
                "source", consumer_id="rollback_client"
            ) as d_res:
                self.assertIn("mod.py", d_res.added)
                raise RuntimeError("Simulated downstream indexer crash")

        # Cursor must remain at 0 so retry still sees mod.py as added
        retry_diff = scanner.diff("source", consumer_id="rollback_client")
        self.assertEqual(retry_diff.from_generation, 0)
        self.assertIn("mod.py", retry_diff.added)

        # Corrupt the YFP2 binary file on disk
        snap_path = scanner.get_snapshot_path("source")
        snap_path.write_bytes(b"BAD_MAGIC_CORRUPTED_BYTES")

        with self.assertRaises(FingerprintCorruptedError):
            BinarySnapshotManager(snap_path).load_state()

        # High-level scanner.snapshot() / diff() must self-heal by rebuilding the snapshot
        recovered_snap = scanner.snapshot("source")
        self.assertIn("mod.py", recovered_snap)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_top_level_sdk_facade(self) -> None:
        """Verify top-level file_space module facade functions and singleton lifecycle."""
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
            self.assertIn("facade_mod.py", snap)

            m_root = file_space.merkle_root("source")
            self.assertEqual(len(m_root), 40)

            d_res = file_space.diff("source", consumer_id="sdk_user", auto_refresh=False)
            self.assertIn("facade_mod.py", d_res.added)

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
                self.assertIn("facade_mod.py", c_diff.added)

            after_diff = file_space.diff(
                "source", consumer_id="sdk_user", auto_refresh=False
            )
            self.assertEqual(after_diff.added, [])
        finally:
            file_space._DEFAULT_MANAGER = None
            file_space._DEFAULT_SCANNER = None

        self.mark_passed()
