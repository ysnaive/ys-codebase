"""
Unit and Integration Tests for Server Real-time Logging & Crash Recovery System.
Covers immediate flush, start banner, rolling retention, crash recovery (header & mtime),
archive collisions, graceful shutdown, master integration, IPC logging, and file rotation.
"""

from datetime import datetime
import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from dev.testing.case import YSCBTestCase
from server.logger import ServerLogger, _safe_replace_file
from server.master import MasterSupervisor


class TestServerLogging(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)

    def tearDown(self):
        self.doCleanups()
        self.temp_dir.cleanup()
        super().tearDown()

    def _make_logger(self, **kwargs) -> ServerLogger:
        kwargs.setdefault("yscb_root", self.root_dir)
        kwargs.setdefault("log_dir", self.cache_dir)
        logger = ServerLogger(**kwargs)
        self.addCleanup(logger.archive_and_close)
        return logger

    def _make_supervisor(self, **kwargs) -> MasterSupervisor:
        kwargs.setdefault("yscb_root", self.root_dir)
        kwargs.setdefault("idle_timeout_sec", 0.0)
        kwargs.setdefault("enable_watcher", False)
        sup = MasterSupervisor(**kwargs)
        self.addCleanup(sup.logger.archive_and_close)
        self.addCleanup(sup.stop)
        return sup

    def test_logger_write_and_flush(self):
        """ServerLogger writes start banner, formatted lines, and flushes immediately."""
        logger = self._make_logger()
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

        # Verify echo_console=True mirrors output to sys.stdout without raising NameError
        logger.echo_console = True
        fake_out = io.StringIO()
        with patch("sys.stdout", fake_out):
            logger.info("Console echoed message", component="console_test")
        self.assertIn("[INFO] [console_test] Console echoed message", fake_out.getvalue())

        # Close handle
        logger.archive_and_close()
        self.mark_passed()

    def test_rolling_retention(self):
        """History log rolling keeps newest 5 files and ignores non-matching assets."""
        logger = self._make_logger()

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
        """Startup detects un-archived legacy log and archives by header start timestamp."""
        active_log = os.path.join(self.cache_dir, "log")
        header_ts = "2026_09_07_10.15.30"
        with open(active_log, "w", encoding="utf-8") as f:
            f.write(f'server start at time "{header_ts}"\n')
            f.write("[2026-09-07 10:15:30.123] [1234] [INFO] [master] Previous crash occurred\n")

        logger = self._make_logger()
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
        """Startup falls back to file mtime if header start banner is missing or corrupted."""
        active_log = os.path.join(self.cache_dir, "log")
        with open(active_log, "w", encoding="utf-8") as f:
            f.write("Corrupted first line with no banner\nSecond line\n")

        mtime = os.path.getmtime(active_log)
        expected_ts = datetime.fromtimestamp(mtime).strftime(ServerLogger.TIME_FORMAT)

        logger = self._make_logger()
        logger.recover_and_open()

        expected_hist = os.path.join(self.cache_dir, f"{expected_ts}_log")
        self.assertTrue(os.path.exists(expected_hist))
        with open(expected_hist, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Corrupted first line", content)

        logger.archive_and_close()
        self.mark_passed()

    def test_archive_collision_handling(self):
        """Archiving handles filename collisions by appending suffix index and falls back to copy2+remove on rename OSError."""
        logger = self._make_logger()
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

        # Verify _safe_replace_file fallback to copy2 + remove when os.rename raises OSError
        src_file = os.path.join(self.cache_dir, "fallback_src.log")
        dst_file = os.path.join(self.cache_dir, "fallback_dst.log")
        with open(src_file, "w", encoding="utf-8") as f:
            f.write("cross-device fallback payload\n")

        with patch("server.logger.os.rename", side_effect=OSError("EXDEV cross-device link")):
            _safe_replace_file(src_file, dst_file)

        self.assertFalse(os.path.exists(src_file))
        self.assertTrue(os.path.exists(dst_file))
        with open(dst_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "cross-device fallback payload\n")

        # Verify _safe_replace_file tolerates os.remove OSError during fallback
        src_locked = os.path.join(self.cache_dir, "fallback_src_locked.log")
        dst_locked = os.path.join(self.cache_dir, "fallback_dst_locked.log")
        with open(src_locked, "w", encoding="utf-8") as f:
            f.write("locked remove payload\n")

        with patch("server.logger.os.rename", side_effect=OSError("rename locked")), \
             patch("server.logger.os.remove", side_effect=OSError("remove locked")):
            _safe_replace_file(src_locked, dst_locked)

        self.assertTrue(os.path.exists(dst_locked))
        with open(dst_locked, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "locked remove payload\n")

        self.mark_passed()

    def test_graceful_stop_archival(self):
        """archive_and_close writes graceful stop banner and renames log to history."""
        logger = self._make_logger()
        logger.recover_and_open()
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
        """MasterSupervisor initializes logger, records startup, and archives on stop."""
        sup = self._make_supervisor(idle_timeout_sec=0.0, enable_watcher=False)
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
        """Master intercepts IPC log packets from Worker stream without leaking to task chunks via real dispatch_task."""
        sup = self._make_supervisor(idle_timeout_sec=0.0, enable_watcher=False)
        sup.logger.recover_and_open()

        emitted_chunks = []

        def mock_chunk_emitter(pkt):
            emitted_chunks.append(pkt)

        # Construct real NDJSON packets simulating Worker stdout stream
        log_packet = json.dumps({"type": "log", "level": "INFO", "component": "worker", "msg": "Worker pre_warm done"}) + "\n"
        task_chunk = json.dumps({"type": "stdout", "data": "Hello from CLI\n"}) + "\n"
        task_finish = json.dumps({"type": "task_finish", "exit_code": 0, "duration_ms": 15.0}) + "\n"
        stream_bytes = (log_packet + task_chunk + task_finish).encode("utf-8")

        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.stdin = io.BytesIO()
        mock_proc.stdout = io.BytesIO(stream_bytes)
        mock_proc.poll.return_value = None

        sup._worker_proc = mock_proc
        # Injected worker is treated as having completed the worker_ready handshake
        sup._worker_ready_event.set()

        with unittest.mock.patch("server.master.is_process_alive", return_value=True):
            # Real execution of sup.dispatch_task()
            ret = sup.dispatch_task({"module": "dummy_mod", "args": ["arg1"]}, mock_chunk_emitter)
            self.assertEqual(ret, 0)

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

    def test_non_inheritable_lock_fd_and_log_tail_rotation_reset(self):
        """驗證 InterProcessLock 與 ServerLogger 檔案描述符不可繼承，且 read_tail_chunks 在日誌輪替/截斷與 inode 變更時重置偏移量。"""
        from core.platform.lock import InterProcessLock

        lock_path = os.path.join(self.cache_dir, "test_non_inheritable.lock")
        lock = InterProcessLock(lock_path, timeout=2.0)
        self.assertTrue(lock.acquire())
        try:
            self.assertIsNotNone(lock._fd)
            self.assertFalse(os.get_inheritable(lock._fd))
        finally:
            lock.release()

        logger = self._make_logger()
        # 當日誌檔尚未存在時，read_tail_chunks 應安全回傳空字串與 0 偏移
        self.assertEqual(logger.read_tail_chunks(10, 123), ("", 0, None))

        logger.recover_and_open()
        self.assertIsNotNone(logger._file)
        self.assertFalse(os.get_inheritable(logger._file.fileno()))

        logger.info("Line one Long Message For Offset")
        chunk1, off1, ino1 = logger.read_tail_chunks(0, None)
        self.assertIn("Line one Long Message For Offset", chunk1)
        self.assertGreater(off1, 0)

        # 模擬日誌輪替重啟後檔案變短，read_tail_chunks 應自動從 0 重新讀取新內容
        logger.archive_and_close()
        logger.recover_and_open()
        self.assertIsNotNone(logger._file)
        self.assertFalse(os.get_inheritable(logger._file.fileno()))

        logger.info("Short line")
        chunk2, off2, ino2 = logger.read_tail_chunks(off1 + 5000, ino1)
        self.assertIn("Short line", chunk2)
        self.assertGreater(off2, 0)

        # 模擬檔案大小未小於 last_offset，但 last_inode 發生變化時，應重置從 0 完整讀取
        self.assertIsNotNone(ino2)
        chunk3, off3, ino3 = logger.read_tail_chunks(10, (ino2 or 1) + 999999)
        self.assertTrue(chunk3.startswith('server start at time "'))
        self.assertIn("Short line", chunk3)
        self.assertEqual(off3, off2)
        self.assertEqual(ino3, ino2)

        logger.archive_and_close()
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
