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

    @require(Requirement.LOGIC)
    def test_et_02_racy_stat_gate_and_broken_symlink_safety(self) -> None:
        """驗證同秒級同長度覆寫時透過 Racy Stat Gate 重新計算雜湊，且懸空符號連結不引發掃描崩潰。"""
        target_f = self.space_a_dir / "racy.py"
        target_f.write_text("AAAA\n", encoding="utf-8")

        broken_link = self.space_a_dir / "broken_link.py"
        try:
            os.symlink(self.space_a_dir / "non_existent_target.py", broken_link)
        except OSError:
            pass

        scanner = self._build_multi_space_scanner()
        scanner.refresh("space_a")
        scanner.ack("space_a", consumer_id="kdb")

        # 覆寫為相同位元組長度但內容不同之檔案，即使處於同秒視窗內亦必須偵測出 modified
        target_f.write_text("BBBB\n", encoding="utf-8")
        scanner.refresh("space_a")
        diff_res = scanner.diff("space_a", consumer_id="kdb", auto_refresh=False)
        self.assertIn("racy.py", diff_res.modified)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_backdated_mtime_no_permanent_racy_and_tombstone_resurrection(self) -> None:
        """Verify backdated mtime (ctime_ns > mtime_ns) hits cache after first scan, and resurrected tombstone keeps created_gen."""
        import time

        f_utime = self.space_a_dir / "backdated.py"
        f_utime.write_text("content_v1\n", encoding="utf-8")
        # Backdate mtime by 60 seconds so ctime_ns > mtime_ns permanently
        past_ts = time.time() - 60.0
        os.utime(f_utime, (past_ts, past_ts))
        # Wait 15ms so scan_start_ns - ctime_ns > RACY_CLEAN_WINDOW_NS (10ms)
        time.sleep(0.015)

        scanner = self._build_multi_space_scanner()
        scanner.refresh("space_a")
        snap1, _ = scanner._load_or_recover_state("space_a")
        self.assertEqual(snap1.head_generation, 1)
        self.assertEqual(snap1.entries["backdated.py"].created_gen, 1)

        # Second scan must NOT re-hash f_utime even though ctime_ns > prev_fp.mtime_ns
        with patch.object(scanner, "compute_file_hash", wraps=scanner.compute_file_hash) as mock_hash:
            scanner.refresh("space_a")
            snap2, _ = scanner._load_or_recover_state("space_a")
            self.assertEqual(mock_hash.call_count, 0)
            self.assertEqual(snap2.head_generation, 1)

        # Delete backdated.py -> tombstone at Gen 2, then recreate -> updated at Gen 3 preserving created_gen=1
        f_utime.unlink()
        scanner.refresh("space_a")
        snap3, _ = scanner._load_or_recover_state("space_a")
        self.assertTrue(snap3.entries["backdated.py"].is_deleted)
        self.assertEqual(snap3.entries["backdated.py"].updated_gen, 2)

        f_utime.write_text("content_v2_resurrected\n", encoding="utf-8")
        scanner.refresh("space_a")
        snap4, _ = scanner._load_or_recover_state("space_a")
        self.assertFalse(snap4.entries["backdated.py"].is_deleted)
        self.assertEqual(snap4.entries["backdated.py"].created_gen, 1)
        self.assertEqual(snap4.entries["backdated.py"].updated_gen, 3)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_patch_space_files_and_watcher_directory_move_delete_guard(self) -> None:
        """Verify patch_space_files incremental updates and Watcher directory move/delete full-rescan fallback."""
        from file_space.service import FileSpaceWatcherServiceWorker

        f1 = self.space_a_dir / "keep.py"
        f2 = self.space_a_dir / "edit.py"
        sub_dir = self.space_a_dir / "pkg"
        sub_dir.mkdir(parents=True)
        f3 = sub_dir / "sub_mod.py"
        f1.write_text("keep = 1\n", encoding="utf-8")
        f2.write_text("edit = 1\n", encoding="utf-8")
        f3.write_text("sub = 1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh("space_a")
        scanner.ack("space_a", consumer_id="ast")

        # 1. Incremental patch_space_files: modify f2, add f4, delete f1
        f2.write_text("edit = 2\n", encoding="utf-8")
        f4 = self.space_a_dir / "added.py"
        f4.write_text("added = 1\n", encoding="utf-8")
        f1.unlink()

        patched_snap = scanner.patch_space_files("space_a", [f1, f2, f4])
        self.assertEqual(patched_snap.head_generation, 2)
        self.assertTrue(patched_snap.entries["keep.py"].is_deleted)
        self.assertFalse(patched_snap.entries["added.py"].is_deleted)

        diff_res = scanner.diff("space_a", consumer_id="ast", auto_refresh=False)
        self.assertIn("added.py", diff_res.added)
        self.assertIn("edit.py", diff_res.modified)
        self.assertIn("keep.py", diff_res.deleted)
        scanner.ack("space_a", consumer_id="ast", generation=diff_res.to_generation)

        # 2. Watcher directory deletion triggers full rescan to purge sub_dir/sub_mod.py ghost entry
        worker = FileSpaceWatcherServiceWorker(
            space_manager=scanner.space_manager,
            scanner=scanner,
        )
        # Fast segment filter ignores .git and .cache before Path.resolve()
        self.assertEqual(worker.notify_file_event(str(self.space_a_dir / ".git" / "HEAD")), [])

        shutil.rmtree(sub_dir)
        matched = worker.notify_file_event(str(sub_dir), is_directory=True, event_type="deleted")
        self.assertIn("space_a", matched)
        self.assertIn("space_a", worker._full_rescan_spaces)

        flush_res = worker.flush_space_now("space_a")
        self.assertIsNotNone(flush_res)
        diff_after_dir_del = scanner.diff("space_a", consumer_id="ast", auto_refresh=False)
        self.assertIn("pkg/sub_mod.py", diff_after_dir_del.deleted)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_watcher_state_awareness_and_diff_all_spaces_aggregation(self) -> None:
        """Verify is_watcher_active checks watcher_state.json + space watch flag, and _diff_all_spaces aggregates generations."""
        import json
        from file_space.scanner import is_watcher_active

        (self.space_a_dir / "a.py").write_text("a = 1\n", encoding="utf-8")
        (self.space_b_dir / "b.py").write_text("b = 1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh(None)

        all_diff = scanner.diff(None, consumer_id="kdb", auto_refresh=False)
        self.assertGreater(all_diff.to_generation, 0)
        self.assertTrue(len(all_diff.merkle_root) > 0)
        self.assertEqual(all_diff.space_generations.get("space_a"), 1)
        self.assertEqual(all_diff.space_generations.get("space_b"), 1)

        state_file = self.proj_root / "ys_codebase" / ".cache" / "file-space" / "watcher_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "watchdog_running": False,
                    "watched_spaces": ["space_a"],
                }
            ),
            encoding="utf-8",
        )
        # When watchdog_running is False, is_watcher_active must return False
        self.assertFalse(is_watcher_active(self.proj_root, space_name="space_a", space_manager=scanner.space_manager))

        state_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "watchdog_running": True,
                    "watched_spaces": ["space_a"],
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(is_watcher_active(self.proj_root, space_name="space_a", space_manager=scanner.space_manager))
        # space_b has watch=False, so is_watcher_active(..., space_name="space_b") must return False
        self.assertFalse(is_watcher_active(self.proj_root, space_name="space_b", space_manager=scanner.space_manager))
        self.mark_passed()

