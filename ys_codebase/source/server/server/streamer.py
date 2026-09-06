"""
Server Module - Debounced IO Streamer.

Captures stdout and stderr with 500ms debounce flush, packaging stream chunks
into structured NDJSON packets ("terminal_stream" vs "task_finish").
"""

import io
import json
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class DebouncedIOStreamer:
    """
    Thread-safe debounced stream interceptor for stdout & stderr.
    Buffers terminal chunks and flushes every `debounce_ms` (default 500ms),
    or immediately upon newline / explicit flush / close.
    """

    def __init__(
        self,
        emit_chunk: Callable[[Dict[str, Any]], None],
        debounce_ms: int = 500,
    ) -> None:
        self.emit_chunk = emit_chunk
        self.debounce_sec = debounce_ms / 1000.0
        self._lock = threading.Lock()
        self._buffer: List[Dict[str, str]] = []
        self._timer: Optional[threading.Timer] = None
        self._last_flush_time = time.time()
        self._is_closed = False

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        self._stdout_proxy = _StreamProxy(self, "stdout")
        self._stderr_proxy = _StreamProxy(self, "stderr")

    def write(self, stream_name: str, text: str) -> None:
        if not text:
            return

        with self._lock:
            if self._is_closed:
                return

            self._buffer.append({"stream": stream_name, "text": text})

            # Check if buffer contains a newline or exceeds debounce interval
            now = time.time()
            has_newline = "\n" in text
            time_since_flush = now - self._last_flush_time

            if has_newline or time_since_flush >= self.debounce_sec:
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
            self._last_flush_time = time.time()
            return

        # Consolidate buffer into stream segments
        consolidated: Dict[str, List[str]] = {}
        for item in self._buffer:
            s_name = item["stream"]
            if s_name not in consolidated:
                consolidated[s_name] = []
            consolidated[s_name].append(item["text"])

        self._buffer.clear()
        self._last_flush_time = time.time()

        for s_name, chunks in consolidated.items():
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
        """Flushes remaining terminal stream and sends task_finish packet."""
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
        sys.stdout = self._stdout_proxy  # type: ignore
        sys.stderr = self._stderr_proxy  # type: ignore
        return self

    def stop_capture(self) -> None:
        self.flush()
        with self._lock:
            self._is_closed = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr

    def __enter__(self) -> "DebouncedIOStreamer":
        return self.start_capture()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_capture()


class _StreamProxy(io.TextIOBase):
    """Proxy object redirecting writes to DebouncedIOStreamer."""

    def __init__(self, streamer: DebouncedIOStreamer, stream_name: str) -> None:
        self._streamer = streamer
        self._stream_name = stream_name

    def write(self, s: str) -> int:
        self._streamer.write(self._stream_name, s)
        return len(s)

    def flush(self) -> None:
        self._streamer.flush()
