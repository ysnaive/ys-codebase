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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

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


    def test_warm_worker_system_exit_interception(self):
        """FT-07: WarmWorker intercepts SystemExit without crashing."""
        packets = []
        worker = WarmWorker(yscb_root=self.root_dir, emit_packet_fn=lambda p: packets.append(p))

        # Create a mock module that raises SystemExit(42)
        mock_mod_dir = os.path.join(self.root_dir, "source", "mock_exit", "scripts")
        os.makedirs(mock_mod_dir, exist_ok=True)
        with open(os.path.join(mock_mod_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("def process(args):\n    import sys\n    sys.exit(42)\n")

        exit_code = worker.execute_task(module="mock_exit", args=[], cwd=self.root_dir)
        self.assertEqual(exit_code, 42)

        finish_packets = [p for p in packets if p.get("type") == "task_finish"]
        self.assertEqual(len(finish_packets), 1)
        self.assertEqual(finish_packets[0]["exit_code"], 42)

    def test_service_manager_lifecycle(self):
        """FT-08: ServiceManager unifies service lifecycle with server."""
        mgr = ServiceManager()
        svc = MockService("test-kdb-watcher")
        mgr.register(svc)

        self.assertFalse(svc.started)
        mgr.start_all({"root": self.root_dir})
        self.assertTrue(svc.started)

        st = mgr.get_status()
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["name"], "test-kdb-watcher")
        self.assertTrue(st[0]["alive"])

        mgr.stop_all()
        self.assertTrue(svc.stopped)

    def test_modules_watcher_detection(self):
        """FT-10: ModulesWatcher detects file changes under .modules."""
        modules_dir = os.path.join(self.root_dir, ".modules")
        os.makedirs(modules_dir, exist_ok=True)

        change_notified = []

        def on_change():
            change_notified.append(True)

        watcher = ModulesWatcher(modules_dir=modules_dir, on_change_callback=on_change, poll_interval_sec=0.1)
        watcher.start()

        try:
            time.sleep(0.15)
            # Create a new file
            with open(os.path.join(modules_dir, "dummy.py"), "w", encoding="utf-8") as f:
                f.write("# update")
            time.sleep(0.3)
            self.assertGreater(len(change_notified), 0)
        finally:
            watcher.stop()

    def test_master_supervisor_http_and_lifecycle(self):
        """FT-09 & FT-11: MasterSupervisor initializes dynamic port, writes state, responds to HTTP, and stops cleanly."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=300.0, enable_watcher=False)
        pid = sup.start(foreground=False)

        try:
            self.assertGreater(sup.port, 0)
            self.assertTrue(os.path.exists(sup.state_file))

            # Test unauthorized request (403)
            url = f"http://127.0.0.1:{sup.port}/api/status"
            req_unauth = urllib.request.Request(url)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req_unauth)
            self.assertEqual(cm.exception.code, 403)

            # Test authorized GET /api/status
            req_auth = urllib.request.Request(url, headers={"Authorization": f"Bearer {sup.token}"})
            with urllib.request.urlopen(req_auth) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body["status"], "running")
                self.assertEqual(body["pid"], os.getpid())

        finally:
            sup.stop()

        self.assertFalse(os.path.exists(sup.state_file))


if __name__ == "__main__":
    unittest.main()
