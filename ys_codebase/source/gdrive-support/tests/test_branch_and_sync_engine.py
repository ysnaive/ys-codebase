"""
Unit, integration, and edge-case tests for module:gdrive-support branch management and sync engine.

100% locked to LocalSandboxTransport, stateless reconciler.py, SyncCoordinator, and GDriveSyncServiceWorker.
No external Google Drive API calls or user credentials are required or tested here.
"""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from core.commands import CmdBags, CmdOption
from dev.testing import YSCBTestCase
from dev.testing.requirement import Requirement, require

from gdrive_support import (
    FileEntry,
    GDriveConfig,
    GDriveConflictError,
    GDriveDirtyWorktreeError,
    GDriveRepoSyncDisabledError,
    GDriveRepoUninitializedError,
    GDriveSyncServiceWorker,
    GDriveTransportError,
    LocalSandboxTransport,
    ROOT_README_BEGIN_MARKER,
    ROOT_README_END_MARKER,
    SyncActionType,
    SyncCoordinator,
    SyncSpaceSpec,
    collect_space_local_files_with_stat,
    compute_history_ref_counts,
    compute_orphan_history_file_ids,
    is_file_id_referenced_by_other_branches,
    reconcile_root_readme_state,
    reconcile_three_way,
)

_cli_spec = importlib.util.spec_from_file_location(
    "_gdrive_support_cli_sub02", _pkg_root / "scripts" / "cli.py"
)
assert _cli_spec is not None and _cli_spec.loader is not None
cli = importlib.util.module_from_spec(_cli_spec)
_cli_spec.loader.exec_module(cli)


