"""
Unit, integration, and edge-case tests for module:gdrive-support branch management and sync engine.

100% locked to LocalSandboxTransport, stateless reconciler.py, SyncCoordinator, and GDriveSyncServiceWorker.
No external Google Drive API calls or user credentials are required or tested here.
"""
from contextlib import redirect_stdout
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
        Verify LocalSandboxTransport.get_start_page_token() and list_changes() (FT-01):
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
        Verify SyncCoordinator 3-level remote_repo_cache with changes API (FT-02):
        - Level 0: Second run_sync makes 0 list_files calls and reports cache_hit_level == 0.
        - Level 1: Single remote file update, new file in known dir, and Shortcut target_file_id update
          patch cache in-memory with 0 list_files calls (cache_hit_level == 1).
        - Level 2: Adding a new remote directory automatically falls back to full scan (cache_hit_level == 2).
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

            # 4. Level 2 Fallback: Create a new remote subdirectory under repo/v1.0/docs/new_sub/
            rem_sub = self.tmp_root / "rem_sub_doc.md"
            rem_sub.write_text("Deep Subdir Doc\n", encoding="utf-8")
            self.transport.upload_file(
                rem_sub, "repo/v1.0/docs/new_sub/deep_doc.md"
            )

            rep_l2 = self.coord.run_sync(mode="pull")
            self.assertEqual(rep_l2.cache_hit_level, 2)
            self.assertIn("docs/new_sub/deep_doc.md", rep_l2.pulled)
            self.assertEqual(
                (self.docs_dir / "new_sub" / "deep_doc.md").read_text(
                    encoding="utf-8"
                ),
                "Deep Subdir Doc\n",
            )
        finally:
            self.transport.list_files = orig_list_files  # type: ignore[method-assign]
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_12_cli_yield_signal_preemption_orphan_self_healing_and_atomic_cow_mid_sync(
        self,
    ) -> None:
        """
        Verify foreground CLI lock preemption and atomic per-file CoW safety (FT-03):
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


if __name__ == "__main__":
    unittest.main()

