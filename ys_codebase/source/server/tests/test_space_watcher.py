"""
Unit & Integration Tests for `CoreSpaceWatcherServiceWorker` in `module:server`.
Covers contributes registration, 500ms debounce coalescing, `.yscb.lock` transaction deference,
directory create/move/delete full-rescan escalation, composite & short-name union propagation,
runtime ephemeral space (`define_ephemeral_space`) dynamic watcher scheduling, and
`on_file_space_changed` (`emit_module="core"`) event broadcasting.
"""

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from core import vfs
from core.platform.lock import InterProcessLock
from core.space import (
    clear_subscribers,
    consume_diff,
    define_ephemeral_space,
    diff,
    get_default_registry,
    get_default_scanner,
    is_watcher_active,
    register_active_watcher,
    reset_default_instances,
    scan,
    subscribe,
)
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from server.service import ServiceManager, _load_service_class_from_uri
from server.space_watcher import CoreSpaceWatcherServiceWorker


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreSpaceWatcherService(YSCBTestCase):
    """Verify `CoreSpaceWatcherServiceWorker` lifecycle, debouncing, lock deference, and event broadcasting."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_srv_space_watcher_"))
        self.proj_root = self.temp_dir / "workspace"
        self.yscb_root = self.proj_root / "ys_codebase"
        self.proj_root.mkdir(parents=True, exist_ok=True)
        self.yscb_root.mkdir(parents=True, exist_ok=True)

        vfs.write_json(
            str(self.proj_root / "yscb.config.json"),
            {"yscb_dir": "./ys_codebase"},
        )
        cfg_core_dir = self.yscb_root / "config" / "core"
        cfg_core_dir.mkdir(parents=True, exist_ok=True)
        vfs.write_json(
            str(cfg_core_dir / "config.project.json"),
            {"project_root": "./"},
        )

    def tearDown(self) -> None:
        clear_subscribers()
        register_active_watcher(None)
        reset_default_instances()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def _write_module_contrib(self, mod_name: str, file_name: str, payload: dict) -> Path:
        c_dir = self.yscb_root / ".modules" / mod_name / "contributes"
        c_dir.mkdir(parents=True, exist_ok=True)
        c_file = c_dir / file_name
        vfs.write_json(str(c_file), payload)
        return c_file

    def _write_project_core_contrib(self, payload: dict) -> Path:
        c_dir = self.yscb_root / "config" / "core"
        c_dir.mkdir(parents=True, exist_ok=True)
        c_file = c_dir / "contribute.json"
        vfs.write_json(str(c_file), payload)
        return c_file

    def test_service_contributes_loading_and_lifecycle_beacons(self) -> None:
        """Verify `contributes/server.json` loads `CoreSpaceWatcherServiceWorker` and manages `watcher_state.json`."""
        srv_contrib_path = (
            Path(__file__).resolve().parents[1] / "contributes" / "server.json"
        )
        self.assertTrue(srv_contrib_path.is_file())
        srv_data = json.loads(srv_contrib_path.read_text(encoding="utf-8"))
        services = srv_data.get("services", [])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["name"], "core-space-watcher")
        self.assertEqual(
            services[0]["worker_class"],
            "server.space_watcher:CoreSpaceWatcherServiceWorker",
        )
        self.assertTrue(services[0]["auto_start"])

        cls_obj = _load_service_class_from_uri(
            services[0]["worker_class"], provider="server"
        )
        self.assertIs(cls_obj, CoreSpaceWatcherServiceWorker)

        src_dir = self.proj_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "app.py").write_text("x = 1\n", encoding="utf-8")

        self._write_module_contrib(
            "core",
            "core.json",
            {
                "spaces": {
                    "source": {
                        "entries": ["project://src"],
                        "include": ["*.py"],
                    }
                }
            },
        )

        worker = CoreSpaceWatcherServiceWorker(
            context={
                "project_root": str(self.proj_root),
                "yscb_root": str(self.yscb_root),
                "debounce_seconds": 0.05,
            }
        )
        mgr = ServiceManager()
        mgr.register(
            worker,
            name="core-space-watcher",
            provider="server",
            description="Test watcher",
            auto_start=True,
        )

        try:
            mgr.start_all(
                {
                    "project_root": str(self.proj_root),
                    "yscb_root": str(self.yscb_root),
                    "debounce_seconds": 0.05,
                }
            )
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if worker.health_check() and (
                    self.yscb_root / ".cache" / "core" / "space" / "watcher_state.json"
                ).is_file():
                    break
                time.sleep(0.02)

            self.assertTrue(worker.health_check())
            self.assertTrue(
                is_watcher_active(
                    "core/source",
                    project_root=self.proj_root,
                    yscb_dir=self.yscb_root,
                )
            )
            metrics = worker.get_custom_metrics()
            self.assertIn("core/source", metrics["watched_spaces"])
        finally:
            mgr.stop_all()

        self.assertFalse(worker.is_alive())
        self.assertFalse(
            (
                self.yscb_root / ".cache" / "core" / "space" / "watcher_state.json"
            ).exists()
        )
        self.mark_passed()

    def test_debounce_coalescing_lock_deference_and_event_broadcast(self) -> None:
        """
        Verify:
        - Fast ignore of `.git`, `__pycache__`, `.cache`, `.yscb.lock`, `*.tmp`.
        - 500ms debounce window coalescing and `.yscb.lock` transaction deference.
        - `patch_files` incremental update, composite & short-name union snapshot sync,
          in-process `subscribe`, and `on_file_space_changed` (`emit_module="core"`).
        - Directory `created`/`deleted` escalation to full space rescan.
        """
        mod_a = self.proj_root / "mod_a"
        mod_b = self.proj_root / "mod_b"
        mod_a.mkdir(parents=True, exist_ok=True)
        mod_b.mkdir(parents=True, exist_ok=True)
        fa = mod_a / "a.py"
        fb = mod_b / "b.py"
        fa.write_text("a = 1\n", encoding="utf-8")
        fb.write_text("b = 1\n", encoding="utf-8")

        self._write_module_contrib(
            "mod_a",
            "core.json",
            {
                "spaces": {
                    "source": {
                        "entries": ["project://mod_a"],
                        "include": ["*.py"],
                    }
                }
            },
        )
        self._write_project_core_contrib(
            {
                "spaces": {
                    "source": {
                        "entries": ["project://mod_b"],
                        "include": ["*.py"],
                    },
                    "composite_all": {
                        "compose": ["mod_a/source", "project/source"],
                    },
                }
            }
        )

        worker = CoreSpaceWatcherServiceWorker(
            context={
                "project_root": str(self.proj_root),
                "yscb_root": str(self.yscb_root),
                "debounce_seconds": 0.2,
            }
        )

        # Warm up initial snapshots (gen 1) for qualified, short-name union, and composite spaces
        scan("mod_a/source", project_root=self.proj_root, yscb_dir=self.yscb_root)
        scan("project/source", project_root=self.proj_root, yscb_dir=self.yscb_root)
        scan("source", project_root=self.proj_root, yscb_dir=self.yscb_root)
        scan("project/composite_all", project_root=self.proj_root, yscb_dir=self.yscb_root)
        scan(None, project_root=self.proj_root, yscb_dir=self.yscb_root)

        # Idle flush_dirty_spaces must NOT probe is_transaction_locked() when _dirty_spaces is empty
        with patch.object(worker, "is_transaction_locked") as mock_lock_probe:
            self.assertEqual(worker.flush_dirty_spaces(force=False), {})
            mock_lock_probe.assert_not_called()

        # 1. Fast-ignored paths return [] and do not mark watcher dirty
        self.assertEqual(
            worker.notify_file_event(self.proj_root / ".git" / "index"), []
        )
        self.assertEqual(
            worker.notify_file_event(mod_a / "__pycache__" / "a.pyc"), []
        )
        self.assertEqual(
            worker.notify_file_event(mod_a / "temp.py.tmp"), []
        )
        self.assertEqual(
            worker.notify_file_event(self.proj_root / ".yscb.lock"), []
        )
        self.assertFalse(worker.scanner.has_watcher_dirty_marker())

        # 2. Modify `fa` -> matches `mod_a/source` and `project/composite_all`
        fa.write_text("a = 2\n", encoding="utf-8")
        matched = worker.notify_file_event(fa, is_directory=False, event_type="modified")
        self.assertIn("mod_a/source", matched)
        self.assertIn("project/composite_all", matched)
        self.assertTrue(worker.scanner.has_watcher_dirty_marker())

        # Before debounce window elapses, `flush_dirty_spaces(force=False)` is a no-op and does not probe lock
        with patch.object(worker, "is_transaction_locked") as mock_lock_debounce:
            self.assertEqual(worker.flush_dirty_spaces(force=False), {})
            mock_lock_debounce.assert_not_called()

        # 3. Active `.yscb.lock` defers flushing and increments `deferred_by_lock_count`
        lock_file = self.yscb_root / ".cache" / ".yscb.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        ip_lock = InterProcessLock(str(lock_file))
        self.assertTrue(ip_lock.acquire(blocking=False))
        try:
            proj_lock = self.proj_root / ".yscb.lock"
            proj_lock.write_text("locked", encoding="utf-8")
            self.assertTrue(worker.is_transaction_locked())
            self.assertEqual(worker.flush_dirty_spaces(force=True), {})
            self.assertEqual(
                worker.get_custom_metrics()["deferred_by_lock_count"], 1
            )
        finally:
            if (self.proj_root / ".yscb.lock").exists():
                (self.proj_root / ".yscb.lock").unlink()
            ip_lock.release()

        # 4. Subscribe and flush with `force=True` -> verifies dependent snapshots (`source` & `__all__`)
        # are already updated BEFORE subscribers and `on_file_space_changed` broadcast fire!
        sub_notifications: list = []
        observed_union_gen_at_broadcast: list = []
        observed_all_gen_at_broadcast: list = []

        def _on_sub(sp, df):
            sub_notifications.append((sp, df.to_generation, df.modified))
            d_u = diff(
                "source",
                consumer_id="probe_sub",
                auto_refresh=False,
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
            )
            d_all = diff(
                None,
                consumer_id="probe_all",
                auto_refresh=False,
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
            )
            observed_union_gen_at_broadcast.append(d_u.to_generation)
            observed_all_gen_at_broadcast.append(d_all.to_generation)

        unsub = subscribe(
            _on_sub,
            spaces=["source", "project/composite_all"],
        )
        try:
            with patch("core.events.broadcast") as mock_bcast:
                flushed = worker.flush_dirty_spaces(force=True)
                self.assertIn("mod_a/source", flushed)
                self.assertIn("project/composite_all", flushed)
                self.assertEqual(flushed["mod_a/source"].to_generation, 2)
                self.assertEqual(flushed["mod_a/source"].modified, ["mod_a/a.py"])
                self.assertEqual(flushed["project/composite_all"].to_generation, 2)
                self.assertEqual(flushed["project/composite_all"].modified, ["mod_a/a.py"])
                self.assertFalse(worker.scanner.has_watcher_dirty_marker())

                # Subscribers on `"source"` and `"project/composite_all"` both received notifications
                self.assertEqual(
                    sub_notifications,
                    [
                        ("mod_a/source", 2, ["mod_a/a.py"]),
                        ("project/composite_all", 2, ["mod_a/a.py"]),
                    ],
                )
                # At the exact moment subscriber/broadcast fired, `"source"` and `__all__` were ALREADY gen 2
                self.assertEqual(observed_union_gen_at_broadcast, [2, 2])
                self.assertEqual(observed_all_gen_at_broadcast, [2, 2])

                # Broadcast was emitted with `emit_module="core"`
                self.assertTrue(mock_bcast.called)
                b_args, b_kwargs = mock_bcast.call_args_list[0]
                self.assertEqual(b_args[0], "on_file_space_changed")
                self.assertEqual(b_kwargs.get("emit_module"), "core")

            # Short-name union snapshot `"source"` was automatically synced to generation 2
            d_union = diff(
                "source",
                consumer_id="c_union",
                auto_refresh=False,
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
            )
            self.assertEqual(d_union.to_generation, 2)
        finally:
            unsub()

        # 5. Directory creation/deletion escalates to `_full_rescan_spaces`
        sub_dir = mod_a / "sub_pkg"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "new_mod.py").write_text("n = 1\n", encoding="utf-8")
        dir_matched = worker.notify_file_event(
            sub_dir, is_directory=True, event_type="created"
        )
        self.assertIn("mod_a/source", dir_matched)
        flushed_dir = worker.flush_dirty_spaces(force=True)
        self.assertEqual(flushed_dir["mod_a/source"].to_generation, 3)
        self.assertEqual(
            flushed_dir["mod_a/source"].added, ["mod_a/sub_pkg/new_mod.py"]
        )
        self.mark_passed()

    def test_ephemeral_space_dynamic_registration_and_in_process_flush(self) -> None:
        """
        Verify `[P00:DR-02]`:
        - Defining a runtime ephemeral space (`define_ephemeral_space("yscb-skills", ...)`) while
          `CoreSpaceWatcherServiceWorker` is active automatically schedules its directories
          (`watch=True` by default) and flushes dirty events on `consume_diff("yscb-skills")`.
        """
        skills_dir = self.proj_root / ".agents" / "skills" / "demo"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("# Demo Skill v1\n", encoding="utf-8")

        worker = CoreSpaceWatcherServiceWorker(
            context={
                "project_root": str(self.proj_root),
                "yscb_root": str(self.yscb_root),
                "debounce_seconds": 10.0,  # Long debounce to prove synchronous flush_space_now on read
            }
        )
        register_active_watcher(worker)
        try:
            # Dynamically define ephemeral space (`watch=True` by default)
            ephem_cfg = define_ephemeral_space(
                "yscb-skills",
                {"entries": ["project://.agents/skills"], "include": ["*.md"]},
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
            )
            self.assertTrue(ephem_cfg.watch)
            self.assertIn(
                ephem_cfg.qualified_name,
                worker.get_custom_metrics()["watched_spaces"],
            )

            # Initial consume_diff (gen 1)
            with consume_diff(
                "yscb-skills",
                consumer_id="agent_wf",
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
            ) as d1:
                self.assertEqual(d1.to_generation, 1)
                self.assertEqual(d1.added, [".agents/skills/demo/SKILL.md"])

            # Modify file and notify watcher (debounce is 10s so background loop hasn't flushed yet)
            skill_file.write_text("# Demo Skill v2\n", encoding="utf-8")
            matched = worker.notify_file_event(
                skill_file, is_directory=False, event_type="modified"
            )
            self.assertIn(ephem_cfg.qualified_name, matched)

            # Calling `consume_diff("yscb-skills", auto_refresh=False)` when worker is alive
            # synchronously flushes the in-process watcher via `flush_space_now("yscb-skills")`!
            with patch.object(worker, "is_alive", return_value=True):
                with consume_diff(
                    "yscb-skills",
                    consumer_id="agent_wf",
                    auto_refresh=False,
                    project_root=self.proj_root,
                    yscb_dir=self.yscb_root,
                ) as d2:
                    self.assertEqual(d2.from_generation, 1)
                    self.assertEqual(d2.to_generation, 2)
                    self.assertEqual(d2.modified, [".agents/skills/demo/SKILL.md"])
            self.assertEqual(worker.state, worker.STATE_READY)

            # Verify Watchdog handler binds worker RuntimeScope & LogExecutionScope on callback
            from core.context import get_current_scope
            from server.space_watcher import _CoreSpaceWatchdogHandler

            captured_scope = {}
            orig_notify = worker.notify_file_event

            def _spy_notify(path_arg, is_directory=False, event_type="modified"):
                sc = get_current_scope()
                captured_scope["host_dir"] = sc.active_host_dir if sc else None
                captured_scope["yscb_dir"] = sc.active_yscb_dir if sc else None
                return orig_notify(path_arg, is_directory=is_directory, event_type=event_type)

            class _DummyEvt:
                is_directory = False
                event_type = "modified"
                src_path = str(skill_file)
                dest_path = None

            handler = _CoreSpaceWatchdogHandler(worker)
            with patch.object(worker, "notify_file_event", side_effect=_spy_notify):
                handler.on_any_event(_DummyEvt())

            self.assertEqual(captured_scope.get("host_dir"), str(self.proj_root.resolve()))
            self.assertEqual(captured_scope.get("yscb_dir"), str(self.yscb_root.resolve()))

            worker.stop()
            self.assertIsNone(worker._thread)
            self.assertEqual(worker.state, worker.STATE_STOPPED)
        finally:
            register_active_watcher(None)
        self.mark_passed()

    def test_stale_unlocked_lockfile_macos_private_prefix_and_unschedule(self) -> None:
        """Verify stale unlocked .yscb.lock does not freeze watcher, macOS /private/var symlink dir/file matching works, and removed watch dirs are unscheduled."""
        from server.space_watcher import _match_prefix_rel

        src_dir = self.proj_root / "src_mod"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "init.py").write_text("x = 1\n", encoding="utf-8")
        self._write_module_contrib(
            "core",
            "core.json",
            {
                "spaces": {
                    "source": {
                        "entries": ["project://src_mod"],
                        "include": ["*.py"],
                    }
                }
            },
        )

        worker = CoreSpaceWatcherServiceWorker(
            context={
                "project_root": str(self.proj_root),
                "yscb_root": str(self.yscb_root),
                "debounce_seconds": 0.05,
            }
        )
        # Stale empty/unlocked .yscb.lock in project_root must not report transaction locked
        stale_lock = self.proj_root / ".yscb.lock"
        stale_lock.write_text("", encoding="utf-8")
        try:
            self.assertFalse(worker.is_transaction_locked())
        finally:
            if stale_lock.exists():
                stale_lock.unlink()

        # Symmetric macOS /private/var alias normalization
        rel = _match_prefix_rel("/private/var/folders/xx/proj/mod_a/file.py", "/var/folders/xx/proj")
        self.assertEqual(rel, "mod_a/file.py")

        # Verify symlinked project_root alias (simulating macOS /var -> /private/var) matches both directory and file events
        alias_root = self.temp_dir / "alias_workspace"
        has_symlink = False
        try:
            os.symlink(str(self.proj_root), str(alias_root))
            has_symlink = True
        except OSError:
            has_symlink = False

        if has_symlink:
            sub_dir_via_real = self.proj_root / "src_mod" / "nested"
            sub_dir_via_real.mkdir(parents=True, exist_ok=True)
            # Configure registry with alias_root while watchdog emits physical self.proj_root paths
            alias_worker = CoreSpaceWatcherServiceWorker(
                context={
                    "project_root": str(alias_root),
                    "yscb_root": str(alias_root / "ys_codebase"),
                    "debounce_seconds": 0.05,
                }
            )
            matched_dir = alias_worker.notify_file_event(
                sub_dir_via_real, is_directory=True, event_type="created"
            )
            self.assertIn("core/source", matched_dir)
            matched_file = alias_worker.notify_file_event(
                self.proj_root / "src_mod" / "init.py",
                is_directory=False,
                event_type="modified",
            )
            self.assertIn("core/source", matched_file)

        # Verify unschedule when a watched directory is removed from desired set
        unscheduled = []

        class _FakeObserver:
            def schedule(self, handler, path, recursive=True):
                return f"watch:{path}"

            def unschedule(self, watch_obj):
                unscheduled.append(watch_obj)

        worker._observer = _FakeObserver()
        worker._watchdog_handler = object()
        extra_dir = os.path.normcase(str((self.proj_root / "ephem_dir").resolve()))
        worker._scheduled_watches[extra_dir] = "watch:ephem_dir"
        worker._scheduled_dirs.add(extra_dir)
        worker.sync_watched_directories()
        self.assertIn("watch:ephem_dir", unscheduled)
        self.assertNotIn(extra_dir, worker._scheduled_watches)

        # Verify is_alive() checks _stop_event before _thread.is_alive()
        worker._stop_event.set()
        self.assertFalse(worker.is_alive())
        self.mark_passed()

    def test_flush_dirty_spaces_defers_when_foreground_active(self) -> None:
        """Verify `CoreSpaceWatcherServiceWorker.flush_dirty_spaces(force=False)` yields when `is_foreground_active()` is True and increments `deferred_by_foreground_count`."""
        from core.context import foreground_task_scope

        src_dir = self.proj_root / "fg_yield_src"
        src_dir.mkdir(parents=True, exist_ok=True)
        f_py = src_dir / "item.py"
        f_py.write_text("v = 1\n", encoding="utf-8")

        self._write_module_contrib(
            "mod_fg",
            "core.json",
            {
                "spaces": {
                    "source": {
                        "entries": ["project://fg_yield_src"],
                        "include": ["*.py"],
                    }
                }
            },
        )
        scan("mod_fg/source", project_root=self.proj_root, yscb_dir=self.yscb_root)

        worker = CoreSpaceWatcherServiceWorker(
            context={
                "project_root": str(self.proj_root),
                "yscb_root": str(self.yscb_root),
                "debounce_seconds": 0.0,
            }
        )
        f_py.write_text("v = 2\n", encoding="utf-8")
        matched = worker.notify_file_event(f_py, is_directory=False, event_type="modified")
        self.assertIn("mod_fg/source", matched)

        with foreground_task_scope():
            res_deferred = worker.flush_dirty_spaces(force=False)
            self.assertEqual(res_deferred, {})
            self.assertEqual(worker.get_custom_metrics()["deferred_by_foreground_count"], 1)

        # Once foreground task completes, background flush proceeds cleanly
        res_flushed = worker.flush_dirty_spaces(force=False)
        self.assertIn("mod_fg/source", res_flushed)
        self.assertEqual(res_flushed["mod_fg/source"].modified, ["fg_yield_src/item.py"])
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
