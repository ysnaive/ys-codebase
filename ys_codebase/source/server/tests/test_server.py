"""
Unit & Integration Tests for Server Module.
Covers FT-05 ~ FT-12: Debounced Streamer, WarmWorker pre-warm events & lazy loading,
SystemExit interception, ServiceManager, MasterSupervisor HTTP dispatch, and ModulesWatcher.
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from dev.testing.case import YSCBTestCase
from core import events
from server.streamer import DebouncedIOStreamer
from server.service import BaseServiceWorker, ServiceManager
from server.worker import WarmWorker
from server.watcher import ModulesWatcher
from server.master import MasterSupervisor, ServerDaemonState


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


class TestServerModule(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    def test_debounced_streamer(self):
        """FT-05: DebouncedIOStreamer captures output, debounces, and emits structured packets."""
        packets = []

        def emit_cb(pkt):
            packets.append(pkt)

        streamer = DebouncedIOStreamer(emit_chunk=emit_cb, debounce_ms=100)
        with streamer:
            sys.stdout.write("Hello ")
            sys.stdout.write("World!\n")
            sys.stderr.write("Warn 1\n")

        # After exiting context manager, all streams are flushed
        streamer.send_task_finish(exit_code=0, duration_ms=15.0)

        self.assertGreater(len(packets), 0)
        types = [p["type"] for p in packets]
        self.assertIn("terminal_stream", types)
        self.assertIn("task_finish", types)

        stdout_chunks = [p["text"] for p in packets if p.get("stream") == "stdout"]
        self.assertIn("Hello World!\n", "".join(stdout_chunks))

        finish_pkt = [p for p in packets if p["type"] == "task_finish"][0]
        self.assertEqual(finish_pkt["exit_code"], 0)
        self.mark_passed()

    def test_warm_worker_pre_warm_events(self):
        """FT-06: WarmWorker emits warming and ready events via core.events."""
        captured_events = []

        from unittest.mock import patch

        def mock_broadcast(event_name, context=None, emit_module="core", search_roots=None):
            captured_events.append((event_name, context, emit_module))
            return {}

        with patch.object(events, "broadcast", side_effect=mock_broadcast):
            worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
            worker.pre_warm()

        event_names = [e[0] for e in captured_events]
        self.assertIn("server_worker_warming", event_names)
        self.assertIn("server_worker_ready", event_names)
        self.mark_passed()


    def test_warm_worker_system_exit_interception(self):
        """FT-07: WarmWorker intercepts SystemExit without crashing."""
        packets = []
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: packets.append(p))

        # Create a mock module that raises SystemExit(42)
        mock_mod_dir = os.path.join(self.root_dir, ".modules", "mock_exit", "scripts")
        os.makedirs(mock_mod_dir, exist_ok=True)
        with open(os.path.join(mock_mod_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("def help(cmd_bags):\n    import sys\n    sys.exit(42)\n")

        exit_code = worker.execute_task(module="mock_exit", args=[], cwd=self.root_dir)
        self.assertEqual(exit_code, 42)

        finish_packets = [p for p in packets if p.get("type") == "task_finish"]
        self.assertEqual(len(finish_packets), 1)
        self.assertEqual(finish_packets[0]["exit_code"], 42)
        self.mark_passed()

    def test_service_manager_lifecycle(self):
        """FT-08: ServiceManager unifies service lifecycle, metadata, and status with server."""
        mgr = ServiceManager()
        svc = MockService("test-kdb-watcher")
        mgr.register(svc, provider="knowledge-db", description="Test file watcher")

        self.assertFalse(svc.started)
        st_init = mgr.get_status()
        self.assertEqual(len(st_init), 1)
        self.assertEqual(st_init[0]["name"], "test-kdb-watcher")
        self.assertEqual(st_init[0]["provider"], "knowledge-db")
        self.assertEqual(st_init[0]["description"], "Test file watcher")
        self.assertFalse(st_init[0]["alive"])

        mgr.start_all({"root": self.root_dir})
        self.assertTrue(svc.started)
        self.assertTrue(mgr.get_status()[0]["alive"])

        mgr.stop_all()
        self.assertTrue(svc.stopped)
        self.assertFalse(mgr.get_status()[0]["alive"])
        self.mark_passed()

    def test_modules_watcher_detection(self):
        """FT-10: ModulesWatcher detects file changes under .modules and extracts affected module names."""
        modules_dir = os.path.join(self.root_dir, ".modules")
        kdb_dir = os.path.join(modules_dir, "knowledge-db")
        os.makedirs(kdb_dir, exist_ok=True)

        notified_modules = []

        def on_change(affected):
            notified_modules.append(affected)

        watcher = ModulesWatcher(modules_dir=modules_dir, on_change_callback=on_change, poll_interval_sec=0.1, debounce_sec=0.1)
        watcher.start()

        try:
            time.sleep(0.15)
            with open(os.path.join(kdb_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "knowledge-db"}')
            time.sleep(0.35)
            self.assertGreater(len(notified_modules), 0)
            self.assertIn("knowledge-db", notified_modules[0])
        finally:
            watcher.stop()
        self.mark_passed()

    def test_master_supervisor_http_and_lifecycle(self):
        """FT-07, FT-09, FT-11: MasterSupervisor initializes dynamic port, writes state, responds to HTTP endpoints (/api/status, /api/reload, /api/shutdown, /api/dispatch), and stops cleanly."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        pid = sup.start(foreground=False)

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

            # 4. Test POST /api/dispatch (EC-05: yscb_root mismatch -> 400 Bad Request)
            url_dispatch = f"http://127.0.0.1:{sup.port}/api/dispatch"
            bad_payload = json.dumps({"module": "dummy", "args": [], "yscb_root": "/mismatched/root"}).encode("utf-8")
            req_dispatch_bad = urllib.request.Request(url_dispatch, data=bad_payload, headers=auth_headers, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req_dispatch_bad)
            self.assertEqual(cm.exception.code, 400)

            # 5. Test POST /api/shutdown (Regression test for Defect 1: no AttributeError on supervisor.service_manager)
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
        """FT-01: Verify WarmWorker._module_cache avoids re-executing modules."""
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
        self.assertEqual(len(worker._module_cache), 0)

        # Create a dummy module with execution counter
        mod_dir = os.path.join(self.root_dir, ".modules", "test_cache", "scripts")
        os.makedirs(mod_dir, exist_ok=True)
        with open(os.path.join(mod_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("EXEC_COUNT = 0\n"
                    "def help(cmd_bags):\n"
                    "    global EXEC_COUNT\n"
                    "    EXEC_COUNT += 1\n"
                    "    return EXEC_COUNT\n")

        # First call: loads module
        res1 = worker.execute_task("test_cache", [], cwd=self.root_dir)
        self.assertEqual(res1, 1)
        self.assertIn("test_cache", worker._module_cache)

        # Second call: reuses cached module, EXEC_COUNT increments in memory
        res2 = worker.execute_task("test_cache", [], cwd=self.root_dir)
        self.assertEqual(res2, 2)
        self.mark_passed()

    def test_watcher_reload_dispatch_worker(self):
        """FT-02: Non-server module change dispatches to restart_worker."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        with unittest.mock.patch.object(sup, "restart_worker") as mock_worker, \
             unittest.mock.patch.object(sup, "restart_server") as mock_server:
            sup.on_modules_changed({"knowledge-db", "dev"})
            mock_worker.assert_called_once()
            mock_server.assert_not_called()
        self.mark_passed()

    def test_watcher_reload_dispatch_server(self):
        """FT-03: server or core module change dispatches to restart_server."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
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
        """FT-04: MasterSupervisor get_status_dict includes ModulesWatcher observability."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=True)
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
        sup_disabled = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        status_disabled = sup_disabled.get_status_dict()
        watcher_disabled = status_disabled["watcher"]
        self.assertFalse(watcher_disabled["enabled"])
        self.assertFalse(watcher_disabled["active"])
        self.assertIsNone(watcher_disabled["monitored_dir"])
        self.mark_passed()

    def test_format_startup_banner_and_shutdown_summary(self):
        """FT-15: Verify startup banner and shutdown summary formatting functions."""
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
        """FT-16: Verify MasterSupervisor get_status_dict and shutdown summary enrichment."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0)
        status_dict = sup.get_status_dict()
        self.assertIn("start_time", status_dict)
        self.assertIn("uptime_seconds", status_dict)
        self.assertIn("log_file", status_dict)
        self.assertGreaterEqual(status_dict["uptime_seconds"], 0.0)
        self.mark_passed()

    def test_service_manager_load_from_contributes_and_auto_start(self):
        """FT-01, ET-01, ET-02: load_from_contributes handles hyphenated module names, injects sys.path, and respects auto_start."""
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
                "worker_class": "code.class://mock-kdb-service/mock_kdb_service.worker.DummyWorker",
                "description": "Manual start service",
                "auto_start": False,
            },
        ]

        mgr = ServiceManager()
        try:
            with patch.object(contributes, "get", return_value=mock_contrib):
                mgr.load_from_contributes(yscb_root=self.root_dir)

            # Ensure .modules/mock-kdb-service was injected into sys.path
            self.assertIn(os.path.abspath(mod_dir), [os.path.abspath(p) for p in sys.path])

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
        self.mark_passed()

    def test_worker_main_ipc_isolation_and_exit_handshake(self):
        """FT-02, ET-03: worker_main isolates IPC stdout via private handle, redirects sys.stdout to stderr, and handles exit."""
        import threading
        from server.worker import worker_main

        # We simulate stdin with two commands: an echo/log command with background print, followed by exit
        in_stream = io.BytesIO()
        in_stream.write(json.dumps({"action": "ping"}).encode("utf-8") + b"\n")
        in_stream.write(json.dumps({"action": "exit"}).encode("utf-8") + b"\n")
        in_stream.seek(0)

        # Intercept real sys.stdout and sys.stderr during worker_main execution
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        fake_stdout = io.StringIO()
        fake_stderr = io.StringIO()
        sys.stdout = fake_stdout
        sys.stderr = fake_stderr

        try:
            # Run worker_main with out_stream=None so it wraps sys.stdout.buffer into _ipc_stdout
            # To capture its binary IPC output, we can redirect sys.stdout to a TextIOWrapper with a BytesIO buffer
            raw_ipc_out = io.BytesIO()
            fake_raw_stdout = io.TextIOWrapper(raw_ipc_out, encoding="utf-8")
            sys.stdout = fake_raw_stdout

            # Simulate background stdout prints right after worker_main starts
            def background_noise():
                time.sleep(0.01)
                print("BACKGROUND UNSTRUCTURED LOGGING", flush=True)

            t = threading.Thread(target=background_noise)
            t.start()

            worker_main(yscb_root=self.root_dir, in_stream=in_stream, out_stream=None)
            t.join()

            fake_raw_stdout.flush()
            raw_ipc_out.seek(0)
            ipc_lines = [line.strip() for line in raw_ipc_out if line.strip()]

            # Every line in raw_ipc_out MUST be a valid JSON packet from IPC
            for line in ipc_lines:
                pkt = json.loads(line.decode("utf-8"))
                self.assertIn("type", pkt)

            # The background noise MUST have gone to fake_stderr, NOT raw_ipc_out
            stderr_val = fake_stderr.getvalue()
            self.assertIn("BACKGROUND UNSTRUCTURED LOGGING", stderr_val)

        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

        self.mark_passed()

    def test_master_supervisor_start_time_persistence(self):
        """FT-03: MasterSupervisor preserves start_time across restart_worker."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        initial_start_time = 1700000000.0
        sup._start_time = initial_start_time

        # Mock worker process and restart
        with unittest.mock.patch.object(sup, "_kill_worker_locked"), \
             unittest.mock.patch.object(sup, "_spawn_worker_locked", return_value=12345), \
             unittest.mock.patch.object(sup, "_write_state") as mock_write_state:
            sup.restart_worker()
            mock_write_state.assert_called()

        self.assertEqual(sup._start_time, initial_start_time)
        self.mark_passed()

    def test_worker_and_master_zero_source_path_injection(self):
        """FT-04: Worker and Master supervisor execution paths contain zero source/ in sys.path or env."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
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
            sup._spawn_worker_locked()

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
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: None)
        for p in sys.path:
            norm_p = p.replace("\\", "/")
            # sys.path should not have this root's source/ directory
            self.assertFalse(f"{self.root_dir}/source" in norm_p)
        self.mark_passed()

    def test_master_two_stage_kill_fallback(self):
        """ET-04: MasterSupervisor _kill_worker_locked sends exit and falls back to kill_process_tree on timeout."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        mock_proc = unittest.mock.MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None  # Process doesn't exit on its own
        mock_proc.wait.side_effect = Exception("timeout")
        mock_proc.stdin = unittest.mock.MagicMock()
        sup._worker_proc = mock_proc

        with unittest.mock.patch("server.master.kill_process_tree") as mock_kill, \
             unittest.mock.patch("time.sleep") as mock_sleep:
            sup._kill_worker_locked(timeout_sec=1.5)

            # Verify Stage 1 sent exit NDJSON
            mock_proc.stdin.write.assert_called_with(b'{"action": "exit"}\n')
            mock_proc.stdin.flush.assert_called()

            # Verify Stage 2 fallback to kill_process_tree
            mock_kill.assert_called_once_with(mock_proc.pid, timeout_sec=1.5)
            self.assertIsNone(sup._worker_proc)

        self.mark_passed()

    def test_prewarm_load_order_and_master_stop_idempotency(self):
        """FT-02 (2026_10_25_1103): Verify WarmWorker loads service contributes before broadcasting warming event, and MasterSupervisor.stop is idempotent."""
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
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        sup._is_running = True
        with unittest.mock.patch.object(sup.logger, "archive_and_close") as mock_archive:
            sup.stop()
            sup.stop()
            self.assertEqual(mock_archive.call_count, 1)

        self.mark_passed()

    def test_master_start_lock_contention_never_falls_through(self):
        """FR-01 & EC-01 (2026_10_27_1143): Verify MasterSupervisor.start() immediately exits without spawning HTTP/Worker when daemon.lock is held, even if daemon.json is missing."""
        from core.platform import InterProcessLock

        lock_path = os.path.join(self.root_dir, ".cache", "server", "daemon.lock")
        held_lock = InterProcessLock(lock_path)
        self.assertTrue(held_lock.acquire(blocking=False))
        try:
            # Ensure daemon.json does NOT exist (simulating startup race window)
            state_path = os.path.join(self.root_dir, ".cache", "server", "daemon.json")
            if os.path.exists(state_path):
                os.remove(state_path)

            sup2 = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
            with unittest.mock.patch.object(sup2, "_spawn_worker") as mock_spawn, \
                 unittest.mock.patch("server.master._create_http_server") as mock_http:
                ret_pid = sup2.start(foreground=False)
                self.assertEqual(ret_pid, 0)
                mock_spawn.assert_not_called()
                mock_http.assert_not_called()
                self.assertFalse(sup2._is_running)
        finally:
            held_lock.release()

        self.mark_passed()

    def test_master_restart_server_reentrancy_guard_and_watcher_transaction_lock(self):
        """FR-02 & FR-05 (2026_10_27_1143): Verify restart_server() only spawns once under concurrent calls, and ModulesWatcher defers polling while .yscb.lock is held."""
        from core.platform import InterProcessLock

        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        spawn_calls = []

        with unittest.mock.patch.object(sup, "stop"), \
             unittest.mock.patch("server.master.spawn_detached", side_effect=lambda cmd, **kw: spawn_calls.append(cmd) or 12345), \
             unittest.mock.patch("os._exit"):
            sup.restart_server()
            sup.restart_server()
            sup.restart_server()
            time.sleep(0.1)

        self.assertEqual(len(spawn_calls), 1)

        # Verify ModulesWatcher._is_core_transaction_locked() detects held .yscb.lock
        modules_dir = os.path.join(self.root_dir, ".modules")
        os.makedirs(modules_dir, exist_ok=True)
        watcher = ModulesWatcher(modules_dir, on_change_callback=lambda *a: None)
        self.assertFalse(watcher._is_core_transaction_locked())

        core_lock_path = os.path.join(self.root_dir, ".cache", ".yscb.lock")
        core_lock = InterProcessLock(core_lock_path)
        self.assertTrue(core_lock.acquire(blocking=False))
        try:
            with unittest.mock.patch.object(InterProcessLock, "acquire", return_value=False):
                self.assertTrue(watcher._is_core_transaction_locked())
        finally:
            core_lock.release()

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
