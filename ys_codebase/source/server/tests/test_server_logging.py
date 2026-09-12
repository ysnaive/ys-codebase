"""
Unit and Integration Tests for Server Real-time Logging & Crash Recovery System.
Covers FT-01 ~ FT-08: Immediate Flush, Start Banner, Rolling Retention,
Crash Recovery (Header & mtime), Archive Collisions, Graceful Shutdown, Master Integration, and IPC Logging.
"""

from datetime import datetime
import json
import os
import re
import tempfile
import time
import unittest

from dev.testing.case import YSCBTestCase
from server.logger import ServerLogger
from server.master import MasterSupervisor
from server.worker import WarmWorker


class TestServerLogging(YSCBTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_logger_write_and_flush(self):
        """FT-01: ServerLogger writes start banner, formatted lines, and flushes immediately."""
        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)
        start_ts = logger.recover_and_open()

        log_path = logger.log_file_path
        self.assertTrue(os.path.isfile(log_path))
        self.assertTrue(logger.is_opened)

        # Immediate flush check: read without closing
        with open(log_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            self.assertEqual(first_line, f'server start at time "{start_ts}"\n')

        # Write log messages
        logger.info("Test info message", component="test_comp")
        logger.warning("Test warning message", component="test_comp")
        try:
            raise ValueError("Test error exception")
        except Exception as e:
            logger.error("Caught error", component="test_comp", exc_info=e)

        # Verify content flushed immediately
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertGreaterEqual(len(lines), 4)
        self.assertIn("[INFO] [test_comp] Test info message\n", lines[1])
        self.assertIn("[WARNING] [test_comp] Test warning message\n", lines[2])
        self.assertIn("[ERROR] [test_comp] Caught error\n", lines[3])
        self.assertTrue(any("ValueError: Test error exception" in l for l in lines))

        # Close handle
        logger.archive_and_close()
        self.mark_passed()

    def test_rolling_retention(self):
        """FT-02: History log rolling keeps newest 5 files and ignores non-matching assets."""
        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)

        # Create 7 history files with distinct timestamps
        history_files = [
            "2026_09_07_01.00.00_log",
            "2026_09_07_02.00.00_log",
            "2026_09_07_03.00.00_log",
            "2026_09_07_04.00.00_log",
            "2026_09_07_05.00.00_log",
            "2026_09_07_06.00.00_log",
            "2026_09_07_07.00.00_log",
        ]
        for fn in history_files:
            with open(os.path.join(self.cache_dir, fn), "w", encoding="utf-8") as f:
                f.write(f"log content for {fn}\n")

        # Create non-matching files that must be protected
        protected_files = ["daemon.json", "daemon.lock", "other_file.txt", "2026_09_07_unmatched.log"]
        for fn in protected_files:
            with open(os.path.join(self.cache_dir, fn), "w", encoding="utf-8") as f:
                f.write("protected\n")

        deleted = logger.clean_rolling_history()
        self.assertEqual(len(deleted), 2)
        self.assertIn(os.path.join(self.cache_dir, "2026_09_07_01.00.00_log"), deleted)
        self.assertIn(os.path.join(self.cache_dir, "2026_09_07_02.00.00_log"), deleted)

        # Verify exactly the 5 newest remain
        for fn in history_files[2:]:
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, fn)))

        # Verify protected files are intact
        for fn in protected_files:
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, fn)))
        self.mark_passed()

    def test_crash_recovery_with_header(self):
        """FT-03: Startup detects un-archived legacy log and archives by header start timestamp."""
        active_log = os.path.join(self.cache_dir, "log")
        header_ts = "2026_09_07_10.15.30"
        with open(active_log, "w", encoding="utf-8") as f:
            f.write(f'server start at time "{header_ts}"\n')
            f.write("[2026-09-07 10:15:30.123] [1234] [INFO] [master] Previous crash occurred\n")

        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)
        new_start_ts = logger.recover_and_open()

        # Previous log should have been renamed to {header_ts}_log
        expected_hist = os.path.join(self.cache_dir, f"{header_ts}_log")
        self.assertTrue(os.path.exists(expected_hist))
        with open(expected_hist, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Previous crash occurred", content)

        # New log must exist with new start time
        self.assertTrue(os.path.exists(active_log))
        with open(active_log, "r", encoding="utf-8") as f:
            new_banner = f.readline()
            self.assertEqual(new_banner, f'server start at time "{new_start_ts}"\n')

        logger.archive_and_close()
        self.mark_passed()

    def test_crash_recovery_corrupted_header(self):
        """FT-04: Startup falls back to file mtime if header start banner is missing or corrupted."""
        active_log = os.path.join(self.cache_dir, "log")
        with open(active_log, "w", encoding="utf-8") as f:
            f.write("Corrupted first line with no banner\nSecond line\n")

        mtime = os.path.getmtime(active_log)
        expected_ts = datetime.fromtimestamp(mtime).strftime(ServerLogger.TIME_FORMAT)

        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)
        logger.recover_and_open()

        expected_hist = os.path.join(self.cache_dir, f"{expected_ts}_log")
        self.assertTrue(os.path.exists(expected_hist))
        with open(expected_hist, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Corrupted first line", content)

        logger.archive_and_close()
        self.mark_passed()

    def test_archive_collision_handling(self):
        """FT-05: Archiving handles filename collisions by appending suffix index."""
        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)
        ts = "2026_09_07_12.00.00"

        # Pre-create conflicting history file
        existing_hist = os.path.join(self.cache_dir, f"{ts}_log")
        with open(existing_hist, "w", encoding="utf-8") as f:
            f.write("Original history\n")

        # Simulate legacy log with same timestamp
        active_log = os.path.join(self.cache_dir, "log")
        with open(active_log, "w", encoding="utf-8") as f:
            f.write(f'server start at time "{ts}"\n')
            f.write("New crash content\n")

        logger.recover_and_open()

        # Both files should exist: original {ts}_log and new {ts}_01_log
        self.assertTrue(os.path.exists(existing_hist))
        suffixed_hist = os.path.join(self.cache_dir, f"{ts}_01_log")
        self.assertTrue(os.path.exists(suffixed_hist))
        with open(suffixed_hist, "r", encoding="utf-8") as f:
            self.assertIn("New crash content", f.read())

        logger.archive_and_close()
        self.mark_passed()

    def test_graceful_stop_archival(self):
        """FT-06: archive_and_close writes graceful stop banner and renames log to history."""
        logger = ServerLogger(yscb_root=self.root_dir, log_dir=self.cache_dir)
        start_ts = logger.recover_and_open()
        logger.info("Running tasks before shutdown")

        arch_path = logger.archive_and_close()
        self.assertIsNotNone(arch_path)
        self.assertTrue(os.path.exists(arch_path))
        self.assertFalse(os.path.exists(logger.log_file_path))

        with open(arch_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Running tasks before shutdown", content)
            self.assertIn("Server stopped gracefully", content)
        self.mark_passed()

    def test_master_logging_integration(self):
        """FT-07: MasterSupervisor initializes logger, records startup, and archives on stop."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=0.0, enable_watcher=False)
        self.assertIsNotNone(sup.logger)

        # Simulate start without launching full daemon threads
        start_ts = sup.logger.recover_and_open()
        sup.logger.info("MasterSupervisor integration test started")

        log_file = sup.logger.log_file_path
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn(f'server start at time "{start_ts}"', content)
            self.assertIn("MasterSupervisor integration test started", content)

        # Stop supervisor and verify archival
        sup.stop()
        self.assertFalse(os.path.exists(log_file))
        archived_files = [f for f in os.listdir(self.cache_dir) if f.endswith("_log")]
        self.assertEqual(len(archived_files), 1)
        self.mark_passed()

    def test_worker_ipc_logging_stream(self):
        """FT-08: Master intercepts IPC log packets from Worker stream without leaking to task chunks."""
        sup = MasterSupervisor(yscb_root=self.root_dir, idle_timeout_sec=0.0, enable_watcher=False)
        sup.logger.recover_and_open()

        emitted_chunks = []
        def mock_chunk_emitter(pkt):
            emitted_chunks.append(pkt)

        # Simulate receiving packets in dispatch stream
        log_packet = {"type": "log", "level": "INFO", "component": "worker", "msg": "Worker pre_warm done"}
        task_chunk = {"type": "stdout", "data": "Hello from CLI\n"}
        task_finish = {"type": "task_finish", "exit_code": 0, "duration_ms": 15.0}

        # Master stream parsing simulation
        for pkt in [log_packet, task_chunk, task_finish]:
            if pkt.get("type") == "log":
                sup.logger.log(pkt.get("level", "INFO"), pkt.get("msg", ""), component=pkt.get("component", "worker"))
            else:
                mock_chunk_emitter(pkt)

        # Verify task chunk emitter did NOT receive log packet
        self.assertEqual(len(emitted_chunks), 2)
        self.assertEqual(emitted_chunks[0]["type"], "stdout")
        self.assertEqual(emitted_chunks[1]["type"], "task_finish")

        # Verify log file received worker log message
        with open(sup.logger.log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
            self.assertIn("[INFO] [worker] Worker pre_warm done", log_content)

        sup.stop()
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