class _SimpleFileSpaceManager:
    """Deterministic file-space enumerator scanning a local directory for sandbox tests."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    def iter_space_files(self, _space_name: str):
        results = []
        if not self.root_dir.exists():
            return iter(results)
        for p in sorted(self.root_dir.rglob("*")):
            if p.is_file() and ".conflict." not in p.name:
                rel = p.relative_to(self.root_dir).as_posix()
                results.append((rel, p, self.root_dir))
        return iter(results)


class TestGDriveBranchAndSyncEngine(YSCBTestCase):
    """Test suite for reconciler.py, SyncCoordinator, Shortcut branches, CoW .history/.trash GC, and service.py."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_root = Path(tempfile.mkdtemp(prefix="yscb_gdrive_sub02_")).resolve()
        self.proj_dir = self.tmp_root / "project"
        self.docs_dir = self.proj_dir / "docs"
        self.sandbox_dir = self.tmp_root / "sandbox_cloud"
        self.cache_dir = self.tmp_root / "cache"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.transport = LocalSandboxTransport(self.sandbox_dir)
        self.fs_mgr = _SimpleFileSpaceManager(self.docs_dir)
        self.cfg = GDriveConfig(
            root_folder_id="sandbox_root",
            active_branch="main",
            auto_sync=False,
            repo_sync_enabled=True,
            sandbox_dir=self.sandbox_dir.as_posix(),
            sync_spaces=(SyncSpaceSpec(space="docs"),),
        )
        self.coord = SyncCoordinator(
            config=self.cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.cache_dir / "sync_state.json",
            lock_path=self.cache_dir / "sync.lock",
            log_path=self.cache_dir / "sync.log",
            readme_state_path=self.cache_dir / "readme_sync_state.json",
            file_space_manager=self.fs_mgr,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_stateless_reconciler_8_states_and_history_ref_counts(self) -> None:
        """Verify pure 3-way reconciliation produces all 8 SyncActionType states and computes history ref counts."""
        base = {
            "in_sync.md": FileEntry(rel_path="in_sync.md", md5="m1", size=10),
            "mod_loc.md": FileEntry(rel_path="mod_loc.md", md5="m2", size=10),
            "mod_rem.md": FileEntry(rel_path="mod_rem.md", md5="m3", size=10),
            "del_loc.md": FileEntry(rel_path="del_loc.md", md5="m4", size=10),
            "del_rem.md": FileEntry(rel_path="del_rem.md", md5="m5", size=10),
            "conflict.md": FileEntry(rel_path="conflict.md", md5="m6", size=10),
        }
        loc = {
            "in_sync.md": FileEntry(rel_path="in_sync.md", md5="m1", size=10),
            "mod_loc.md": FileEntry(rel_path="mod_loc.md", md5="m2_new", size=12),
            "mod_rem.md": FileEntry(rel_path="mod_rem.md", md5="m3", size=10),
            "del_rem.md": FileEntry(rel_path="del_rem.md", md5="m5", size=10),
            "conflict.md": FileEntry(rel_path="conflict.md", md5="m6_loc", size=11),
            "new_loc.md": FileEntry(rel_path="new_loc.md", md5="m7", size=8),
        }
        rem = {
            "in_sync.md": FileEntry(rel_path="in_sync.md", md5="m1", size=10),
            "mod_loc.md": FileEntry(rel_path="mod_loc.md", md5="m2", size=10),
            "mod_rem.md": FileEntry(rel_path="mod_rem.md", md5="m3_new", size=14),
            "del_loc.md": FileEntry(rel_path="del_loc.md", md5="m4", size=10),
            "conflict.md": FileEntry(rel_path="conflict.md", md5="m6_rem", size=15),
            "new_rem.md": FileEntry(rel_path="new_rem.md", md5="m8", size=9),
        }

        actions = {
            a.rel_path: a.action
            for a in reconcile_three_way(
                loc, rem, base, mode="sync", allow_pull_delete=True, allow_push_delete=True
            )
        }
        self.assertEqual(actions["in_sync.md"], SyncActionType.IN_SYNC)
        self.assertEqual(actions["mod_loc.md"], SyncActionType.PUSH_UPDATE)
        self.assertEqual(actions["mod_rem.md"], SyncActionType.PULL_UPDATE)
        self.assertEqual(actions["del_loc.md"], SyncActionType.DELETE_REMOTE)
        self.assertEqual(actions["del_rem.md"], SyncActionType.DELETE_LOCAL)
        self.assertEqual(actions["conflict.md"], SyncActionType.CONFLICT)
        self.assertEqual(actions["new_loc.md"], SyncActionType.PUSH_NEW)
        self.assertEqual(actions["new_rem.md"], SyncActionType.PULL_NEW)

        branch_map = {
            "main": {"a.md": "fid_v2", "b.md": "fid_b"},
            "v1.0": {"a.md": "fid_v1", "b.md": "fid_b"},
        }
        self.assertTrue(
            is_file_id_referenced_by_other_branches("fid_b", "main", branch_map)
        )
        self.assertFalse(
            is_file_id_referenced_by_other_branches("fid_v2", "main", branch_map)
        )
        counts = compute_history_ref_counts({"fid_v1", "fid_orphan"}, branch_map)
        self.assertEqual(counts, {"fid_v1": 1, "fid_orphan": 0})
        self.assertEqual(
            compute_orphan_history_file_ids({"fid_v1", "fid_orphan"}, branch_map),
            ["fid_orphan"],
        )
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_02_init_repo_and_readme_generation(self) -> None:
        """Verify init_repo creates repo/{.yscb_gdrive.json, README.md, .history/, .trash/, main/} and top-level README.md."""
        default_coord = SyncCoordinator(
            config=self.cfg,
            transport=self.transport,
            project_root=self.proj_dir,
        )
        self.assertTrue(
            default_coord.state_path.as_posix().endswith(
                ".storage.local/gdrive-support/sync_state.json"
            )
        )
        self.assertTrue(
            default_coord.readme_state_path.as_posix().endswith(
                ".storage.local/gdrive-support/readme_sync_state.json"
            )
        )
        self.assertTrue(
            default_coord.lock_path.as_posix().endswith(
                ".cache/gdrive-support/sync.lock"
            )
        )
        self.assertTrue(
            default_coord.log_path.as_posix().endswith(
                ".cache/gdrive-support/sync.log"
            )
        )

        res = self.coord.init_repo()
        self.assertEqual(res["status"], "initialized")
        self.assertIsNotNone(self.transport.get_entry("repo/.yscb_gdrive.json"))
        self.assertIsNotNone(self.transport.get_entry("repo/README.md"))
        self.assertIsNotNone(self.transport.get_entry("repo/.history"))
        self.assertIsNotNone(self.transport.get_entry("repo/.trash"))
        self.assertIsNotNone(self.transport.get_entry("repo/main"))
        self.assertIsNotNone(self.transport.get_entry("README.md"))

        readme_local = self.tmp_root / "check_readme.md"
        self.transport.download_file("repo/README.md", readme_local)
        self.assertIn("yscb module:gdrive-support", readme_local.read_text(encoding="utf-8"))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_03_branch_shortcut_cow_history_and_unreferenced_gc_to_trash(self) -> None:
        """
        Verify full lifecycle under repo/ (default repo_sync_root):
        1. Push file v1 on 'main' (fid_v1).
        2. Create branch 'v1.0' -> creates Shortcut pointing to fid_v1.
        3. Modify file on 'main' and push -> since 'v1.0' references fid_v1 (ref_count > 0),
           fid_v1 is moved to repo/.history/ (Copy-on-Write) and 'main' gets new fid_v2;
           'v1.0' shortcut still downloads frozen v1 content!
        4. Delete branch 'v1.0' (or overwrite its shortcut) -> fid_v1 in repo/.history/ now has
           ref_count == 0 and is automatically moved from repo/.history/ to repo/.trash/!
        """
        f_guide = self.docs_dir / "guide.md"
        f_guide.write_text("Version 1.0 Frozen Content\n", encoding="utf-8")

        # 1. Push v1 on main
        rep1 = self.coord.run_sync(mode="push")
        self.assertEqual(rep1.pushed, ["docs/guide.md"])
        main_v1_entry = self.transport.get_entry("repo/main/docs/guide.md")
        assert main_v1_entry is not None
        fid_v1 = main_v1_entry.file_id

        # 2. Create branch v1.0
        br_res = self.coord.create_branch("v1.0", from_branch="main")
        self.assertEqual(br_res["shortcuts_created"], 1)
        v1_sc = self.transport.get_entry("repo/v1.0/docs/guide.md")
        assert v1_sc is not None
        self.assertTrue(v1_sc.is_shortcut)
        self.assertEqual(v1_sc.target_file_id, fid_v1)

        # 3. Update guide.md on main -> must trigger Copy-on-Write into repo/.history/
        f_guide.write_text("Version 2.0 Main Trunk Content\n", encoding="utf-8")
        rep2 = self.coord.run_sync(mode="push")
        self.assertEqual(rep2.pushed, ["docs/guide.md"])
        self.assertIn(fid_v1, rep2.moved_to_history)
        self.assertEqual(rep2.gc_history_to_trash, [])

        main_v2_entry = self.transport.get_entry("repo/main/docs/guide.md")
        assert main_v2_entry is not None
        self.assertNotEqual(main_v2_entry.file_id, fid_v1)

        # Verify repo/.history/ contains fid_v1 and v1.0 shortcut still resolves to frozen v1 content!
        hist_entries = self.transport.list_files("repo/.history")
        self.assertEqual(len(hist_entries), 1)
        self.assertEqual(hist_entries[0].file_id, fid_v1)

        frozen_check = self.tmp_root / "frozen_v1.md"
        self.transport.download_file("repo/v1.0/docs/guide.md", frozen_check)
        self.assertEqual(
            frozen_check.read_text(encoding="utf-8"), "Version 1.0 Frozen Content\n"
        )

        # 4. Delete branch v1.0 -> fid_v1 in repo/.history/ now has 0 references -> auto-moved via transport.trash_file()!
        # Also simulate an external AI dropping a stray file into repo/.trash/ and verify it is auto-flushed!
        ext_trash_src = self.tmp_root / "ext_ai_dropped.txt"
        ext_trash_src.write_text("Dropped by web AI into repo/.trash/\n", encoding="utf-8")
        ext_trash_entry = self.transport.upload_file(ext_trash_src, "repo/.trash/ext_ai_dropped.txt")

        del_res = self.coord.delete_branch("v1.0")
        self.assertIn(fid_v1, del_res["gc_history_to_trash"])
        self.assertIn(ext_trash_entry.file_id, del_res["flushed_external_trash"])
        self.assertEqual(len(self.transport.list_files("repo/.history")), 0)
        self.assertEqual(len(self.transport.list_files("repo/.trash")), 0)
        trash_ids = [e.file_id for e in self.transport.list_files(".trash")]
        self.assertIn(fid_v1, trash_ids)
        self.assertIn(ext_trash_entry.file_id, trash_ids)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_04_checkout_branch_worktree_alignment_and_orphan_cleanup(self) -> None:
        """Verify checkout switches branches, pulls branch files, and cleans up old-branch-only local files."""
        (self.docs_dir / "shared.md").write_text("Shared v1\n", encoding="utf-8")
        self.coord.run_sync(mode="push")
        self.coord.create_branch("v1.0", from_branch="main")

        # Add a main-only file and update shared.md on main
        (self.docs_dir / "main_only.md").write_text("Only on main\n", encoding="utf-8")
        (self.docs_dir / "shared.md").write_text("Shared v2 on main\n", encoding="utf-8")
        self.coord.run_sync(mode="push")

        # Checkout v1.0 -> main_only.md must be removed from local worktree and shared.md reverted to v1
        co_res = self.coord.checkout_branch("v1.0")
        self.assertEqual(co_res["active_branch"], "v1.0")
        self.assertIn("docs/main_only.md", co_res["removed_orphans"])
        self.assertFalse((self.docs_dir / "main_only.md").exists())
        self.assertEqual(
            (self.docs_dir / "shared.md").read_text(encoding="utf-8"), "Shared v1\n"
        )
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_05_service_worker_standby_health_and_unsubscribe_on_stop(self) -> None:
        """Verify GDriveSyncServiceWorker stays in standby when auto_sync=False (healthy=True) and unsubscribes on stop()."""
        worker_standby = GDriveSyncServiceWorker(config=self.cfg, coordinator=self.coord)
        worker_standby.start()
        self.assertTrue(worker_standby.standby_mode)
        self.assertTrue(worker_standby.health_check())
        self.assertEqual(worker_standby.get_service_status()["mode"], "standby")
        worker_standby.stop()

        unsubscribed = {"called": False}

        def _fake_subscribe(cb, *, spaces=None):
            def _unsub():
                unsubscribed["called"] = True

            return _unsub

        active_cfg = GDriveConfig(
            root_folder_id="sandbox_root",
            active_branch="main",
            auto_sync=True,
            repo_sync_enabled=True,
            poll_interval_sec=60.0,
            sandbox_dir=self.sandbox_dir.as_posix(),
            sync_spaces=(SyncSpaceSpec(space="docs"),),
        )
        worker_active = GDriveSyncServiceWorker(
            config=active_cfg,
            coordinator=self.coord,
            subscribe_fn=_fake_subscribe,
        )
        worker_active.start()
        self.assertFalse(worker_active.standby_mode)
        self.assertTrue(worker_active.health_check())
        self.assertTrue(worker_active.get_service_status()["subscribed"])
        worker_active.stop()
        self.assertTrue(unsubscribed["called"])
        self.assertFalse(worker_active.get_service_status()["subscribed"])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_01_non_empty_uninitialized_remote_root_aborts_sync(self) -> None:
        """Verify sync aborts with GDriveRepoUninitializedError if remote repo/ is non-empty and lacks .yscb_gdrive.json."""
        stray_file = self.tmp_root / "stray.txt"
        stray_file.write_text("personal file inside repo", encoding="utf-8")
        self.transport.upload_file(stray_file, "repo/personal/stray.txt")

        with self.assertRaises(GDriveRepoUninitializedError):
            self.coord.run_sync(mode="sync")
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_02_conflict_isolation_in_sync_vs_force_backup_resolution(self) -> None:
        """Verify bidirectional sync isolates conflicts (exit_code=2) while syncing clean files, and --force --backup creates .bak."""
        f_conflict = self.docs_dir / "conflict.md"
        f_clean = self.docs_dir / "clean.md"
        f_conflict.write_text("Baseline\n", encoding="utf-8")
        f_clean.write_text("Clean v1\n", encoding="utf-8")
        self.coord.run_sync(mode="push")

        # Modify conflict.md both locally and remotely; modify clean.md locally only
        f_conflict.write_text("Local Diverged\n", encoding="utf-8")
        f_clean.write_text("Clean v2 Local\n", encoding="utf-8")
        rem_tmp = self.tmp_root / "rem_diverged.md"
        rem_tmp.write_text("Remote Diverged\n", encoding="utf-8")
        self.transport.upload_file(rem_tmp, "repo/main/docs/conflict.md")

        # Bidirectional sync isolates conflict.md (exit_code=2) but still pushes clean.md!
        rep = self.coord.run_sync(mode="sync")
        self.assertEqual(rep.exit_code, 2)
        self.assertEqual(rep.conflicts, ["docs/conflict.md"])
        self.assertEqual(rep.pushed, ["docs/clean.md"])
        self.assertEqual(f_conflict.read_text(encoding="utf-8"), "Local Diverged\n")

        # Unidirectional pull without --force raises GDriveConflictError
        with self.assertRaises(GDriveConflictError):
            self.coord.run_sync(mode="pull", force=False)

        # Pull with --force --backup resolves to remote version and creates .conflict.<ts>.bak
        rep_forced = self.coord.run_sync(mode="pull", force=True, backup=True)
        self.assertEqual(rep_forced.exit_code, 0)
        self.assertIn("docs/conflict.md", rep_forced.pulled)
        self.assertEqual(f_conflict.read_text(encoding="utf-8"), "Remote Diverged\n")
        backups = list(self.docs_dir.glob("conflict.md.conflict.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "Local Diverged\n")
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_03_dirty_worktree_blocks_checkout_without_force(self) -> None:
        """Verify checkout_branch raises GDriveDirtyWorktreeError when local files have unsynced modifications."""
        f_doc = self.docs_dir / "doc.md"
        f_doc.write_text("v1\n", encoding="utf-8")
        self.coord.run_sync(mode="push")
        self.coord.create_branch("v1.0", from_branch="main")

        # Modify local file without syncing
        f_doc.write_text("unsynced local edit\n", encoding="utf-8")
        with self.assertRaises(GDriveDirtyWorktreeError):
            self.coord.checkout_branch("v1.0", force=False)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_04_stabilization_window_and_incremental_state_commit_on_mid_sync_failure(
        self,
    ) -> None:
        """Verify <2.0s large file stabilization deferral and per-file incremental state commit when a later file fails."""
        f_a = self.docs_dir / "a_first.md"
        f_b = self.docs_dir / "b_second.md"
        f_large = self.docs_dir / "c_large_writing.bin"
        f_a.write_text("File A\n", encoding="utf-8")
        f_b.write_text("File B\n", encoding="utf-8")
        with open(f_large, "wb") as lf:
            lf.truncate(10 * 1024 * 1024)
        large_mtime_ns = int(f_large.stat().st_mtime_ns)

        self.coord.init_repo()

        # 1. Verify <2.0s large file is deferred via skipped_stabilizing when now_ns is within 0.5s of mtime_ns
        orig_upload = self.transport.upload_file
        call_count = {"n": 0}

        def _failing_on_second_file(local_path, remote_path, in_place_file_id=None):
            if remote_path.endswith("b_second.md"):
                call_count["n"] += 1
                raise RuntimeError("Simulated mid-batch network drop on second file")
            return orig_upload(local_path, remote_path, in_place_file_id=in_place_file_id)

        self.transport.upload_file = _failing_on_second_file  # type: ignore[method-assign]
        try:
            with self.assertRaises(RuntimeError):
                self.coord.run_sync(mode="push", now_ns=large_mtime_ns + 500_000_000)
        finally:
            self.transport.upload_file = orig_upload  # type: ignore[method-assign]

        # Verify a_first.md was already committed to sync_state.json before b_second.md failed!
        saved_state = json.loads(
            (self.cache_dir / "sync_state.json").read_text(encoding="utf-8")
        )
        main_files = saved_state["branches"]["main"]["files"]
        self.assertIn("docs/a_first.md", main_files)
        self.assertNotIn("docs/b_second.md", main_files)

        # Remove b_second.md and verify c_large_writing.bin is reported in skipped_stabilizing when <2.0s
        f_b.unlink()
        rep_stab = self.coord.run_sync(
            mode="push", now_ns=large_mtime_ns + 500_000_000
        )
        self.assertIn("docs/c_large_writing.bin", rep_stab.skipped_stabilizing)
        self.assertNotIn("docs/c_large_writing.bin", rep_stab.pushed)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_06_repo_sync_disabled_gate_and_cloud_only_root_isolation(self) -> None:
        """
        Verify:
        1. When repo_sync_enabled=False, init_repo / list_branches / create_branch / checkout_branch / run_sync
           raise GDriveRepoSyncDisabledError, while atomic transport operations on <root_folder_id>/* remain available.
        2. When repo_sync_enabled=True, pure-cloud files at <root_folder_id>/cloud_only_notes.txt (outside repo_sync/)
           are 100% untouched by init_repo, run_sync, and checkout_branch.
        """
        # Upload a pure-cloud file at top-level root (outside repo_sync/)
        cloud_only_src = self.tmp_root / "cloud_only_notes.txt"
        cloud_only_src.write_text("Pure cloud asset - never pull to local workspace\n", encoding="utf-8")
        self.transport.upload_file(cloud_only_src, "cloud_only_notes.txt")
        self.transport.upload_file(cloud_only_src, "archives/dataset_2026.bin")

        disabled_cfg = GDriveConfig(
            root_folder_id="sandbox_root",
            active_branch="main",
            auto_sync=False,
            repo_sync_enabled=False,
            sandbox_dir=self.sandbox_dir.as_posix(),
            sync_spaces=(),
        )
        disabled_coord = SyncCoordinator(
            config=disabled_cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.cache_dir / "sync_state_disabled.json",
            lock_path=self.cache_dir / "sync_disabled.lock",
            log_path=self.cache_dir / "sync_disabled.log",
            readme_state_path=self.cache_dir / "readme_disabled.json",
            file_space_manager=self.fs_mgr,
        )

        with self.assertRaises(GDriveRepoSyncDisabledError):
            disabled_coord.init_repo()
        with self.assertRaises(GDriveRepoSyncDisabledError):
            disabled_coord.list_branches()
        with self.assertRaises(GDriveRepoSyncDisabledError):
            disabled_coord.create_branch("v1.0")
        with self.assertRaises(GDriveRepoSyncDisabledError):
            disabled_coord.checkout_branch("main")
        with self.assertRaises(GDriveRepoSyncDisabledError):
            disabled_coord.run_sync(mode="sync")

        # Now run enabled coordinator sync + branch + checkout and verify top-level pure-cloud files are untouched
        (self.docs_dir / "tracked.md").write_text("Tracked in repo_sync\n", encoding="utf-8")
        self.coord.run_sync(mode="sync", delete=True)
        self.coord.create_branch("v1.0", from_branch="main")
        self.coord.checkout_branch("v1.0")

        self.assertIsNotNone(self.transport.get_entry("cloud_only_notes.txt"))
        self.assertIsNotNone(self.transport.get_entry("archives/dataset_2026.bin"))
        self.assertFalse((self.proj_dir / "cloud_only_notes.txt").exists())
        self.assertFalse((self.docs_dir / "cloud_only_notes.txt").exists())
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_07_local_cache_driven_root_readme_soft_merge_and_soft_remove(self) -> None:
        """
        Verify local-cache-driven top-level <root_folder_id>/README.md lifecycle:
        1. Initial enable=False -> no-op (0 cloud writes).
        2. Pre-existing unmanaged root/README.md + transition to enable=True -> soft-merges managed block
           while preserving 100% of user text; subsequent calls with enable=True are cache hits (no-op).
        3. Transition to enable=False -> strips managed block and preserves user text (soft-remove).
        4. When root/README.md contains ONLY the managed block and transitions to enable=False -> moves to .trash/.
        """
        readme_state_file = self.cache_dir / "readme_transition_state.json"
        cfg_off = GDriveConfig(
            root_folder_id="sandbox_root",
            repo_sync_enabled=False,
            sandbox_dir=self.sandbox_dir.as_posix(),
        )
        cfg_on = GDriveConfig(
            root_folder_id="sandbox_root",
            repo_sync_enabled=True,
            sandbox_dir=self.sandbox_dir.as_posix(),
        )

        # 1. Initial enable=False -> no-op, records state False
        r0 = reconcile_root_readme_state(
            config=cfg_off, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r0["action"], "initialized_disabled_cache")
        self.assertIsNone(self.transport.get_entry("README.md"))

        # Create a user-written unmanaged README.md at cloud root
        user_readme = self.tmp_root / "user_root_readme.md"
        user_text = "# My Personal Cloud Drive\n\nImportant custom notes outside git.\n"
        user_readme.write_text(user_text, encoding="utf-8")
        self.transport.upload_file(user_readme, "README.md")

        # 2. Transition enable: False -> True -> soft-merges managed block preserving user_text
        r1 = reconcile_root_readme_state(
            config=cfg_on, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r1["action"], "soft_merged")
        dl_merged = self.tmp_root / "dl_merged.md"
        self.transport.download_file("README.md", dl_merged)
        merged_content = dl_merged.read_text(encoding="utf-8")
        self.assertIn("Important custom notes outside git.", merged_content)
        self.assertIn(ROOT_README_BEGIN_MARKER, merged_content)
        self.assertIn(ROOT_README_END_MARKER, merged_content)

        # Calling again with enable=True is a local cache hit (noop_cached)
        r1_repeat = reconcile_root_readme_state(
            config=cfg_on, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r1_repeat["action"], "noop_cached")

        # 3. Transition enable: True -> False -> soft-removes managed block, preserving user_text
        r2 = reconcile_root_readme_state(
            config=cfg_off, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r2["action"], "soft_removed")
        dl_stripped = self.tmp_root / "dl_stripped.md"
        self.transport.download_file("README.md", dl_stripped)
        stripped_content = dl_stripped.read_text(encoding="utf-8")
        self.assertIn("Important custom notes outside git.", stripped_content)
        self.assertNotIn(ROOT_README_BEGIN_MARKER, stripped_content)

        # 4. Remove user README.md, transition False -> True (creates pure managed README.md),
        #    then True -> False (moves pure managed README.md to .trash/)
        self.transport.trash_file("README.md")
        r3 = reconcile_root_readme_state(
            config=cfg_on, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r3["action"], "created")
        self.assertIsNotNone(self.transport.get_entry("README.md"))

        r4 = reconcile_root_readme_state(
            config=cfg_off, transport=self.transport, readme_state_path=readme_state_file
        )
        self.assertEqual(r4["action"], "removed_to_trash")
        self.assertIsNone(self.transport.get_entry("README.md"))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_05_path_escape_guard_and_external_branch_shortcut_cow_and_push_backup(self) -> None:
        """
        Verify security and logic invariants from blind audit:
        1. Unmapped remote files outside SyncSpaceSpec.include_roots (e.g., 'secrets/leak.txt' when
           only 'docs' is included) are blocked by _resolve_remote_rel_to_local_abs() during pull/sync.
        2. An external Shortcut created directly on another branch ('ext_br') without updating local
           sync_state.json is discovered during run_sync() and triggers Copy-on-Write into repo/.history/.
        3. Unidirectional push with --force --backup creates a remote .conflict.<ts>.bak before overwriting.
        """
        strict_cfg = GDriveConfig(
            root_folder_id="sandbox_root",
            active_branch="main",
            auto_sync=False,
            repo_sync_enabled=True,
            sandbox_dir=self.sandbox_dir.as_posix(),
            sync_spaces=(
                SyncSpaceSpec(
                    space="docs",
                    include_roots=(self.docs_dir.as_posix(),),
                ),
            ),
        )
        strict_coord = SyncCoordinator(
            config=strict_cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.cache_dir / "strict_sync_state.json",
            lock_path=self.cache_dir / "strict_sync.lock",
            log_path=self.cache_dir / "strict_sync.log",
            readme_state_path=self.cache_dir / "strict_readme.json",
            file_space_manager=self.fs_mgr,
        )
        strict_coord.init_repo()

        # 1. Upload an out-of-scope file 'repo/main/secrets/leak.txt' and verify pull ignores it
        leak_src = self.tmp_root / "leak.txt"
        leak_src.write_text("should never write outside docs/\n", encoding="utf-8")
        self.transport.upload_file(leak_src, "repo/main/secrets/leak.txt")
        rep_pull = strict_coord.run_sync(mode="pull")
        self.assertNotIn("secrets/leak.txt", rep_pull.pulled)
        self.assertFalse((self.proj_dir / "secrets" / "leak.txt").exists())

        # Remove the stray out-of-scope remote file so subsequent tests stay clean
        self.transport.trash_file("repo/main/secrets/leak.txt")

        # 2. Push docs/spec.md v1, then create branch 'ext_br' and add an external shortcut via transport directly
        f_spec = self.docs_dir / "spec.md"
        f_spec.write_text("Spec v1\n", encoding="utf-8")
        strict_coord.run_sync(mode="push")

        # Create branch 'ext_br' before adding another file 'docs/late_added.md'
        strict_coord.create_branch("ext_br", from_branch="main")
        f_late = self.docs_dir / "late_added.md"
        f_late.write_text("Late v1\n", encoding="utf-8")
        strict_coord.run_sync(mode="push")
        late_v1_entry = self.transport.get_entry("repo/main/docs/late_added.md")
        assert late_v1_entry is not None
        fid_late_v1 = late_v1_entry.file_id

        # Simulate external agent adding a shortcut on 'ext_br' pointing to fid_late_v1 without updating .yscb_gdrive.json
        self.transport.create_shortcut(fid_late_v1, "repo/ext_br/docs/late_added.md")

        # Modify docs/late_added.md locally and push -> must refresh 'ext_br' snapshot and CoW fid_late_v1 to repo/.history/
        f_late.write_text("Late v2\n", encoding="utf-8")
        rep_cow = strict_coord.run_sync(mode="push")
        self.assertIn(fid_late_v1, rep_cow.moved_to_history)

        # 3. Simulate conflict on docs/spec.md and verify push --force --backup creates local .remote_conflict.*.bak
        f_spec.write_text("Spec v3 Local\n", encoding="utf-8")
        rem_div = self.tmp_root / "rem_spec_div.md"
        rem_div.write_text("Spec v3 Remote Diverged\n", encoding="utf-8")
        self.transport.upload_file(rem_div, "repo/main/docs/spec.md")

        rep_push_bak = strict_coord.run_sync(mode="push", force=True, backup=True)
        self.assertIn("docs/spec.md", rep_push_bak.pushed)
        rem_baks = list(self.docs_dir.glob("spec.md.remote_conflict.*.bak"))
        self.assertEqual(len(rem_baks), 1)
        self.assertEqual(rem_baks[0].read_text(encoding="utf-8"), "Spec v3 Remote Diverged\n")
        self.mark_passed()

    @require(Requirement.ENV)
    def test_et_06_orthogonal_cloud_branch_discovery_both_deleted_prune_and_untracked_checkout_guard(self) -> None:
        """
        Verify the 3 orthogonal multi-dimensional edge cases:
        1. Cloud-created branch directory ('repo/cloud_feat/') without updating .yscb_gdrive.json is
           auto-discovered by list_branches(), checkout_branch(), and run_sync() CoW ref-counting.
        2. When a tracked file is deleted on both local and remote and synced WITHOUT --delete,
           its ghost baseline in sync_state.json and .yscb_gdrive.json['branch_files'] is pruned
           so recreating the file later performs a clean PUSH_NEW without false conflict.
        3. checkout_branch(..., force=True) preserves untracked local files (e.g. .gitignore files
           in sync_spaces not yet in curr_base) when absent on target branch, and auto-backups them
           before overwriting when target branch has a colliding path.
        """
        self.coord.init_repo()

        # --- Sub-case 1: Both-side deletion without --delete prunes ghost baseline ---
        f_ghost = self.docs_dir / "ghost_test.md"
        f_ghost.write_text("Ghost v1\n", encoding="utf-8")
        self.coord.run_sync(mode="sync")
        self.assertIsNotNone(self.transport.get_entry("repo/main/docs/ghost_test.md"))

        # Delete on both local and remote, then run sync WITHOUT --delete
        f_ghost.unlink()
        self.transport.trash_file("repo/main/docs/ghost_test.md")
        rep_both_del = self.coord.run_sync(mode="sync", delete=False)
        self.assertEqual(rep_both_del.conflicts, [])

        # Recreate f_ghost with new content and sync WITHOUT --delete -> must cleanly PUSH_NEW (no conflict!)
        f_ghost.write_text("Ghost v2 Reborn\n", encoding="utf-8")
        rep_reborn = self.coord.run_sync(mode="sync", delete=False, now_ns=time.time_ns() + 5_000_000_000)
        self.assertEqual(rep_reborn.conflicts, [])
        self.assertIn("docs/ghost_test.md", rep_reborn.pushed)

        # --- Sub-case 2: Cloud-created branch directory auto-discovery ---
        self.transport.mkdir("repo/cloud_feat")
        cloud_only_src = self.tmp_root / "cloud_branch_doc.md"
        cloud_only_src.write_text("Created on Cloud Branch\n", encoding="utf-8")
        self.transport.upload_file(cloud_only_src, "repo/cloud_feat/docs/cloud_doc.md")
        # Also upload a colliding file on cloud_feat
        colliding_remote = self.tmp_root / "colliding_remote.md"
        colliding_remote.write_text("Remote Colliding Content on cloud_feat\n", encoding="utf-8")
        self.transport.upload_file(colliding_remote, "repo/cloud_feat/docs/untracked_collide.md")

        branches_info = self.coord.list_branches()
        self.assertIn("cloud_feat", branches_info["branches"])
        self.assertTrue(branches_info["branches"]["cloud_feat"].get("auto_discovered"))

        # --- Sub-case 3: Untracked local (.gitignore) file protection during checkout --force ---
        untracked_keep = self.docs_dir / "untracked_local_only.md"
        untracked_keep.write_text("Local gitignored config to keep\n", encoding="utf-8")
        untracked_collide = self.docs_dir / "untracked_collide.md"
        untracked_collide.write_text("Local gitignored colliding v1\n", encoding="utf-8")

        co_res = self.coord.checkout_branch("cloud_feat", force=True, backup=False)
        self.assertEqual(co_res["active_branch"], "cloud_feat")
        # Tracked main file ('docs/ghost_test.md') absent on cloud_feat is removed as orphan
        self.assertFalse(f_ghost.exists())
        # Untracked local file absent on cloud_feat is preserved!
        self.assertTrue(untracked_keep.is_file())
        self.assertEqual(untracked_keep.read_text(encoding="utf-8"), "Local gitignored config to keep\n")
        # Untracked local file colliding with cloud_feat was automatically backed up even with backup=False!
        self.assertEqual(untracked_collide.read_text(encoding="utf-8"), "Remote Colliding Content on cloud_feat\n")
        collide_baks = list(self.docs_dir.glob("untracked_collide.md.conflict.*.bak"))
        self.assertEqual(len(collide_baks), 1)
        self.assertEqual(collide_baks[0].read_text(encoding="utf-8"), "Local gitignored colliding v1\n")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_09_parallel_push_pull_and_branch_create_precreates_dirs(self) -> None:
        """
        Verify multi-directory concurrent push, create_branch, and pull pre-create parent
        directories deterministically before parallel file/shortcut transfers and maintain
        100% state integrity across multiple nested subdirectories.
        """
        self.coord.init_repo()
        nested_paths = [
            "a/b/c/file_1.md",
            "a/b/c/file_2.md",
            "a/b/d/file_3.md",
            "x/y/z/file_4.md",
            "x/y/z/file_5.md",
            "root_file.md",
        ]
        for rel in nested_paths:
            f_path = self.docs_dir / rel
            f_path.parent.mkdir(parents=True, exist_ok=True)
            f_path.write_text(f"Content of {rel}\n", encoding="utf-8")

        precreated_before_upload = set()
        upload_started = {"flag": False}
        orig_mkdir = self.transport.mkdir
        orig_upload = self.transport.upload_file

        def _spy_mkdir(remote_rel_path: str):
            if not upload_started["flag"]:
                precreated_before_upload.add(remote_rel_path)
            return orig_mkdir(remote_rel_path)

        def _spy_upload(local_path: Path, remote_rel_path: str, in_place_file_id=None):
            if remote_rel_path.startswith("repo/main/docs/"):
                upload_started["flag"] = True
            return orig_upload(local_path, remote_rel_path, in_place_file_id=in_place_file_id)

        self.transport.mkdir = _spy_mkdir  # type: ignore[method-assign]
        self.transport.upload_file = _spy_upload  # type: ignore[method-assign]
        try:
            rep_push = self.coord.run_sync(mode="push")
        finally:
            self.transport.mkdir = orig_mkdir  # type: ignore[method-assign]
            self.transport.upload_file = orig_upload  # type: ignore[method-assign]

        expected_pushed = sorted(f"docs/{p}" for p in nested_paths)
        self.assertEqual(rep_push.pushed, expected_pushed)
        self.assertIn("repo/main/docs/a/b/c", precreated_before_upload)
        self.assertIn("repo/main/docs/a/b/d", precreated_before_upload)
        self.assertIn("repo/main/docs/x/y/z", precreated_before_upload)

        # Create branch 'parallel_br' concurrently
        br_res = self.coord.create_branch("parallel_br", from_branch="main")
        self.assertEqual(br_res["shortcuts_created"], len(nested_paths))

        # Delete local files and pull concurrently from 'main'
        shutil.rmtree(self.docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        # Clear local state baseline to trigger PULL_NEW for all files
        (self.cache_dir / "sync_state.json").unlink(missing_ok=True)

        rep_pull = self.coord.run_sync(mode="pull")
        self.assertEqual(rep_pull.pulled, expected_pushed)
        for rel in nested_paths:
            self.assertEqual(
                (self.docs_dir / rel).read_text(encoding="utf-8"),
                f"Content of {rel}\n",
            )
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_10_sandbox_changes_api_physical_and_shortcut_virtual_items(self) -> None:
        """
        Verify LocalSandboxTransport.get_start_page_token() and list_changes():
        - Tracks physical file creation/modification/trash, Shortcut target changes, and virtual entries.
        - Rejects invalid or expired page_token with GDriveTransportError.
        """
        tok0 = self.transport.get_start_page_token()
        self.assertTrue(tok0.startswith("sbx_"))

        src_f = self.tmp_root / "src_change.md"
        src_f.write_text("Initial v1\n", encoding="utf-8")
        ent_f = self.transport.upload_file(src_f, "docs/change_target.md")
        ent_sc = self.transport.create_shortcut(
            ent_f.file_id, "shortcuts/change_sc.md"
        )
        virt_fid = self.transport.inject_virtual_entry(
            "virtual/doc.gdoc",
            mime_type="application/vnd.google-apps.document",
            md5="virt_md5_1",
            size=42,
        )

        changes1, tok1 = self.transport.list_changes(tok0)
        self.assertNotEqual(tok1, tok0)
        by_id1 = {c.file_id: c for c in changes1}
        self.assertIn(ent_f.file_id, by_id1)
        self.assertFalse(by_id1[ent_f.file_id].removed)
        self.assertIn(ent_sc.file_id, by_id1)
        self.assertFalse(by_id1[ent_sc.file_id].removed)
        self.assertIn(virt_fid, by_id1)
        self.assertFalse(by_id1[virt_fid].removed)

        # No-op check
        changes_noop, tok2 = self.transport.list_changes(tok1)
        self.assertEqual(changes_noop, [])

        # Modify physical file (which is also the target of ent_sc) and trash virtual item
        src_f.write_text("Updated v2 Content\n", encoding="utf-8")
        self.transport.upload_file(
            src_f, "docs/change_target.md", in_place_file_id=ent_f.file_id
        )
        self.transport.trash_file("virtual/doc.gdoc")

        changes2, _tok3 = self.transport.list_changes(tok2)
        by_id2 = {c.file_id: c for c in changes2}
        self.assertIn(ent_f.file_id, by_id2)
        self.assertFalse(by_id2[ent_f.file_id].removed)
        self.assertIn(ent_sc.file_id, by_id2)
        self.assertFalse(by_id2[ent_sc.file_id].removed)
        assert by_id2[ent_sc.file_id].entry is not None
        assert by_id2[ent_f.file_id].entry is not None
        self.assertEqual(
            by_id2[ent_sc.file_id].entry.md5, by_id2[ent_f.file_id].entry.md5
        )
        self.assertIn(virt_fid, by_id2)
        self.assertTrue(by_id2[virt_fid].removed)

        # Negative assertion: invalid/expired token raises GDriveTransportError
        with self.assertRaises(GDriveTransportError):
            self.transport.list_changes("sbx_999999_expired")
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_11_changes_api_three_level_cache_short_circuit_and_shortcut_target_patch(
        self,
    ) -> None:
        """
        Verify SyncCoordinator 3-level remote_repo_cache with changes API:
        - Level 0: Second run_sync makes 0 list_files calls and reports cache_hit_level == 0.
        - Level 1: Single remote file update, new file in known dir, topological new nested subdirectories,
          and Shortcut target_file_id update patch cache in-memory with 0 list_files calls (cache_hit_level == 1).
        - Level 2: Moving/renaming an existing directory or creating a new cloud branch under repo/
          safely falls back to full scan (cache_hit_level == 2).
        """
        f_guide = self.docs_dir / "guide.md"
        f_guide.write_text("Guide v1\n", encoding="utf-8")

        rep_init = self.coord.run_sync(mode="sync")
        self.assertEqual(rep_init.cache_hit_level, 2)
        self.assertEqual(rep_init.pushed, ["docs/guide.md"])

        list_files_calls = {"n": 0}
        orig_list_files = self.transport.list_files

        def _counting_list_files(remote_path: str = "", recursive: bool = False):
            list_files_calls["n"] += 1
            return orig_list_files(remote_path, recursive=recursive)

        self.transport.list_files = _counting_list_files  # type: ignore[method-assign]
        try:
            # 1. Level 0: 0 cloud changes -> 0 list_files calls, cache_hit_level == 0
            list_files_calls["n"] = 0
            rep_l0 = self.coord.run_sync(mode="sync")
            self.assertEqual(rep_l0.cache_hit_level, 0)
            self.assertEqual(list_files_calls["n"], 0)

            # 2. Level 1: Remote in-place file update + new file (including docs/README.md) in existing 'docs' directory
            rem_v2 = self.tmp_root / "rem_guide_v2.md"
            rem_v2.write_text("Guide v2 Remote Patch\n", encoding="utf-8")
            guide_ent = self.transport.get_entry("repo/main/docs/guide.md")
            assert guide_ent is not None
            self.transport.upload_file(
                rem_v2, "repo/main/docs/guide.md", in_place_file_id=guide_ent.file_id
            )
            rem_added = self.tmp_root / "rem_added.md"
            rem_added.write_text("Added in known dir\n", encoding="utf-8")
            self.transport.upload_file(rem_added, "repo/main/docs/added.md")
            rem_sub_readme = self.tmp_root / "rem_sub_readme.md"
            rem_sub_readme.write_text("Subdir README v1\n", encoding="utf-8")
            self.transport.upload_file(rem_sub_readme, "repo/main/docs/README.md")

            list_files_calls["n"] = 0
            rep_l1 = self.coord.run_sync(mode="sync")
            self.assertEqual(rep_l1.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertEqual(
                sorted(rep_l1.pulled),
                ["docs/README.md", "docs/added.md", "docs/guide.md"],
            )
            self.assertEqual(
                f_guide.read_text(encoding="utf-8"), "Guide v2 Remote Patch\n"
            )
            self.assertEqual(
                (self.docs_dir / "added.md").read_text(encoding="utf-8"),
                "Added in known dir\n",
            )
            self.assertEqual(
                (self.docs_dir / "README.md").read_text(encoding="utf-8"),
                "Subdir README v1\n",
            )

            # 3. Level 1 Shortcut target_file_id update AND removal propagation:
            # Create branch v1.0, checkout v1.0, warm cache on v1.0, then modify & delete target_file_id on main
            self.coord.create_branch("v1.0", from_branch="main")
            self.coord.checkout_branch("v1.0")
            rep_v1_warm = self.coord.run_sync(mode="sync")
            self.assertEqual(rep_v1_warm.cache_hit_level, 2)

            rem_v3 = self.tmp_root / "rem_guide_v3_target.md"
            rem_v3.write_text("Guide v3 Shortcut Target Updated\n", encoding="utf-8")
            self.transport.upload_file(
                rem_v3, "repo/main/docs/guide.md", in_place_file_id=guide_ent.file_id
            )

            list_files_calls["n"] = 0
            rep_sc_l1 = self.coord.run_sync(mode="pull")
            self.assertEqual(rep_sc_l1.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertIn("docs/guide.md", rep_sc_l1.pulled)
            self.assertEqual(
                f_guide.read_text(encoding="utf-8"),
                "Guide v3 Shortcut Target Updated\n",
            )

            # Trash the Shortcut target file on main -> Level 1 removes referencing Shortcut entry from v1.0 cache
            self.transport.trash_file("repo/main/docs/guide.md")
            list_files_calls["n"] = 0
            rep_sc_rm = self.coord.run_sync(mode="pull", delete=True)
            self.assertEqual(rep_sc_rm.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertEqual(rep_sc_rm.deleted_local, ["docs/guide.md"])
            self.assertFalse(f_guide.exists())

            # 4. Level 1 Topological Subdirectory Patch: Create a new remote subdirectory under repo/v1.0/docs/new_sub/
            rem_sub = self.tmp_root / "rem_sub_doc.md"
            rem_sub.write_text("Deep Subdir Doc\n", encoding="utf-8")
            self.transport.upload_file(
                rem_sub, "repo/v1.0/docs/new_sub/deep_doc.md"
            )

            list_files_calls["n"] = 0
            rep_sub_l1 = self.coord.run_sync(mode="pull")
            self.assertEqual(rep_sub_l1.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertIn("docs/new_sub/deep_doc.md", rep_sub_l1.pulled)
            self.assertEqual(
                (self.docs_dir / "new_sub" / "deep_doc.md").read_text(
                    encoding="utf-8"
                ),
                "Deep Subdir Doc\n",
            )

            # 5. Level 2 Fallback: Renaming an existing tracked subdirectory falls back to full scan
            self.transport.move_file(
                "repo/v1.0/docs/new_sub", "repo/v1.0/docs/renamed_sub"
            )
            rep_l2 = self.coord.run_sync(mode="pull", delete=True)
            self.assertEqual(rep_l2.cache_hit_level, 2)
            self.assertIn("docs/renamed_sub/deep_doc.md", rep_l2.pulled)
            self.assertFalse((self.docs_dir / "new_sub" / "deep_doc.md").exists())
            self.assertEqual(
                (self.docs_dir / "renamed_sub" / "deep_doc.md").read_text(
                    encoding="utf-8"
                ),
                "Deep Subdir Doc\n",
            )
        finally:
            self.transport.list_files = orig_list_files  # type: ignore[method-assign]
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_13_level1_topological_nested_subdirs_removal_shortcut_purge_and_zero_stat_snapshot(
        self,
    ) -> None:
        """
        Verify:
        1. Level 1 creates multi-level new subdirectories (e.g. plans/2026_11_05_new/sub_01) and files
           in a single batch with 0 list_files calls, registering all new dir_ids into cache and pulling files.
        2. Level 1 deleting a known subdirectory purges its subtree from dir_ids, raw_entries, and
           cross-branch Shortcuts pointing to files inside that deleted subdirectory.
        3. collect_space_local_files_with_stat and _collect_local_snapshot reuse iter_space_files_with_stat
           (mtime_ns, size) without calling Path.stat() or Path.is_file() during local snapshot collection.
        """
        f_init = self.docs_dir / "root.md"
        f_init.write_text("Root v1\n", encoding="utf-8")
        rep_init = self.coord.run_sync(mode="sync")
        self.assertEqual(rep_init.cache_hit_level, 2)

        list_files_calls = {"n": 0}
        orig_list_files = self.transport.list_files

        def _counting_list_files(remote_path: str = "", recursive: bool = False):
            list_files_calls["n"] += 1
            return orig_list_files(remote_path, recursive=recursive)

        self.transport.list_files = _counting_list_files  # type: ignore[method-assign]
        try:
            # (a) Multi-level new subdirectories + files in a single batch -> Level 1 (0 list_files calls)
            f_plan_a = self.tmp_root / "plan_a.md"
            f_plan_b = self.tmp_root / "plan_b.md"
            f_plan_a.write_text("Plan Spec A\n", encoding="utf-8")
            f_plan_b.write_text("Plan Task B\n", encoding="utf-8")
            self.transport.upload_file(
                f_plan_a, "repo/main/docs/plans/2026_11_05_new/P00_discuss.md"
            )
            ent_b = self.transport.upload_file(
                f_plan_b, "repo/main/docs/plans/2026_11_05_new/sub_01/task.md"
            )

            list_files_calls["n"] = 0
            rep_nested = self.coord.run_sync(mode="pull")
            self.assertEqual(rep_nested.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertEqual(
                sorted(rep_nested.pulled),
                [
                    "docs/plans/2026_11_05_new/P00_discuss.md",
                    "docs/plans/2026_11_05_new/sub_01/task.md",
                ],
            )
            self.assertEqual(
                (
                    self.docs_dir
                    / "plans"
                    / "2026_11_05_new"
                    / "sub_01"
                    / "task.md"
                ).read_text(encoding="utf-8"),
                "Plan Task B\n",
            )
            saved_state = json.loads(
                (self.cache_dir / "sync_state.json").read_text(encoding="utf-8")
            )
            cached_main_dirs = saved_state["remote_repo_cache"]["branches"]["main"][
                "dir_ids"
            ].values()
            self.assertIn("docs/plans", cached_main_dirs)
            self.assertIn("docs/plans/2026_11_05_new", cached_main_dirs)
            self.assertIn("docs/plans/2026_11_05_new/sub_01", cached_main_dirs)

            # (b) Create branch v1.0 (which has Shortcuts to main's files in docs/plans/2026_11_05_new/...),
            #     checkout v1.0, warm cache, then trash the entire subdirectory on main!
            self.coord.create_branch("v1.0", from_branch="main")
            self.coord.checkout_branch("v1.0")
            rep_warm = self.coord.run_sync(mode="sync")
            self.assertEqual(rep_warm.cache_hit_level, 2)

            # Trash the parent directory on main -> removes physical files on main AND purges v1.0's shortcuts in Level 1
            self.transport.trash_file("repo/main/docs/plans/2026_11_05_new")
            list_files_calls["n"] = 0
            rep_del_dir = self.coord.run_sync(mode="pull", delete=True)
            self.assertEqual(rep_del_dir.cache_hit_level, 1)
            self.assertEqual(list_files_calls["n"], 0)
            self.assertEqual(
                sorted(rep_del_dir.deleted_local),
                [
                    "docs/plans/2026_11_05_new/P00_discuss.md",
                    "docs/plans/2026_11_05_new/sub_01/task.md",
                ],
            )
            saved_after_del = json.loads(
                (self.cache_dir / "sync_state.json").read_text(encoding="utf-8")
            )
            main_after = saved_after_del["remote_repo_cache"]["branches"]["main"]
            v1_after = saved_after_del["remote_repo_cache"]["branches"]["v1.0"]
            self.assertNotIn(
                "docs/plans/2026_11_05_new", main_after["dir_ids"].values()
            )
            self.assertNotIn(
                "docs/plans/2026_11_05_new/sub_01", main_after["dir_ids"].values()
            )
            self.assertNotIn(
                "docs/plans/2026_11_05_new/sub_01/task.md", main_after["raw_entries"]
            )
            self.assertNotIn(
                "docs/plans/2026_11_05_new/sub_01/task.md", v1_after["raw_entries"]
            )
            self.assertNotIn(ent_b.file_id, v1_after["raw_entries"].values())
        finally:
            self.transport.list_files = orig_list_files  # type: ignore[method-assign]

        # (c) Verify zero-redundant stat() when file_space_manager provides iter_space_files_with_stat
        class _StatProvidingFileSpaceManager:
            def __init__(self, root_dir: Path) -> None:
                self.root_dir = root_dir

            def iter_space_files_with_stat(self, _space_name: str):
                f_p = self.root_dir / "root.md"
                st = os.stat(f_p)
                yield (
                    "root.md",
                    f_p,
                    self.root_dir,
                    int(st.st_mtime_ns),
                    int(st.st_ctime_ns),
                    int(st.st_size),
                )

            def iter_space_files(self, _space_name: str):
                raise AssertionError(
                    "iter_space_files should not be called when iter_space_files_with_stat is present"
                )

        stat_mgr = _StatProvidingFileSpaceManager(self.docs_dir)
        spec_docs = SyncSpaceSpec(space="docs")
        with_stat_map = collect_space_local_files_with_stat(
            spec_docs,
            project_root=self.proj_dir,
            file_space_manager=stat_mgr,
        )
        self.assertIn("docs/root.md", with_stat_map)
        abs_p, m_ns, sz_val = with_stat_map["docs/root.md"]
        self.assertEqual(abs_p, self.docs_dir / "root.md")
        self.assertIsNotNone(m_ns)
        self.assertIsNotNone(sz_val)

        # Warm fingerprint_cache so compute_local_hashes is also a cache hit, then block Path.stat
        self.coord._file_space_manager = stat_mgr
        state_obj = self.coord._load_local_state()
        self.coord._collect_local_snapshot(state_obj)

        orig_path_stat = Path.stat

        def _forbid_stat(path_self: Path, *args, **kwargs):
            if path_self == (self.docs_dir / "root.md"):
                raise AssertionError(
                    f"Redundant Path.stat() called on {path_self} despite pre-collected stat!"
                )
            return orig_path_stat(path_self, *args, **kwargs)

        Path.stat = _forbid_stat  # type: ignore[method-assign]
        try:
            snap_zero_stat, _, _ = self.coord._collect_local_snapshot(state_obj)
        finally:
            Path.stat = orig_path_stat  # type: ignore[method-assign]

        self.assertIn("docs/root.md", snap_zero_stat)
        self.assertEqual(snap_zero_stat["docs/root.md"].size, sz_val)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_12_cli_yield_signal_preemption_orphan_self_healing_and_atomic_cow_mid_sync(
        self,
    ) -> None:
        """
        Verify foreground CLI lock preemption and atomic per-file CoW safety:
        1. Orphan cli_yield.signal (expired ts > 120s or dead PID) is auto-cleaned and does not yield.
        2. Foreground _acquire_lock(non_blocking=False) writes cli_yield.signal when lock is busy,
           preempts background_worker=True sync, and immediately unlinks cli_yield.signal upon lock acquisition.
        3. When Stage 3 yields mid-batch during PUSH_UPDATE with CoW, completed files have both CoW .history/
           and .yscb_gdrive.json committed, while unstarted files are NOT prematurely moved to .history/.
        """
        # 1. Orphan signal self-healing (expired timestamp & dead PID)
        self.coord.yield_signal_path.parent.mkdir(parents=True, exist_ok=True)
        self.coord.yield_signal_path.write_text(
            json.dumps({"pid": os.getpid(), "ts": time.time() - 250.0}),
            encoding="utf-8",
        )
        self.assertFalse(self.coord.should_yield_background())
        self.assertFalse(self.coord.yield_signal_path.exists())

        self.coord.yield_signal_path.write_text(
            json.dumps({"pid": 99999999, "ts": time.time()}),
            encoding="utf-8",
        )
        self.assertFalse(self.coord.should_yield_background())
        self.assertFalse(self.coord.yield_signal_path.exists())

        # 2. Setup 2 tracked files referenced by branch 'v1.0' so updating on 'main' requires CoW
        f1 = self.docs_dir / "cow_1.md"
        f2 = self.docs_dir / "cow_2.md"
        f1.write_text("CoW 1 v1\n", encoding="utf-8")
        f2.write_text("CoW 2 v1\n", encoding="utf-8")
        self.coord.run_sync(mode="push")
        ent1_v1 = self.transport.get_entry("repo/main/docs/cow_1.md")
        ent2_v1 = self.transport.get_entry("repo/main/docs/cow_2.md")
        assert ent1_v1 is not None and ent2_v1 is not None
        fid1_v1 = ent1_v1.file_id
        fid2_v1 = ent2_v1.file_id

        self.coord.create_branch("v1.0", from_branch="main")

        # Modify both files locally on main
        f1.write_text("CoW 1 v2 Updated\n", encoding="utf-8")
        f2.write_text("CoW 2 v2 Updated\n", encoding="utf-8")

        import gdrive_support.coordinator as coord_mod

        orig_workers = coord_mod.PARALLEL_TRANSFER_WORKERS
        coord_mod.PARALLEL_TRANSFER_WORKERS = 1
        orig_upload = self.transport.upload_file
        first_upload_entered = threading.Event()
        fg_lock_acquired = threading.Event()
        fg_errors: list[BaseException] = []

        def _fg_lock_requester() -> None:
            first_upload_entered.wait(timeout=5.0)
            try:
                fg_lock = self.coord._acquire_lock(
                    non_blocking=False, timeout_sec=10.0
                )
                try:
                    # Signal file must already be unlinked as soon as _acquire_lock returns
                    if self.coord.yield_signal_path.exists():
                        fg_errors.append(
                            AssertionError("cli_yield.signal was not cleaned up!")
                        )
                    fg_lock_acquired.set()
                finally:
                    fg_lock.release()
            except BaseException as exc:
                fg_errors.append(exc)

        def _hooked_upload(
            local_path: Path, remote_path: str, in_place_file_id=None
        ):
            res = orig_upload(
                local_path, remote_path, in_place_file_id=in_place_file_id
            )
            if remote_path.endswith("cow_1.md") and not first_upload_entered.is_set():
                first_upload_entered.set()
                # Wait briefly until foreground thread writes cli_yield.signal
                deadline = time.time() + 3.0
                while (
                    time.time() < deadline
                    and not self.coord.yield_signal_path.exists()
                ):
                    time.sleep(0.02)
            return res

        self.transport.upload_file = _hooked_upload  # type: ignore[method-assign]
        fg_thread = threading.Thread(target=_fg_lock_requester, daemon=True)
        fg_thread.start()
        try:
            rep_bg = self.coord.run_sync(
                mode="push", non_blocking_lock=True, background_worker=True
            )
            fg_thread.join(timeout=10.0)
        finally:
            self.transport.upload_file = orig_upload  # type: ignore[method-assign]
            coord_mod.PARALLEL_TRANSFER_WORKERS = orig_workers

        self.assertEqual(fg_errors, [])
        self.assertTrue(fg_lock_acquired.is_set())
        self.assertFalse(self.coord.yield_signal_path.exists())
        self.assertTrue(rep_bg.yielded)
        self.assertEqual(rep_bg.pushed, ["docs/cow_1.md"])
        self.assertIn(fid1_v1, rep_bg.moved_to_history)
        self.assertNotIn(fid2_v1, rep_bg.moved_to_history)

        # Verify cow_2.md was NOT prematurely moved to .history/ on remote!
        rem_cow2 = self.transport.get_entry("repo/main/docs/cow_2.md")
        assert rem_cow2 is not None
        self.assertEqual(rem_cow2.file_id, fid2_v1)

        # Verify remote .yscb_gdrive.json was atomically saved in finally with fid1_v1 in history_files
        remote_meta = self.coord._read_remote_repo_meta()
        assert remote_meta is not None
        self.assertIn(fid1_v1, remote_meta["history_files"])
        self.assertNotIn(fid2_v1, remote_meta["history_files"])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation(
        self,
    ) -> None:
        """
        Verify deep audit remediations across SyncCoordinator and CLI sandbox isolation:
        1. Unpushed local changes in pull mode preserve their baseline entry (not overwritten by IN_SYNC),
           so a subsequent push mode detects and uploads the local modification.
        2. Empty sync_spaces raises GDriveConfigError instead of silently treating worktree as empty.
        3. Branch-root README.md (e.g. <repo>/<branch>/README.md) and dot/underscore directories
           (e.g. .github/workflows/ci.yml, _internal/spec.md) are synced and incrementally patched in Level 1.
        4. Deleting the last file inside a remote subdirectory prunes empty remote subdirectories bottom-up
           while preserving the branch root and system directories.
        5. Sandbox checkout and CLI --sandbox-dir isolate state/lock/log/readme_state and never pollute
           global config://gdrive-support/ active_branch.
        """
        from gdrive_support.config import GDriveConfig, GDriveConfigError, PathMappingRule, SyncSpaceSpec
        from gdrive_support.coordinator import SyncCoordinator

        # 1. Empty sync_spaces guard
        empty_cfg = GDriveConfig(
            root_folder_id="dummy_root",
            sandbox_dir=str(self.sandbox_dir),
            repo_sync_enabled=True,
            sync_spaces=(),
        )
        empty_coord = SyncCoordinator(
            config=empty_cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.coord.state_path,
            lock_path=self.coord.lock_path,
            log_path=self.coord.log_path,
            readme_state_path=self.coord.readme_state_path,
            file_space_manager=self.fs_mgr,
        )
        with self.assertRaises(GDriveConfigError):
            empty_coord.run_sync(mode="sync")

        # 2. Local modification during pull mode must NOT overwrite baseline, so subsequent push uploads it
        doc_a = self.docs_dir / "keep_baseline.md"
        doc_a.write_text("v1 baseline\n", encoding="utf-8")
        self.coord.run_sync(mode="push")

        doc_a.write_text("v2 local unpushed edit\n", encoding="utf-8")
        rep_pull = self.coord.run_sync(mode="pull")
        self.assertEqual(rep_pull.pushed, [])
        self.assertEqual(rep_pull.pulled, [])

        rep_push = self.coord.run_sync(mode="push")
        self.assertIn("docs/keep_baseline.md", rep_push.pushed)
        dl_check = self.tmp_root / "dl_keep_baseline.md"
        self.transport.download_file("repo/main/docs/keep_baseline.md", dl_check)
        self.assertEqual(
            dl_check.read_text(encoding="utf-8"), "v2 local unpushed edit\n"
        )

        # 3. Empty remote directory bottom-up pruning on DELETE_REMOTE
        deep_file = self.docs_dir / "2026_11_05_prune" / "nested" / "P01.md"
        deep_file.parent.mkdir(parents=True, exist_ok=True)
        deep_file.write_text("# Prune Me\n", encoding="utf-8")
        self.coord.run_sync(mode="push")
        self.assertIsNotNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_prune/nested")
        )

        deep_file.unlink()
        shutil.rmtree(self.docs_dir / "2026_11_05_prune")
        rep_del = self.coord.run_sync(mode="push", delete=True)
        self.assertIn("docs/2026_11_05_prune/nested/P01.md", rep_del.deleted_remote)
        self.assertIsNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_prune/nested")
        )
        self.assertIsNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_prune")
        )
        self.assertIsNotNone(self.transport.get_entry("repo/main"))

        # 3b. Pre-existing empty remote directory shells are NOT trashed when deleted_remote is empty
        # (protects newly mkdir'd cloud folders while external agents are still uploading files into them!)
        self.transport.mkdir("repo/main/docs/2026_11_05_new_cloud_dir/sub_shell")
        self.assertIsNotNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_new_cloud_dir/sub_shell")
        )
        rep_shell_keep = self.coord.run_sync(mode="sync")
        self.assertEqual(rep_shell_keep.deleted_remote, [])
        self.assertIsNotNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_new_cloud_dir/sub_shell")
        )
        self.assertIsNotNone(
            self.transport.get_entry("repo/main/docs/2026_11_05_new_cloud_dir")
        )
        self.transport.trash_file("repo/main/docs/2026_11_05_new_cloud_dir")

        # 3c. Auto-discovered branch forces live remote scan during .history/ GC
        hist_src = self.tmp_root / "frozen_hist_target.md"
        hist_src.write_text("Frozen History Content\n", encoding="utf-8")
        hist_ent = self.transport.upload_file(
            hist_src, "repo/.history/frozen_hist_target.md"
        )
        self.transport.mkdir("repo/ext_web_branch/docs")
        self.transport.create_shortcut(
            hist_ent.file_id, "repo/ext_web_branch/docs/ref_from_auto.md"
        )
        meta_ec03 = self.coord._read_remote_repo_meta()
        assert meta_ec03 is not None
        meta_ec03.setdefault("history_files", {})[hist_ent.file_id] = (
            "repo/.history/frozen_hist_target.md"
        )
        meta_ec03.setdefault("branches", {})["ext_web_branch"] = {
            "auto_discovered": True
        }
        # Even if branch_files has a stale non-empty dict without hist_ent.file_id, auto_discovered=True must force a live scan!
        meta_ec03.setdefault("branch_files", {})["ext_web_branch"] = {
            "docs/stale_dummy.md": "fid_stale_dummy"
        }
        trashed_by_gc = self.coord._gc_unreferenced_history_files(
            meta_ec03, scan_physical=False
        )
        self.assertNotIn(hist_ent.file_id, trashed_by_gc)
        self.assertIsNotNone(
            self.transport.get_entry("repo/.history/frozen_hist_target.md")
        )
        self.assertEqual(
            meta_ec03["branch_files"]["ext_web_branch"].get("docs/ref_from_auto.md"),
            hist_ent.file_id,
        )

        # 4. Branch-root README.md and dot/underscore directories (.github, _internal) in Level 1 & Level 2
        root_mapped_cfg = GDriveConfig(
            root_folder_id="dummy_root",
            sandbox_dir=str(self.sandbox_dir),
            repo_sync_enabled=True,
            active_branch="main",
            sync_spaces=(
                SyncSpaceSpec(
                    space="root_proj",
                    mappings=(
                        PathMappingRule(
                            local_uri="project://",
                            local_rel_prefix="",
                            remote_rel_prefix="",
                        ),
                    ),
                ),
            ),
        )
        root_coord = SyncCoordinator(
            config=root_mapped_cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.tmp_root / "root_state.json",
            lock_path=self.tmp_root / "root_sync.lock",
            log_path=self.tmp_root / "root_sync.log",
            readme_state_path=self.tmp_root / "root_readme_state.json",
            file_space_manager=_SimpleFileSpaceManager(self.proj_dir),
        )
        proj_readme = self.proj_dir / "README.md"
        proj_readme.write_text("# Project Root README\n", encoding="utf-8")
        dot_wf = self.proj_dir / ".github" / "workflows" / "ci.yml"
        dot_wf.parent.mkdir(parents=True, exist_ok=True)
        dot_wf.write_text("name: CI\n", encoding="utf-8")

        rep_root_init = root_coord.run_sync(mode="push")
        self.assertIn("README.md", rep_root_init.pushed)
        self.assertIn(".github/workflows/ci.yml", rep_root_init.pushed)

        # Remote addition of branch-root README update and new _internal/guide.md via Level 1 incremental cache
        rem_tmp = self.tmp_root / "rem_internal.md"
        rem_tmp.write_text("Internal Guide\n", encoding="utf-8")
        self.transport.upload_file(rem_tmp, "repo/main/_internal/guide.md")
        rem_readme_v2 = self.tmp_root / "rem_readme_v2.md"
        rem_readme_v2.write_text("# Project Root README v2\n", encoding="utf-8")
        self.transport.upload_file(rem_readme_v2, "repo/main/README.md")

        rep_l1 = root_coord.run_sync(mode="pull")
        self.assertEqual(rep_l1.cache_hit_level, 1)
        self.assertIn("README.md", rep_l1.pulled)
        self.assertIn("_internal/guide.md", rep_l1.pulled)
        self.assertEqual(
            proj_readme.read_text(encoding="utf-8"), "# Project Root README v2\n"
        )
        self.assertTrue((self.proj_dir / "_internal" / "guide.md").is_file())

        # 5. Sandbox checkout does not write to core_config and CLI _build_coordinator isolates state paths
        from core import config as core_config

        self.coord.create_branch("sbx_branch", from_branch="main")
        orig_cfg_set = core_config.set
        cfg_set_calls: list[tuple] = []

        def _spy_cfg_set(*args, **kwargs):
            cfg_set_calls.append((args, kwargs))
            return orig_cfg_set(*args, **kwargs)

        core_config.set = _spy_cfg_set  # type: ignore[assignment]
        try:
            self.coord.checkout_branch("sbx_branch", force=True)
            self.assertEqual(cfg_set_calls, [])
        finally:
            core_config.set = orig_cfg_set  # type: ignore[assignment]

        isolated_sbx = self.tmp_root / "cli_isolated_sbx"
        isolated_sbx.mkdir(parents=True, exist_ok=True)
        built_coord = cli._build_coordinator(str(isolated_sbx))
        self.assertEqual(
            built_coord.state_path, isolated_sbx.resolve() / ".yscb_sync_state.json"
        )
        self.assertEqual(
            built_coord.lock_path, isolated_sbx.resolve() / ".yscb_sync.lock"
        )
        self.assertEqual(
            built_coord.log_path, isolated_sbx.resolve() / ".yscb_sync.log"
        )
        self.assertEqual(
            built_coord.readme_state_path,
            isolated_sbx.resolve() / ".yscb_readme_state.json",
        )

        # 6. Level 1 fallback does NOT mutate state["remote_repo_cache"] in-place,
        #    and mid-Stage-3 transfer failure does NOT advance cache["page_token"]
        from gdrive_support.transport import ChangeRecord, RemoteEntry

        self.coord.checkout_branch("main", force=True)
        self.coord.run_sync(mode="sync")
        state_before_fallback = self.coord._load_local_state()
        cache_before = copy.deepcopy(state_before_fallback["remote_repo_cache"])
        first_branch_name = next(iter(cache_before["branches"]))
        first_branch_dir_ids = cache_before["branches"][first_branch_name]["dir_ids"]
        known_dir_fid = next(iter(first_branch_dir_ids))

        orig_list_changes = self.transport.list_changes
        self.transport.list_changes = lambda _tok: (  # type: ignore[method-assign]
            [
                ChangeRecord(
                    file_id="fid_mutated_before_abort",
                    removed=True,
                    entry=None,
                ),
                ChangeRecord(
                    file_id=known_dir_fid,
                    removed=False,
                    entry=RemoteEntry(
                        rel_path="",
                        name="renamed_triggering_fallback",
                        file_id=known_dir_fid,
                        mime_type="application/vnd.google-apps.folder",
                        is_dir=True,
                        parent_id="unknown_parent_fid",
                    ),
                    parent_id="unknown_parent_fid",
                    name="renamed_triggering_fallback",
                    mime_type="application/vnd.google-apps.folder",
                ),
            ],
            "sbx_999999_uncommitted",
        )
        try:
            inc_res = self.coord._try_incremental_remote_cache(
                state_before_fallback,
                self.coord.config.active_branch,
            )
            self.assertIsNone(inc_res)
            self.assertEqual(
                state_before_fallback["remote_repo_cache"],
                cache_before,
            )
        finally:
            self.transport.list_changes = orig_list_changes  # type: ignore[method-assign]

        # Verify page_token is NOT committed when Stage 3 push fails mid-batch
        tok_before_err = self.coord._load_local_state()["remote_repo_cache"]["page_token"]
        rem_new_f = self.tmp_root / "rem_before_push_err.md"
        rem_new_f.write_text("Remote Change Before Push Error\n", encoding="utf-8")
        self.transport.upload_file(rem_new_f, "repo/main/docs/rem_before_push_err.md")
        loc_fail_f = self.docs_dir / "loc_fail_push.md"
        loc_fail_f.write_text("Will Fail On Upload\n", encoding="utf-8")

        orig_upload_err = self.transport.upload_file

        def _failing_upload(local_path: Path, remote_path: str, in_place_file_id=None):
            if remote_path.endswith("loc_fail_push.md"):
                raise GDriveTransportError("Simulated mid-Stage-3 upload failure")
            return orig_upload_err(local_path, remote_path, in_place_file_id=in_place_file_id)

        self.transport.upload_file = _failing_upload  # type: ignore[method-assign]
        try:
            with self.assertRaises(GDriveTransportError):
                self.coord.run_sync(mode="sync")
        finally:
            self.transport.upload_file = orig_upload_err  # type: ignore[method-assign]
            loc_fail_f.unlink(missing_ok=True)

        tok_after_err = self.coord._load_local_state()["remote_repo_cache"]["page_token"]
        self.assertEqual(tok_after_err, tok_before_err)

        # 7. reconcile_root_readme_state updates README when repo_sync_root changes while enabled
        custom_root_cfg = GDriveConfig(
            root_folder_id="sandbox_root",
            active_branch="main",
            repo_sync_enabled=True,
            repo_sync_root="custom_vault",
            sandbox_dir=self.sandbox_dir.as_posix(),
            sync_spaces=self.cfg.sync_spaces,
        )
        custom_root_coord = SyncCoordinator(
            config=custom_root_cfg,
            transport=self.transport,
            project_root=self.proj_dir,
            state_path=self.coord.state_path,
            lock_path=self.coord.lock_path,
            log_path=self.coord.log_path,
            readme_state_path=self.coord.readme_state_path,
            file_space_manager=self.fs_mgr,
        )
        res_changed = custom_root_coord.reconcile_root_readme()
        self.assertTrue(res_changed["changed"])
        dl_root_readme = self.tmp_root / "dl_root_readme_custom.md"
        self.transport.download_file("README.md", dl_root_readme)
        self.assertIn("`custom_vault/`", dl_root_readme.read_text(encoding="utf-8"))
        res_noop = custom_root_coord.reconcile_root_readme()
        self.assertFalse(res_noop["changed"])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_15_untracked_delete_guard_restored_folder_scan_and_wal_journal_replay(
        self,
    ) -> None:
        """
        Verify sub_09 remediations:
        1. [FR-01 / TODO-24] Unidirectional push --delete and pull --delete preserve untracked new files
           (base is None) unless --force is explicitly passed; tracked deletions (base is not None) still delete.
        2. [FR-02 / TODO-25] Restoring a trashed folder (or moving a pre-populated folder into a branch)
           when changes.list only reports the folder change record falls back to Level 2 scan and pulls child files.
        3. [FR-03] Stage 3 writes per-file WAL entries to sync_state.journal.jsonl (only 1 atomic sync_state.json
           write in finally), and _load_local_state() automatically replays uncommitted journal records (ignoring
           any truncated trailing line from simulated power loss) and compacts them into sync_state.json.
        """
        from gdrive_support.transport import ChangeRecord, FOLDER_MIME_TYPE, RemoteEntry

        self.coord.init_repo()

        # --- 1. [FR-01] push --delete & pull --delete guard untracked (base is None) files ---
        rem_untracked = self.tmp_root / "cloud_created_untracked.md"
        rem_untracked.write_text("Created directly on Cloud before pull\n", encoding="utf-8")
        self.transport.upload_file(rem_untracked, "repo/main/docs/cloud_new.md")

        loc_untracked = self.docs_dir / "local_new.md"
        loc_untracked.write_text("Created locally before push\n", encoding="utf-8")

        # (a) push --delete (without --force) pushes local_new.md and MUST NOT delete cloud_new.md!
        rep_push_del = self.coord.run_sync(mode="push", delete=True, force=False)
        self.assertIn("docs/local_new.md", rep_push_del.pushed)
        self.assertEqual(rep_push_del.deleted_remote, [])
        self.assertIsNotNone(self.transport.get_entry("repo/main/docs/cloud_new.md"))

        # (b) Create another local untracked file; pull --delete (without --force) pulls cloud_new.md
        #     and MUST NOT delete local_untracked_2.md!
        loc_untracked_2 = self.docs_dir / "local_untracked_2.md"
        loc_untracked_2.write_text("Second local untracked file\n", encoding="utf-8")
        rep_pull_del = self.coord.run_sync(mode="pull", delete=True, force=False)
        self.assertIn("docs/cloud_new.md", rep_pull_del.pulled)
        self.assertEqual(rep_pull_del.deleted_local, [])
        self.assertTrue(loc_untracked_2.is_file())

        # (c) With --force AND --delete, untracked files on the target side ARE deleted
        rep_pull_force_del = self.coord.run_sync(mode="pull", delete=True, force=True)
        self.assertIn("docs/local_untracked_2.md", rep_pull_force_del.deleted_local)
        self.assertFalse(loc_untracked_2.exists())

        # --- 2. [FR-02] Folder untrash / move-in with only folder ChangeRecord falls back to Level 2 ---
        self.coord.run_sync(mode="sync")
        # Upload a folder with a child file on remote
        restored_child = self.tmp_root / "restored_child.md"
        restored_child.write_text("Restored from Trash Content\n", encoding="utf-8")
        self.transport.upload_file(
            restored_child, "repo/main/docs/restored_plan/P00_discuss.md"
        )
        restored_dir_ent = self.transport.get_entry("repo/main/docs/restored_plan")
        assert restored_dir_ent is not None

        # Simulate Google Drive changes.list emitting ONLY the folder change record (as happens on untrash)
        orig_list_changes = self.transport.list_changes
        self.transport.list_changes = lambda _tok: (  # type: ignore[method-assign]
            [
                ChangeRecord(
                    file_id=restored_dir_ent.file_id,
                    removed=False,
                    entry=restored_dir_ent,
                    parent_id=restored_dir_ent.parent_id,
                    name=restored_dir_ent.name,
                    mime_type=FOLDER_MIME_TYPE,
                )
            ],
            "sbx_untrashed_folder_only",
        )
        try:
            rep_untrash = self.coord.run_sync(mode="pull")
            self.assertEqual(rep_untrash.cache_hit_level, 2)
            self.assertIn("docs/restored_plan/P00_discuss.md", rep_untrash.pulled)
            self.assertEqual(
                (self.docs_dir / "restored_plan" / "P00_discuss.md").read_text(
                    encoding="utf-8"
                ),
                "Restored from Trash Content\n",
            )
        finally:
            self.transport.list_changes = orig_list_changes  # type: ignore[method-assign]

        # --- 3. [FR-03 & EC-01] WAL Journal single final snapshot write & crash recovery replay ---
        for i in range(5):
            (self.docs_dir / f"batch_{i}.md").write_text(f"Batch {i}\n", encoding="utf-8")

        save_calls = {"n": 0}
        orig_save = self.coord._save_local_state

        def _counting_save(st):
            save_calls["n"] += 1
            return orig_save(st)

        self.coord._save_local_state = _counting_save  # type: ignore[method-assign]
        try:
            rep_batch = self.coord.run_sync(mode="push")
            self.assertEqual(len(rep_batch.pushed), 5)
            # Stage 1 snapshot + Stage 3 finally = at most 2 full JSON writes (NOT 5+ per-file writes!)
            self.assertLessEqual(save_calls["n"], 2)
            self.assertFalse(self.coord.state_journal_path.exists())
        finally:
            self.coord._save_local_state = orig_save  # type: ignore[method-assign]

        # Simulate crash leaving sync_state.journal.jsonl with 1 valid upsert, 1 valid delete, and 1 truncated line
        fake_entry = FileEntry(
            rel_path="docs/journal_recovered.md",
            md5="m_rec",
            sha256="s_rec",
            size=12,
            mtime_ns=12345,
            file_id="fid_rec_99",
        ).to_dict()
        journal_lines = [
            json.dumps(
                {
                    "op": "upsert_file",
                    "branch": "main",
                    "rel_path": "docs/journal_recovered.md",
                    "base_entry": fake_entry,
                    "cache_entry": None,
                }
            ),
            json.dumps(
                {
                    "op": "delete_file",
                    "branch": "main",
                    "rel_path": "docs/batch_0.md",
                    "remove_from_cache": True,
                }
            ),
            '{"op": "upsert_file", "branch": "main", "truncated_json_on_power_loss',
        ]
        self.coord.state_journal_path.write_text(
            "\n".join(journal_lines) + "\n", encoding="utf-8"
        )
        reloaded = self.coord._load_local_state()
        main_tracked = reloaded["branches"]["main"]["files"]
        self.assertIn("docs/journal_recovered.md", main_tracked)
        self.assertNotIn("docs/batch_0.md", main_tracked)
        self.assertFalse(self.coord.state_journal_path.exists())
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

