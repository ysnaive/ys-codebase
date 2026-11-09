"""
Unit & Integration Tests for Server Module.
Covers DebouncedIOStreamer, WarmWorker pre-warm events & lazy loading,
SystemExit interception, ServiceManager, MasterSupervisor HTTP dispatch, and ModulesWatcher.
"""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from dev.testing.case import YSCBTestCase
from core import events
from core.commands import dispatcher as core_dispatcher
from server import service as server_service
from server.master import MasterSupervisor, ServerDaemonState, WorkerSpawnError, read_daemon_state
from server.service import BaseServiceWorker, ServiceManager, _load_service_class_from_uri
from server.streamer import DebouncedIOStreamer
from server.watcher import ModulesWatcher, _scan_modules_dir
from server.worker import WarmWorker


def _load_server_cli():
    """Loads server/scripts/cli.py dynamically for CLI handler unit tests."""
    cli_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "cli.py")
    spec = importlib.util.spec_from_file_location("_server_cli_test", cli_path)
    server_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_cli)
    return server_cli


class MockService(BaseServiceWorker):
    def __init__(self, name: str = "mock-service") -> None:
        self._name = name
        self.started = False
        self.stopped = False

    @property
    def name(self) -> str:
        return self._name

    def start(self, context) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def health_check(self) -> bool:
        return self.started and not self.stopped


class FaultyService(BaseServiceWorker):
    def __init__(self, name: str = "faulty-service") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def start(self, context) -> None:
        raise RuntimeError("start failure")

    def stop(self) -> None:
        raise RuntimeError("stop failure")

    def health_check(self) -> bool:
        raise RuntimeError("health_check failure")


