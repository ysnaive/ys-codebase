"""
Unit tests for file_space service forwarding shell, CLI subcommands, providers, hooks, and migrations.
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
from file_space.scanner import FingerprintScanner
from file_space.schema import ScanDiffDetail, ScanDiffResult
from file_space.service import (
    FileSpaceWatcherServiceWorker,
    _dispatch_to_subscribers,
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
    """Tests for service forwarding shell, CLI command handlers, providers, hooks, and migrations."""

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
    def test_service_forwarding_and_noop_worker(self) -> None:
        """Verify subscribe forwarding to core.space.watcher and no-op FileSpaceWatcherServiceWorker."""
        received: List[ScanDiffResult] = []
        unsub = subscribe(
            lambda s_name, diff_res: received.append(diff_res),
            spaces=["source"],
        )
        dummy_diff = ScanDiffResult(
            space_name="source",
            from_generation=0,
            to_generation=1,
            added_count=1,
            detail=ScanDiffDetail(added={"main.py"}),
        )
        _dispatch_to_subscribers("source", dummy_diff)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].added, ["main.py"])
        unsub()

        worker = FileSpaceWatcherServiceWorker(
            name="file-space-watcher",
            context={"project_root": self.proj_root, "storage_root": self.storage_root},
            space_manager=self.mgr,
            scanner=self.scanner,
        )
        worker.start()
        self.assertTrue(worker.is_alive())
        self.assertEqual(worker.notify_file_event(str(self.src_dir / "main.py")), [])
        self.assertEqual(worker.flush_dirty_spaces(), {})
        self.assertIsNone(worker.flush_space_now("source"))
        self.assertTrue(worker.get_custom_metrics().get("deprecated_shell"))
        worker.stop()
        self.assertFalse(worker.is_alive())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_commands_json_text_and_error_branches(self) -> None:
        """Verify CLI scan, status, files, diff, clean in JSON/text modes and error branches."""
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

        with patch.object(
            file_space_cli, "_create_scanner", return_value=self.scanner
        ):
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

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.status(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            status_out = json.loads(buf.getvalue())
            self.assertEqual(status_out["space_count"], 1)
            self.assertEqual(
                status_out["spaces"][0]["active_file_count"], 1
            )

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.status(_make_bags(space="source"))
            self.assertEqual(rc, 0)
            self.assertIn("=== File-Space Status", buf.getvalue())

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.files(
                    _make_bags(space="source", pattern="*.py", json=True)
                )
            self.assertEqual(rc, 0)
            files_out = json.loads(buf.getvalue())
            self.assertEqual(files_out["count"], 1)
            self.assertTrue(files_out["files"][0]["path"].endswith("main.py"))

            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.files(_make_bags(space="source"))
            self.assertEqual(rc, 0)
            self.assertIn("=== Managed Files", buf.getvalue())

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
            self.assertTrue(
                any(
                    s.endswith("source.yfp2.bin")
                    for s in clean_s_out["removed_snapshots"]
                )
            )

            self.scanner.refresh("source")
            self.scanner.ack("source", consumer_id="test_c")
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.clean(_make_bags())
            self.assertEqual(rc, 0)
            self.assertIn("[File-Space Clean]", buf.getvalue())

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
    def test_providers_delegation(self) -> None:
        """Verify file_space.providers delegates to core.space.providers."""
        with patch(
            "core.contributes.get",
            return_value={"space_weights": {"source": 1.0, "_comment": "ignore"}},
        ), patch("core.uri.resolve", return_value=""):
            names_dict = _resolve_knowledge_db_indexed_space_names()
            self.assertEqual(names_dict, {"source"})

        reg_table = get_registered_file_spaces_table()
        self.assertIsInstance(reg_table, str)
        kdb_table = get_knowledge_db_spaces()
        self.assertIsInstance(kdb_table, str)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hooks_and_migration_scripts(self) -> None:
        """Verify hook.dev.py, hook.server.py background warming, and migrations/1.0.1.x.py."""
        sb_dir = self.tmp_dir / "dev_sandbox"
        ctx = SimpleNamespace(sandbox_dir=str(sb_dir))
        hook_dev.on_test_setup(ctx)
        self.assertTrue((sb_dir / ".storage.local" / "file-space" / "snapshots").is_dir())
        self.assertTrue((sb_dir / ".storage.local" / "file-space" / "cursors").is_dir())
        self.assertTrue((sb_dir / ".cache" / "file-space").is_dir())
        hook_dev.on_test_teardown(ctx)

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

        yscb_dir = self.tmp_dir / "mig_yscb"
        legacy_snap = yscb_dir / ".cache" / "file-space" / "snapshots"
        legacy_cur = yscb_dir / ".cache" / "file-space" / "cursors"
        legacy_snap.mkdir(parents=True, exist_ok=True)
        legacy_cur.mkdir(parents=True, exist_ok=True)

        (legacy_snap / "source.yfp2.bin").write_bytes(b"LEGACY_SNAP")
        (legacy_snap / "conflict.yfp2.bin").write_bytes(b"OLD_CONFLICT")
        (legacy_cur / "kdb.json").write_text('{"source": 1}', encoding="utf-8")

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
        self.assertTrue(migration_101x.migrate(mig_ctx))
        self.mark_passed()
