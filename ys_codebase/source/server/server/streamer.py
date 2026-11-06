"""
Server Module - Debounced IO Streamer.

Captures stdout and stderr with 500ms debounce flush, packaging stream chunks
into structured NDJSON packets ("terminal_stream" vs "task_finish").
"""

import io
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple


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
