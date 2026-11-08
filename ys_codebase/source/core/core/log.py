"""
Core Log Pipeline & Streamer Infrastructure.
100% Python Standard Library. Zero Upper-Layer Coupling.

Provides two orthogonal logging and I/O families:
1. Caller Terminal Stream Family (`log*`):
   - `log`, `log_stream`, `log_info`, `log_warn`, `log_error`, `log_debug`
   - `LogExecutionScope` & `bind_log_context` (ContextVar execution plane routing)
   - `DebouncedIOStreamer` & `_StreamProxy` (500ms debounce / 4KB chunk interceptor)
   - Dispatch-level `error_hint` accumulation and extraction (`extract_error_hint`, `record_error_hint`, `get_last_error_hint`, `clear_error_hint`)
2. Incremental Rolling File Family (`log_file*`):
   - `RollingFileLogger` (crash-recoverable rolling file logger with <= 5 history retention)
   - `_extract_log_file_timestamp`, `_safe_replace_file` (cross-platform atomic `os.replace` with fallback)
   - `log_file`, `log_file_jsonl`, `read_log_file_jsonl`, `read_log_file_tail`
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import traceback
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

PathTarget = Union[str, Path]

MAX_ERROR_HINT_CHUNKS: int = 16


@dataclass(frozen=True)
class LogExecutionScope:
    """
    Execution scope bound via `ContextVar` to route `log*` calls across planes:
    - Foreground CLI / Sandbox tests (default): writes to current `sys.stdout` / `sys.stderr`.
    - WarmWorker hot dispatch (`streamer` set): writes to `DebouncedIOStreamer` (unless an inner test redirected `sys.stdout`/`sys.stderr`).
    - Background ServiceWorker (`background_sink` set): routes output to `RollingFileLogger` with structured component tags.
    """

    streamer: Optional["DebouncedIOStreamer"] = None
    background_sink: Optional["RollingFileLogger"] = None
    component: str = "core"
    debug_enabled: bool = False
    error_chunks: List[str] = field(default_factory=list)


_ACTIVE_LOG_SCOPE: ContextVar[Optional[LogExecutionScope]] = ContextVar(
    "_ACTIVE_LOG_SCOPE", default=None
)


def _get_fallback_log_state() -> Tuple[threading.RLock, List[str], threading.RLock]:
    """Returns process-level fallback error hint buffer and file lock from `RuntimeContext`."""
    from core.context import get_runtime_context

    ctx = get_runtime_context()
    return (ctx.log_error_lock, ctx.log_error_chunks, ctx.log_file_op_lock)


def get_current_log_scope() -> Optional[LogExecutionScope]:
    """Returns the currently active `LogExecutionScope` in this context, or None."""
    return _ACTIVE_LOG_SCOPE.get()


@contextmanager
def bind_log_context(
    *,
    streamer: Optional["DebouncedIOStreamer"] = None,
    background_sink: Optional["RollingFileLogger"] = None,
    component: Optional[str] = None,
    debug_enabled: Optional[bool] = None,
    isolated_error_scope: bool = False,
) -> Iterator[LogExecutionScope]:
    """
    Context manager binding execution plane routing parameters to `_ACTIVE_LOG_SCOPE`.
    """
    parent = _ACTIVE_LOG_SCOPE.get()
    eff_streamer = streamer if streamer is not None else (parent.streamer if parent else None)
    eff_sink = (
        background_sink
        if background_sink is not None
        else (parent.background_sink if parent else None)
    )
    eff_comp = component if component is not None else (parent.component if parent else "core")
    if debug_enabled is not None:
        eff_debug = debug_enabled
    elif parent is not None:
        eff_debug = parent.debug_enabled
    else:
        from core.context import get_env

        eff_debug = get_env("YSCB_DEBUG", "").strip() == "1"

    if isolated_error_scope or parent is None:
        err_list: List[str] = []
    else:
        err_list = parent.error_chunks

    scope = LogExecutionScope(
        streamer=eff_streamer,
        background_sink=eff_sink,
        component=eff_comp,
        debug_enabled=eff_debug,
        error_chunks=err_list,
    )
    token: Token = _ACTIVE_LOG_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _ACTIVE_LOG_SCOPE.reset(token)


# ==============================================================================
# 1. Dispatch-Level Error Hint Accumulation & Extraction
# ==============================================================================


def extract_error_hint(text: str, max_len: int = 200) -> str:
    """Extracts the most representative single-line error summary from terminal or error output."""
    if not text:
        return ""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return ""
    priority_keywords = ("[error]", "error:", "[fail]", "[blocker]", "exception", "traceback")
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in priority_keywords):
            return ln[:max_len]
    return lines[0][:max_len]


def record_error_hint(text: str) -> None:
    """Records an error message snippet into the active dispatch scope (retaining up to 16 chunks)."""
    if not text or not str(text).strip():
        return
    cleaned = str(text).strip()
    scope = _ACTIVE_LOG_SCOPE.get()
    if scope is not None:
        if len(scope.error_chunks) < MAX_ERROR_HINT_CHUNKS:
            scope.error_chunks.append(cleaned)
    err_lock, err_chunks, _ = _get_fallback_log_state()
    with err_lock:
        if len(err_chunks) < MAX_ERROR_HINT_CHUNKS:
            err_chunks.append(cleaned)


def get_last_error_hint(max_len: int = 200) -> str:
    """Extracts the highest-priority error summary from accumulated error chunks in the current dispatch."""
    scope = _ACTIVE_LOG_SCOPE.get()
    chunks: List[str] = []
    if scope is not None and scope.error_chunks:
        chunks = list(scope.error_chunks)
    else:
        err_lock, err_chunks, _ = _get_fallback_log_state()
        with err_lock:
            chunks = list(err_chunks)
    if not chunks:
        return ""
    combined = "\n".join(chunks)
    return extract_error_hint(combined, max_len=max_len)


def clear_error_hint() -> None:
    """Clears accumulated error hint chunks at the start of a new CLI dispatch."""
    scope = _ACTIVE_LOG_SCOPE.get()
    if scope is not None:
        scope.error_chunks.clear()
    err_lock, err_chunks, _ = _get_fallback_log_state()
    with err_lock:
        err_chunks.clear()


# ==============================================================================
# 2. Caller Terminal Stream Family (`log*`)
# ==============================================================================


def _write_to_active_target(
    text: str,
    *,
    stream: str = "stdout",
    level: str = "INFO",
    flush: bool = False,
) -> None:
    """
    Internal router dispatching terminal text to:
    1. Background `RollingFileLogger` if `scope.background_sink` is active (Plane P4).
    2. Inner redirected stream if a test replaced `sys.stdout` / `sys.stderr` inside `DebouncedIOStreamer`.
    3. `DebouncedIOStreamer` if `scope.streamer` is active (Plane P3).
    4. Current `sys.stdout` or `sys.stderr` (Planes P2 / P5).
    """
    if not text:
        return

    norm_stream = "stderr" if stream == "stderr" else "stdout"
    scope = _ACTIVE_LOG_SCOPE.get()

    if scope is not None and scope.background_sink is not None:
        sink = scope.background_sink
        comp = scope.component or "service"
        stripped = text.rstrip("\r\n")
        if stripped:
            for ln in stripped.splitlines():
                sink.log(level, ln, component=comp)
        return

    target_stream_obj = sys.stderr if norm_stream == "stderr" else sys.stdout

    if scope is not None and scope.streamer is not None and not scope.streamer._is_closed:
        expected_proxy = (
            scope.streamer._stderr_proxy
            if norm_stream == "stderr"
            else scope.streamer._stdout_proxy
        )
        # If an inner unit test used redirect_stdout/stderr or patch("sys.stdout"),
        # target_stream_obj will differ from expected_proxy -> write to the inner stream!
        if target_stream_obj is expected_proxy or target_stream_obj is None:
            scope.streamer.write(norm_stream, text)
            if flush:
                scope.streamer.flush()
            return

    if target_stream_obj is not None:
        try:
            target_stream_obj.write(text)
            if flush:
                target_stream_obj.flush()
        except OSError:
            pass


def log(
    *objects: Any,
    sep: str = " ",
    end: str = "\n",
    flush: bool = False,
    stream: str = "stdout",
) -> None:
    """
    Drop-in replacement for built-in `print()` routing through `core.log`.
    Preserves verbatim message formatting in foreground modes and records `error_hint`
    when `stream == "stderr"` or text contains error markers.
    """
    text = sep.join(str(obj) for obj in objects) + end
    if stream == "stderr":
        record_error_hint(text)
    elif "[error]" in text.lower() or "error:" in text.lower() or "[fail]" in text.lower():
        record_error_hint(text)
    _write_to_active_target(text, stream=stream, level="INFO", flush=flush)


def log_stream(
    text: str,
    *,
    stream: str = "stdout",
    flush: bool = True,
    record_hint: bool = False,
) -> None:
    """
    Writes raw pre-formatted text (without appending a newline) to the active stream.
    Replaces `sys.stdout.write(...)` and `sys.stderr.write(...)`.
    """
    s = str(text)
    if record_hint or stream == "stderr":
        record_error_hint(s)
    _write_to_active_target(s, stream=stream, level="INFO", flush=flush)


def log_info(
    msg: Any,
    *,
    stream: str = "stdout",
    flush: bool = False,
) -> None:
    """
    Logs an informational message line.
    Outputs verbatim in foreground modes (preserving 100% existing CLI output assertions)
    and tags as `[INFO]` when routed to a background `RollingFileLogger`.
    """
    text = f"{msg}\n"
    _write_to_active_target(text, stream=stream, level="INFO", flush=flush)


def log_warn(
    msg: Any,
    *,
    stream: str = "stdout",
    flush: bool = False,
) -> None:
    """
    Logs a warning message line.
    Outputs verbatim in foreground modes and tags as `[WARNING]` in background `RollingFileLogger`.
    """
    text = f"{msg}\n"
    _write_to_active_target(text, stream=stream, level="WARNING", flush=flush)


def log_error(
    msg: Any,
    *,
    stream: str = "stdout",
    flush: bool = False,
    record_hint: bool = True,
) -> None:
    """
    Logs an error message line and automatically records it into the dispatch `error_hint` buffer.
    Outputs verbatim in foreground modes and tags as `[ERROR]` in background `RollingFileLogger`.
    """
    s = str(msg)
    if record_hint:
        record_error_hint(s)
    text = f"{s}\n"
    _write_to_active_target(text, stream=stream, level="ERROR", flush=flush)


def log_debug(
    msg: Any,
    *,
    stream: str = "stderr",
    flush: bool = False,
) -> None:
    """
    Logs a diagnostic debug message line when `YSCB_DEBUG=1` or `scope.debug_enabled` is True,
    or when running inside a background `RollingFileLogger` scope.
    """
    from core.context import get_env

    scope = _ACTIVE_LOG_SCOPE.get()
    is_debug = (
        (scope is not None and (scope.debug_enabled or scope.background_sink is not None))
        or get_env("YSCB_DEBUG", "").strip() == "1"
    )
    if not is_debug:
        return
    text = f"{msg}\n"
    _write_to_active_target(text, stream=stream, level="DEBUG", flush=flush)


# ==============================================================================
# 3. Debounced IO Streamer (100% Compatible with `server/streamer.py`)
# ==============================================================================


class _StreamProxy(io.TextIOBase):
    """Proxy object redirecting `sys.stdout` / `sys.stderr` writes to `DebouncedIOStreamer`."""

    def __init__(self, streamer: "DebouncedIOStreamer", stream_name: str) -> None:
        self._streamer = streamer
        self._stream_name = stream_name

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._stream_name == "stderr":
            record_error_hint(s)
        self._streamer.write(self._stream_name, s)
        return len(s)

    def flush(self) -> None:
        self._streamer.flush()


class DebouncedIOStreamer:
    """
    Thread-safe debounced stream interceptor for stdout & stderr.
    Buffers terminal chunks and flushes every `debounce_ms` (default 500ms),
    or immediately upon reaching `max_buffer_bytes` / explicit flush / close.
    """

    def __init__(
        self,
        emit_chunk: Callable[[Dict[str, Any]], None],
        debounce_ms: int = 500,
        max_buffer_bytes: int = 4096,
    ) -> None:
        self.emit_chunk = emit_chunk
        self.debounce_sec = debounce_ms / 1000.0
        self.max_buffer_bytes = max_buffer_bytes
        self._lock = threading.RLock()
        self._buffer: List[Dict[str, str]] = []
        self._buffer_bytes: int = 0
        self._timer: Optional[threading.Timer] = None
        self._is_closed = False

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._scope_token: Optional[Token] = None

        self._stdout_proxy = _StreamProxy(self, "stdout")
        self._stderr_proxy = _StreamProxy(self, "stderr")

    def write(self, stream_name: str, text: str) -> None:
        if not text:
            return

        with self._lock:
            if self._is_closed:
                return

            self._buffer.append({"stream": stream_name, "text": text})
            self._buffer_bytes += len(text.encode("utf-8", errors="replace"))

            if self._buffer_bytes >= self.max_buffer_bytes:
                self._flush_locked()
            else:
                self._ensure_timer_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None

        if not self._buffer:
            self._buffer_bytes = 0
            return

        consolidated: List[Tuple[str, List[str]]] = []
        for item in self._buffer:
            s_name = item["stream"]
            if consolidated and consolidated[-1][0] == s_name:
                consolidated[-1][1].append(item["text"])
            else:
                consolidated.append((s_name, [item["text"]]))

        # Clear buffer state BEFORE calling emit_chunk to prevent re-entrant duplication
        self._buffer.clear()
        self._buffer_bytes = 0

        for s_name, chunks in consolidated:
            combined_text = "".join(chunks)
            if combined_text:
                packet = {
                    "type": "terminal_stream",
                    "stream": s_name,
                    "text": combined_text,
                }
                try:
                    self.emit_chunk(packet)
                except Exception:
                    pass

    def _ensure_timer_locked(self) -> None:
        if self._timer is None and not self._is_closed:
            self._timer = threading.Timer(self.debounce_sec, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self) -> None:
        with self._lock:
            self._flush_locked()

    def send_task_finish(
        self,
        exit_code: int,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Flushes remaining terminal stream and sends `task_finish` packet."""
        self.flush()
        packet = {
            "type": "task_finish",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "error": error,
        }
        try:
            self.emit_chunk(packet)
        except Exception:
            pass

    def start_capture(self) -> "DebouncedIOStreamer":
        with self._lock:
            self._is_closed = False
            self._orig_stdout = sys.stdout
            self._orig_stderr = sys.stderr
            sys.stdout = self._stdout_proxy  # type: ignore[assignment]
            sys.stderr = self._stderr_proxy  # type: ignore[assignment]
            parent = _ACTIVE_LOG_SCOPE.get()
            new_scope = LogExecutionScope(
                streamer=self,
                background_sink=parent.background_sink if parent else None,
                component=parent.component if parent else "worker",
                debug_enabled=parent.debug_enabled if parent else False,
                error_chunks=parent.error_chunks if parent else [],
            )
            self._scope_token = _ACTIVE_LOG_SCOPE.set(new_scope)
        return self

    def stop_capture(self) -> None:
        with self._lock:
            if self._is_closed:
                return
            self._flush_locked()
            self._is_closed = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
            token = self._scope_token
            self._scope_token = None
            if sys.stdout is self._stdout_proxy:
                sys.stdout = self._orig_stdout
            if sys.stderr is self._stderr_proxy:
                sys.stderr = self._orig_stderr
            if token is not None:
                try:
                    _ACTIVE_LOG_SCOPE.reset(token)
                except ValueError:
                    pass

    def __enter__(self) -> "DebouncedIOStreamer":
        return self.start_capture()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop_capture()