class TestServerModule(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)
        server_service.reset_touch_state()

    def tearDown(self):
        self.doCleanups()
        for mod_key in [
            k for k in list(sys.modules.keys())
            if k == "mock_kdb_service" or k.startswith("mock_kdb_service.")
        ]:
            sys.modules.pop(mod_key, None)

        root_prefix = os.path.normcase(os.path.abspath(self.root_dir))
        for cache_key in [
            k for k in list(core_dispatcher._MODULE_CACHE.keys())
            if os.path.normcase(os.path.abspath(k)).startswith(root_prefix)
        ]:
            core_dispatcher._MODULE_CACHE.pop(cache_key, None)
        if core_dispatcher._GLOBAL_REGISTRY_ROOT == root_prefix:
            core_dispatcher._GLOBAL_REGISTRY = None
            core_dispatcher._GLOBAL_REGISTRY_ROOT = None

        server_service.reset_touch_state()
        try:
            super().tearDown()
        finally:
            self.temp_dir.cleanup()

    def _make_supervisor(self, **kwargs) -> MasterSupervisor:
        kwargs.setdefault("yscb_root", self.root_dir)
        kwargs.setdefault("idle_timeout_sec", 300.0)
        kwargs.setdefault("enable_watcher", False)
        sup = MasterSupervisor(**kwargs)
        self.addCleanup(sup.logger.archive_and_close)
        self.addCleanup(sup.stop)
        return sup

    def test_debounced_streamer(self):
        """DebouncedIOStreamer captures output, preserves alternating stdout/stderr order, prevents re-entrancy deadlock, and emits structured packets."""
        packets = []
        streamer_ref = None

        def emit_cb(pkt):
            packets.append(pkt)
            # Verify re-entrant flush inside emit_chunk does not deadlock RLock
            if len(packets) == 1 and streamer_ref is not None:
                streamer_ref.flush()

        streamer = DebouncedIOStreamer(emit_chunk=emit_cb, debounce_ms=100)
        streamer_ref = streamer
        with streamer:
            sys.stdout.write("Hello ")
            sys.stdout.write("World!\n")
            sys.stderr.write("Warn 1\n")
            sys.stdout.write("After warn\n")

        # After exiting context manager, all streams are flushed
        streamer.send_task_finish(exit_code=0, duration_ms=15.0)

        self.assertGreater(len(packets), 0)
        types = [p["type"] for p in packets]
        self.assertIn("terminal_stream", types)
        self.assertIn("task_finish", types)

        stream_seq = [(p["stream"], p["text"]) for p in packets if p["type"] == "terminal_stream"]
        self.assertEqual(
            stream_seq,
            [
                ("stdout", "Hello World!\n"),
                ("stderr", "Warn 1\n"),
                ("stdout", "After warn\n"),
            ],
        )

        finish_pkt = [p for p in packets if p["type"] == "task_finish"][0]
        self.assertEqual(finish_pkt["exit_code"], 0)
        self.mark_passed()

    def test_warm_worker_pre_warm_events(self):
        """WarmWorker emits warming and ready events via core.events."""
        captured_events = []

        from unittest.mock import patch

        def mock_broadcast(event_name, context=None, emit_module="core", search_roots=None):
            captured_events.append((event_name, context, emit_module))
            return {}

        with patch.object(events, "broadcast", side_effect=mock_broadcast):
            worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
            self.addCleanup(worker.service_manager.stop_all)
            self.assertEqual(worker.yscb_root, os.path.abspath(self.root_dir))
            self.assertTrue(worker.host_dir)
            worker.pre_warm()
            worker.service_manager.stop_all()

        event_names = [e[0] for e in captured_events]
        self.assertIn("server_worker_warming", event_names)
        self.assertIn("server_worker_ready", event_names)
        self.mark_passed()

    def test_warm_worker_system_exit_interception(self):
        """WarmWorker intercepts SystemExit(int), SystemExit(None), SystemExit(str), and get_virtual_cwd fallback without crashing."""
        packets = []
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: packets.append(p))

        # 1. SystemExit(42) -> exit_code 42
        mock_mod_dir = os.path.join(self.root_dir, ".modules", "mock_exit", "scripts")
        os.makedirs(mock_mod_dir, exist_ok=True)
        with open(os.path.join(mock_mod_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("def help(cmd_bags):\n    import sys\n    sys.exit(42)\n")

        exit_code = worker.execute_task(module="mock_exit", args=[], cwd=self.root_dir)
        self.assertEqual(exit_code, 42)

        finish_packets = [p for p in packets if p.get("type") == "task_finish"]
        self.assertEqual(len(finish_packets), 1)
        self.assertEqual(finish_packets[0]["exit_code"], 42)

        # 2. SystemExit(None) -> exit_code 0
        packets.clear()
        mock_none_dir = os.path.join(self.root_dir, ".modules", "mock_exit_none", "scripts")
        os.makedirs(mock_none_dir, exist_ok=True)
        with open(os.path.join(mock_none_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("def help(cmd_bags):\n    raise SystemExit(None)\n")

        exit_code_none = worker.execute_task(module="mock_exit_none", args=[], cwd=self.root_dir)
        self.assertEqual(exit_code_none, 0)
        self.assertEqual([p for p in packets if p.get("type") == "task_finish"][0]["exit_code"], 0)

        # 3. SystemExit("err") -> exit_code 1
        packets.clear()
        mock_str_dir = os.path.join(self.root_dir, ".modules", "mock_exit_str", "scripts")
        os.makedirs(mock_str_dir, exist_ok=True)
        with open(os.path.join(mock_str_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("def help(cmd_bags):\n    raise SystemExit('err')\n")

        exit_code_str = worker.execute_task(module="mock_exit_str", args=[], cwd=self.root_dir)
        self.assertEqual(exit_code_str, 1)
        self.assertEqual([p for p in packets if p.get("type") == "task_finish"][0]["exit_code"], 1)

        # 4. Empty or deleted cwd falls back to self.yscb_root via get_virtual_cwd and still emits task_finish
        packets.clear()
        with unittest.mock.patch("server.worker.get_virtual_cwd", return_value=self.root_dir):
            exit_code_cwd = worker.execute_task(module="mock_exit_none", args=[], cwd="")
        self.assertEqual(exit_code_cwd, 0)
        self.assertEqual(len([p for p in packets if p.get("type") == "task_finish"]), 1)
        self.mark_passed()

    def test_service_manager_lifecycle(self):
        """ServiceManager unifies service lifecycle, metadata, status, and isolates single-service exceptions."""
        mgr = ServiceManager()
        svc = MockService("test-kdb-watcher")
        faulty = FaultyService("faulty-watcher")
        mgr.register(svc, provider="knowledge-db", description="Test file watcher")
        mgr.register(faulty, provider="faulty-mod", description="Faulty service")

        self.assertFalse(svc.started)
        st_init = {s["name"]: s for s in mgr.get_status()}
        self.assertEqual(len(st_init), 2)
        self.assertEqual(st_init["test-kdb-watcher"]["provider"], "knowledge-db")
        self.assertEqual(st_init["test-kdb-watcher"]["description"], "Test file watcher")
        self.assertFalse(st_init["test-kdb-watcher"]["alive"])
        self.assertFalse(st_init["faulty-watcher"]["alive"])

        # Faulty service raising in start/health_check/stop must not block healthy service
        with unittest.mock.patch("server.service.log_error"):
            mgr.start_all({"root": self.root_dir})
            self.assertTrue(svc.started)
            st_running = {s["name"]: s["alive"] for s in mgr.get_status()}
            self.assertTrue(st_running["test-kdb-watcher"])
            self.assertFalse(st_running["faulty-watcher"])
            mgr.stop_all()
        self.assertTrue(svc.stopped)
        st_stopped = {s["name"]: s["alive"] for s in mgr.get_status()}
        self.assertFalse(st_stopped["test-kdb-watcher"])
        self.assertFalse(st_stopped["faulty-watcher"])
        self.mark_passed()

    def test_modules_watcher_detection(self):
        """ModulesWatcher filters watched file extensions, scans .dist-info directory contents, detects changes and deletions, and extracts affected module names."""
        modules_dir = os.path.join(self.root_dir, ".modules")
        kdb_dir = os.path.join(modules_dir, "knowledge-db")
        dist_info_dir = os.path.join(kdb_dir, "pkg-1.0.dist-info")
        hidden_dir = os.path.join(modules_dir, ".staging_temp")
        os.makedirs(dist_info_dir, exist_ok=True)
        os.makedirs(hidden_dir, exist_ok=True)

        # Verify _scan_modules_dir filters (.py, .json, .zip, .dist-info) and includes files inside .dist-info/
        py_file = os.path.join(kdb_dir, "mod.py")
        txt_file = os.path.join(kdb_dir, "readme.txt")
        tmp_file = os.path.join(kdb_dir, "cache.tmp")
        dist_meta = os.path.join(dist_info_dir, "METADATA")
        dist_record = os.path.join(dist_info_dir, "RECORD")
        with open(py_file, "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("ignored text\n")
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write("ignored tmp\n")
        with open(dist_meta, "w", encoding="utf-8") as f:
            f.write("Name: pkg\nVersion: 1.0\n")
        with open(dist_record, "w", encoding="utf-8") as f:
            f.write("pkg/__init__.py,,\n")

        snap = _scan_modules_dir(modules_dir)
        self.assertIn(py_file, snap)
        self.assertIn(dist_meta, snap)
        self.assertIn(dist_record, snap)
        self.assertNotIn(txt_file, snap)
        self.assertNotIn(tmp_file, snap)
        self.assertEqual(_scan_modules_dir(os.path.join(self.root_dir, "nonexistent_modules")), {})

        notified_modules = []

        def on_change(affected):
            notified_modules.append(affected)

        watcher = ModulesWatcher(
            modules_dir=modules_dir,
            on_change_callback=on_change,
            poll_interval_sec=0.05,
            debounce_sec=0.05,
        )

        # Verify _extract_affected_modules detects file deletion and ignores hidden .staging directories
        hidden_json = os.path.join(hidden_dir, "manifest.json")
        prev_snap = {py_file: 100.0, hidden_json: 100.0}
        curr_snap = {}
        affected_del = watcher._extract_affected_modules(prev_snap, curr_snap)
        self.assertEqual(affected_del, {"knowledge-db"})

        watcher.start()
        try:
            manifest_path = os.path.join(kdb_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write('{"name": "knowledge-db"}')
            deadline = time.monotonic() + 3.0
            while not notified_modules and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertGreater(len(notified_modules), 0)
            self.assertIn("knowledge-db", notified_modules[0])

            # Verify live deletion triggers notification
            notified_modules.clear()
            os.remove(manifest_path)
            deadline_del = time.monotonic() + 3.0
            while not notified_modules and time.monotonic() < deadline_del:
                time.sleep(0.02)
            self.assertGreater(len(notified_modules), 0)
            self.assertIn("knowledge-db", notified_modules[0])
        finally:
            watcher.stop()
        self.mark_passed()

    def test_master_supervisor_http_and_lifecycle(self):
        """MasterSupervisor initializes dynamic port, writes state, responds to HTTP endpoints (/api/status, /api/reload, /api/shutdown, /api/dispatch), and stops cleanly."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
            sup.start(foreground=False)

        try:
            self.assertGreater(sup.port, 0)
            self.assertTrue(os.path.exists(sup.state_file))

            # 1. Test unauthorized request (403)
            url_status = f"http://127.0.0.1:{sup.port}/api/status"
            req_unauth = urllib.request.Request(url_status)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req_unauth)
            self.assertEqual(cm.exception.code, 403)

            # 2. Test authorized GET /api/status
            auth_headers = {"Authorization": f"Bearer {sup.token}", "Content-Type": "application/json"}
            req_auth = urllib.request.Request(url_status, headers=auth_headers)
            with urllib.request.urlopen(req_auth) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body["status"], "running")
                self.assertEqual(body["pid"], os.getpid())

            # 3. Test POST /api/reload
            url_reload = f"http://127.0.0.1:{sup.port}/api/reload"
            with unittest.mock.patch.object(sup, "restart_worker", return_value=88888):
                req_reload = urllib.request.Request(url_reload, data=b"{}", headers=auth_headers, method="POST")
                with urllib.request.urlopen(req_reload) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(body["status"], "worker_restarted")
                    self.assertEqual(body["new_worker_pid"], 88888)

            # 4. Test POST /api/dispatch (yscb_root mismatch -> 400 Bad Request)
            url_dispatch = f"http://127.0.0.1:{sup.port}/api/dispatch"
            bad_payload = json.dumps({"module": "dummy", "args": [], "yscb_root": "/mismatched/root"}).encode("utf-8")
            req_dispatch_bad = urllib.request.Request(url_dispatch, data=bad_payload, headers=auth_headers, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req_dispatch_bad)
            self.assertEqual(cm.exception.code, 400)

            # 5. Test POST /api/shutdown
            url_shutdown = f"http://127.0.0.1:{sup.port}/api/shutdown"
            req_shutdown = urllib.request.Request(url_shutdown, data=b"{}", headers=auth_headers, method="POST")
            with urllib.request.urlopen(req_shutdown) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body["status"], "shutting_down")
                self.assertIn("summary", body)
                self.assertEqual(body["summary"]["services_stopped"], 0)

        finally:
            sup.stop()

        self.assertFalse(os.path.exists(sup.state_file))
        self.mark_passed()

    def test_worker_module_cache(self):
        """Verify WarmWorker.execute_task reuses dispatcher _MODULE_CACHE across calls."""
        from core.commands.dispatcher import _MODULE_CACHE

        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)

        # Create a dummy module with execution counter
        mod_dir = os.path.join(self.root_dir, ".modules", "test_cache", "scripts")
        cli_path = os.path.normpath(os.path.join(mod_dir, "cli.py"))
        os.makedirs(mod_dir, exist_ok=True)
        with open(cli_path, "w", encoding="utf-8") as f:
            f.write(
                "EXEC_COUNT = 0\n"
                "def help(cmd_bags):\n"
                "    global EXEC_COUNT\n"
                "    EXEC_COUNT += 1\n"
                "    return EXEC_COUNT\n"
            )

        # First call: loads module into dispatcher _MODULE_CACHE
        res1 = worker.execute_task("test_cache", [], cwd=self.root_dir)
        self.assertEqual(res1, 1)
        self.assertIn(cli_path, _MODULE_CACHE)

        # Second call: reuses cached module, EXEC_COUNT increments in memory
        res2 = worker.execute_task("test_cache", [], cwd=self.root_dir)
        self.assertEqual(res2, 2)
        self.mark_passed()

    def test_watcher_reload_dispatch_worker(self):
        """Non-server module change dispatches to restart_worker."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "restart_worker") as mock_worker, \
             unittest.mock.patch.object(sup, "restart_server") as mock_server:
            sup.on_modules_changed({"knowledge-db", "dev"})
            mock_worker.assert_called_once()
            mock_server.assert_not_called()
        self.mark_passed()

    def test_watcher_reload_dispatch_server(self):
        """server or core module change dispatches to restart_server."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "restart_worker") as mock_worker, \
             unittest.mock.patch.object(sup, "restart_server") as mock_server:
            sup.on_modules_changed({"server"})
            mock_server.assert_called_once()
            mock_worker.assert_not_called()

        with unittest.mock.patch.object(sup, "restart_worker") as mock_worker, \
             unittest.mock.patch.object(sup, "restart_server") as mock_server:
            sup.on_modules_changed({"core", "knowledge-db"})
            mock_server.assert_called_once()
            mock_worker.assert_not_called()
        self.mark_passed()

    def test_watcher_observability_status_payload(self):
        """MasterSupervisor get_status_dict includes ModulesWatcher observability."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=True)
        try:
            modules_dir = os.path.join(self.root_dir, ".modules")
            os.makedirs(modules_dir, exist_ok=True)
            sup.watcher = ModulesWatcher(modules_dir, on_change_callback=lambda x: None)
            sup.watcher.start()

            status = sup.get_status_dict()
            watcher_status = status["watcher"]
            self.assertTrue(watcher_status["enabled"])
            self.assertTrue(watcher_status["active"])
            self.assertEqual(watcher_status["monitored_dir"], os.path.abspath(modules_dir))
        finally:
            if sup.watcher:
                sup.watcher.stop()

        # Watcher disabled case
        sup_disabled = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        status_disabled = sup_disabled.get_status_dict()
        watcher_disabled = status_disabled["watcher"]
        self.assertFalse(watcher_disabled["enabled"])
        self.assertFalse(watcher_disabled["active"])
        self.assertIsNone(watcher_disabled["monitored_dir"])
        self.mark_passed()

    def test_format_startup_banner_and_shutdown_summary(self):
        """Verify startup banner and shutdown summary formatting functions."""
        from server.master import format_startup_banner, format_shutdown_summary

        mock_info = {
            "pid": 9991,
            "worker_pid": 9992,
            "port": 54321,
            "root": "/mock/workspace",
            "state": "ready",
            "idle_seconds_left": 800.0,
            "idle_timeout_sec": 900.0,
            "log_file": "/mock/workspace/.cache/server/log",
            "services": [{"name": "search-sync", "provider": "knowledge-db", "alive": True}],
            "watcher": {"enabled": True, "active": True, "monitored_dir": "/mock/workspace/.modules"},
        }
        banner = format_startup_banner(mock_info)
        self.assertIn("[Server] Daemon successfully started!", banner)
        self.assertIn("Master PID      : 9991", banner)
        self.assertIn("Worker PID      : 9992 (State: READY)", banner)
        self.assertIn("Listening Port  : 54321", banner)
        self.assertIn("Workspace Root  : /mock/workspace", banner)
        self.assertIn("Idle Timeout    : 900.0s", banner)
        self.assertIn("Modules Watcher : ACTIVE", banner)
        self.assertIn("Background Svcs : 1 registered (search-sync)", banner)
        self.assertIn("Real-time Log   : /mock/workspace/.cache/server/log", banner)

        mock_summary = {
            "pid": 9991,
            "worker_pid": 9992,
            "uptime_seconds": 125.4,
            "tasks_executed": 7,
            "services_stopped": 1,
            "reason": "Graceful CLI shutdown request",
            "archive_log": "/mock/workspace/.cache/server/2026_10_14_14.00.00_log",
        }
        summary_txt = format_shutdown_summary(mock_summary)
        self.assertIn("[Server] Daemon stopped gracefully.", summary_txt)
        self.assertIn("Total Uptime    : 2m 5.4s (125.4s)", summary_txt)
        self.assertIn("Tasks Handled   : 7 tasks executed", summary_txt)
        self.assertIn("Services Stopped: 1 background services terminated", summary_txt)
        self.assertIn("Shutdown Reason : Graceful CLI shutdown request", summary_txt)
        self.assertIn("Archived Log    : /mock/workspace/.cache/server/2026_10_14_14.00.00_log", summary_txt)
        self.mark_passed()

    def test_status_and_shutdown_api_payloads(self):
        """Verify MasterSupervisor get_status_dict and shutdown summary enrichment."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=True)
        status_dict = sup.get_status_dict()
        self.assertIn("start_time", status_dict)
        self.assertIn("uptime_seconds", status_dict)
        self.assertIn("log_file", status_dict)
        self.assertGreaterEqual(status_dict["uptime_seconds"], 0.0)
        self.mark_passed()

    def test_service_manager_load_from_contributes_and_auto_start(self):
        """load_from_contributes handles hyphenated module names, colon and dotted URIs, injects sys.path, and respects auto_start."""
        from core import contributes
        from unittest.mock import patch

        mod_dir = os.path.join(self.root_dir, ".modules", "mock-kdb-service")
        pkg_dir = os.path.join(mod_dir, "mock_kdb_service")
        os.makedirs(pkg_dir, exist_ok=True)
        worker_code = (
            "from server.service import BaseServiceWorker\n"
            "class DummyWorker(BaseServiceWorker):\n"
            "    def __init__(self):\n"
            "        self.started = False\n"
            "        self.stopped = False\n"
            "    @property\n"
            "    def name(self):\n"
            "        return 'dummy-worker'\n"
            "    def start(self, ctx):\n"
            "        self.started = True\n"
            "    def stop(self):\n"
            "        self.stopped = True\n"
            "    def health_check(self):\n"
            "        return self.started and not self.stopped\n"
            "class BrokenInitWorker(BaseServiceWorker):\n"
            "    def __init__(self):\n"
            "        raise RuntimeError('cannot instantiate')\n"
            "    @property\n"
            "    def name(self):\n"
            "        return 'broken'\n"
            "    def start(self, ctx): pass\n"
            "    def stop(self): pass\n"
            "    def health_check(self): return False\n"
        )
        with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(pkg_dir, "worker.py"), "w", encoding="utf-8") as f:
            f.write(worker_code)

        mock_contrib = [
            {
                "_provider": "mock-kdb-service",
                "name": "auto-dummy",
                "worker_class": "code.class://mock-kdb-service/mock_kdb_service.worker.DummyWorker",
                "description": "Auto start service",
                "auto_start": True,
            },
            {
                "_provider": "mock-kdb-service",
                "name": "manual-dummy",
                "worker_class": "code.class://mock-kdb-service/mock_kdb_service.worker:DummyWorker",
                "description": "Manual start service via colon URI",
                "auto_start": False,
            },
            {
                "_provider": "mock-kdb-service",
                "name": "broken-init",
                "worker_class": "code.class://mock-kdb-service/mock_kdb_service.worker:BrokenInitWorker",
                "description": "Broken init service isolated from healthy services",
                "auto_start": True,
            },
        ]

        mgr = ServiceManager()
        try:
            with patch.object(contributes, "get", return_value=mock_contrib), \
                 patch("server.service.log_error"):
                mgr.load_from_contributes(yscb_root=self.root_dir)

            # Ensure .modules/mock-kdb-service was injected into sys.path
            self.assertIn(os.path.abspath(mod_dir), [os.path.abspath(p) for p in sys.path])

            # Verify invalid URI without ':' or '.' returns None safely
            self.assertIsNone(_load_service_class_from_uri("InvalidUriWithoutSeparator"))

            status = mgr.get_status()
            self.assertEqual(len(status), 2)
            names = [s["name"] for s in status]
            self.assertIn("auto-dummy", names)
            self.assertIn("manual-dummy", names)

            # start_all respects auto_start
            mgr.start_all({})
            status_after = {s["name"]: s["alive"] for s in mgr.get_status()}
            self.assertTrue(status_after["auto-dummy"])
            self.assertFalse(status_after["manual-dummy"])

            mgr.stop_all()
            status_stop = {s["name"]: s["alive"] for s in mgr.get_status()}
            self.assertFalse(status_stop["auto-dummy"])
            self.assertFalse(status_stop["manual-dummy"])
        finally:
            if mod_dir in sys.path:
                sys.path.remove(mod_dir)
            if os.path.abspath(mod_dir) in sys.path:
                sys.path.remove(os.path.abspath(mod_dir))
            for mod_key in [
                k for k in list(sys.modules.keys())
                if k == "mock_kdb_service" or k.startswith("mock_kdb_service.")
            ]:
                sys.modules.pop(mod_key, None)
        self.mark_passed()

    def test_worker_main_ipc_isolation_and_exit_handshake(self):
        """worker_main isolates IPC stdout packets, routes background core.log via _WorkerIPCLinkSink, recovers from bad JSON lines, and handles exit."""
        from core.log import log_info
        from server.worker import worker_main

        in_stream = io.BytesIO()
        in_stream.write(b"{corrupted_json_line\n")
        in_stream.write(json.dumps({"action": "exit"}).encode("utf-8") + b"\n")
        in_stream.seek(0)

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        fake_stderr = io.StringIO()
        raw_ipc_out = io.BytesIO()
        fake_raw_stdout = io.TextIOWrapper(raw_ipc_out, encoding="utf-8")
        sys.stdout = fake_raw_stdout
        sys.stderr = fake_stderr

        try:
            with unittest.mock.patch.object(
                WarmWorker,
                "pre_warm",
                side_effect=lambda: log_info("BACKGROUND STRUCTURED LOGGING"),
            ):
                worker_main(yscb_root=self.root_dir, in_stream=in_stream, out_stream=fake_raw_stdout)

            fake_raw_stdout.flush()
            raw_ipc_out.seek(0)
            ipc_lines = [line.strip() for line in raw_ipc_out if line.strip()]

            # Verify valid JSON packets from IPC (worker_alive, worker_ready, task_finish)
            parsed_packets = []
            for line in ipc_lines:
                txt = line.decode("utf-8")
                if txt.startswith("{"):
                    pkt = json.loads(txt)
                    self.assertIn("type", pkt)
                    parsed_packets.append(pkt)

            pkt_types = [p["type"] for p in parsed_packets]
            self.assertIn("worker_alive", pkt_types)
            self.assertIn("worker_ready", pkt_types)
            self.assertLess(pkt_types.index("worker_alive"), pkt_types.index("worker_ready"))

            # Malformed JSON line must emit a failing task_finish packet and continue to exit cleanly
            finish_pkts = [p for p in parsed_packets if p["type"] == "task_finish"]
            self.assertEqual(len(finish_pkts), 1)
            self.assertEqual(finish_pkts[0]["exit_code"], 1)
            self.assertTrue(bool(finish_pkts[0].get("error")))
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

        self.mark_passed()

    def test_master_supervisor_start_time_persistence(self):
        """MasterSupervisor preserves start_time and updates worker_pid on disk across restart_worker."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        initial_start_time = 1700000000.0
        sup._start_time = initial_start_time

        def _fake_spawn():
            sup._worker_proc = unittest.mock.MagicMock(pid=12345, poll=lambda: None)
            return 12345

        with unittest.mock.patch.object(sup, "_kill_worker_locked"), \
             unittest.mock.patch.object(sup, "_spawn_worker_locked", side_effect=_fake_spawn):
            sup.restart_worker()

        self.assertEqual(sup._start_time, initial_start_time)
        persisted = read_daemon_state(self.root_dir)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.start_time, initial_start_time)
        self.assertEqual(persisted.worker_pid, 12345)
        self.mark_passed()

    def test_worker_and_master_zero_source_path_injection(self):
        """Worker and Master supervisor execution paths contain zero source/ in sys.path or env."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        captured_env = {}

        def mock_popen(cmd, **kwargs):
            nonlocal captured_env
            captured_env = kwargs.get("env", {})
            fake_proc = unittest.mock.MagicMock()
            fake_proc.pid = 77777
            fake_proc.poll.return_value = None
            fake_proc.stdout.readline.return_value = b'{"type": "worker_ready", "services": []}\n'
            fake_proc.stderr = io.BytesIO()
            return fake_proc

        with unittest.mock.patch("subprocess.Popen", side_effect=mock_popen):
            ret_pid = sup._spawn_worker_locked()
            self.assertEqual(ret_pid, 77777)

        # Verify handshake failure (EOF before worker_alive) cleans up worker and raises WorkerSpawnError
        def mock_popen_unready(cmd, **kwargs):
            fake_proc = unittest.mock.MagicMock()
            fake_proc.pid = 77778
            fake_proc.poll.return_value = 1
            fake_proc.stdout.readline.return_value = b""
            fake_proc.stderr = io.BytesIO()
            return fake_proc

        with unittest.mock.patch("subprocess.Popen", side_effect=mock_popen_unready):
            with self.assertRaises(WorkerSpawnError):
                sup._spawn_worker_locked()
            self.assertIsNone(sup._worker_proc)

        # Real assertion on the PYTHONPATH actually passed by _spawn_worker_locked to subprocess
        self.assertIn("PYTHONPATH", captured_env)
        pythonpath_entries = captured_env["PYTHONPATH"].split(os.pathsep)
        for entry in pythonpath_entries:
            norm_entry = entry.replace("\\", "/")
            self.assertFalse(
                "/source/" in norm_entry or norm_entry.endswith("/source"),
                f"Illegal source/ path found in worker PYTHONPATH: {entry}",
            )

        # Verify WarmWorker sys.path initialization does not inject source/
        WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
        for p in sys.path:
            norm_p = p.replace("\\", "/")
            self.assertFalse(f"{self.root_dir}/source" in norm_p)
        self.mark_passed()

    def test_master_two_stage_kill_fallback(self):
        """MasterSupervisor _kill_worker_locked sends exit, falls back to terminate_popen_tree on timeout, and resets _worker_services."""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        mock_proc = unittest.mock.MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None  # Process doesn't exit on its own
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="worker", timeout=1.5)
        mock_proc.stdin = unittest.mock.MagicMock()
        sup._worker_proc = mock_proc
        sup._worker_services = [{"name": "stale-svc", "provider": "kdb", "alive": True}]

        with unittest.mock.patch("server.master.terminate_popen_tree", return_value=True) as mock_kill, \
             unittest.mock.patch("time.sleep"):
            sup._kill_worker_locked(timeout_sec=1.5)

            # Verify Stage 1 sent exit NDJSON
            mock_proc.stdin.write.assert_called_with(b'{"action": "exit"}\n')
            mock_proc.stdin.flush.assert_called()

            # Verify Stage 2 fallback to terminate_popen_tree (Popen-owned reaping)
            mock_kill.assert_called_once_with(mock_proc, timeout_sec=1.5)
            self.assertIsNone(sup._worker_proc)
            self.assertEqual(sup._worker_services, [])
            self.assertEqual(sup.get_status_dict()["services"], [])

        self.mark_passed()

    def test_prewarm_load_order_and_master_stop_idempotency(self):
        """Verify WarmWorker loads service contributes before broadcasting warming event, and MasterSupervisor.stop is idempotent."""
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
        call_order = []

        def fake_load(root):
            call_order.append("load_from_contributes")

        def fake_broadcast(evt_name, *args, **kwargs):
            call_order.append(f"broadcast:{evt_name}")

        def fake_start_all(ctx):
            call_order.append("start_all")

        with unittest.mock.patch.object(worker.service_manager, "load_from_contributes", side_effect=fake_load), \
             unittest.mock.patch.object(events, "broadcast", side_effect=fake_broadcast), \
             unittest.mock.patch.object(worker.service_manager, "start_all", side_effect=fake_start_all):
            worker.pre_warm()

        self.assertIn("load_from_contributes", call_order)
        self.assertIn("broadcast:server_worker_warming", call_order)
        self.assertLess(
            call_order.index("load_from_contributes"),
            call_order.index("broadcast:server_worker_warming"),
        )

        # Verify MasterSupervisor.stop() idempotency when called twice
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        sup._is_running = True
        with unittest.mock.patch.object(sup.logger, "archive_and_close") as mock_archive:
            sup.stop()
            sup.stop()
            self.assertEqual(mock_archive.call_count, 1)

        self.mark_passed()

    def test_master_start_lock_contention_never_falls_through(self):
        """Verify MasterSupervisor.start() immediately exits without spawning HTTP/Worker when daemon.lock is held, even if daemon.json is missing."""
        from core.platform import InterProcessLock

        lock_path = os.path.join(self.root_dir, ".cache", "server", "daemon.lock")
        held_lock = InterProcessLock(lock_path)
        self.assertTrue(held_lock.acquire(blocking=False))
        try:
            # Ensure daemon.json does NOT exist (simulating startup race window)
            state_path = os.path.join(self.root_dir, ".cache", "server", "daemon.json")
            if os.path.exists(state_path):
                os.remove(state_path)

            sup2 = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
            with unittest.mock.patch.object(sup2, "_spawn_worker_locked") as mock_spawn, \
                 unittest.mock.patch("server.master._create_http_server") as mock_http:
                ret_pid = sup2.start(foreground=False)
                self.assertEqual(ret_pid, 0)
                mock_spawn.assert_not_called()
                mock_http.assert_not_called()
                self.assertFalse(sup2._is_running)
        finally:
            held_lock.release()

        # Verify startup failure after lock acquisition triggers self.stop() and releases lock
        sup3 = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch("server.master._create_http_server", side_effect=RuntimeError("bind failed")):
            with self.assertRaises(RuntimeError):
                sup3.start(foreground=False)
        self.assertTrue(sup3._is_stopped)
        self.assertIsNone(sup3._lock)

        self.mark_passed()

    def test_master_restart_server_reentrancy_guard_and_watcher_transaction_lock(self):
        """Verify restart_server() only spawns once under concurrent calls, foreground loop joins _restart_thread when restarting, and ModulesWatcher defers polling while .yscb.lock is held or .modules/core lacks manifest.json."""
        from core.platform import InterProcessLock

        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        spawn_calls = []
        exit_called = threading.Event()

        with unittest.mock.patch.object(sup, "stop"), \
             unittest.mock.patch("server.master.spawn_detached", side_effect=lambda cmd, **kw: spawn_calls.append(cmd) or 12345), \
             unittest.mock.patch("os._exit", side_effect=lambda code: exit_called.set()):
            sup.restart_server()
            sup.restart_server()
            sup.restart_server()
            self.assertTrue(exit_called.wait(timeout=2.0))
            if sup._restart_thread is not None:
                sup._restart_thread.join(timeout=2.0)

        self.assertEqual(len(spawn_calls), 1)
        self.assertIsNotNone(sup._restart_thread)

        # Verify foreground _run_supervisor_main_loop joins _restart_thread instead of calling stop() when _restarting is True
        fg_sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        fg_sup._httpd = unittest.mock.MagicMock()
        mock_restart_th = unittest.mock.MagicMock()
        fg_sup._restarting = True
        fg_sup._restart_thread = mock_restart_th
        with unittest.mock.patch.object(fg_sup, "stop") as mock_fg_stop, redirect_stdout(io.StringIO()):
            fg_sup._run_supervisor_main_loop(foreground=True)
            mock_fg_stop.assert_not_called()
            mock_restart_th.join.assert_called_once_with(timeout=5.0)

        # Verify ModulesWatcher._is_core_transaction_locked() detects held .yscb.lock
        modules_dir = os.path.join(self.root_dir, ".modules")
        os.makedirs(modules_dir, exist_ok=True)
        watcher = ModulesWatcher(modules_dir, on_change_callback=lambda *a: None)
        self.assertFalse(watcher._is_core_transaction_locked())

        core_lock_path = os.path.join(self.root_dir, ".cache", ".yscb.lock")
        core_lock = InterProcessLock(core_lock_path)
        self.assertTrue(core_lock.acquire(blocking=False))
        try:
            self.assertTrue(watcher._is_core_transaction_locked())
        finally:
            core_lock.release()
        self.assertFalse(watcher._is_core_transaction_locked())

        # Verify .modules/core directory without manifest.json is treated as transaction-locked
        core_mod_dir = os.path.join(modules_dir, "core")
        os.makedirs(core_mod_dir, exist_ok=True)
        self.assertTrue(watcher._is_core_transaction_locked())
        with open(os.path.join(core_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "core", "version": "1.0.0.0"}')
        self.assertFalse(watcher._is_core_transaction_locked())

        self.mark_passed()

    def test_daemon_state_roundtrip_and_stop_lock_protection(self):
        """Verify read_daemon_state round-trip via vfs.read_json and cli.stop preserving daemon.json when daemon.lock is held."""
        from core.commands.bags import CmdBags
        from core.platform import InterProcessLock
        from core import vfs

        server_cli = _load_server_cli()
        empty_bags = CmdBags()

        # 1. Missing daemon.json returns None without error
        self.assertIsNone(read_daemon_state(self.root_dir))

        # 2. Valid daemon.json round-trips accurately
        state_file = os.path.join(self.root_dir, ".cache", "server", "daemon.json")
        sample_state = {
            "pid": os.getpid(),
            "worker_pid": os.getpid(),
            "port": 59999,
            "token": "tok_test_123",
            "root": self.root_dir,
            "start_time": 1700000000.0,
            "idle_timeout_sec": 300.0,
            "tasks_executed": 2,
        }
        vfs.write_json(state_file, sample_state)
        loaded = read_daemon_state(self.root_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.pid, os.getpid())
        self.assertEqual(loaded.port, 59999)
        self.assertEqual(loaded.token, "tok_test_123")
        self.assertEqual(loaded.tasks_executed, 2)

        # 3. Corrupted daemon.json while daemon.lock is held: cli.stop() must NOT delete daemon.json
        vfs.write_text(state_file, "{corrupted_json")
        self.assertIsNone(read_daemon_state(self.root_dir))

        lock_file = os.path.join(self.root_dir, ".cache", "server", "daemon.lock")
        held_lock = InterProcessLock(lock_file)
        self.assertTrue(held_lock.acquire(blocking=False))
        try:
            with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
                 unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
                 redirect_stdout(io.StringIO()):
                rc = server_cli.stop(empty_bags)
                self.assertEqual(rc, 0)
                self.assertTrue(os.path.exists(state_file), "daemon.json must NOT be deleted when daemon.lock is held")
        finally:
            held_lock.release()

        # 4. When daemon.lock is NOT held and daemon is dead, stale daemon.json is cleaned up
        with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
             unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
             redirect_stdout(io.StringIO()):
            rc2 = server_cli.stop(empty_bags)
            self.assertEqual(rc2, 0)
            self.assertFalse(os.path.exists(state_file), "Stale daemon.json should be cleaned up when lock is free")

        self.mark_passed()

    def test_spawn_detached_master_quote_safe_args_and_restart_worker_lock_order(self):
        """Verify spawn_detached_master quote safety; restart_worker kills without _dispatch_lock, then spawns under it."""
        from server import master as master_mod

        captured_cmd = []
        with unittest.mock.patch.object(master_mod, "spawn_detached", side_effect=lambda cmd, cwd=None: captured_cmd.extend(cmd) or 12345):
            quoted_root = os.path.join(self.root_dir, "O'Connor's Workspace")
            pid = master_mod.spawn_detached_master(quoted_root, idle_timeout_sec=120.0, enable_watcher=False)
            self.assertEqual(pid, 12345)
            self.assertGreaterEqual(len(captured_cmd), 8)
            self.assertNotIn("O'Connor", captured_cmd[2])
            self.assertTrue(captured_cmd[5].endswith("O'Connor's Workspace"))
            self.assertEqual(captured_cmd[6], "120.0")
            self.assertEqual(captured_cmd[7], "0")

        sup = self._make_supervisor(yscb_root=self.root_dir, idle_timeout_sec=60.0, enable_watcher=False)
        dispatch_held_during_kill = []
        dispatch_held_during_spawn = []

        def _fake_spawn():
            dispatch_held_during_spawn.append(sup._dispatch_lock.locked())
            return 9999

        with unittest.mock.patch.object(
            sup, "_kill_worker_locked", side_effect=lambda timeout_sec=1.5: dispatch_held_during_kill.append(sup._dispatch_lock.locked())
        ), unittest.mock.patch.object(sup, "_spawn_worker_locked", side_effect=_fake_spawn), \
             unittest.mock.patch.object(sup, "_write_state"):
            new_pid = sup.restart_worker()
            self.assertEqual(new_pid, 9999)
            self.assertEqual(dispatch_held_during_kill, [False])
            self.assertEqual(dispatch_held_during_spawn, [True])

        self.mark_passed()

    def _write_fake_worker(self, body: str) -> str:
        path = os.path.join(self.root_dir, "fake_worker.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("import json, os, sys, time\n")
            f.write("def emit(p):\n    sys.stdout.write(json.dumps(p) + '\\n'); sys.stdout.flush()\n")
            f.write(body)
        return path

    def _spawn_fake_worker(self, sup: MasterSupervisor, script: str) -> int:
        real_popen = subprocess.Popen

        def popen_fake(cmd, **kwargs):
            return real_popen([sys.executable, script], **kwargs)

        with unittest.mock.patch("server.master.subprocess.Popen", side_effect=popen_fake):
            with sup._worker_lock:
                return sup._spawn_worker_locked()

    def test_worker_main_emits_alive_before_ready(self):
        """worker_main 於 pre_warm 前送出 worker_alive，之後才送 worker_ready。"""
        out = io.StringIO()
        with unittest.mock.patch.object(WarmWorker, "pre_warm"):
            from server.worker import worker_main
            worker_main(self.root_dir, in_stream=io.StringIO('{"action": "exit"}\n'), out_stream=out)
        types = [json.loads(line)["type"] for line in out.getvalue().splitlines() if line.strip()]
        self.assertGreaterEqual(len(types), 2)
        self.assertEqual(types[0], "worker_alive")
        self.assertIn("worker_ready", types)
        self.assertLess(types.index("worker_alive"), types.index("worker_ready"))
        self.mark_passed()

    def test_two_stage_handshake_warming_then_ready(self):
        """alive 後狀態 warming（含 warming_elapsed_sec），ready 後轉 ready；dispatch 於 warming 期間等待 ready。"""
        script = self._write_fake_worker(
            "emit({'type': 'worker_alive'})\n"
            "time.sleep(1.0)\n"
            "emit({'type': 'worker_ready', 'services': []})\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    if req.get('action') == 'exit':\n        break\n"
            "    emit({'type': 'task_finish', 'exit_code': 7, 'duration_ms': 1.0})\n"
        )
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        try:
            pid = self._spawn_fake_worker(sup, script)
            self.assertGreater(pid, 0)
            status = sup.get_status_dict()
            self.assertEqual(status["state"], "warming")
            self.assertIn("warming_elapsed_sec", status)
            self.assertIsNone(status["current_task"])

            packets = []
            with unittest.mock.patch.object(sup, "_write_state"):
                rc = sup.dispatch_task({"module": "dummy", "args": ["x"]}, packets.append)
            self.assertEqual(rc, 7)
            self.assertEqual(packets[-1]["type"], "task_finish")
            ready_status = sup.get_status_dict()
            self.assertEqual(ready_status["state"], "ready")
            self.assertNotIn("warming_elapsed_sec", ready_status)
        finally:
            with sup._worker_lock:
                sup._kill_worker_locked(timeout_sec=1.0)
        self.mark_passed()

    def test_alive_timeout_and_death_during_warming(self):
        """未送 alive 即逾時拋 WorkerSpawnError；warming 中死亡時等待之 dispatch 回傳 1。"""
        silent = self._write_fake_worker("time.sleep(30)\n")
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        sup._worker_alive_timeout_sec = 0.5
        t0 = time.time()
        with self.assertRaises(WorkerSpawnError) as ctx:
            self._spawn_fake_worker(sup, silent)
        self.assertIn("worker_alive", str(ctx.exception))
        self.assertLess(time.time() - t0, 5.0)
        self.assertIsNone(sup._worker_proc)

        dying = self._write_fake_worker("emit({'type': 'worker_alive'})\ntime.sleep(0.5)\nsys.exit(3)\n")
        sup._worker_alive_timeout_sec = 5.0
        self._spawn_fake_worker(sup, dying)
        try:
            packets = []
            rc = sup.dispatch_task({"module": "dummy", "args": []}, packets.append)
            self.assertEqual(rc, 1)
            self.assertEqual(packets[-1]["error"], "Worker exited before becoming ready")
        finally:
            with sup._worker_lock:
                sup._kill_worker_locked(timeout_sec=1.0)

        # Respawn failure inside dispatch is reported, not masked as PID 0
        with unittest.mock.patch.object(sup, "_spawn_worker_locked", side_effect=WorkerSpawnError("boom")):
            packets2 = []
            rc2 = sup.dispatch_task({"module": "dummy", "args": []}, packets2.append)
        self.assertEqual(rc2, 1)
        self.assertEqual(packets2[-1], {"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": "boom"})
        self.mark_passed()

    def test_restart_worker_preempts_stuck_dispatch(self):
        """卡住之 dispatch 期間 status 回報 current_task；restart_worker 搶占後 dispatch 回傳 1 並於時限內完成重啟。"""
        stuck = self._write_fake_worker(
            "emit({'type': 'worker_alive'})\n"
            "emit({'type': 'worker_ready', 'services': []})\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    if req.get('action') == 'exit':\n        break\n"
            "    if 'hang' in req.get('args', []):\n        time.sleep(60)\n"
            "    emit({'type': 'task_finish', 'exit_code': 0, 'duration_ms': 1.0})\n"
        )
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        real_popen = subprocess.Popen
        with unittest.mock.patch("server.master.subprocess.Popen", side_effect=lambda cmd, **kw: real_popen([sys.executable, stuck], **kw)), \
             unittest.mock.patch.object(sup, "_write_state"):
            try:
                with sup._worker_lock:
                    old_pid = sup._spawn_worker_locked()
                self.assertTrue(sup._wait_worker_ready(timeout_sec=5.0))
                result = {}
                packets = []

                def _run():
                    result["rc"] = sup.dispatch_task({"module": "dummy", "args": ["hang"]}, packets.append)

                th = threading.Thread(target=_run, daemon=True)
                th.start()
                deadline = time.time() + 5.0
                while sup.get_status_dict()["current_task"] is None and time.time() < deadline:
                    time.sleep(0.05)
                task = sup.get_status_dict()["current_task"]
                self.assertIsNotNone(task)
                self.assertEqual(task["module"], "dummy")
                self.assertEqual(task["args"], ["hang"])
                self.assertGreaterEqual(task["elapsed_sec"], 0.0)

                t0 = time.time()
                new_pid = sup.restart_worker()
                self.assertLess(time.time() - t0, 1.5 + 5.0)
                th.join(timeout=5.0)
                self.assertFalse(th.is_alive())
                self.assertEqual(result["rc"], 1)
                self.assertEqual(packets[-1]["error"], "Worker terminated by restart/stop")
                self.assertNotEqual(new_pid, old_pid)
                self.assertIsNone(sup.get_status_dict()["current_task"])

                # Fresh worker serves the next request normally
                packets_ok = []
                self.assertEqual(sup.dispatch_task({"module": "dummy", "args": []}, packets_ok.append), 0)
            finally:
                with sup._worker_lock:
                    sup._kill_worker_locked(timeout_sec=1.0)
        self.mark_passed()

    def test_restart_worker_spawn_failure_raises_and_reload_returns_500(self):
        """Error contract: restart_worker 不再以 PID 0 冒充成功，改拋 WorkerSpawnError；/api/reload 轉 HTTP 500。"""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "_spawn_worker_locked", side_effect=WorkerSpawnError("no alive")), \
             unittest.mock.patch.object(sup, "_write_state") as mock_write:
            with self.assertRaises(WorkerSpawnError):
                sup.restart_worker()
            mock_write.assert_not_called()

        with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
            sup.start(foreground=False)
        try:
            auth_headers = {"Authorization": f"Bearer {sup.token}", "Content-Type": "application/json"}
            req = urllib.request.Request(f"http://127.0.0.1:{sup.port}/api/reload", data=b"{}", headers=auth_headers, method="POST")
            with unittest.mock.patch.object(sup, "restart_worker", side_effect=WorkerSpawnError("no alive")):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 500)
            self.assertIn("no alive", cm.exception.read().decode("utf-8"))
            cm.exception.close()
        finally:
            sup.stop()
        self.mark_passed()

    def test_stop_keeps_lock_file_and_marks_clean_exit(self):
        """stop() 僅移除 daemon.json、保留 daemon.lock 且鎖可再取得，並寫入 clean exit 歸零回收計數。"""
        import json as _json
        from core.platform import InterProcessLock, daemon_probe

        daemon_probe.record_spawn(self.root_dir, 1)
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
            sup.start(foreground=False)
        self.assertTrue(os.path.exists(sup.state_file))
        sup.stop()
        self.assertFalse(os.path.exists(sup.state_file))
        self.assertTrue(os.path.exists(sup.lock_file))
        probe_lock = InterProcessLock(sup.lock_file)
        self.assertTrue(probe_lock.acquire(blocking=False))
        probe_lock.release()
        with open(os.path.join(self.root_dir, daemon_probe.PROBE_REL_PATH), "r", encoding="utf-8") as f:
            entry = _json.load(f)[daemon_probe.env_fingerprint()]
        self.assertTrue(entry["clean_exit"])
        self.assertEqual(entry["reaped_count"], 0)
        self.mark_passed()

    def test_cli_status_dashboard_and_start_readiness_exit_code(self):
        """儀表板顯示 Current Task、預熱秒數與背景服務清單；start -d 依就緒狀態或 spawn PID 存活決定回傳 0/1。"""
        from core.commands.bags import CmdBags, CmdOption

        server_cli = _load_server_cli()

        state = ServerDaemonState(
            pid=1,
            worker_pid=0,
            port=1,
            token="t",
            root=self.root_dir,
            start_time=time.time(),
            idle_timeout_sec=0.0,
        )
        info = {
            "state": "warming",
            "warming_elapsed_sec": 2.5,
            "idle_seconds_left": 0.0,
            "current_task": {"module": "dev", "args": ["test", "core"], "started_at": 0.0, "elapsed_sec": 12.0},
            "services": [{"name": "kdb-sync", "provider": "knowledge-db", "alive": True}],
            "watcher": {"enabled": True, "active": True, "monitored_dir": os.path.join(self.root_dir, ".modules")},
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            server_cli._render_status_dashboard(info, state)
        self.assertIn("WARMING (pre-warming 2.5s)", buf.getvalue())
        self.assertIn("Current Task  : dev test core (running 12.0s)", buf.getvalue())
        self.assertIn("[kdb-sync] (module: knowledge-db) : RUNNING", buf.getvalue())

        idle_buf = io.StringIO()
        with redirect_stdout(idle_buf):
            server_cli._render_status_dashboard(
                dict(info, state="ready", warming_elapsed_sec=None, current_task=None, services=[]),
                state,
            )
        self.assertIn("Current Task  : Idle", idle_buf.getvalue())
        self.assertNotIn("pre-warming", idle_buf.getvalue())

        bags = CmdBags(raw_cmd="start -d", command="start", args=[], options={"daemon": CmdOption(name="daemon", params=True)})
        for alive, expected_rc in ((False, 1), (True, 0)):
            out, err = io.StringIO(), io.StringIO()
            with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
                 unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
                 unittest.mock.patch.object(server_cli, "read_daemon_state", return_value=None), \
                 unittest.mock.patch.object(server_cli, "spawn_detached_master", return_value=424242), \
                 unittest.mock.patch.object(server_cli, "is_process_alive", return_value=alive), \
                 unittest.mock.patch.object(server_cli.time, "sleep"), \
                 redirect_stdout(out), redirect_stderr(err):
                rc = server_cli.start(bags)
            self.assertEqual(rc, expected_rc)
            if alive:
                self.assertIn("still starting up", out.getvalue())
            else:
                self.assertIn("exited before becoming ready", err.getvalue())

        # Verify background daemon start succeeds immediately when read_daemon_state becomes ready during polling
        out_ready = io.StringIO()
        with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
             unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
             unittest.mock.patch.object(server_cli, "read_daemon_state", side_effect=[None, state]), \
             unittest.mock.patch.object(server_cli, "spawn_detached_master", return_value=424242), \
             unittest.mock.patch.object(server_cli, "is_process_alive", return_value=True), \
             unittest.mock.patch.object(server_cli, "_http_request", return_value=info), \
             unittest.mock.patch.object(server_cli.time, "sleep"), \
             redirect_stdout(out_ready):
            self.assertEqual(server_cli.start(bags), 0)
        self.assertIn("Daemon successfully started!", out_ready.getvalue())
        self.mark_passed()

    def test_cli_forced_stop_marks_clean_exit(self):
        """server stop --force 與優雅關閉逾時之強制終止路徑於 kill 後清理孤兒 daemon.json 並寫入 clean exit，不累計回收計數。"""
        import json as _json
        from core.commands.bags import CmdBags, CmdOption
        from core.platform import daemon_probe
        from core import vfs

        server_cli = _load_server_cli()

        state = ServerDaemonState(
            pid=424242,
            worker_pid=0,
            port=1,
            token="t",
            root=self.root_dir,
            start_time=time.time(),
            idle_timeout_sec=0.0,
        )
        force_bags = CmdBags(raw_cmd="stop --force", command="stop", args=[], options={"force": CmdOption(name="force", params=True)})
        graceful_bags = CmdBags(raw_cmd="stop", command="stop", args=[], options={})
        probe_file = os.path.join(self.root_dir, daemon_probe.PROBE_REL_PATH)
        state_file = os.path.join(self.root_dir, ".cache", "server", "daemon.json")
        real_mark = daemon_probe.mark_clean_exit
        for bags in (force_bags, graceful_bags):
            daemon_probe.record_spawn(self.root_dir, 424242)
            vfs.write_json(state_file, {"pid": 424242, "port": 1, "token": "t"})
            active_log = os.path.join(self.root_dir, ".cache", "server", "log")
            vfs.write_text(active_log, 'server start at time "2026_11_06_05.00.00"\n', encoding="utf-8", atomic=True)
            self.assertTrue(os.path.exists(state_file))
            order = []
            out_buf = io.StringIO()
            with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
                 unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
                 unittest.mock.patch.object(server_cli, "read_daemon_state", return_value=state), \
                 unittest.mock.patch.object(server_cli, "is_process_alive", return_value=True), \
                 unittest.mock.patch.object(server_cli, "_http_request", return_value=None), \
                 unittest.mock.patch.object(server_cli, "kill_process_tree", side_effect=lambda *a, **k: order.append("kill")), \
                 unittest.mock.patch.object(server_cli.daemon_probe, "mark_clean_exit", side_effect=lambda root: (order.append("mark"), real_mark(root))), \
                 redirect_stdout(out_buf):
                self.assertEqual(server_cli.stop(bags), 0)
            self.assertEqual(order, ["kill", "mark"])
            self.assertFalse(os.path.exists(state_file), "Forced stop must clean up orphaned daemon.json")
            self.assertFalse(os.path.exists(active_log), "Forced stop must immediately archive active log")
            self.assertRegex(out_buf.getvalue(), r"2026_11_06_05\.00\.00(?:_\d+)?_log")
            with open(probe_file, "r", encoding="utf-8") as f:
                entry = _json.load(f)[daemon_probe.env_fingerprint()]
            self.assertTrue(entry["clean_exit"])
            self.assertEqual(entry["pid"], 0)
            self.assertFalse(daemon_probe.is_reaping_env(self.root_dir, daemon_active=False))
        self.mark_passed()

    def test_master_start_retries_transient_lock_contention(self):
        """無活躍 daemon 時鎖短暫被探針持有，start 以短暫阻塞重試取得鎖而非直接放棄。"""
        from core.platform import InterProcessLock

        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        prober = InterProcessLock(sup.lock_file)
        self.assertTrue(prober.acquire(blocking=False))
        timer = threading.Timer(0.15, prober.release)
        timer.start()
        try:
            with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
                ret = sup.start(foreground=False)
            self.assertEqual(ret, os.getpid())
            self.assertTrue(sup._is_running)
        finally:
            timer.join()
            sup.stop()
        self.assertFalse(prober.is_locked)
        self.mark_passed()

    def test_restart_worker_config_error_is_non_destructive(self):
        """restart_worker 先載入組態；組態載入失敗時於任何破壞性動作前拋出，現役 worker 保留。"""
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch("server.config.ServerConfig.load", side_effect=RuntimeError("bad config")), \
             unittest.mock.patch.object(sup, "_kill_worker_locked") as mock_kill, \
             unittest.mock.patch.object(sup, "_spawn_worker_locked") as mock_spawn:
            with self.assertRaises(RuntimeError):
                sup.restart_worker()
        mock_kill.assert_not_called()
        mock_spawn.assert_not_called()
        self.mark_passed()

    def test_master_start_binds_master_pid(self):
        """MasterSupervisor.start 取得單例鎖後將 auto-spawn 紀錄之 launcher PID 改綁為 master PID。"""
        import json as _json
        from core.platform import daemon_probe

        daemon_probe.record_spawn(self.root_dir, 111)
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        try:
            with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
                sup.start(foreground=False)
            with open(os.path.join(self.root_dir, daemon_probe.PROBE_REL_PATH), "r", encoding="utf-8") as f:
                entry = _json.load(f)[daemon_probe.env_fingerprint()]
            self.assertEqual(entry["pid"], os.getpid())
            self.assertFalse(entry["clean_exit"])
        finally:
            sup.stop()
        self.mark_passed()

    def test_worker_restore_env_diff_without_clearing_os_environ(self):
        """WarmWorker.execute_task isolates virtual_cwd and env overrides via bind_runtime_context without mutating os.getcwd() or os.environ, and background ServiceWorker logs never pollute foreground streamer."""
        baseline_key = "YSCB_TEST_BASELINE_CONTINUOUS_KEY"
        modified_key = "YSCB_TEST_MODIFIED_KEY"
        os.environ[baseline_key] = "always_present"
        os.environ[modified_key] = "orig_val"

        observed_mutations = []
        stop_bg = threading.Event()
        orig_cwd = os.getcwd()

        def bg_env_observer():
            while not stop_bg.is_set():
                if (
                    os.environ.get(baseline_key) != "always_present"
                    or os.environ.get(modified_key) != "orig_val"
                    or "PATH" not in os.environ
                    or os.getcwd() != orig_cwd
                ):
                    observed_mutations.append(True)
                time.sleep(0.0005)

        bg_thread = threading.Thread(target=bg_env_observer, daemon=True)
        bg_thread.start()
        try:
            packets = []
            worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=packets.append)
            sub_cwd = os.path.join(self.root_dir, "virtual_subdir")
            os.makedirs(sub_cwd, exist_ok=True)
            mod_dir = os.path.join(self.root_dir, ".modules", "mock_env_diff", "scripts")
            os.makedirs(mod_dir, exist_ok=True)
            with open(os.path.join(mod_dir, "cli.py"), "w", encoding="utf-8") as f:
                f.write(
                    "import os\n"
                    "from core.context import get_env, get_virtual_cwd\n"
                    "from core.log import log\n"
                    "def help(cmd_bags):\n"
                    f"    val = get_env('{modified_key}')\n"
                    "    vcwd = get_virtual_cwd()\n"
                    "    log(f'VCWD={vcwd}|ENV={val}')\n"
                    "    return 0\n"
                )

            # Register a background ServiceWorker that logs continuously via core.log
            class NoisyBgWorker(BaseServiceWorker):
                def __init__(self) -> None:
                    self._stop = threading.Event()
                    self._th = None

                @property
                def name(self) -> str:
                    return "noisy-bg-svc"

                def start(self, context) -> None:
                    self._stop.clear()
                    self.set_state(self.STATE_READY)
                    self._th = self.start_managed_thread(self._loop, context=context)

                def _loop(self) -> None:
                    from core.log import log_info
                    while not self._stop.is_set():
                        log_info("BG_WORKER_NOISE_LINE")
                        time.sleep(0.002)

                def stop(self) -> None:
                    self.stop_managed_thread(self._th, self._stop, timeout=1.0)

                def health_check(self) -> bool:
                    return bool(self._th and self._th.is_alive())

            bg_svc = NoisyBgWorker()
            worker.service_manager.register(bg_svc, provider="test")
            worker.service_manager.start_all({"yscb_root": self.root_dir, "log_sink": worker._ipc_log_sink})
            try:
                for _ in range(5):
                    packets.clear()
                    rc = worker.execute_task(
                        module="mock_env_diff",
                        args=[],
                        cwd=sub_cwd,
                        env={modified_key: "override_val"},
                    )
                    self.assertEqual(rc, 0)
                    self.assertEqual(os.environ.get(baseline_key), "always_present")
                    self.assertEqual(os.environ.get(modified_key), "orig_val")
                    self.assertEqual(os.getcwd(), orig_cwd)
                    stream_text = "".join(
                        p.get("text", "") for p in packets if p.get("type") == "terminal_stream"
                    )
                    self.assertIn(f"VCWD={os.path.normpath(sub_cwd)}|ENV=override_val", stream_text)
                    self.assertNotIn("BG_WORKER_NOISE_LINE", stream_text)
            finally:
                worker.service_manager.stop_all()
                self.assertEqual(bg_svc.state, BaseServiceWorker.STATE_STOPPED)
        finally:
            stop_bg.set()
            bg_thread.join(timeout=1.0)
            for k in (baseline_key, modified_key):
                os.environ.pop(k, None)

        self.assertEqual(
            observed_mutations,
            [],
            "os.environ or os.getcwd() was mutated globally during execute_task!",
        )
        self.mark_passed()

    def test_debounced_streamer_max_buffer_bytes(self):
        """DebouncedIOStreamer 不因單純換行立即 flush，而是於累積達 max_buffer_bytes、計時器觸發或顯式 flush 時送出，並在 stop_capture 後拒絕新寫入。"""
        packets = []
        streamer = DebouncedIOStreamer(
            emit_chunk=lambda pkt: packets.append(pkt),
            debounce_ms=5000,
            max_buffer_bytes=64,
        )
        try:
            streamer.write("stdout", "")
            streamer.write("stdout", "line1\n")
            streamer.write("stdout", "line2\n")
            # Accumulated 12 bytes < 64 bytes -> still buffered despite newlines
            self.assertEqual(len(packets), 0)

            # Writing 60 bytes crosses max_buffer_bytes=64 -> flushes immediately
            streamer.write("stdout", "x" * 60 + "\n")
            self.assertEqual(len(packets), 1)
            self.assertEqual(packets[0]["text"], "line1\nline2\n" + "x" * 60 + "\n")

            # Subsequent short write stays buffered until explicit flush()
            streamer.write("stdout", "tail\n")
            self.assertEqual(len(packets), 1)
            streamer.flush()
            self.assertEqual(len(packets), 2)
            self.assertEqual(packets[1]["text"], "tail\n")
        finally:
            streamer.stop_capture()

        # Verify write after stop_capture() is ignored by _is_closed guard
        streamer.write("stdout", "after_close\n")
        streamer.flush()
        self.assertEqual(len(packets), 2)

        # Verify background _on_timer automatically flushes buffered output within debounce window
        timer_packets = []
        timer_streamer = DebouncedIOStreamer(
            emit_chunk=timer_packets.append,
            debounce_ms=30,
            max_buffer_bytes=4096,
        )
        try:
            timer_streamer.write("stdout", "auto_timer_flush\n")
            deadline = time.monotonic() + 2.0
            while not timer_packets and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(timer_packets), 1)
            self.assertEqual(timer_packets[0]["text"], "auto_timer_flush\n")
        finally:
            timer_streamer.stop_capture()

        self.mark_passed()

    def test_handshake_ignores_non_json_noise_and_sets_utf8_env(self):
        """Verify _read_handshake tolerates non-JSON stdout noise and non-dict JSON values, and _spawn_worker_locked sets PYTHONIOENCODING=utf-8."""
        script = self._write_fake_worker(
            "sys.stdout.write('C-extension startup banner noise\\n')\n"
            "sys.stdout.write('12345\\n')\n"
            "sys.stdout.flush()\n"
            "emit({'type': 'worker_alive'})\n"
            "sys.stdout.write('another non-json line before ready\\n')\n"
            "sys.stdout.flush()\n"
            "emit({'type': 'worker_ready', 'services': []})\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    if req.get('action') == 'exit':\n        break\n"
        )
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        captured_env = {}
        real_popen = subprocess.Popen

        def popen_spy(cmd, **kwargs):
            captured_env.update(kwargs.get("env") or {})
            return real_popen([sys.executable, script], **kwargs)

        with unittest.mock.patch("server.master.subprocess.Popen", side_effect=popen_spy):
            try:
                with sup._worker_lock:
                    pid = sup._spawn_worker_locked()
                self.assertGreater(pid, 0)
                self.assertEqual(captured_env.get("PYTHONIOENCODING"), "utf-8")
                self.assertTrue(sup._wait_worker_ready(timeout_sec=5.0))
                self.assertEqual(sup.get_status_dict()["state"], "ready")
            finally:
                with sup._worker_lock:
                    sup._kill_worker_locked(timeout_sec=1.0)
        self.mark_passed()

    def test_worker_unhandled_exception_streams_stderr_and_finish_error(self):
        """Verify WarmWorker.execute_task flushes unhandled exception to stderr before closing streamer and passes error to task_finish."""
        packets = []
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=packets.append)

        with unittest.mock.patch(
            "core.commands.dispatcher.dispatch_local",
            side_effect=RuntimeError("unexpected worker boom"),
        ):
            rc = worker.execute_task("mock_boom", [], cwd=self.root_dir)
        self.assertEqual(rc, 1)

        stderr_texts = [p.get("text", "") for p in packets if p.get("type") == "terminal_stream" and p.get("stream") == "stderr"]
        self.assertTrue(any("[Server Worker Error] RuntimeError: unexpected worker boom" in t for t in stderr_texts))

        finish_pkts = [p for p in packets if p.get("type") == "task_finish"]
        self.assertEqual(len(finish_pkts), 1)
        self.assertEqual(finish_pkts[0]["exit_code"], 1)
        self.assertIn("RuntimeError: unexpected worker boom", finish_pkts[0].get("error", ""))
        self.mark_passed()

    def test_dispatch_payload_validation_root_normalization_and_touch_throttling(self):
        """Verify /api/dispatch rejects invalid payloads with 400, normalizes yscb_root across relative/parent/symlink paths, and throttles touch_activity."""
        from server.service import touch_activity

        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=0):
            sup.start(foreground=False)

        try:
            auth_headers = {"Authorization": f"Bearer {sup.token}", "Content-Type": "application/json"}
            url_dispatch = f"http://127.0.0.1:{sup.port}/api/dispatch"

            for bad_body in (
                b"[]",
                b'{"args": []}',
                b'{"module": "  "}',
                b'{"module": "core", "args": "not-a-list"}',
                b'{"module": "core", "args": [], "yscb_root": 123}',
            ):
                req_bad = urllib.request.Request(url_dispatch, data=bad_body, headers=auth_headers, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req_bad)
                self.assertEqual(cm.exception.code, 400)
                cm.exception.close()

            def _fake_dispatch_task(req_data, chunk_emitter):
                chunk_emitter({"type": "terminal_stream", "stream": "stdout", "text": "dispatched ok\n"})
                chunk_emitter({"type": "task_finish", "exit_code": 0, "duration_ms": 1.0, "error": None})
                return 0

            # Unconditionally verify 200 OK chunked response with '..' relative path and parent root path
            rel_dotdot_root = os.path.join(self.root_dir, ".cache", "..")
            parent_root = os.path.dirname(self.root_dir)
            with unittest.mock.patch.object(sup, "dispatch_task", side_effect=_fake_dispatch_task) as mock_disp:
                for valid_root in (rel_dotdot_root, parent_root):
                    payload = json.dumps({"module": "core", "args": ["status"], "yscb_root": valid_root}).encode("utf-8")
                    req_ok = urllib.request.Request(url_dispatch, data=payload, headers=auth_headers, method="POST")
                    with urllib.request.urlopen(req_ok) as resp:
                        self.assertEqual(resp.status, 200)
                        raw_chunked = resp.read().decode("utf-8", errors="replace")
                        self.assertIn("dispatched ok", raw_chunked)
                        self.assertIn("task_finish", raw_chunked)
                self.assertEqual(mock_disp.call_count, 2)

            # Symlinked workspace root should also be accepted when filesystem supports symlinks
            link_root = os.path.join(self.root_dir, "symlink_ws")
            has_symlink = False
            try:
                os.symlink(self.root_dir, link_root)
                has_symlink = True
            except OSError:
                has_symlink = False

            if has_symlink:
                with unittest.mock.patch.object(sup, "dispatch_task", side_effect=_fake_dispatch_task) as mock_disp_sym:
                    payload = json.dumps({"module": "core", "args": ["status"], "yscb_root": link_root}).encode("utf-8")
                    req_ok = urllib.request.Request(url_dispatch, data=payload, headers=auth_headers, method="POST")
                    with urllib.request.urlopen(req_ok) as resp:
                        self.assertEqual(resp.status, 200)
                        self.assertIn("task_finish", resp.read().decode("utf-8", errors="replace"))
                    mock_disp_sym.assert_called_once()

            # touch_activity throttling with explicit yscb_root
            self.assertTrue(touch_activity(self.root_dir, force=True))
            with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
                # Within 1.0s debounce window, even with explicit yscb_root, should short-circuit without HTTP call
                self.assertTrue(touch_activity(self.root_dir, force=False))
                mock_urlopen.assert_not_called()
        finally:
            sup.stop()

        self.mark_passed()

    def test_execute_task_isolates_virtual_cwd_and_env_without_os_mutation(self):
        """WarmWorker.execute_task binds virtual_cwd and env via RuntimeContext without mutating os.getcwd/os.environ, and captures get_last_error_hint()."""
        from core.context import get_env, get_virtual_cwd
        from core.log import log_error

        packets = []
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: packets.append(p))
        sub_cwd = os.path.join(self.root_dir, "virtual_sub_cwd")
        os.makedirs(sub_cwd, exist_ok=True)

        orig_os_cwd = os.getcwd()
        observed = {}

        def _fake_dispatch_local(module_name, cmd_name, raw_args, cmd_spec, yscb_abs):
            observed["virtual_cwd"] = get_virtual_cwd()
            observed["os_cwd"] = os.getcwd()
            observed["custom_env"] = get_env("YSCB_TEST_ISOLATED_VAR")
            observed["os_env_present"] = "YSCB_TEST_ISOLATED_VAR" in os.environ
            log_error("[Error] Simulated domain error for hint")
            return 2

        with unittest.mock.patch("core.commands.dispatcher.dispatch_local", side_effect=_fake_dispatch_local):
            rc = worker.execute_task(
                module="core",
                args=["status"],
                cwd=sub_cwd,
                env={"YSCB_TEST_ISOLATED_VAR": "isolated_val_123"},
            )

        self.assertEqual(rc, 2)
        self.assertEqual(observed.get("virtual_cwd"), os.path.abspath(sub_cwd))
        self.assertEqual(observed.get("os_cwd"), orig_os_cwd)
        self.assertEqual(observed.get("custom_env"), "isolated_val_123")
        self.assertFalse(observed.get("os_env_present"))
        self.assertNotIn("YSCB_TEST_ISOLATED_VAR", os.environ)

        finish_pkts = [p for p in packets if p.get("type") == "task_finish"]
        self.assertEqual(len(finish_pkts), 1)
        self.assertEqual(finish_pkts[0]["exit_code"], 2)
        self.assertIn("Simulated domain error for hint", finish_pkts[0].get("error") or "")
        self.mark_passed()

    def test_managed_thread_contextvar_propagation_and_service_status_sync(self):
        """Verify BaseServiceWorker.start_managed_thread propagates RuntimeScope/LogExecutionScope across threads and synchronizes service_status IPC packets to MasterSupervisor._worker_services."""
        from core.context import bind_runtime_context, get_current_scope, get_env, get_virtual_cwd
        from core.log import log_info

        emitted_packets = []

        class _FakeSink:
            def __init__(self, emit_fn):
                self.emit_packet_fn = emit_fn

            def log(self, level, msg, component="service"):
                self.emit_packet_fn({"type": "log", "level": level, "component": component, "msg": str(msg)})

        sink = _FakeSink(emitted_packets.append)
        observed_thread_ctx = {}
        done_evt = threading.Event()

        class _CtxProbeWorker(BaseServiceWorker):
            def __init__(self) -> None:
                self._th = None

            @property
            def name(self) -> str:
                return "ctx-probe-svc"

            def start(self, context) -> None:
                self.set_state(self.STATE_STARTING)
                self._th = self.start_managed_thread(self._run, context=context)

            def _run(self) -> None:
                scope = get_current_scope()
                observed_thread_ctx["virtual_cwd"] = get_virtual_cwd()
                observed_thread_ctx["host_dir"] = scope.active_host_dir if scope else None
                observed_thread_ctx["yscb_dir"] = scope.active_yscb_dir if scope else None
                observed_thread_ctx["parent_env"] = get_env("YSCB_TEST_PARENT_CTXVAR")
                log_info("probe thread background log")
                self.set_state(self.STATE_DEGRADED_OFFLINE)
                done_evt.set()

            def stop(self) -> None:
                self.stop_managed_thread(self._th, timeout=1.0)
                self._th = None

            def health_check(self) -> bool:
                return True

        mgr = ServiceManager()
        probe_worker = _CtxProbeWorker()
        mgr.register(probe_worker, name="ctx-probe-svc", provider="test-mod", description="Probe service")

        custom_host = os.path.join(self.root_dir, "host_ws")
        os.makedirs(custom_host, exist_ok=True)
        with bind_runtime_context(
            virtual_cwd=self.root_dir,
            env={"YSCB_TEST_PARENT_CTXVAR": "inherited_from_parent"},
            host_dir=custom_host,
            yscb_dir=self.root_dir,
        ):
            mgr.start_all({
                "yscb_root": self.root_dir,
                "workspace_root": custom_host,
                "log_sink": sink,
            })
            self.assertTrue(done_evt.wait(timeout=2.0))
            mgr.stop_all()

        self.assertEqual(observed_thread_ctx.get("virtual_cwd"), os.path.abspath(self.root_dir))
        self.assertEqual(observed_thread_ctx.get("host_dir"), os.path.abspath(custom_host))
        self.assertEqual(observed_thread_ctx.get("yscb_dir"), os.path.abspath(self.root_dir))
        self.assertEqual(observed_thread_ctx.get("parent_env"), "inherited_from_parent")

        svc_status_pkts = [p for p in emitted_packets if p.get("type") == "service_status"]
        self.assertGreaterEqual(len(svc_status_pkts), 2)
        states_seen = [p.get("state") for p in svc_status_pkts]
        self.assertIn(BaseServiceWorker.STATE_DEGRADED_OFFLINE, states_seen)

        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        sup._worker_services = [{"name": "ctx-probe-svc", "provider": "test-mod", "description": "Probe service", "alive": True, "state": "STARTING"}]
        degraded_pkt = [p for p in svc_status_pkts if p.get("state") == BaseServiceWorker.STATE_DEGRADED_OFFLINE][-1]
        self.assertTrue(sup._handle_worker_control_packet(degraded_pkt))
        self.assertEqual(sup.get_status_dict()["services"][0]["state"], BaseServiceWorker.STATE_DEGRADED_OFFLINE)
        self.mark_passed()


    def test_idle_worker_demuxer_drains_bg_logs_metrics_and_busy_rss_guard(self):
        """Verify ServiceManager custom metrics in get_status, single-owner stdout demuxer idle draining, and busy-aware RSS recycling without resetting idle timer."""
        class _MetricsService(BaseServiceWorker):
            def __init__(self) -> None:
                self._busy = True

            @property
            def name(self) -> str:
                return "metrics-svc"

            def start(self, context) -> None:
                self.set_state(self.STATE_READY)

            def stop(self) -> None:
                self.set_state(self.STATE_STOPPED)

            def health_check(self) -> bool:
                return True

            def is_busy(self) -> bool:
                return self._busy

            def get_custom_metrics(self):
                return {"indexed_files": 42, "queue_depth": 0}

        mgr = ServiceManager()
        m_svc = _MetricsService()
        mgr.register(m_svc, name="metrics-svc", provider="server", description="Metrics test service")
        mgr.start_all({"yscb_root": self.root_dir})
        try:
            st_list = mgr.get_status()
            self.assertEqual(len(st_list), 1)
            self.assertEqual(st_list[0]["metrics"], {"indexed_files": 42, "queue_depth": 0})
            self.assertTrue(st_list[0]["busy"])
        finally:
            mgr.stop_all()

        # Verify single-owner demuxer drains background packets while idle and routes task packets to _yscb_task_queue
        script = self._write_fake_worker(
            "emit({'type': 'worker_alive'})\n"
            "emit({'type': 'worker_ready', 'services': [{'name': 'bg-idx', 'provider': 'core', 'state': 'READY', 'alive': True, 'busy': False, 'metrics': {'count': 1}}]})\n"
            "emit({'type': 'service_status', 'name': 'bg-idx', 'state': 'READY', 'alive': True, 'busy': True, 'metrics': {'count': 7}})\n"
            "emit({'type': 'touch_activity'})\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    if req.get('action') == 'exit':\n"
            "        break\n"
            "    emit({'type': 'terminal_stream', 'stream': 'stdout', 'text': 'demux_ok\\n'})\n"
            "    emit({'type': 'task_finish', 'exit_code': 0, 'duration_ms': 1.0, 'error': None})\n"
        )
        sup = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        real_popen = subprocess.Popen
        with unittest.mock.patch(
            "server.master.subprocess.Popen",
            side_effect=lambda cmd, **kw: real_popen([sys.executable, script], **kw),
        ):
            try:
                with sup._worker_lock:
                    sup._spawn_worker_locked()
                self.assertTrue(sup._wait_worker_ready(timeout_sec=5.0))
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    if sup.is_any_worker_service_busy():
                        break
                    time.sleep(0.02)
                self.assertTrue(sup.is_any_worker_service_busy())
                svc_entry = sup.get_status_dict()["services"][0]
                self.assertEqual(svc_entry.get("metrics"), {"count": 7})

                # While service is busy, RSS health check must defer recycling
                with unittest.mock.patch("server.master.get_process_rss_mb", return_value=99999.0), \
                     unittest.mock.patch.object(sup, "restart_worker") as mock_restart:
                    sup._evaluate_worker_memory_health()
                    mock_restart.assert_not_called()

                # Stream a foreground task through the demuxer queue
                chunks = []
                rc = sup.dispatch_task({"module": "core", "args": ["status"]}, chunks.append)
                self.assertEqual(rc, 0)
                self.assertTrue(any("demux_ok" in c.get("text", "") for c in chunks if c.get("type") == "terminal_stream"))

                # Mark service idle and verify restart_worker(touch_activity=False) preserves _last_active_time
                sup._handle_worker_packet({"type": "service_status", "name": "bg-idx", "state": "READY", "alive": True, "busy": False})
                self.assertFalse(sup.is_any_worker_service_busy())
                sup._last_active_time = 12345.0
                with unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=9999):
                    restarted = sup.restart_worker(if_idle_only=True, touch_activity=False)
                self.assertEqual(restarted, 9999)
                self.assertEqual(sup._last_active_time, 12345.0)
            finally:
                with sup._worker_lock:
                    sup._kill_worker_locked(timeout_sec=1.0)
        self.mark_passed()


    def test_ipc_touch_activity_idle_ttl_busy_guard_ready_timeout_and_cli_ttl_preservation(self):
        """Verify BaseServiceWorker IPC touch_activity, _idle_ttl_loop busy guard, _wait_worker_ready timeout cleanup, explicit CLI TTL preservation across restart_worker, and locked stop log protection."""
        from core.commands.bags import CmdBags, CmdOption
        from core import vfs

        # 1. BaseServiceWorker.touch_activity sends IPC packet via _log_sink.emit_packet_fn with 1s throttling
        ipc_packets = []

        class _Sink:
            def __init__(self):
                self.emit_packet_fn = ipc_packets.append

        svc = MockService("ipc-keepalive-svc")
        svc._log_sink = _Sink()
        with unittest.mock.patch("server.service.touch_activity") as mock_http_touch:
            self.assertTrue(svc.touch_activity())
            self.assertTrue(svc.touch_activity())
            mock_http_touch.assert_not_called()
        self.assertEqual(ipc_packets, [{"type": "touch_activity", "source": "ipc-keepalive-svc"}])

        # 2. _idle_ttl_loop refreshes activity via busy_guard instead of shutting down when worker is busy
        sup = self._make_supervisor(idle_timeout_sec=0.01, enable_watcher=False)
        sup._is_running = True
        sup._last_active_time = 1.0
        sup._current_task = {"module": "dev", "args": ["test"], "started_at": time.time()}

        sleep_calls = 0

        def _fake_sleep(_sec):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                sup._is_running = False

        with unittest.mock.patch("server.master.time.sleep", side_effect=_fake_sleep), \
             unittest.mock.patch.object(sup, "stop") as mock_stop:
            sup._idle_ttl_loop()
            mock_stop.assert_not_called()
            self.assertGreater(sup._last_active_time, 100.0)
        sup._current_task = None

        # 3. _wait_worker_ready timeout terminates hung warming worker and releases _dispatch_lock
        hung_warming = self._write_fake_worker(
            "emit({'type': 'worker_alive'})\n"
            "time.sleep(60)\n"
        )
        sup_hang = self._make_supervisor(idle_timeout_sec=300.0, enable_watcher=False)
        real_popen = subprocess.Popen
        with unittest.mock.patch(
            "server.master.subprocess.Popen",
            side_effect=lambda cmd, **kw: real_popen([sys.executable, hung_warming], **kw),
        ):
            try:
                with sup_hang._worker_lock:
                    sup_hang._spawn_worker_locked()
                self.assertFalse(sup_hang._wait_worker_ready(timeout_sec=0.15))
                pkts = []
                with unittest.mock.patch.object(sup_hang, "_wait_worker_ready", return_value=False):
                    rc = sup_hang.dispatch_task({"module": "core", "args": ["status"]}, pkts.append)
                self.assertEqual(rc, 1)
                self.assertIn("timed out", pkts[-1].get("error", ""))
                self.assertIsNone(sup_hang._worker_proc)
            finally:
                with sup_hang._worker_lock:
                    sup_hang._kill_worker_locked(timeout_sec=1.0)

        # 4. Explicit CLI idle_timeout_sec is preserved across restart_worker, whereas default (None) syncs config
        sup_explicit = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=45.0, enable_watcher=False)
        self.addCleanup(sup_explicit.logger.archive_and_close)
        self.addCleanup(sup_explicit.stop)
        sup_default = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=None, enable_watcher=False)
        self.addCleanup(sup_default.logger.archive_and_close)
        self.addCleanup(sup_default.stop)
        with unittest.mock.patch.object(sup_explicit, "_kill_worker_locked"), \
             unittest.mock.patch.object(sup_explicit, "_spawn_worker_locked", return_value=11111), \
             unittest.mock.patch.object(sup_explicit, "_write_state"):
            sup_explicit.restart_worker()
        self.assertEqual(sup_explicit.idle_timeout_sec, 45.0)

        with unittest.mock.patch("server.config.ServerConfig.load") as mock_cfg_load, \
             unittest.mock.patch.object(sup_default, "_kill_worker_locked"), \
             unittest.mock.patch.object(sup_default, "_spawn_worker_locked", return_value=22222), \
             unittest.mock.patch.object(sup_default, "_write_state"):
            from server.config import ServerConfig
            mock_cfg_load.return_value = ServerConfig(idle_timeout_sec=720.0)
            sup_default.restart_worker()
        self.assertEqual(sup_default.idle_timeout_sec, 720.0)

        # 5. cli.stop() does NOT archive active log when daemon.lock is held by another process
        server_cli = _load_server_cli()
        active_log = os.path.join(self.root_dir, ".cache", "server", "log")
        vfs.write_text(active_log, 'server start at time "2026_11_09_01.00.00"\n', encoding="utf-8", atomic=True)
        state = ServerDaemonState(
            pid=424242,
            worker_pid=0,
            port=1,
            token="t",
            root=self.root_dir,
            start_time=time.time(),
            idle_timeout_sec=0.0,
        )
        force_bags = CmdBags(raw_cmd="stop --force", command="stop", args=[], options={"force": CmdOption(name="force", params=True)})
        with unittest.mock.patch.object(server_cli, "guard_dispatch"), \
             unittest.mock.patch.object(server_cli, "_get_yscb_root", return_value=self.root_dir), \
             unittest.mock.patch.object(server_cli, "read_daemon_state", return_value=state), \
             unittest.mock.patch.object(server_cli, "is_process_alive", return_value=True), \
             unittest.mock.patch.object(server_cli, "kill_process_tree"), \
             unittest.mock.patch.object(server_cli.InterProcessLock, "acquire", return_value=False), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(server_cli.stop(force_bags), 0)
        self.assertTrue(os.path.exists(active_log), "Active log must NOT be archived without acquiring daemon.lock")
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
