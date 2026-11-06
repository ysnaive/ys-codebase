"""
Unit tests for FileSpaceWatcherServiceWorker (debounce, .yscb.lock deference, subscribe,
watchdog event routing, worker lifecycle), CLI subcommands, providers, hooks, and migrations.
"""
from dataclasses import dataclass, field
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def _load_script_module(mod_name: str, *rel_candidates: str) -> Any:
    for rel_path in rel_candidates:
        full_path = os.path.join(_pkg_root, rel_path)
        if os.path.isfile(full_path):
            spec = importlib.util.spec_from_file_location(mod_name, full_path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(
        f"Unable to locate script module '{mod_name}' in {rel_candidates}"
    )


file_space_cli = _load_script_module(
    "file_space_scripts_cli", os.path.join("scripts", "cli.py")
)
hook_dev = _load_script_module(
    "file_space_scripts_hook_dev", os.path.join("scripts", "hook.dev.py")
)
hook_server = _load_script_module(
    "file_space_scripts_hook_server", os.path.join("scripts", "hook.server.py")
)
migration_101x = _load_script_module(
    "file_space_migrations_101x",
    os.path.join("migrations", "1.0.1.x.py"),
    os.path.join("scripts", "migrations", "1.0.1.x.py"),
)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from file_space.manager import FileSpaceManager
from file_space.providers import (
    _resolve_knowledge_db_indexed_space_names,
    get_knowledge_db_spaces,
    get_registered_file_spaces_table,
)
from file_space.scanner import FingerprintScanner, is_watcher_active
from file_space.schema import ScanDiffResult
from file_space.service import (
    FileSpaceWatcherServiceWorker,
    _FileSpaceWatchdogHandler,
    clear_subscribers,
    subscribe,
)


@dataclass
class _MockArg:
    val: Any


@dataclass
class _MockOptBag:
    args: List[_MockArg] = field(default_factory=list)
    params: Any = None


@dataclass
class _MockCmdBags:
    options: Dict[str, _MockOptBag] = field(default_factory=dict)
    args: List[Any] = field(default_factory=list)


def _make_bags(**kwargs: Any) -> _MockCmdBags:
    opts: Dict[str, _MockOptBag] = {}
    for k, v in kwargs.items():
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            opts[flag] = _MockOptBag(args=[])
        elif v is not False and v is not None:
            opts[flag] = _MockOptBag(args=[_MockArg(val=v)])
    return _MockCmdBags(options=opts)


class TestServiceAndCli(YSCBTestCase):
    """Tests for FileSpaceWatcherServiceWorker, CLI command handlers, providers, hooks, and migrations."""

    def setUp(self) -> None:
        super().setUp()
        clear_subscribers()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_space_svc_cli_"))
        self.proj_root = self.tmp_dir / "project"
        self.storage_root = self.tmp_dir / "storage"
        self.src_dir = self.proj_root / "src"
        self.src_dir.mkdir(parents=True)
        (self.src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")

        self.mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "description": "Test source space",
                    "include": [self.src_dir.as_posix()],
                    "exclude": [".git"],
                    "file_patterns": ["*.py"],
                    "watch": True,
                }
            },
            contributed_spaces={},
        )
        self.scanner = FingerprintScanner(
            space_manager=self.mgr, storage_root=self.storage_root
        )

    def tearDown(self) -> None:
        clear_subscribers()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_service_worker_debounce_lock_and_subscribe(self) -> None:
        """Verify debounce window via time.monotonic, .yscb.lock deference, exception rollback, and external .cache space."""
        self.scanner.refresh("source")

        received_events: List[ScanDiffResult] = []
        unsub = subscribe(
            lambda s_name, diff_res: received_events.append(diff_res),
            spaces=["source"],
        )

        worker = FileSpaceWatcherServiceWorker(
            name="file-space-watcher",
            context={"project_root": self.proj_root, "storage_root": self.storage_root},
            space_manager=self.mgr,
            scanner=self.scanner,
            debounce_seconds=0.5,
        )

        new_file = self.src_dir / "added.py"
        new_file.write_text("a = 1\n", encoding="utf-8")

        with patch("file_space.service.time.monotonic") as mock_mono:
            mock_mono.return_value = 100.0
            matched = worker.notify_file_event(str(new_file))
            self.assertEqual(matched, ["source"])
            self.assertTrue(self.scanner.is_watcher_dirty("source"))

            # Within 0.5s debounce window -> flush_dirty_spaces(force=False) returns {} without refreshing
            mock_mono.return_value = 100.2
            early_res = worker.flush_dirty_spaces(force=False)
            self.assertEqual(early_res, {})
            self.assertEqual(len(received_events), 0)
            self.assertTrue(self.scanner.is_watcher_dirty("source"))

            # Advance past debounce window, but simulate active .yscb.lock -> yields and increments deferred_by_lock_count
            mock_mono.return_value = 100.8
            lock_file = self.proj_root / ".yscb.lock"
            lock_file.write_text("locked", encoding="utf-8")
            deferred_res = worker.flush_dirty_spaces(force=False)
            self.assertEqual(deferred_res, {})
            self.assertEqual(len(received_events), 0)
            metrics = worker.get_custom_metrics()
            self.assertGreaterEqual(metrics["deferred_by_lock_count"], 1)
            lock_file.unlink()

            # Simulate _refresh_or_patch_space raising an exception -> state rolls back and keeps .watcher_dirty
            with patch.object(
                worker,
                "_refresh_or_patch_space",
                side_effect=RuntimeError("Simulated transient scan error"),
            ):
                self.assertIsNone(worker.flush_space_now("source"))
                self.assertIn("source", worker._dirty_spaces)
                self.assertTrue(self.scanner.is_watcher_dirty("source"))

                failed_batch = worker.flush_dirty_spaces(force=False)
                self.assertEqual(failed_batch, {})
                self.assertIn("source", worker._dirty_spaces)
                self.assertTrue(self.scanner.is_watcher_dirty("source"))

            # Once error resolves, flush_dirty_spaces(force=False) after debounce window succeeds and clears .watcher_dirty
            mock_mono.return_value = 101.5
            flushed_res = worker.flush_dirty_spaces(force=False)
            self.assertIn("source", flushed_res)
            self.assertIn("added.py", flushed_res["source"].added)
            self.assertFalse(self.scanner.is_watcher_dirty("source"))
            self.assertEqual(len(received_events), 1)
            self.assertIn("added.py", received_events[0].added)

        # Verify watched space located under an external .cache ancestor directory is not falsely ignored
        ext_cache_space_dir = self.tmp_dir / ".cache" / "ext_space"
        ext_cache_space_dir.mkdir(parents=True, exist_ok=True)
        ext_file = ext_cache_space_dir / "ext_mod.py"
        ext_file.write_text("ext = 1\n", encoding="utf-8")
        self.mgr.define_ephemeral_space(
            "ext_cache_space",
            {
                "include": [ext_cache_space_dir.as_posix()],
                "file_patterns": ["*.py"],
                "watch": True,
            },
        )
        matched_ext = worker.notify_file_event(str(ext_file))
        self.assertIn("ext_cache_space", matched_ext)
        worker.flush_space_now("ext_cache_space")

        unsub()
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_watchdog_handler_routing_and_worker_lifecycle(self) -> None:
        """Verify _FileSpaceWatchdogHandler event routing (including directory created/moved/deleted) and worker start/stop."""
        worker = FileSpaceWatcherServiceWorker(
            name="file-space-watcher",
            context={"project_root": self.proj_root, "storage_root": self.storage_root},
            space_manager=self.mgr,
            scanner=self.scanner,
            debounce_seconds=0.05,
        )
        handler = _FileSpaceWatchdogHandler(worker)

        with patch.object(worker, "notify_file_event") as mock_notify:
            # 1. Regular file event forwards src_path and dest_path with is_directory=False
            file_ev = SimpleNamespace(
                is_directory=False,
                event_type="moved",
                src_path=str(self.src_dir / "old.py"),
                dest_path=str(self.src_dir / "new.py"),
            )
            handler.on_any_event(file_ev)  # type: ignore[arg-type]
            self.assertEqual(mock_notify.call_count, 2)
            mock_notify.assert_any_call(
                str(self.src_dir / "old.py"),
                is_directory=False,
                event_type="moved",
            )
            mock_notify.assert_any_call(
                str(self.src_dir / "new.py"),
                is_directory=False,
                event_type="moved",
            )
            mock_notify.reset_mock()

            # 2. Directory "modified" event is ignored
            dir_mod_ev = SimpleNamespace(
                is_directory=True,
                event_type="modified",
                src_path=str(self.src_dir),
                dest_path=None,
            )
            handler.on_any_event(dir_mod_ev)  # type: ignore[arg-type]
            self.assertEqual(mock_notify.call_count, 0)

            # 3. Directory "created", "moved", "deleted" events forward is_directory=True and set _yscb_handled=True
            for ev_type, specific_method in (
                ("created", getattr(handler, "on_created", None)),
                ("moved", handler.on_moved),
                ("deleted", handler.on_deleted),
            ):
                mock_notify.reset_mock()
                dir_ev = SimpleNamespace(
                    is_directory=True,
                    event_type=ev_type,
                    src_path=str(self.src_dir / f"dir_{ev_type}"),
                    dest_path=None,
                )
                handler.on_any_event(dir_ev)  # type: ignore[arg-type]
                self.assertTrue(getattr(dir_ev, "_yscb_handled", False))
                mock_notify.assert_called_once_with(
                    str(self.src_dir / f"dir_{ev_type}"),
                    is_directory=True,
                    event_type=ev_type,
                )
                if callable(specific_method):
                    specific_method(dir_ev)  # type: ignore[arg-type]
                    self.assertEqual(mock_notify.call_count, 1)

        # 4. Verify worker.start() and worker.stop() lifecycle with _start_watchdog_observer patched
        with patch.object(worker, "_start_watchdog_observer"):
            try:
                worker.start()
                state_path = worker._resolve_watcher_state_path()
                deadline = threading.Event()
                for _ in range(40):
                    if state_path.exists():
                        break
                    deadline.wait(0.02)
                self.assertTrue(worker.is_alive())
                self.assertTrue(state_path.exists())
                self.assertTrue(
                    is_watcher_active(
                        self.proj_root,
                        space_name="source",
                        space_manager=self.mgr,
                    )
                )
            finally:
                worker.stop(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertFalse(worker._resolve_watcher_state_path().exists())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_commands_json_text_and_error_branches(self) -> None:
        """Verify CLI scan, status, files, diff, clean in JSON/text modes, error branches, and option helpers."""
        # 1. Verify _extract_opt and _has_opt across get_option_value, has_option, params, and positional args (.val)
        custom_bags = SimpleNamespace(
            get_option_value=lambda k: "from_getter" if k == "space" else None,
            has_option=lambda k: k == "json",
            options={},
            args=[],
        )
        self.assertEqual(
            file_space_cli._extract_opt(custom_bags, "--space"), "from_getter"
        )
        self.assertTrue(file_space_cli._has_opt(custom_bags, "--json"))

        params_bags = _MockCmdBags(
            options={"space": _MockOptBag(params="from_params")}
        )
        self.assertEqual(
            file_space_cli._extract_opt(params_bags, "--space"), "from_params"
        )

        pos_bags = _MockCmdBags(options={}, args=[_MockArg(val="from_pos_arg")])
        self.assertEqual(
            file_space_cli._extract_opt(pos_bags, "--space"), "from_pos_arg"
        )

        with patch.object(
            file_space_cli, "_create_scanner", return_value=self.scanner
        ):
            # 2. scan (--json and text)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.scan(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            scan_out = json.loads(buf.getvalue())
            self.assertEqual(scan_out["status"], "ok")
            self.assertEqual(scan_out["added_count"], 1)

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.scan(_make_bags(space="source"))
            self.assertEqual(rc, 0)
            self.assertIn("[File-Space Scan]", buf.getvalue())

            # 3. status (--json and text)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.status(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            status_out = json.loads(buf.getvalue())
            self.assertEqual(status_out["status"], "ok")
            self.assertEqual(
                status_out["spaces"]["source"]["active_files"], 1
            )

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.status(_make_bags(space="source"))
            self.assertEqual(rc, 0)
            self.assertIn("=== File-Space Status", buf.getvalue())

            # 4. files (--json and text)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.files(
                    _make_bags(space="source", pattern="*.py", json=True)
                )
            self.assertEqual(rc, 0)
            files_out = json.loads(buf.getvalue())
            self.assertEqual(files_out["count"], 1)
            self.assertEqual(files_out["files"][0]["path"], "main.py")

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.files(_make_bags(space="source"))
            self.assertEqual(rc, 0)
            self.assertIn("=== Managed Files", buf.getvalue())

            # 5. diff (--json and text)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.diff(
                    _make_bags(
                        space="source",
                        consumer="test_c",
                        ack=True,
                        json=True,
                    )
                )
            self.assertEqual(rc, 0)
            diff_out = json.loads(buf.getvalue())
            self.assertTrue(diff_out["acknowledged"])
            self.assertEqual(diff_out["added_count"], 1)

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.diff(
                    _make_bags(space="source", consumer="test_c")
                )
            self.assertEqual(rc, 0)
            self.assertIn("[File-Space Diff]", buf.getvalue())

            # 6. clean (--consumer, --space, and full clean in --json and text modes)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.clean(
                    _make_bags(space="source", consumer="test_c", json=True)
                )
            self.assertEqual(rc, 0)
            clean_c_out = json.loads(buf.getvalue())
            self.assertEqual(clean_c_out["reset_consumers"], ["test_c"])

            self.scanner.ack("source", consumer_id="test_c")
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.clean(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            clean_s_out = json.loads(buf.getvalue())
            self.assertIn("source.yfp2.bin", clean_s_out["removed_snapshots"])

            self.scanner.refresh("source")
            self.scanner.ack("source", consumer_id="test_c")
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.clean(_make_bags())
            self.assertEqual(rc, 0)
            self.assertIn("[File-Space Clean]", buf.getvalue())

            # 7. Error branches for missing space (--space="missing") in both --json and text modes
            for cmd_fn in (
                file_space_cli.status,
                file_space_cli.scan,
                file_space_cli.files,
                file_space_cli.diff,
                file_space_cli.clean,
            ):
                err_json_buf = io.StringIO()
                with patch("sys.stdout", err_json_buf):
                    rc_json = cmd_fn(_make_bags(space="missing", json=True))
                self.assertEqual(rc_json, 1)
                err_payload = json.loads(err_json_buf.getvalue())
                self.assertEqual(err_payload["status"], "error")

                err_txt_buf = io.StringIO()
                with patch("sys.stdout", err_txt_buf), patch(
                    "sys.stderr", err_txt_buf
                ):
                    rc_txt = cmd_fn(_make_bags(space="missing"))
                self.assertEqual(rc_txt, 1)
                self.assertIn("[Error]", err_txt_buf.getvalue())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_providers_table_and_knowledge_db_filtering(self) -> None:
        """Verify providers table rendering, knowledge-db space_weights dict/list filtering, and empty fallback."""
        unindexed_dir = self.proj_root / "unindexed"
        unindexed_dir.mkdir(parents=True, exist_ok=True)
        real_mgr = FileSpaceManager(
            project_root=self.proj_root,
            storage_root=self.storage_root,
            spaces_config={
                "source": {
                    "description": "Indexed primary source",
                    "include": [self.src_dir.as_posix()],
                    "file_patterns": ["*.py"],
                    "watch": True,
                },
                "unindexed": {
                    "description": "Unindexed scratch space",
                    "include": [unindexed_dir.as_posix()],
                    "file_patterns": ["*.tmp"],
                    "watch": False,
                },
            },
            contributed_spaces={},
        )

        # 1. _resolve_knowledge_db_indexed_space_names with dict and list formats, ignoring '_' prefixed keys
        with patch(
            "core.contributes.get",
            return_value={
                "space_weights": {"source": 1.0, "_comment": "ignore_me"}
            },
        ), patch("core.uri.resolve", return_value=""):
            names_dict = _resolve_knowledge_db_indexed_space_names()
            self.assertEqual(names_dict, {"source"})

        with patch(
            "core.contributes.get",
            return_value=[
                {
                    "data": {
                        "space_weights": {"source": 1.0, "_meta": 0.0}
                    }
                }
            ],
        ), patch("core.uri.resolve", return_value=""):
            names_list = _resolve_knowledge_db_indexed_space_names()
            self.assertEqual(names_list, {"source"})

        # 2. Real table rendering with FileSpaceManager mocked to return real_mgr
        with patch(
            "file_space.providers.FileSpaceManager", return_value=real_mgr
        ), patch(
            "file_space.providers._resolve_knowledge_db_indexed_space_names",
            return_value={"source"},
        ):
            reg_table = get_registered_file_spaces_table()
            self.assertIn("| `source` |", reg_table)
            self.assertIn("| `unindexed` |", reg_table)
            self.assertIn("Indexed primary source", reg_table)

            kdb_table = get_knowledge_db_spaces()
            self.assertIn("**`source`**", kdb_table)
            self.assertNotIn("unindexed", kdb_table)

        # 3. Fallback table when no spaces exist or exception occurs
        with patch(
            "file_space.providers.FileSpaceManager",
            side_effect=RuntimeError("init error"),
        ):
            empty_reg = get_registered_file_spaces_table()
            self.assertIn("*(尚未註冊空間)*", empty_reg)
            empty_kdb = get_knowledge_db_spaces()
            self.assertIn("*(目前無已註冊空間)*", empty_kdb)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hooks_and_migration_scripts(self) -> None:
        """Verify hook.dev.py, hook.server.py background warming synchronization, and migrations/1.0.1.x.py."""
        # 1. hook.dev.py setup and teardown
        sb_dir = self.tmp_dir / "dev_sandbox"
        ctx = SimpleNamespace(sandbox_dir=str(sb_dir))
        hook_dev.on_test_setup(ctx)
        self.assertTrue((sb_dir / ".storage.local" / "file-space" / "snapshots").is_dir())
        self.assertTrue((sb_dir / ".storage.local" / "file-space" / "cursors").is_dir())
        self.assertTrue((sb_dir / ".cache" / "file-space").is_dir())
        hook_dev.on_test_teardown(ctx)

        # 2. hook.server.py warming thread synchronized via threading.Event inside patch("file_space.refresh")
        done_ev = threading.Event()
        refresh_calls: List[bool] = []

        def _sync_refresh(*, background: bool = False, **kwargs: Any) -> None:
            refresh_calls.append(background)
            done_ev.set()

        if hasattr(hook_server, "_PREWARM_RUNNING"):
            hook_server._PREWARM_RUNNING = False

        with patch("file_space.refresh", side_effect=_sync_refresh):
            status_str = hook_server.on_server_worker_warming({})
            self.assertEqual(status_str, "warming_started")
            self.assertTrue(done_ev.wait(timeout=2.0))
            for t in list(threading.enumerate()):
                if t.name == "file-space-prewarm":
                    t.join(timeout=2.0)

        self.assertEqual(refresh_calls, [True])

        # Verify exception tolerance in hook.server.py
        err_done_ev = threading.Event()

        def _failing_refresh(**kwargs: Any) -> None:
            err_done_ev.set()
            raise RuntimeError("Simulated prewarm failure")

        if hasattr(hook_server, "_PREWARM_RUNNING"):
            hook_server._PREWARM_RUNNING = False

        with patch("file_space.refresh", side_effect=_failing_refresh):
            status_err = hook_server.on_server_worker_warming({})
            self.assertEqual(status_err, "warming_started")
            self.assertTrue(err_done_ev.wait(timeout=2.0))
            for t in list(threading.enumerate()):
                if t.name == "file-space-prewarm":
                    t.join(timeout=2.0)

        # 3. migrations/1.0.1.x.py: migrate snapshots/cursors, preserve existing destination files, clean broken symlinks, idempotency
        yscb_dir = self.tmp_dir / "mig_yscb"
        legacy_snap = yscb_dir / ".cache" / "file-space" / "snapshots"
        legacy_cur = yscb_dir / ".cache" / "file-space" / "cursors"
        legacy_snap.mkdir(parents=True, exist_ok=True)
        legacy_cur.mkdir(parents=True, exist_ok=True)

        (legacy_snap / "source.yfp2.bin").write_bytes(b"LEGACY_SNAP")
        (legacy_snap / "conflict.yfp2.bin").write_bytes(b"OLD_CONFLICT")
        (legacy_cur / "kdb.json").write_text('{"source": 1}', encoding="utf-8")

        broken_mig_link = legacy_snap / "dangling_link.bin"
        try:
            os.symlink(yscb_dir / "non_existent_target.bin", broken_mig_link)
        except (OSError, NotImplementedError):
            pass

        dst_storage = yscb_dir / ".storage.local" / "file-space"
        dst_snap = dst_storage / "snapshots"
        dst_snap.mkdir(parents=True, exist_ok=True)
        (dst_snap / "conflict.yfp2.bin").write_bytes(b"NEW_KEEP")

        mig_ctx = {
            "yscb_dir": str(yscb_dir),
            "storage_local_dir": str(dst_storage),
        }
        self.assertTrue(migration_101x.migrate(mig_ctx))
        self.assertEqual(
            (dst_snap / "source.yfp2.bin").read_bytes(), b"LEGACY_SNAP"
        )
        self.assertEqual(
            (dst_snap / "conflict.yfp2.bin").read_bytes(), b"NEW_KEEP"
        )
        self.assertEqual(
            (dst_storage / "cursors" / "kdb.json").read_text(encoding="utf-8"),
            '{"source": 1}',
        )
        self.assertFalse((legacy_snap / "conflict.yfp2.bin").exists())
        self.assertFalse(os.path.lexists(broken_mig_link))

        # Idempotent second execution
        self.assertTrue(migration_101x.migrate(mig_ctx))
        self.mark_passed()