# ==============================================================================
# 4. Incremental Rolling File Family (`log_file*` & `RollingFileLogger`)
# ==============================================================================


def _resolve_log_target(target: PathTarget) -> Optional[Path]:
    """
    Resolves a file path or semantic URI (e.g. `cache://core/telemetry.jsonl`) to a local `Path`.
    Forces `interactive=False` on `core.uri.resolve` to prevent TTY prompt deadlocks.
    """
    try:
        if isinstance(target, Path):
            return target.resolve()
        s = str(target).strip()
        if not s:
            return None
        if "://" in s:
            from core import uri

            resolved = uri.resolve(s, interactive=False)
            if not resolved or str(resolved).startswith("!"):
                return None
            return Path(resolved).resolve()
        return Path(s).resolve()
    except Exception:
        return None


def _extract_log_file_timestamp(file_path: str, time_format: str, header_regex: re.Pattern) -> str:
    """
    Resolves timestamp string for a log file:
    1. Attempts to extract start timestamp from first line header banner.
    2. Falls back to file modification time (mtime).
    3. Falls back to current system time.
    """
    if not os.path.exists(file_path):
        return datetime.now().strftime(time_format)
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            if first_line:
                match = header_regex.search(first_line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime).strftime(time_format)
    except OSError:
        pass
    return datetime.now().strftime(time_format)


