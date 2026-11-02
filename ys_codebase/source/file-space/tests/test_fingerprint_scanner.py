"""
Unit tests for FingerprintScanner precise space_generations ack, watch=False auto_refresh,
and CursorStore multi-threaded RLock Read-Modify-Write safety.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from file_space.manager import FileSpaceManager
from file_space.scanner import CursorStore, FingerprintScanner


class TestFingerprintScannerSelfHealing(YSCBTestCase):
    """Tests for space_generations ack race protection, watch=False auto_refresh, and CursorStore RLock."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_fp_self_healing_"))
        self.proj_root = self.tmp_dir / "project"
        self.storage_root = self.tmp_dir / "storage"
        self.space_a_dir = self.proj_root / "space_a"
        self.space_b_dir = self.proj_root / "space_b"
        self.space_a_dir.mkdir(parents=True)
        self.space_b_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    def _build_multi_space_scanner(self) -> FingerprintScanner:
        mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "space_a": {
                    "include": [self.space_a_dir.as_posix()],
                    "exclude": [".git"],
                    "file_patterns": ["*.py", "*.md"],
                    "watch": True,
                },
                "space_b": {
                    "include": [self.space_b_dir.as_posix()],
                    "exclude": [".git"],
                    "file_patterns": ["*.py", "*.md"],
                    "watch": False,
                },
            },
            contributed_spaces={},
        )
        return FingerprintScanner(
            space_manager=mgr, storage_root=self.storage_root
        )

    @require(Requirement.LOGIC)
    def test_ft_01_precise_space_generations_ack_prevents_lost_update(self) -> None:
        """Verify consume_diff(None) / ack(None, space_generations=...) preserves concurrent new generations."""
        (self.space_a_dir / "a.py").write_text("v1\n", encoding="utf-8")
        (self.space_b_dir / "b.py").write_text("v1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh(None)
        scanner.ack(None, consumer_id="kdb")

        # Modify space_a -> Gen 2
        (self.space_a_dir / "a.py").write_text("v2\n", encoding="utf-8")
        scanner.refresh("space_a")

        with scanner.consume_diff(None, consumer_id="kdb", auto_refresh=False) as diff_res:
            self.assertEqual(diff_res.space_generations.get("space_a"), 2)
            self.assertEqual(diff_res.space_generations.get("space_b"), 1)
            self.assertIn("a.py", diff_res.modified)

            # Simulate Watcher concurrently refreshing space_a to Gen 3 BEFORE consume_diff exits
            (self.space_a_dir / "a_concurrent.py").write_text("v3\n", encoding="utf-8")
            scanner.refresh("space_a")
            state_a, _ = scanner._load_or_recover_state("space_a")
            self.assertEqual(state_a.head_generation, 3)

        # After consume_diff exits, cursor for space_a must be at 2 (not overwritten to 3!)
        cur_a = scanner.cursor_store.get_cursor("space_a", "kdb")
        self.assertEqual(cur_a["acked_gen"], 2)

        # Next diff must still report a_concurrent.py from Gen 3
        next_diff = scanner.diff(None, consumer_id="kdb", auto_refresh=False)
        self.assertIn("a_concurrent.py", next_diff.added)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_watch_false_space_auto_refreshes_when_watcher_active(self) -> None:
        """Verify watch=False spaces still auto-refresh during consume_diff / _diff_all_spaces when watcher is active."""
        (self.space_a_dir / "a.py").write_text("v1\n", encoding="utf-8")
        (self.space_b_dir / "b.py").write_text("v1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh(None)
        scanner.ack(None, consumer_id="kdb")

        # Edit file in space_b (watch=False) without manual refresh
        (self.space_b_dir / "b.py").write_text("v2_unwatched_change\n", encoding="utf-8")

        with patch("file_space.service.is_watcher_active", return_value=True):
            # 1. consume_diff(None) should auto-refresh space_b because space_b.watch is False
            with scanner.consume_diff(None, consumer_id="kdb") as diff_all:
                self.assertIn("b.py", diff_all.modified)
                self.assertEqual(diff_all.space_generations.get("space_b"), 2)

            # 2. Direct consume_diff("space_b") when watcher is active should also auto-refresh
            (self.space_b_dir / "b2.py").write_text("v3_unwatched_added\n", encoding="utf-8")
            with scanner.consume_diff("space_b", consumer_id="kdb") as diff_b:
                self.assertIn("b2.py", diff_b.added)
                self.assertEqual(diff_b.to_generation, 3)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_cursor_store_concurrent_rmw_thread_safety(self) -> None:
        """Verify CursorStore RLock prevents multi-threaded set_cursor calls from overwriting sibling spaces."""
        store = CursorStore(self.storage_root)
        num_threads = 12
        barrier = threading.Barrier(num_threads)
        errors = []

        def _worker(idx: int) -> None:
            try:
                barrier.wait(timeout=5.0)
                for gen in range(1, 15):
                    store.set_cursor(
                        space_key=f"space_{idx}",
                        consumer_id="shared_consumer",
                        acked_gen=gen,
                        merkle_root=f"root_{idx}_{gen}",
                        config_hash=f"cfg_{idx}",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_worker, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(errors, [])
        all_Data = store.load_consumer("shared_consumer")
        self.assertEqual(len(all_Data), num_threads)
        for i in range(num_threads):
            rec = store.get_cursor(f"space_{i}", "shared_consumer")
            self.assertEqual(rec["acked_gen"], 14)
            self.assertEqual(rec["merkle_root"], f"root_{i}_14")

        self.mark_passed()
