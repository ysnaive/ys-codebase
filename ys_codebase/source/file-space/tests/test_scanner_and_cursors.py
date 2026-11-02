"""
Unit tests for FingerprintScanner, 4 HashPolicy modes, 192KB sparse sampling,
10ms Racy-Clean guard, YFP2 atomic snapshots, and multi-consumer cursors.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from file_space.exceptions import FingerprintCorruptedError
from file_space.manager import FileSpaceManager
from file_space.scanner import BinarySnapshotManager, FingerprintScanner
from file_space.schema import HashPolicy


class TestScannerAndCursors(YSCBTestCase):
    """Tests for two-stage scanning, YFP2 binary persistence, and multi-consumer watermark cursors."""

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
    def test_ft03_four_hash_policies_and_sparse_sampling(self) -> None:
        """FT-03: Verify adaptive (with 192KB sparse sampling), full_hash, stat_only, and lazy_stabilized."""
        small_file = self.src_dir / "small.py"
        small_file.write_text("x = 42\n", encoding="utf-8")

        large_file = self.src_dir / "large.bin"
        large_bytes = b"A" * (1024 * 1024 + 128 * 1024)
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
        self.assertTrue(
            snap_ad["large.bin"].content_hash.startswith("sample2b:")
        )

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
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft04_racy_clean_guard(self) -> None:
        """FT-04: Verify 10ms Racy-Clean guard detects same-size same-mtime_ns in-place edits."""
        target = self.src_dir / "racy.py"
        target.write_text("AAAA\n", encoding="utf-8")

        scanner = self._build_scanner(hash_policy="full_hash")
        now_ns = time.time_ns()
        os.utime(target, ns=(now_ns, now_ns))

        # Initial scan records mtime_ns within the racy window
        scanner.refresh("source")
        first_hash = scanner.snapshot("source")["racy.py"].content_hash

        # Modify content with exact same byte length and restore identical mtime_ns
        target.write_text("BBBB\n", encoding="utf-8")
        os.utime(target, ns=(now_ns, now_ns))

        # Force scan_start_ns to be within 5ms of mtime_ns by touching right before refresh
        fresh_ns = time.time_ns()
        target.write_text("AAAA\n", encoding="utf-8")
        os.utime(target, ns=(fresh_ns, fresh_ns))
        scanner.refresh("source", force=True)

        target.write_text("BBBB\n", encoding="utf-8")
        os.utime(target, ns=(fresh_ns, fresh_ns))
        diff_res = scanner.refresh("source")

        second_hash = scanner.snapshot("source")["racy.py"].content_hash
        self.assertNotEqual(first_hash, second_hash)
        self.assertIn("racy.py", diff_res.modified)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft05_multi_consumer_cursors_and_ephemeral_cancellation(self) -> None:
        """FT-05: Verify independent consumer_A and consumer_B watermarks and transient add+delete cancellation."""
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
    def test_et02_consume_diff_exception_rollback_and_yfp2_corruption_healing(
        self,
    ) -> None:
        """ET-02: Verify consume_diff preserves cursor on exception and corrupted YFP2 triggers self-healing."""
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