def _safe_replace_file(src: str, dst: str) -> None:
    """
    Safely moves `src` to `dst` using cross-platform atomic `os.replace`,
    falling back to `shutil.copy2` + `os.remove` across filesystems or Windows handle locks.
    """
    try:
        os.replace(src, dst)
    except OSError:
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except OSError:
            pass


class RollingFileLogger:
    """
    Central real-time immediate flush rolling file logger.
    Guarantees thread-safe writes, immediate disk flush, crash-safe recovery,
    non-inheritable file descriptors, and rolling history retention <= 5 copies.
    100% compatible with `server.logger.ServerLogger`.
    """

    TIME_FORMAT: str = "%Y_%m_%d_%H.%M.%S"
    HIST_REGEX: re.Pattern = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}(?:_\d{2,})?_log$")
    MAX_HIST_FILES: int = 5
    START_BANNER_PREFIX: str = 'server start at time "'
    HEADER_TIME_REGEX: re.Pattern = re.compile(
        re.escape(START_BANNER_PREFIX) + r'(\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2})"'
    )

    def __init__(
        self,
        yscb_root: str = "",
        log_dir: Optional[str] = None,
        echo_console: bool = False,
    ) -> None:
        """
        Initializes RollingFileLogger instance.

        Args:
            yscb_root: Absolute or relative path to YSCB root workspace.
            log_dir: Optional custom log directory path. Defaults to yscb_root/.cache/server.
            echo_console: If True, echoes written log lines to the active stdout stream.
        """
        if yscb_root:
            self.yscb_root = os.path.abspath(yscb_root)
        else:
            from core.context import get_virtual_cwd

            self.yscb_root = os.path.abspath(get_virtual_cwd())
        if log_dir:
            resolved_dir = _resolve_log_target(log_dir) if "://" in str(log_dir) else Path(os.path.abspath(log_dir))
            self.log_dir = str(resolved_dir) if resolved_dir else os.path.abspath(log_dir)
        else:
            self.log_dir = os.path.join(self.yscb_root, ".cache", "server")

        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "log")

        self._lock = threading.RLock()
        self._file: Optional[io.TextIOWrapper] = None
        self.start_time_str: Optional[str] = None
        self.echo_console: bool = echo_console

    @property
    def log_file_path(self) -> str:
        """Returns the absolute path to current active log file."""
        return self.log_file

    @property
    def is_opened(self) -> bool:
        """Returns True if current log file handle is open for writing."""
        with self._lock:
            return self._file is not None and not self._file.closed

    def _resolve_safe_archive_path(self, timestamp_str: str) -> str:
        """Resolves target archive path, handling potential collision by appending index suffix."""
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
        Scans `log_dir` for history log files matching `HIST_REGEX`.
        Sorts lexicographically (chronological order) and keeps the newest `MAX_HIST_FILES` (5).
        Deletes any excess older files.

        Returns:
            List of deleted file paths.
        """
        with self._lock:
            if not os.path.isdir(self.log_dir):
                return []

            matched_files = [
                entry
                for entry in os.listdir(self.log_dir)
                if self.HIST_REGEX.match(entry) and os.path.isfile(os.path.join(self.log_dir, entry))
            ]
            matched_files.sort()

            deleted_paths: List[str] = []
            if len(matched_files) > self.MAX_HIST_FILES:
                excess_count = len(matched_files) - self.MAX_HIST_FILES
                for fn in matched_files[:excess_count]:
                    fp = os.path.join(self.log_dir, fn)
                    try:
                        os.remove(fp)
                        deleted_paths.append(fp)
                    except OSError:
                        pass

            return deleted_paths

    def _close_active_handle_locked(self) -> None:
        if self._file and not self._file.closed:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

    def _open_log_stream_locked(self, mode: str) -> None:
        os.makedirs(self.log_dir, exist_ok=True)
        self._file = open(self.log_file, mode, encoding="utf-8")
        try:
            os.set_inheritable(self._file.fileno(), False)
        except OSError:
            pass

    def recover_and_open(self) -> str:
        """
        Pre-flight crash recovery and fresh log initialization:
        1. If active log file exists from prior ungraceful shutdown:
           - Extracts start timestamp from first line or falls back to file mtime
           - Replaces old log to `{timestamp}_log`
           - Enforces <= 5 rolling history retention
        2. Creates fresh log file
        3. Writes start banner: `server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`
        4. Flushes immediately to disk

        Returns:
            Current startup timestamp string.
        """
        with self._lock:
            if os.path.exists(self.log_file):
                self._close_active_handle_locked()
                old_ts = _extract_log_file_timestamp(self.log_file, self.TIME_FORMAT, self.HEADER_TIME_REGEX)
                archive_path = self._resolve_safe_archive_path(old_ts)
                _safe_replace_file(self.log_file, archive_path)
                self.clean_rolling_history()

            self.start_time_str = datetime.now().strftime(self.TIME_FORMAT)
            self._open_log_stream_locked("w")
            banner = f'{self.START_BANNER_PREFIX}{self.start_time_str}"\n'
            assert self._file is not None
            self._file.write(banner)
            self._file.flush()

            return self.start_time_str

    def archive_and_close(self) -> Optional[str]:
        """
        Performs graceful shutdown archival:
        1. Writes shutdown banner and closes open file handle.
        2. Moves active log file to `{start_time_str}_log`.
        3. Enforces <= 5 rolling history retention.

        Returns:
            Path to archived history log file, or None if no log existed.
        """
        with self._lock:
            now_ts = datetime.now().strftime(self.TIME_FORMAT)
            if self._file and not self._file.closed:
                try:
                    shutdown_msg = (
                        f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}] '
                        f'[{os.getpid()}] [INFO] [master] Server stopped gracefully at time "{now_ts}"\n'
                    )
                    self._file.write(shutdown_msg)
                    self._file.flush()
                except OSError:
                    pass
                self._close_active_handle_locked()

            if not os.path.exists(self.log_file):
                return None

            archive_path = self.get_expected_archive_path()
            _safe_replace_file(self.log_file, archive_path)
            self.clean_rolling_history()
            return archive_path

    def close(self) -> None:
        """Closes the active file handle without archiving."""
        with self._lock:
            self._close_active_handle_locked()

    def get_expected_archive_path(self) -> str:
        """Calculates and returns the target archive path where the current log will be moved on shutdown."""
        arch_ts = self.start_time_str or _extract_log_file_timestamp(
            self.log_file, self.TIME_FORMAT, self.HEADER_TIME_REGEX
        )
        return self._resolve_safe_archive_path(arch_ts)

    def write_raw(self, line: str) -> None:
        """Thread-safely writes raw string line and immediately flushes to disk."""
        with self._lock:
            if not self._file or self._file.closed:
                self._open_log_stream_locked("a")

            if not line.endswith("\n"):
                line += "\n"

            assert self._file is not None
            self._file.write(line)
            self._file.flush()
            if self.echo_console:
                log_stream(line, stream="stdout", flush=True)

    def log(
        self,
        level: str,
        msg: str,
        component: str = "master",
        exc_info: Optional[BaseException] = None,
    ) -> None:
        """
        Writes a standard balanced format log line and immediately flushes.
        Format: `[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{COMPONENT}] {MESSAGE}`
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

    def warn(self, msg: str, component: str = "master") -> None:
        self.log("WARNING", msg, component=component)

    def error(
        self,
        msg: str,
        component: str = "master",
        exc_info: Optional[BaseException] = None,
    ) -> None:
        self.log("ERROR", msg, component=component, exc_info=exc_info)

    def read_tail_chunks(
        self,
        last_offset: int = 0,
        last_inode: Optional[int] = None,
    ) -> Tuple[str, int, Optional[int]]:
        """
        Reads newly appended log bytes from the active log file without holding a persistent handle.
        Detects log truncation or file rotation and automatically resets read offset to 0.
        """
        return read_log_file_tail(self.log_file, last_offset=last_offset, last_inode=last_inode)


