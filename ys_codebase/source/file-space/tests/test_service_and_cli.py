"""
Unit tests for FileSpaceWatcherServiceWorker (debounce, .yscb.lock deference, subscribe)
and CLI subcommands (status, scan, files, diff, clean).
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
from typing import Any, Dict, List
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

_cli_spec = importlib.util.spec_from_file_location(
    "file_space_scripts_cli", os.path.join(_pkg_root, "scripts", "cli.py")
)
file_space_cli = importlib.util.module_from_spec(_cli_spec)  # type: ignore[arg-type]
assert _cli_spec and _cli_spec.loader
_cli_spec.loader.exec_module(file_space_cli)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from file_space.manager import FileSpaceManager
from file_space.providers import get_registered_file_spaces_table
from file_space.scanner import FingerprintScanner
from file_space.schema import ScanDiffResult
from file_space.service import (
    FileSpaceWatcherServiceWorker,
    clear_subscribers,
    subscribe,
)


@dataclass
class _MockArg:
    val: Any


@dataclass
class _MockOptBag:
    args: List[_MockArg] = field(default_factory=list)


@dataclass
class _MockCmdBags:
    options: Dict[str, _MockOptBag] = field(default_factory=dict)


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
    """Tests for FileSpaceWatcherServiceWorker background watcher and CLI command handlers."""

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
    def test_ft06_service_worker_debounce_lock_and_subscribe(self) -> None:
        """FT-06: Verify FileSpaceWatcherServiceWorker debounce, .yscb.lock deference, and subscribe callback."""
        self.scanner.refresh("source")

        received_events: List[ ScanDiffResult] = []
        unsub = subscribe(
            lambda s_name, diff_res: received_events.append(diff_res),
            spaces=["source"],
        )

        worker = FileSpaceWatcherServiceWorker(
            name="file-space-watcher",
            context={"project_root": self.proj_root, "storage_root": self.storage_root},
            space_manager=self.mgr,
            scanner=self.scanner,
            debounce_seconds=0.05,
        )

        # Create a new file and notify worker
        new_file = self.src_dir / "added.py"
        new_file.write_text("a = 1\n", encoding="utf-8")
        matched = worker.notify_file_event(str(new_file))
        self.assertEqual(matched, ["source"])

        # Simulate active .yscb.lock transaction lock -> flush must yield/defer
        lock_file = self.proj_root / ".yscb.lock"
        lock_file.write_text("locked", encoding="utf-8")
        deferred_res = worker.flush_dirty_spaces(force=True)
        self.assertEqual(deferred_res, {})
        self.assertEqual(len(received_events), 0)
        metrics = worker.get_custom_metrics()
        self.assertGreaterEqual(metrics["deferred_by_lock_count"], 1)

        # Remove .yscb.lock -> flush updates YFP2 snapshot and invokes subscriber
        lock_file.unlink()
        flushed_res = worker.flush_dirty_spaces(force=True)
        self.assertIn("source", flushed_res)
        self.assertIn("added.py", flushed_res["source"].added)
        self.assertEqual(len(received_events), 1)
        self.assertIn("added.py", received_events[0].added)

        unsub()
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft07_cli_commands_and_providers(self) -> None:
        """FT-07: Verify CLI status, scan, files, diff, clean commands with --json and providers."""
        with patch.object(
            file_space_cli, "_create_scanner", return_value=self.scanner
        ):
            # 1. scan --json
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.scan(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            scan_out = json.loads(buf.getvalue())
            self.assertEqual(scan_out["status"], "ok")
            self.assertEqual(scan_out["added_count"], 1)

            # 2. status --json
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.status(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            status_out = json.loads(buf.getvalue())
            self.assertEqual(status_out["status"], "ok")
            self.assertIn("source", status_out["spaces"])
            self.assertEqual(
                status_out["spaces"]["source"]["active_files"], 1
            )

            # 3. files --json
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.files(
                    _make_bags(space="source", pattern="*.py", json=True)
                )
            self.assertEqual(rc, 0)
            files_out = json.loads(buf.getvalue())
            self.assertEqual(files_out["count"], 1)
            self.assertEqual(files_out["files"][0]["path"], "main.py")

            # 4. diff --consumer test_c --ack --json
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

            # Subsequent diff for test_c should have 0 changes
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.diff(
                    _make_bags(space="source", consumer="test_c", json=True)
                )
            self.assertEqual(rc, 0)
            diff_out2 = json.loads(buf.getvalue())
            self.assertEqual(diff_out2["added_count"], 0)

            # 5. clean --json
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = file_space_cli.clean(_make_bags(space="source", json=True))
            self.assertEqual(rc, 0)
            clean_out = json.loads(buf.getvalue())
            self.assertEqual(clean_out["status"], "ok")
            self.assertIn("source.yfp2.bin", clean_out["removed_snapshots"])

        table_md = get_registered_file_spaces_table()
        self.assertIn("| 空間名稱 |", table_md)
        self.mark_passed()
