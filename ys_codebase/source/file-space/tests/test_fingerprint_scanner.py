"""
Unit tests for FingerprintScanner cursor forwarding, CursorStore multi-threaded RLock safety,
broken symlink tombstone handling, and core.vfs atomic write retry via the file-space shell.
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
from file_space.scanner import (
    CursorStore,
    FingerprintScanner,
    _atomic_write_bytes,
    is_watcher_active,
)


class TestFingerprintScannerSelfHealing(YSCBTestCase):
    """Tests for FingerprintScanner forwarding to core.space.SpaceScanner and CursorStore RLock."""

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
    def test_precise_space_generations_ack_prevents_lost_update(self) -> None:
        """Verify consume_diff(None) / ack(None, space_generations=...) preserves concurrent new generations."""
        (self.space_a_dir / "a.py").write_text("v1\n", encoding="utf-8")
        (self.space_b_dir / "b.py").write_text("v1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh(None)
        scanner.ack(None, consumer_id="kdb")

        # Modify space_a -> Gen 2
        (self.space_a_dir / "a.py").write_text("v2\n", encoding="utf-8")
        scanner.refresh("space_a")
        scanner.refresh(None)

        with scanner.consume_diff(None, consumer_id="kdb", auto_refresh=False) as diff_res:
            self.assertIn("space_a/a.py", diff_res.modified)

            # Simulate concurrent refresh of space_a BEFORE consume_diff exits
            (self.space_a_dir / "a_concurrent.py").write_text("v3\n", encoding="utf-8")
            scanner.refresh("space_a")

        # Next diff with auto_refresh=True must still report a_concurrent.py
        next_diff = scanner.diff(None, consumer_id="kdb", auto_refresh=True)
        self.assertIn("space_a/a_concurrent.py", next_diff.added)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cursor_store_concurrent_rmw_thread_safety(self) -> None:
        """Verify CursorStore RLock prevents multi-threaded set_cursor calls from overwriting sibling spaces."""
        scanner = self._build_multi_space_scanner()
        store: CursorStore = scanner.cursor_store
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
            threading.Thread(target=_worker, args=(i,), daemon=True)
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            self.assertFalse(t.is_alive())

        self.assertEqual(errors, [])
        all_data = store.load_consumer("shared_consumer")
        self.assertEqual(len(all_data), num_threads)
        for i in range(num_threads):
            rec = store.get_cursor(f"space_{i}", "shared_consumer")
            self.assertEqual(rec["acked_gen"], 14)
            self.assertEqual(rec["merkle_root"], f"root_{i}_14")

        store.set_cursor(
            space_key="space_0",
            consumer_id="alpha_consumer",
            acked_gen=1,
            merkle_root="root_0_1",
            config_hash="cfg_0",
        )
        self.assertEqual(
            scanner.cursor_store.list_consumers(),
            ["alpha_consumer", "shared_consumer"],
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_broken_symlink_safety_and_patch_tombstone(self) -> None:
        """Verify broken symlinks do not crash refresh and patch_space_files marks newly broken symlink as tombstone."""
        ext_target_dir = self.tmp_dir / "symlink_targets"
        ext_target_dir.mkdir(parents=True, exist_ok=True)
        real_target = ext_target_dir / "real_target.py"
        real_target.write_text("TARGET = 1\n", encoding="utf-8")

        broken_link = self.space_a_dir / "broken_link.py"
        valid_link = self.space_a_dir / "valid_link.py"
        try:
            os.symlink(ext_target_dir / "non_existent_target.py", broken_link)
            os.symlink(real_target, valid_link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation not supported in this environment: {exc}")

        scanner = self._build_multi_space_scanner()
        scanner.space_manager.define_ephemeral_space(
            "sym_space",
            {
                "include": [self.space_a_dir.as_posix()],
                "exclude": [".git"],
                "file_patterns": ["*.py"],
                "follow_symlinks": True,
            },
        )
        scanner.refresh("sym_space")
        scanner.ack("sym_space", consumer_id="kdb")

        snap_initial = scanner.snapshot("sym_space")
        self.assertNotIn("space_a/broken_link.py", snap_initial)
        self.assertIn("space_a/valid_link.py", snap_initial)

        # Delete target file so valid_link.py becomes a broken symlink, then patch_space_files
        real_target.unlink()
        patched_state = scanner.patch_space_files("sym_space", [valid_link])
        self.assertIn("space_a/valid_link.py", patched_state.entries)
        self.assertTrue(patched_state.entries["space_a/valid_link.py"].is_deleted)

        diff_res = scanner.diff("sym_space", consumer_id="kdb", auto_refresh=False)
        self.assertEqual(diff_res.deleted, ["space_a/valid_link.py"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_patch_space_files_and_atomic_write_retry(self) -> None:
        """Verify patch_space_files incremental updates, is_watcher_active forwarding, and _atomic_write_bytes retry."""
        f1 = self.space_a_dir / "keep.py"
        f2 = self.space_a_dir / "edit.py"
        f1.write_text("keep = 1\n", encoding="utf-8")
        f2.write_text("edit = 1\n", encoding="utf-8")

        scanner = self._build_multi_space_scanner()
        scanner.refresh("space_a")
        scanner.ack("space_a", consumer_id="ast")

        f2.write_text("edit = 2\n", encoding="utf-8")
        f4 = self.space_a_dir / "added.py"
        f4.write_text("added = 1\n", encoding="utf-8")
        f1.unlink()

        patched_snap = scanner.patch_space_files("space_a", [f1, f2, f4])
        self.assertEqual(patched_snap.head_generation, 2)
        self.assertTrue(patched_snap.entries["space_a/keep.py"].is_deleted)
        self.assertFalse(patched_snap.entries["space_a/added.py"].is_deleted)

        diff_res = scanner.diff("space_a", consumer_id="ast", auto_refresh=False)
        self.assertIn("space_a/added.py", diff_res.added)
        self.assertIn("space_a/edit.py", diff_res.modified)
        self.assertIn("space_a/keep.py", diff_res.deleted)

        self.assertFalse(
            is_watcher_active(self.proj_root, space_name="space_b", space_manager=scanner.space_manager)
        )

        retry_target = self.tmp_dir / "atomic_retry.bin"
        real_replace = os.replace
        attempts = {"count": 0}

        def _flaky_replace(src: str, dst: str) -> None:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise PermissionError("Simulated Windows file lock")
            real_replace(src, dst)

        with patch("core.vfs.os_backend.os.replace", side_effect=_flaky_replace), patch(
            "core.vfs.os_backend.time.sleep"
        ) as mock_sleep:
            _atomic_write_bytes(retry_target, b"ok_payload")

        self.assertEqual(attempts["count"], 3)
        self.assertEqual(retry_target.read_bytes(), b"ok_payload")
        self.assertEqual(len(mock_sleep.call_args_list), 2)
        self.mark_passed()