# ==============================================================================
# 5. Functional Rolling File & JSONL Ledger Helpers
# ==============================================================================


def _parse_jsonl_dict_line(line: str) -> Optional[Dict[str, Any]]:
    """Parses a single JSONL line; returns the dict if valid, else None."""
    s = line.strip()
    if not s:
        return None
    try:
        item = json.loads(s)
        return item if isinstance(item, dict) else None
    except Exception:
        return None


def _rotate_lines_file(
    target_path: Path,
    keep_lines: int,
    *,
    jsonl_only: bool = False,
) -> None:
    """Atomically truncates `target_path` to retain only the newest `keep_lines` lines."""
    try:
        raw_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
        target_keep = max(1, keep_lines)
        kept_reversed: List[str] = []
        for ln in reversed(raw_lines):
            if jsonl_only:
                if _parse_jsonl_dict_line(ln) is not None:
                    kept_reversed.append(ln.strip())
            else:
                if ln.strip():
                    kept_reversed.append(ln)
            if len(kept_reversed) >= target_keep:
                break

        kept_reversed.reverse()
        kept = kept_reversed
        tmp_path = target_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            tmp_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            _safe_replace_file(str(tmp_path), str(target_path))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def log_file(
    target: PathTarget,
    line: str,
    *,
    max_bytes: int = 0,
    keep_lines: int = 0,
) -> bool:
    """
    Appends a single text line to `target` (path or semantic URI), creating parent directories if needed.
    Optionally performs atomic line-retention truncation when file size exceeds `max_bytes`.
    Silently catches I/O exceptions and returns False on failure.
    """
    try:
        path = _resolve_log_target(target)
        if path is None:
            return False
        _, _, file_op_lock = _get_fallback_log_state()
        with file_op_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            out = line if line.endswith("\n") else f"{line}\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(out)
            if max_bytes > 0 and keep_lines > 0 and path.exists() and path.stat().st_size > max_bytes:
                _rotate_lines_file(path, keep_lines=keep_lines, jsonl_only=False)
        return True
    except Exception:
        return False


