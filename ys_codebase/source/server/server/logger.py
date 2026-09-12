"""
Server Module - Real-time Immediate Flush Logger & Crash Recovery System.

Provides the ServerLogger class managing:
- Real-time immediate flush logging to cache://server/log
- Rolling history files ({YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log) retaining <= 5 entries
- Crash recovery on startup: archives un-archived legacy logs before opening a fresh log
- Thread-safe write and immediate flush guarantees
"""

from datetime import datetime
import os
import re
import threading
import traceback
from typing import List, Optional


class ServerLogger:
    """
    Central real-time immediate flush logger for Server daemon.
    Guarantees thread-safe writes, immediate disk flush, crash-safe recovery,
    and rolling history retention <= 5 copies.
    """

    TIME_FORMAT: str = "%Y_%m_%d_%H.%M.%S"
    HIST_REGEX: re.Pattern = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$")
    MAX_HIST_FILES: int = 5
    START_BANNER_PREFIX: str = 'server start at time "'

    def __init__(self, yscb_root: str, log_dir: Optional[str] = None) -> None:
        """
        Initializes ServerLogger instance.

        Args:
            yscb_root: Absolute or relative path to YSCB root workspace.
            log_dir: Optional custom log directory path. Defaults to yscb_root/.cache/server.
        """
        self.yscb_root = os.path.abspath(yscb_root)
        if log_dir:
            self.log_dir = os.path.abspath(log_dir)
        else:
            self.log_dir = os.path.join(self.yscb_root, ".cache", "server")

        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "log")

        self._lock = threading.RLock()
        self._file = None
        self.start_time_str: Optional[str] = None

    @property
    def log_file_path(self) -> str:
        """Returns the absolute path to current active log file."""
        return self.log_file

    @property
    def is_opened(self) -> bool:
        """Returns True if current log file handle is open for writing."""
        with self._lock:
            return self._file is not None and not self._file.closed

    def extract_start_time_from_header(self, file_path: str) -> Optional[str]:
        """
        Reads first line of file_path and extracts timestamp from start banner:
        server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"

        Returns:
            Extracted timestamp string if matched, None otherwise.
        """
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline()
                if not first_line:
                    return None
                match = re.search(r'server start at time "(\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2})"', first_line)
                if match:
                    return match.group(1)
        except Exception:
            return None
        return None

    def _resolve_safe_archive_path(self, timestamp_str: str) -> str:
        """
        Resolves target archive path, handling potential collision by appending index suffix.
        """
        base_name = f"{timestamp_str}_log"
        cand_path = os.path.join(self.log_dir, base_name)
        if not os.path.exists(cand_path):
            return cand_path

        idx = 1
        while True:
            suffixed = f"{timestamp_str}_{idx:02d}_log"
            cand_path = os.path.join(self.log_dir, suffixed)
            if not os.path.exists(cand_path):
                return cand_path
            idx += 1

    def clean_rolling_history(self) -> List[str]:
        """
        Scans log_dir for history log files matching HIST_REGEX.
        Sorts lexicographically (chronological order) and keeps the newest MAX_HIST_FILES (5).
        Deletes any excess older files.

        Returns:
            List of deleted file paths.
        """
        with self._lock:
            if not os.path.isdir(self.log_dir):
                return []

            matched_files = []
            for entry in os.listdir(self.log_dir):
                if self.HIST_REGEX.match(entry):
                    full_p = os.path.join(self.log_dir, entry)
                    if os.path.isfile(full_p):
                        matched_files.append(entry)

            # Sort ascending so oldest is at beginning
            matched_files.sort()

            deleted_paths: List[str] = []
            if len(matched_files) > self.MAX_HIST_FILES:
                excess_count = len(matched_files) - self.MAX_HIST_FILES
                to_delete = matched_files[:excess_count]
                for fn in to_delete:
                    fp = os.path.join(self.log_dir, fn)
                    try:
                        os.remove(fp)
                        deleted_paths.append(fp)
                    except OSError:
                        pass

            return deleted_paths

    def recover_and_open(self) -> str:
        """
        Pre-flight crash recovery and fresh log initialization:
        1. If active log file exists from prior ungraceful shutdown:
           - Extracts start timestamp from first line or falls back to file mtime
           - Renames old log to {timestamp}_log
           - Enforces <= 5 rolling history retention
        2. Creates fresh log file
        3. Writes start banner: server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"
        4. Flushes immediately to disk

        Returns:
            Current startup timestamp string.
        """
        with self._lock:
            # 1. Check existing un-archived log file
            if os.path.exists(self.log_file):
                # Close handle if somehow open
                if self._file and not self._file.closed:
                    try:
                        self._file.close()
                    except Exception:
                        pass
                    self._file = None

                old_ts = self.extract_start_time_from_header(self.log_file)
                if not old_ts:
                    try:
                        mtime = os.path.getmtime(self.log_file)
                        old_ts = datetime.fromtimestamp(mtime).strftime(self.TIME_FORMAT)
                    except Exception:
                        old_ts = datetime.now().strftime(self.TIME_FORMAT)

                archive_path = self._resolve_safe_archive_path(old_ts)
                try:
                    os.rename(self.log_file, archive_path)
                except Exception:
                    # Fallback copy and remove if cross-filesystem or OS restriction
                    import shutil
                    shutil.copy2(self.log_file, archive_path)
                    try:
                        os.remove(self.log_file)
                    except OSError:
                        pass

                self.clean_rolling_history()

            # 2. Open fresh log file
            self.start_time_str = datetime.now().strftime(self.TIME_FORMAT)
            self._file = open(self.log_file, "w", encoding="utf-8")
            banner = f'server start at time "{self.start_time_str}"\n'
            self._file.write(banner)
            self._file.flush()

            return self.start_time_str

    def archive_and_close(self) -> Optional[str]:
        """
        Performs graceful shutdown archival:
        1. Writes shutdown banner and closes open file handle.
        2. Renames active log file to {start_time_str}_log.
        3. Enforces <= 5 rolling history retention.

        Returns:
            Path to archived history log file, or None if no log existed.
        """
        with self._lock:
            now_ts = datetime.now().strftime(self.TIME_FORMAT)
            if self._file and not self._file.closed:
                try:
                    shutdown_msg = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}] [{os.getpid()}] [INFO] [master] Server stopped gracefully at time "{now_ts}"\n'
                    self._file.write(shutdown_msg)
                    self._file.flush()
                except Exception:
                    pass
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

            if not os.path.exists(self.log_file):
                return None

            arch_ts = self.start_time_str or self.extract_start_time_from_header(self.log_file)
            if not arch_ts:
                try:
                    mtime = os.path.getmtime(self.log_file)
                    arch_ts = datetime.fromtimestamp(mtime).strftime(self.TIME_FORMAT)
                except Exception:
                    arch_ts = now_ts

            archive_path = self._resolve_safe_archive_path(arch_ts)
            try:
                os.rename(self.log_file, archive_path)
            except Exception:
                import shutil
                shutil.copy2(self.log_file, archive_path)
                try:
                    os.remove(self.log_file)
                except OSError:
                    pass

            self.clean_rolling_history()
            return archive_path

    def write_raw(self, line: str) -> None:
        """
        Thread-safely writes raw string line and immediately flushes to disk.
        """
        with self._lock:
            if not self._file or self._file.closed:
                self._file = open(self.log_file, "a", encoding="utf-8")

            if not line.endswith("\n"):
                line += "\n"

            self._file.write(line)
            self._file.flush()

    def log(
        self,
        level: str,
        msg: str,
        component: str = "master",
        exc_info: Optional[Exception] = None,
    ) -> None:
        """
        Writes a standard balanced format log line and immediately flushes.
        Format: [{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{COMPONENT}] {MESSAGE}
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        pid = os.getpid()
        lvl = level.upper()
        line = f"[{now_str}] [{pid}] [{lvl}] [{component}] {msg}"
        self.write_raw(line)

        if exc_info:
            tb_lines = traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
            for tb_line in tb_lines:
                self.write_raw(tb_line.rstrip("\n"))

    def info(self, msg: str, component: str = "master") -> None:
        self.log("INFO", msg, component=component)

    def warning(self, msg: str, component: str = "master") -> None:
        self.log("WARNING", msg, component=component)

    def error(self, msg: str, component: str = "master", exc_info: Optional[Exception] = None) -> None:
        self.log("ERROR", msg, component=component, exc_info=exc_info)
