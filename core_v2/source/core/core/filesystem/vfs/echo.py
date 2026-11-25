"""Self-write echo suppression guard structurally matching execution.runtime.VfsEchoGuardPort."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
import threading
import time

from core.foundation.primitives import HostPath, require_pure_int, safe_real_to_float


@dataclass(frozen=True, slots=True)
class _VfsEchoStamp:
    mtime_ns: int
    size: int
    ino: int
    expires_at: float


class VfsEchoGuard:
    """Bounded TTL + LRU echo guard keyed by canonical HostPath with zero execution-layer imports."""

    def __init__(self, *, ttl_sec: float = 5.0, max_entries: int = 2048) -> None:
        f_ttl = safe_real_to_float(ttl_sec, label="ttl_sec")
        if not math.isfinite(f_ttl) or f_ttl <= 0.0:
            raise ValueError(f"VfsEchoGuard ttl_sec must be finite and > 0, got {ttl_sec!r}")
        safe_max = require_pure_int(max_entries, "max_entries", min_val=1)
        self._ttl_sec = f_ttl
        self._max_entries = safe_max
        self._lock = threading.Lock()
        self._entries: OrderedDict[HostPath, list[_VfsEchoStamp]] = OrderedDict()
        self._total_stamps = 0

    def record_write(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> None:
        if not isinstance(path, HostPath):
            raise ValueError(f"VfsEchoGuard.record_write requires HostPath, got {path!r}")
        c_mtime = require_pure_int(mtime_ns, "mtime_ns", min_val=-1, max_val=None)
        c_size = require_pure_int(size, "size", min_val=-1, max_val=None)
        c_ino = require_pure_int(ino, "ino", min_val=-1, max_val=None)
        now = time.monotonic()
        stamp = _VfsEchoStamp(
            mtime_ns=c_mtime,
            size=c_size,
            ino=c_ino,
            expires_at=now + self._ttl_sec,
        )
        with self._lock:
            self._prune_expired_locked(now)
            bucket = self._entries.get(path)
            if bucket is None:
                bucket = []
                self._entries[path] = bucket
            else:
                self._entries.move_to_end(path)
            for idx, existing in enumerate(bucket):
                if existing.mtime_ns == c_mtime and existing.size == c_size and existing.ino == c_ino:
                    bucket[idx] = stamp
                    return
            bucket.append(stamp)
            self._total_stamps += 1
            self._evict_overflow_locked()

    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> bool:
        if not isinstance(path, HostPath):
            raise ValueError(f"VfsEchoGuard.is_suppressed requires HostPath, got {path!r}")
        c_mtime = require_pure_int(mtime_ns, "mtime_ns", min_val=-1, max_val=None)
        c_size = require_pure_int(size, "size", min_val=-1, max_val=None)
        c_ino = require_pure_int(ino, "ino", min_val=-1, max_val=None)
        now = time.monotonic()
        with self._lock:
            bucket = self._entries.get(path)
            if bucket is None:
                return False
            kept = [st for st in bucket if st.expires_at >= now]
            removed = len(bucket) - len(kept)
            if removed:
                self._total_stamps = max(0, self._total_stamps - removed)
                if not kept:
                    self._entries.pop(path, None)
                    return False
                self._entries[path] = kept
            return any(
                st.mtime_ns == c_mtime
                and st.size == c_size
                and (st.ino == c_ino or st.ino == 0 or c_ino == 0)
                for st in kept
            )

    def _prune_expired_locked(self, now: float) -> None:
        dead_keys: list[HostPath] = []
        for hp, bucket in self._entries.items():
            kept = [st for st in bucket if st.expires_at >= now]
            diff = len(bucket) - len(kept)
            if diff:
                self._total_stamps = max(0, self._total_stamps - diff)
                if kept:
                    self._entries[hp] = kept
                else:
                    dead_keys.append(hp)
        for hp in dead_keys:
            self._entries.pop(hp, None)

    def _evict_overflow_locked(self) -> None:
        while self._total_stamps > self._max_entries and self._entries:
            _oldest_hp, bucket = next(iter(self._entries.items()))
            if len(bucket) <= 1:
                self._entries.popitem(last=False)
                self._total_stamps = max(0, self._total_stamps - len(bucket))
            else:
                bucket.pop(0)
                self._total_stamps = max(0, self._total_stamps - 1)