def log_file_jsonl(
    target: PathTarget,
    record: Dict[str, Any],
    *,
    max_bytes: int = 0,
    keep_lines: int = 0,
) -> bool:
    """
    Appends a structured dictionary as a JSONL line to `target` (path or semantic URI).
    When `max_bytes > 0` and file exceeds `max_bytes`, atomically rotates to retain `keep_lines` valid JSONL records.
    """
    try:
        if not isinstance(record, dict):
            return False
        path = _resolve_log_target(target)
        if path is None:
            return False
        line_str = json.dumps(record, ensure_ascii=False) + "\n"
        _, _, file_op_lock = _get_fallback_log_state()
        with file_op_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line_str)
            if max_bytes > 0 and keep_lines > 0 and path.exists() and path.stat().st_size > max_bytes:
                _rotate_lines_file(path, keep_lines=keep_lines, jsonl_only=True)
        return True
    except Exception:
        return False


def read_log_file_jsonl(
    target: PathTarget,
    *,
    limit: Optional[int] = None,
    filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> List[Dict[str, Any]]:
    """
    Reads valid JSONL dictionary records from `target`, skipping malformed lines.
    Supports optional `filter_fn` predicate and tail `limit`.
    """
    try:
        path = _resolve_log_target(target)
        if path is None or not path.is_file():
            return []

        records: List[Dict[str, Any]] = []
        if filter_fn is None and limit is not None and limit > 0:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_lines = f.readlines()
            for line in reversed(raw_lines):
                item = _parse_jsonl_dict_line(line)
                if item is None:
                    continue
                records.append(item)
                if len(records) >= limit:
                    break
            records.reverse()
            return records

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                item = _parse_jsonl_dict_line(line)
                if item is None:
                    continue
                if filter_fn is not None and not filter_fn(item):
                    continue
                records.append(item)

        if limit is not None and limit > 0 and len(records) > limit:
            records = records[-limit:]
        return records
    except Exception:
        return []


def read_log_file_tail(
    target: PathTarget,
    last_offset: int = 0,
    last_inode: Optional[int] = None,
) -> Tuple[str, int, Optional[int]]:
    """
    Reads newly appended bytes from `target` starting at `last_offset`.
    Automatically resets offset to 0 if the file was truncated or rotated (inode changed).
    """
    path = _resolve_log_target(target)
    if path is None or not path.exists():
        return "", 0, None

    file_str = str(path)
    try:
        st = os.stat(file_str)
        curr_size = st.st_size
        curr_ino = st.st_ino if st.st_ino != 0 else None

        offset = max(0, last_offset)
        if curr_size < offset or (last_inode is not None and curr_ino is not None and curr_ino != last_inode):
            offset = 0

        if curr_size == offset:
            return "", offset, curr_ino

        with open(file_str, "rb") as f:
            if offset > 0:
                f.seek(offset)
            raw = f.read()
            new_offset = f.tell()

        return raw.decode("utf-8", errors="replace"), new_offset, curr_ino
    except OSError:
        return "", last_offset, last_inode


__all__ = (
    "PathTarget",
    "LogExecutionScope",
    "bind_log_context",
    "get_current_log_scope",
    "log",
    "log_stream",
    "log_info",
    "log_warn",
    "log_error",
    "log_debug",
    "extract_error_hint",
    "record_error_hint",
    "get_last_error_hint",
    "clear_error_hint",
    "_StreamProxy",
    "DebouncedIOStreamer",
    "_extract_log_file_timestamp",
    "_safe_replace_file",
    "RollingFileLogger",
    "log_file",
    "log_file_jsonl",
    "read_log_file_jsonl",
    "read_log_file_tail",
)
