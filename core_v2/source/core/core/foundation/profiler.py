"""ImTK-style hierarchical execution profiler, memory guard, sensitive redaction, and 3+1 JSONL flight logs."""

from __future__ import annotations

from collections import deque
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import inspect
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import tracemalloc
from types import MappingProxyType
from typing import Final, Mapping, Optional, Protocol, Sequence

from core.foundation.errors import YscbError, sanitize_utf8_text
from core.foundation.observability import LogLevel, LogRotator
from core.foundation.primitives import (
    FORCE_FLIGHT_LOGS_ENV_KEY,
    INT64_MAX,
    INT64_MIN,
    IS_WINDOWS,
    MAX_USER_JSON_DEPTH,
    TEST_SANDBOX_ENV_KEY,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    clone_strict_json_object,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
    safe_real_to_float,
)

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _WinProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    _PROF_K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _PROF_GET_CURRENT_PROC = _PROF_K32.GetCurrentProcess
    _PROF_GET_CURRENT_PROC.argtypes = []
    _PROF_GET_CURRENT_PROC.restype = wintypes.HANDLE
    _PROF_K32_MEM_INFO = _PROF_K32.K32GetProcessMemoryInfo
    _PROF_K32_MEM_INFO.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WinProcessMemoryCounters),
        wintypes.DWORD,
    ]
    _PROF_K32_MEM_INFO.restype = wintypes.BOOL
else:
    import resource

_REDACTED_LITERAL: Final[str] = "[REDACTED]"
_MAX_CALLERS_PER_NODE: Final[int] = 16
_LEGACY_TEST_SANDBOX_ENV_KEY: Final[str] = "YSCB_TEST_SANDBOX"
_TRUTHY_ENV_STRINGS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_SENSITIVE_KEY_TOKENS: Final[tuple[str, ...]] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "auth",
    "credential",
    "cookie",
    "bearer",
    "private_key",
    "private-key",
    "_yscb_",
)
_SENSITIVE_CLI_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--approve",
        "--token",
        "--secret",
        "--password",
        "--passwd",
        "--api-key",
        "--apikey",
        "--auth",
        "--credential",
        "--cookie",
        "--bearer",
        "--private-key",
    }
)
_URL_CRED_RE: Final[re.Pattern[str]] = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s@:]+):([^/\s@]+)@")
_BEARER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bBearer\s+\S+")
_DATE_STR_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAEMON_LOG_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^daemon_\d{8}_\d{6}_\d+_[A-Za-z0-9_-]+\.jsonl$")
_BOOT_SAFE_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_-]+")


def _read_linux_rss_kb() -> int:
    try:
        status_text = Path("/proc/self/status").read_text(encoding="utf-8", errors="ignore")
        for line in status_text.splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return int(parts[1])
    except OSError:
        pass
    try:
        statm_parts = Path("/proc/self/statm").read_text(encoding="utf-8", errors="ignore").split()
        if len(statm_parts) >= 2 and statm_parts[1].isdigit():
            page_size = os.sysconf("SC_PAGE_SIZE")
            return max(0, (int(statm_parts[1]) * int(page_size)) // 1024)
    except (OSError, ValueError, AttributeError):
        pass
    return 0


def _read_windows_rss_kb() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        counters = _WinProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = _PROF_GET_CURRENT_PROC()
        if _PROF_K32_MEM_INFO(handle, ctypes.byref(counters), counters.cb):
            return max(0, int(counters.WorkingSetSize) // 1024)
    except OSError:
        pass
    return 0


def read_process_rss_kb() -> int:
    """Return the current process resident set size (RSS) in KiB, or 0 if unavailable."""
    if IS_WINDOWS:
        return _read_windows_rss_kb()
    if sys.platform.startswith("linux"):
        linux_rss = _read_linux_rss_kb()
        if linux_rss > 0:
            return linux_rss
    try:
        max_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (OSError, ValueError):
        return 0
    if max_rss <= 0:
        return 0
    return max_rss // 1024 if sys.platform == "darwin" else max_rss


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    if not lowered:
        return False
    return any(tok in lowered for tok in _SENSITIVE_KEY_TOKENS)


def is_sensitive_key(key: str) -> bool:
    """Return True when a configuration or telemetry key name matches a sensitive credential pattern."""
    require_pure_str(key, "is_sensitive_key.key")
    return _is_sensitive_key(key)


def _scrub_inline_secrets(text: str) -> str:
    scrubbed = _URL_CRED_RE.sub(r"\1[REDACTED]@", text)
    return _BEARER_TOKEN_RE.sub("Bearer [REDACTED]", scrubbed)


def _redact_value_recursive(value: JsonValue, *, key_hint: str, depth: int) -> JsonValue:
    if depth > MAX_USER_JSON_DEPTH:
        return _REDACTED_LITERAL
    if _is_sensitive_key(key_hint):
        if value is None:
            return None
        if isinstance(value, str) and not value:
            return ""
        return _REDACTED_LITERAL
    if isinstance(value, Mapping):
        out_map: MutableJsonObject = {}
        for k, v in value.items():
            k_str = k if type(k) is str else str(k)
            out_map[k_str] = _redact_value_recursive(v, key_hint=k_str, depth=depth + 1)
        return out_map
    if isinstance(value, list):
        return [_redact_value_recursive(item, key_hint="", depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value_recursive(item, key_hint="", depth=depth + 1) for item in value)
    if isinstance(value, str):
        return _scrub_inline_secrets(value)
    return value


def redact_sensitive_value(value: JsonValue, *, key_hint: str = "") -> JsonValue:
    """Recursively redact sensitive fields, URL credentials, and bearer tokens without mutating inputs."""
    require_pure_str(key_hint, "redact_sensitive_value.key_hint")
    return _redact_value_recursive(value, key_hint=key_hint, depth=0)


def redact_cli_args(args: Sequence[str]) -> tuple[str, ...]:
    """Return a non-mutating redacted copy of CLI argument tokens safe for disk flight logs."""
    raw_args = require_typed_tuple(args, str, "redact_cli_args.args")
    out: list[str] = []
    redact_next = False
    seen_config = False
    in_config_set = False
    redact_next_config_val = False
    config_set_pos = 0
    after_double_dash = False
    has_local_flag = any(tok == "--local" or tok.startswith("--local=") for tok in raw_args)
    for tok in raw_args:
        if redact_next:
            out.append(_REDACTED_LITERAL)
            redact_next = False
            continue
        if not after_double_dash and tok == "--":
            after_double_dash = True
            out.append(tok)
            continue
        is_positional = after_double_dash or not tok.startswith("-")
        if in_config_set and is_positional:
            if redact_next_config_val or (has_local_flag and config_set_pos == 2):
                out.append(_REDACTED_LITERAL)
                redact_next_config_val = False
                config_set_pos += 1
                continue
            if config_set_pos == 1 and _is_sensitive_key(tok):
                redact_next_config_val = True
            config_set_pos += 1
            out.append(_scrub_inline_secrets(tok))
            continue
        if "=" in tok and not after_double_dash:
            lhs, _, rhs = tok.partition("=")
            lhs_lower = lhs.lower()
            is_flag_secret = lhs_lower in _SENSITIVE_CLI_FLAGS or (
                lhs.startswith("-") and _is_sensitive_key(lhs.lstrip("-"))
            )
            is_kv_secret = (not lhs.startswith("-")) and _is_sensitive_key(lhs)
            if is_flag_secret or is_kv_secret:
                out.append(f"{lhs}={_REDACTED_LITERAL}")
            else:
                out.append(f"{lhs}={_scrub_inline_secrets(rhs)}")
            continue
        tok_lower = tok.lower()
        if not after_double_dash and (
            tok_lower in _SENSITIVE_CLI_FLAGS or (tok.startswith("--") and _is_sensitive_key(tok[2:]))
        ):
            out.append(tok)
            redact_next = True
            continue
        if is_positional:
            if tok == "core.config.set":
                in_config_set = True
                config_set_pos = 0
            elif seen_config and tok == "set":
                in_config_set = True
                config_set_pos = 0
            elif tok == "config":
                seen_config = True
        out.append(_scrub_inline_secrets(tok))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ProfilerNodeSnapshot:
    """Immutable snapshot of a single node in a hierarchical profiler timing tree."""

    name: str
    self_ms: float
    total_ms: float
    calls: int
    alloc_kb: float = 0.0
    callers: tuple[str, ...] = ()
    children: tuple[ProfilerNodeSnapshot, ...] = ()

    def __post_init__(self) -> None:
        require_pure_str(self.name, "ProfilerNodeSnapshot.name", non_empty=True)
        self_val = safe_real_to_float(self.self_ms, label="ProfilerNodeSnapshot.self_ms")
        total_val = safe_real_to_float(self.total_ms, label="ProfilerNodeSnapshot.total_ms")
        alloc_val = safe_real_to_float(self.alloc_kb, label="ProfilerNodeSnapshot.alloc_kb")
        if not math.isfinite(self_val) or self_val < 0.0:
            raise ValueError(f"ProfilerNodeSnapshot.self_ms must be finite and >= 0, got {self.self_ms!r}")
        if not math.isfinite(total_val) or total_val < 0.0:
            raise ValueError(f"ProfilerNodeSnapshot.total_ms must be finite and >= 0, got {self.total_ms!r}")
        if not math.isfinite(alloc_val):
            raise ValueError(f"ProfilerNodeSnapshot.alloc_kb must be finite, got {self.alloc_kb!r}")
        require_pure_int(self.calls, "ProfilerNodeSnapshot.calls", min_val=0, max_val=INT64_MAX)
        clean_callers = require_typed_tuple(self.callers, str, "ProfilerNodeSnapshot.callers")
        clean_children = require_typed_tuple(self.children, ProfilerNodeSnapshot, "ProfilerNodeSnapshot.children")
        object.__setattr__(self, "self_ms", self_val)
        object.__setattr__(self, "total_ms", total_val)
        object.__setattr__(self, "alloc_kb", alloc_val)
        object.__setattr__(self, "callers", clean_callers)
        object.__setattr__(self, "children", clean_children)


def _encode_profiler_snapshot(snap: ProfilerNodeSnapshot) -> MutableJsonObject:
    return {
        "name": snap.name,
        "self_ms": snap.self_ms,
        "total_ms": snap.total_ms,
        "calls": snap.calls,
        "alloc_kb": snap.alloc_kb,
        "callers": list(snap.callers),
        "children": [_encode_profiler_snapshot(ch) for ch in snap.children],
    }


def _check_existing_snapshot_bounds(
    node: ProfilerNodeSnapshot,
    *,
    depth: int,
    max_depth: int,
    max_nodes: int,
    counter: list[int],
) -> bool:
    if depth > max_depth:
        return False
    counter[0] += 1
    if counter[0] > max_nodes:
        return False
    for ch in node.children:
        if not _check_existing_snapshot_bounds(
            ch, depth=depth + 1, max_depth=max_depth, max_nodes=max_nodes, counter=counter
        ):
            return False
    return True


def _decode_snapshot_node(
    raw: object,
    *,
    depth: int,
    max_depth: int,
    max_nodes: int,
    counter: list[int],
) -> Optional[ProfilerNodeSnapshot]:
    if depth > max_depth or not isinstance(raw, Mapping):
        return None
    counter[0] += 1
    if counter[0] > max_nodes:
        return None
    raw_callers = raw.get("callers", ())
    raw_children = raw.get("children", ())
    if not isinstance(raw_callers, (list, tuple)) or len(raw_callers) > 64:
        return None
    if not isinstance(raw_children, (list, tuple)):
        return None
    decoded_children: list[ProfilerNodeSnapshot] = []
    for ch_raw in raw_children:
        ch_snap = _decode_snapshot_node(
            ch_raw, depth=depth + 1, max_depth=max_depth, max_nodes=max_nodes, counter=counter
        )
        if ch_snap is None:
            return None
        decoded_children.append(ch_snap)
    try:
        return ProfilerNodeSnapshot(
            name=require_pure_str(raw.get("name"), "name", non_empty=True),
            self_ms=safe_real_to_float(raw.get("self_ms"), label="self_ms"),
            total_ms=safe_real_to_float(raw.get("total_ms"), label="total_ms"),
            calls=require_pure_int(raw.get("calls"), "calls", min_val=0, max_val=INT64_MAX),
            alloc_kb=safe_real_to_float(raw.get("alloc_kb", 0.0), label="alloc_kb"),
            callers=require_typed_tuple(raw_callers, str, "callers"),
            children=tuple(decoded_children),
        )
    except ValueError:
        return None


def decode_profiler_snapshot(
    raw: object,
    *,
    max_depth: int = 32,
    max_nodes: int = 512,
) -> Optional[ProfilerNodeSnapshot]:
    """Fail-open decoder for untrusted profiler snapshot payloads with strict depth and node caps."""
    require_pure_int(max_depth, "decode_profiler_snapshot.max_depth", min_val=1, max_val=256)
    require_pure_int(max_nodes, "decode_profiler_snapshot.max_nodes", min_val=1, max_val=100000)
    if raw is None:
        return None
    counter = [0]
    if isinstance(raw, ProfilerNodeSnapshot):
        return (
            raw
            if _check_existing_snapshot_bounds(
                raw, depth=1, max_depth=max_depth, max_nodes=max_nodes, counter=counter
            )
            else None
        )
    return _decode_snapshot_node(raw, depth=1, max_depth=max_depth, max_nodes=max_nodes, counter=counter)


@dataclass(frozen=True, slots=True)
class _TreeRow:
    label: str
    pct_str: str
    total_str: str
    self_str: str
    calls_str: str
    alloc_str: str
    callers_str: str


def _collect_tree_rows(
    node: ProfilerNodeSnapshot,
    *,
    prefix: str,
    connector: str,
    parent_total_ms: Optional[float],
    include_mem: bool,
    include_callers: bool,
    rows: list[_TreeRow],
) -> None:
    if parent_total_ms is None:
        pct = 100.0 if node.total_ms > 0.0 else 0.0
    elif parent_total_ms > 0.0:
        pct = (node.total_ms / parent_total_ms) * 100.0
    else:
        pct = 0.0
    rows.append(
        _TreeRow(
            label=f"{prefix}{connector}{node.name}",
            pct_str=f"{pct:5.1f}%",
            total_str=f"{node.total_ms:8.2f}",
            self_str=f"{node.self_ms:8.2f}",
            calls_str=f"{node.calls:5d}",
            alloc_str=f"{node.alloc_kb:+9.1f}" if include_mem else "",
            callers_str=", ".join(node.callers) if include_callers else "",
        )
    )
    child_count = len(node.children)
    for idx, ch in enumerate(node.children):
        is_last = idx == child_count - 1
        next_prefix = prefix + ("" if not connector else ("   " if connector == "\\- " else "|  "))
        next_conn = "\\- " if is_last else "|- "
        _collect_tree_rows(
            ch,
            prefix=next_prefix,
            connector=next_conn,
            parent_total_ms=node.total_ms,
            include_mem=include_mem,
            include_callers=include_callers,
            rows=rows,
        )


def render_profiler_tree(
    root: ProfilerNodeSnapshot,
    *,
    include_mem: bool = False,
    include_callers: bool = True,
) -> str:
    """Render a ProfilerNodeSnapshot as an ImTK-style indented waterfall timing table."""
    if not isinstance(root, ProfilerNodeSnapshot):
        raise ValueError(f"render_profiler_tree requires ProfilerNodeSnapshot, got {root!r}")
    require_pure_bool(include_mem, "render_profiler_tree.include_mem")
    require_pure_bool(include_callers, "render_profiler_tree.include_callers")
    rows: list[_TreeRow] = []
    _collect_tree_rows(
        root,
        prefix="",
        connector="",
        parent_total_ms=None,
        include_mem=include_mem,
        include_callers=include_callers,
        rows=rows,
    )
    scope_width = max(len("Scope"), *(len(row.label) for row in rows))
    header_parts = [
        f"{'Scope':<{scope_width}}",
        f"{'%Parent':>7}",
        f"{'Total ms':>8}",
        f"{'Self ms':>8}",
        f"{'Calls':>5}",
    ]
    if include_mem:
        header_parts.append(f"{'Alloc KB':>9}")
    if include_callers:
        header_parts.append("Callers")
    header = "  ".join(header_parts)
    lines = [header, "-" * max(len(header), scope_width + 38)]
    for row in rows:
        cols = [
            f"{row.label:<{scope_width}}",
            f"{row.pct_str:>7}",
            row.total_str,
            row.self_str,
            row.calls_str,
        ]
        if include_mem:
            cols.append(row.alloc_str)
        if include_callers and row.callers_str:
            cols.append(row.callers_str)
        lines.append("  ".join(cols).rstrip())
    return "\n".join(lines)


class Profiler(Protocol):
    """Protocol for hierarchical execution timing and optional memory attribution."""

    def scope(
        self,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]: ...

    def scope_relative(
        self,
        path: str,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]: ...

    def merge_subtree(
        self,
        subtree: ProfilerNodeSnapshot,
        *,
        mount_path: Optional[str] = None,
    ) -> None: ...

    def snapshot(self) -> ProfilerNodeSnapshot: ...

    def current_span_path(self) -> str: ...


class _NullScopeGuard(AbstractContextManager[None]):
    __slots__ = ()

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        _ = (exc_type, exc_val, exc_tb)


class NullProfiler:
    """Zero-overhead no-op Profiler implementation used when profiling is disabled."""

    def scope(
        self,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        _ = (path, name, caller)
        return _NullScopeGuard()

    def scope_relative(
        self,
        path: str,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        _ = (path, name, caller)
        return _NullScopeGuard()

    def merge_subtree(
        self,
        subtree: ProfilerNodeSnapshot,
        *,
        mount_path: Optional[str] = None,
    ) -> None:
        _ = (subtree, mount_path)

    def snapshot(self) -> ProfilerNodeSnapshot:
        return ProfilerNodeSnapshot(name="Root", self_ms=0.0, total_ms=0.0, calls=0)

    def current_span_path(self) -> str:
        return ""


def _capture_caller_site(skip_frames: int = 3) -> Optional[str]:
    frame = inspect.currentframe()
    try:
        for _ in range(skip_frames):
            if frame is None:
                return None
            frame = frame.f_back
        if frame is None:
            return None
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno
        base = os.path.basename(filename) if filename else "<unknown>"
        return f"{base}:{lineno}"
    finally:
        del frame


@dataclass(slots=True)
class _ProfilerNode:
    name: str
    full_path: str
    self_ns: int = 0
    calls: int = 0
    self_alloc_bytes: int = 0
    callers: list[str] = field(default_factory=list)
    children: dict[str, _ProfilerNode] = field(default_factory=dict)


@dataclass(slots=True)
class _ActiveScopeFrame:
    node: _ProfilerNode
    start_ns: int
    nested_child_ns: int = 0
    start_alloc_bytes: Optional[int] = None
    nested_child_alloc_bytes: int = 0


class _ThreadScopeLocal(threading.local):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[_ActiveScopeFrame] = []


@dataclass(frozen=True, slots=True)
class _SnapshotAccum:
    snap: ProfilerNodeSnapshot
    total_ns: int
    total_alloc_bytes: int


def _parse_scope_segments(path: Optional[str], name: Optional[str], *, require_path: bool) -> list[str]:
    segs: list[str] = []
    if path is not None:
        require_pure_str(path, "profiler scope path", non_empty=require_path)
        for raw_seg in path.split("/"):
            cleaned = raw_seg.strip()
            if cleaned:
                segs.append(cleaned)
    if name is not None:
        clean_name = require_pure_str(name, "profiler scope name").strip()
        if clean_name:
            segs.append(clean_name)
    return segs


def _get_or_create_node(anchor: _ProfilerNode, segments: Sequence[str]) -> _ProfilerNode:
    cur = anchor
    for seg in segments:
        nxt = cur.children.get(seg)
        if nxt is None:
            child_path = f"{cur.full_path}/{seg}" if cur.full_path else seg
            nxt = _ProfilerNode(name=seg, full_path=child_path)
            cur.children[seg] = nxt
        cur = nxt
    return cur


def _record_node_caller(node: _ProfilerNode, caller_tag: str) -> None:
    if not caller_tag:
        return
    if caller_tag not in node.callers and len(node.callers) < _MAX_CALLERS_PER_NODE:
        node.callers.append(caller_tag)


def _merge_node_recursive(target: _ProfilerNode, src: ProfilerNodeSnapshot) -> None:
    target.self_ns += int(round(src.self_ms * 1_000_000.0))
    target.calls += src.calls
    child_alloc_kb = sum(ch.alloc_kb for ch in src.children)
    target.self_alloc_bytes += int(round((src.alloc_kb - child_alloc_kb) * 1024.0))
    for caller_tag in src.callers:
        _record_node_caller(target, caller_tag)
    for child_snap in src.children:
        child_node = _get_or_create_node(target, (child_snap.name,))
        _merge_node_recursive(child_node, child_snap)


def _build_snapshot_accum(node: _ProfilerNode) -> _SnapshotAccum:
    child_accums = [_build_snapshot_accum(ch) for ch in node.children.values()]
    child_accums.sort(key=lambda acc: (-acc.total_ns, acc.snap.name))
    total_ns = node.self_ns + sum(acc.total_ns for acc in child_accums)
    total_alloc = node.self_alloc_bytes + sum(acc.total_alloc_bytes for acc in child_accums)
    snap = ProfilerNodeSnapshot(
        name=node.name,
        self_ms=round(node.self_ns / 1_000_000.0, 4),
        total_ms=round(total_ns / 1_000_000.0, 4),
        calls=node.calls,
        alloc_kb=round(total_alloc / 1024.0, 4),
        callers=tuple(node.callers),
        children=tuple(acc.snap for acc in child_accums),
    )
    return _SnapshotAccum(snap=snap, total_ns=total_ns, total_alloc_bytes=total_alloc)


class _ScopeGuard(AbstractContextManager[None]):
    __slots__ = ("_state", "_segs", "_relative", "_anchor_to_current", "_caller", "_frame", "_exited")

    def __init__(
        self,
        state: _ProfilerState,
        segs: list[str],
        *,
        relative: bool,
        anchor_to_current: bool,
        caller: Optional[str],
    ) -> None:
        self._state = state
        self._segs = segs
        self._relative = relative
        self._anchor_to_current = anchor_to_current
        self._caller = caller
        self._frame: Optional[_ActiveScopeFrame] = None
        self._exited = False

    def __enter__(self) -> None:
        if self._frame is None and not self._exited:
            self._frame = self._state.begin_scope(
                self._segs,
                anchor_to_current=self._anchor_to_current,
                caller=self._caller,
            )
        return None

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        _ = (exc_type, exc_val, exc_tb)
        if not self._exited:
            self._exited = True
            if self._frame is not None:
                self._state.exit_scope(self._frame)


class _ProfilerState:
    def __init__(self, root_name: str, *, track_memory: bool, capture_callers: bool) -> None:
        self._root = _ProfilerNode(name=root_name, full_path="")
        self._lock = threading.RLock()
        self._local = _ThreadScopeLocal()
        self.track_memory = track_memory
        self._capture_callers = capture_callers

    def enter_scope(
        self,
        path: Optional[str],
        name: Optional[str],
        *,
        relative: bool,
        caller: Optional[str],
    ) -> _ScopeGuard:
        if caller is not None:
            require_pure_str(caller, "profiler scope caller")
        segs = _parse_scope_segments(path, name, require_path=relative)
        if not segs:
            if relative:
                raise ValueError("ProfilerSession.scope_relative requires a non-empty path or name.")
            segs = ["<scope>"]
        eff_caller = caller
        if eff_caller is None and self._capture_callers:
            eff_caller = _capture_caller_site(skip_frames=3)
        return _ScopeGuard(
            self,
            segs,
            relative=relative,
            anchor_to_current=bool(relative or path is None),
            caller=eff_caller,
        )

    def begin_scope(
        self,
        segs: Sequence[str],
        *,
        anchor_to_current: bool,
        caller: Optional[str],
    ) -> _ActiveScopeFrame:
        stack = self._local.stack
        anchor = (stack[-1].node if stack else self._root) if anchor_to_current else self._root
        with self._lock:
            node = _get_or_create_node(anchor, segs)
            if caller is not None:
                _record_node_caller(node, caller)
        start_alloc: Optional[int] = None
        if self.track_memory and tracemalloc.is_tracing():
            start_alloc = tracemalloc.get_traced_memory()[0]
        frame = _ActiveScopeFrame(node=node, start_ns=time.perf_counter_ns(), start_alloc_bytes=start_alloc)
        stack.append(frame)
        return frame

    def exit_scope(self, frame: _ActiveScopeFrame) -> None:
        end_ns = time.perf_counter_ns()
        end_alloc: Optional[int] = None
        if self.track_memory and frame.start_alloc_bytes is not None and tracemalloc.is_tracing():
            end_alloc = tracemalloc.get_traced_memory()[0]
        stack = self._local.stack
        if stack and stack[-1] is frame:
            stack.pop()
        elif frame in stack:
            stack.remove(frame)
        elapsed_ns = max(0, end_ns - frame.start_ns)
        self_delta_ns = max(0, elapsed_ns - frame.nested_child_ns)
        alloc_delta = (end_alloc - frame.start_alloc_bytes) if (end_alloc is not None and frame.start_alloc_bytes is not None) else 0
        self_alloc_delta = alloc_delta - frame.nested_child_alloc_bytes
        if stack:
            parent_frame = stack[-1]
            parent_frame.nested_child_ns += elapsed_ns
            parent_frame.nested_child_alloc_bytes += alloc_delta
        with self._lock:
            frame.node.calls += 1
            frame.node.self_ns += self_delta_ns
            frame.node.self_alloc_bytes += self_alloc_delta

    def merge_subtree(self, subtree: ProfilerNodeSnapshot, *, mount_path: Optional[str]) -> None:
        if not isinstance(subtree, ProfilerNodeSnapshot):
            raise ValueError(f"merge_subtree requires ProfilerNodeSnapshot, got {subtree!r}")
        if mount_path is not None:
            require_pure_str(mount_path, "merge_subtree.mount_path")
        stack = self._local.stack
        child_total_ns = int(round(subtree.total_ms * 1_000_000.0))
        with self._lock:
            if mount_path is not None and mount_path.strip():
                segs = _parse_scope_segments(mount_path, None, require_path=False)
                mount_node = _get_or_create_node(self._root, segs)
            elif stack:
                mount_node = stack[-1].node
            else:
                mount_node = self._root
            merge_into_root_directly = (
                mount_node is self._root
                and mount_path is None
                and not stack
                and subtree.name == self._root.name
            )
            if merge_into_root_directly:
                _merge_node_recursive(self._root, subtree)
                return
            active_match: Optional[_ActiveScopeFrame] = None
            for idx in range(len(stack) - 1, -1, -1):
                if stack[idx].node is mount_node:
                    active_match = stack[idx]
                    break
            if active_match is not None:
                active_match.nested_child_ns += child_total_ns
            else:
                mount_node.self_ns = max(0, mount_node.self_ns - child_total_ns)
            target_child = _get_or_create_node(mount_node, (subtree.name,))
            _merge_node_recursive(target_child, subtree)

    def snapshot(self) -> ProfilerNodeSnapshot:
        with self._lock:
            return _build_snapshot_accum(self._root).snap

    def current_span_path(self) -> str:
        stack = self._local.stack
        return stack[-1].node.full_path if stack else ""


class ProfilerSession:
    """Thread-safe ImTK-style hierarchical profiler session with zero module-level global state."""

    def __init__(
        self,
        root_name: str = "Root",
        *,
        track_memory: bool = False,
        capture_callers: bool = True,
    ) -> None:
        clean_root = require_pure_str(root_name, "ProfilerSession.root_name", non_empty=True).strip()
        require_pure_bool(track_memory, "ProfilerSession.track_memory")
        require_pure_bool(capture_callers, "ProfilerSession.capture_callers")
        self._state = _ProfilerState(
            clean_root,
            track_memory=track_memory,
            capture_callers=capture_callers,
        )

    @property
    def track_memory(self) -> bool:
        return self._state.track_memory

    def scope(
        self,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        return self._state.enter_scope(path, name, relative=False, caller=caller)

    def scope_relative(
        self,
        path: str,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        return self._state.enter_scope(path, name, relative=True, caller=caller)

    def merge_subtree(
        self,
        subtree: ProfilerNodeSnapshot,
        *,
        mount_path: Optional[str] = None,
    ) -> None:
        self._state.merge_subtree(subtree, mount_path=mount_path)

    def snapshot(self) -> ProfilerNodeSnapshot:
        return self._state.snapshot()

    def current_span_path(self) -> str:
        return self._state.current_span_path()


class MemoryTrackingGuard:
    """Idempotent context manager enabling tracemalloc only when requested and not already active."""

    def __init__(self, enabled: bool) -> None:
        require_pure_bool(enabled, "MemoryTrackingGuard.enabled")
        self._enabled = enabled
        self._started_by_guard = False

    def __enter__(self) -> MemoryTrackingGuard:
        if self._enabled and not tracemalloc.is_tracing():
            tracemalloc.start()
            self._started_by_guard = True
        else:
            self._started_by_guard = False
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        _ = (exc_type, exc_val, exc_tb)
        if self._started_by_guard:
            self._started_by_guard = False
            if tracemalloc.is_tracing():
                tracemalloc.stop()


@dataclass(frozen=True, slots=True)
class FlightLogConfig:
    """Retention, rotation, slow-threshold, and sandbox policy for 3+1 JSONL flight logs."""

    enabled: bool = True
    max_bytes_per_file: int = 5242880
    max_history_files: int = 3
    retention_days: int = 7
    max_daemon_files: int = 10
    slow_threshold_ms: float = 1000.0
    respect_sandbox: bool = True

    def __post_init__(self) -> None:
        require_pure_bool(self.enabled, "FlightLogConfig.enabled")
        require_pure_int(self.max_bytes_per_file, "FlightLogConfig.max_bytes_per_file", min_val=1, max_val=INT64_MAX)
        require_pure_int(self.max_history_files, "FlightLogConfig.max_history_files", min_val=0, max_val=1000)
        require_pure_int(self.retention_days, "FlightLogConfig.retention_days", min_val=1, max_val=3650)
        require_pure_int(self.max_daemon_files, "FlightLogConfig.max_daemon_files", min_val=1, max_val=1000)
        slow_val = safe_real_to_float(self.slow_threshold_ms, label="FlightLogConfig.slow_threshold_ms")
        if not math.isfinite(slow_val) or slow_val < 0.0:
            raise ValueError(
                f"FlightLogConfig.slow_threshold_ms must be finite and >= 0, got {self.slow_threshold_ms!r}"
            )
        object.__setattr__(self, "slow_threshold_ms", slow_val)
        require_pure_bool(self.respect_sandbox, "FlightLogConfig.respect_sandbox")


@dataclass(frozen=True, slots=True)
class DaemonLogRecord:
    """Daemon process lifecycle and hot RPC request summary JSONL record."""

    ts_utc: str
    epoch_ms: int
    daemon_boot_id: str
    pid: int
    event: str
    level: LogLevel = LogLevel.INFO
    trace_id: str = ""
    task_id: str = ""
    detail: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_pure_str(self.ts_utc, "DaemonLogRecord.ts_utc", non_empty=True)
        require_pure_int(self.epoch_ms, "DaemonLogRecord.epoch_ms", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.daemon_boot_id, "DaemonLogRecord.daemon_boot_id", non_empty=True)
        require_pure_int(self.pid, "DaemonLogRecord.pid", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.event, "DaemonLogRecord.event", non_empty=True)
        if not isinstance(self.level, LogLevel):
            raise ValueError(f"DaemonLogRecord.level must be LogLevel, got {self.level!r}")
        require_pure_str(self.trace_id, "DaemonLogRecord.trace_id")
        require_pure_str(self.task_id, "DaemonLogRecord.task_id")
        cloned = clone_strict_json_object(self.detail, label="DaemonLogRecord.detail")
        object.__setattr__(self, "detail", MappingProxyType(cloned))


@dataclass(frozen=True, slots=True)
class DailyEventRecord:
    """Daily cross-process backbone event record ([IN], [OUT], core events, and module warnings/errors)."""

    ts_utc: str
    epoch_ms: int
    kind: str
    trace_id: str
    daemon_boot_id: str
    pid: int
    exec_mode: str
    module: str
    task_id: str = ""
    level: LogLevel = LogLevel.INFO
    ok: Optional[bool] = None
    duration_ms: Optional[float] = None
    exit_code: Optional[int] = None
    message: str = ""
    fields: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_pure_str(self.ts_utc, "DailyEventRecord.ts_utc", non_empty=True)
        require_pure_int(self.epoch_ms, "DailyEventRecord.epoch_ms", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.kind, "DailyEventRecord.kind", non_empty=True)
        require_pure_str(self.trace_id, "DailyEventRecord.trace_id")
        require_pure_str(self.daemon_boot_id, "DailyEventRecord.daemon_boot_id")
        require_pure_int(self.pid, "DailyEventRecord.pid", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.exec_mode, "DailyEventRecord.exec_mode")
        require_pure_str(self.module, "DailyEventRecord.module")
        require_pure_str(self.task_id, "DailyEventRecord.task_id")
        if not isinstance(self.level, LogLevel):
            raise ValueError(f"DailyEventRecord.level must be LogLevel, got {self.level!r}")
        if self.ok is not None:
            require_pure_bool(self.ok, "DailyEventRecord.ok")
        if self.duration_ms is not None:
            dur = safe_real_to_float(self.duration_ms, label="DailyEventRecord.duration_ms")
            if not math.isfinite(dur) or dur < 0.0:
                raise ValueError(f"DailyEventRecord.duration_ms must be finite and >= 0, got {self.duration_ms!r}")
            object.__setattr__(self, "duration_ms", dur)
        if self.exit_code is not None:
            require_pure_int(self.exit_code, "DailyEventRecord.exit_code", min_val=INT64_MIN, max_val=INT64_MAX)
        object.__setattr__(
            self,
            "message",
            sanitize_utf8_text(require_pure_str(self.message, "DailyEventRecord.message")),
        )
        cloned = clone_strict_json_object(self.fields, label="DailyEventRecord.fields")
        object.__setattr__(self, "fields", MappingProxyType(cloned))


@dataclass(frozen=True, slots=True)
class ExecutionTraceRecord:
    """Execution performance trace JSONL record with task timings, RSS watermarks, and failure context."""

    ts_utc: str
    epoch_ms: int
    trace_id: str
    daemon_boot_id: str
    pid: int
    task_id: str
    args: tuple[str, ...]
    caller_mode: str
    caller_cwd: str
    executed_hot: bool
    exit_code: int
    ok: bool
    duration_ms: float
    rss_kb: int = 0
    rss_delta_kb: int = 0
    mem_tracked: bool = False
    dispatched_tasks: tuple[str, ...] = ()
    profiler_tree: Optional[ProfilerNodeSnapshot] = None
    error_code: str = ""
    error_detail: Optional[JsonObject] = None
    runtime_snapshot: Optional[JsonObject] = None

    def __post_init__(self) -> None:
        require_pure_str(self.ts_utc, "ExecutionTraceRecord.ts_utc", non_empty=True)
        require_pure_int(self.epoch_ms, "ExecutionTraceRecord.epoch_ms", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.trace_id, "ExecutionTraceRecord.trace_id")
        require_pure_str(self.daemon_boot_id, "ExecutionTraceRecord.daemon_boot_id")
        require_pure_int(self.pid, "ExecutionTraceRecord.pid", min_val=0, max_val=INT64_MAX)
        require_pure_str(self.task_id, "ExecutionTraceRecord.task_id", non_empty=True)
        object.__setattr__(self, "args", require_typed_tuple(self.args, str, "ExecutionTraceRecord.args"))
        require_pure_str(self.caller_mode, "ExecutionTraceRecord.caller_mode")
        require_pure_str(self.caller_cwd, "ExecutionTraceRecord.caller_cwd")
        require_pure_bool(self.executed_hot, "ExecutionTraceRecord.executed_hot")
        require_pure_int(self.exit_code, "ExecutionTraceRecord.exit_code", min_val=INT64_MIN, max_val=INT64_MAX)
        require_pure_bool(self.ok, "ExecutionTraceRecord.ok")
        dur = safe_real_to_float(self.duration_ms, label="ExecutionTraceRecord.duration_ms")
        if not math.isfinite(dur) or dur < 0.0:
            raise ValueError(f"ExecutionTraceRecord.duration_ms must be finite and >= 0, got {self.duration_ms!r}")
        object.__setattr__(self, "duration_ms", dur)
        require_pure_int(self.rss_kb, "ExecutionTraceRecord.rss_kb", min_val=0, max_val=INT64_MAX)
        require_pure_int(self.rss_delta_kb, "ExecutionTraceRecord.rss_delta_kb", min_val=INT64_MIN, max_val=INT64_MAX)
        require_pure_bool(self.mem_tracked, "ExecutionTraceRecord.mem_tracked")
        object.__setattr__(
            self,
            "dispatched_tasks",
            require_typed_tuple(self.dispatched_tasks, str, "ExecutionTraceRecord.dispatched_tasks"),
        )
        if self.profiler_tree is not None and not isinstance(self.profiler_tree, ProfilerNodeSnapshot):
            raise ValueError(
                f"ExecutionTraceRecord.profiler_tree must be ProfilerNodeSnapshot or None, got {self.profiler_tree!r}"
            )
        require_pure_str(self.error_code, "ExecutionTraceRecord.error_code")
        if self.error_detail is not None:
            object.__setattr__(
                self,
                "error_detail",
                MappingProxyType(clone_strict_json_object(self.error_detail, label="ExecutionTraceRecord.error_detail")),
            )
        if self.runtime_snapshot is not None:
            object.__setattr__(
                self,
                "runtime_snapshot",
                MappingProxyType(
                    clone_strict_json_object(self.runtime_snapshot, label="ExecutionTraceRecord.runtime_snapshot")
                ),
            )


def _parse_execution_trace_dict(doc: Mapping[str, object]) -> Optional[ExecutionTraceRecord]:
    try:
        raw_args = doc.get("args")
        if not isinstance(raw_args, list):
            return None
        raw_dispatched = doc.get("dispatched_tasks", [])
        if not isinstance(raw_dispatched, list):
            return None
        raw_tree = doc.get("profiler_tree")
        tree_snap = decode_profiler_snapshot(raw_tree) if raw_tree is not None else None
        raw_err_detail = doc.get("error_detail")
        err_detail: Optional[JsonObject] = None
        if raw_err_detail is not None:
            if not isinstance(raw_err_detail, Mapping):
                return None
            err_detail = clone_strict_json_object(raw_err_detail, label="error_detail")
        raw_rt_snap = doc.get("runtime_snapshot")
        rt_snap: Optional[JsonObject] = None
        if raw_rt_snap is not None:
            if not isinstance(raw_rt_snap, Mapping):
                return None
            rt_snap = clone_strict_json_object(raw_rt_snap, label="runtime_snapshot")
        return ExecutionTraceRecord(
            ts_utc=require_pure_str(doc.get("ts_utc"), "ts_utc", non_empty=True),
            epoch_ms=require_pure_int(doc.get("epoch_ms"), "epoch_ms", min_val=0, max_val=INT64_MAX),
            trace_id=require_pure_str(doc.get("trace_id", ""), "trace_id"),
            daemon_boot_id=require_pure_str(doc.get("daemon_boot_id", ""), "daemon_boot_id"),
            pid=require_pure_int(doc.get("pid", 0), "pid", min_val=0, max_val=INT64_MAX),
            task_id=require_pure_str(doc.get("task_id"), "task_id", non_empty=True),
            args=require_typed_tuple(raw_args, str, "args"),
            caller_mode=require_pure_str(doc.get("caller_mode", ""), "caller_mode"),
            caller_cwd=require_pure_str(doc.get("caller_cwd", ""), "caller_cwd"),
            executed_hot=require_pure_bool(doc.get("executed_hot"), "executed_hot"),
            exit_code=require_pure_int(doc.get("exit_code"), "exit_code", min_val=INT64_MIN, max_val=INT64_MAX),
            ok=require_pure_bool(doc.get("ok"), "ok"),
            duration_ms=safe_real_to_float(doc.get("duration_ms"), label="duration_ms"),
            rss_kb=require_pure_int(doc.get("rss_kb", 0), "rss_kb", min_val=0, max_val=INT64_MAX),
            rss_delta_kb=require_pure_int(doc.get("rss_delta_kb", 0), "rss_delta_kb", min_val=INT64_MIN, max_val=INT64_MAX),
            mem_tracked=require_pure_bool(doc.get("mem_tracked", False), "mem_tracked"),
            dispatched_tasks=require_typed_tuple(raw_dispatched, str, "dispatched_tasks"),
            profiler_tree=tree_snap,
            error_code=require_pure_str(doc.get("error_code", ""), "error_code"),
            error_detail=err_detail,
            runtime_snapshot=rt_snap,
        )
    except ValueError:
        return None


def _summarize_samples(samples: Sequence[float]) -> MutableJsonObject:
    count = len(samples)
    ordered = sorted(samples)
    p95_idx = min(count - 1, max(0, math.ceil(0.95 * count) - 1))
    return {
        "count": count,
        "latest_ms": round(samples[-1], 4),
        "avg_ms": round(sum(samples) / count, 4),
        "p95_ms": round(ordered[p95_idx], 4),
        "max_ms": round(ordered[-1], 4),
    }


def _collect_phase_timings(node: ProfilerNodeSnapshot, prefix: str, out: dict[str, list[float]]) -> None:
    for child in node.children:
        child_path = f"{prefix}/{child.name}" if prefix else child.name
        out.setdefault(child_path, []).append(child.total_ms)
        _collect_phase_timings(child, child_path, out)


class ProfilerRingBuffer:
    """Thread-safe bounded ring buffer aggregating per-task and top-phase latency percentiles."""

    def __init__(self, maxlen: int = 512) -> None:
        require_pure_int(maxlen, "ProfilerRingBuffer.maxlen", min_val=1, max_val=100000)
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._entries: deque[ExecutionTraceRecord] = deque(maxlen=maxlen)

    def record(self, trace: ExecutionTraceRecord) -> None:
        if not isinstance(trace, ExecutionTraceRecord):
            raise ValueError(f"ProfilerRingBuffer.record requires ExecutionTraceRecord, got {trace!r}")
        with self._lock:
            self._entries.append(trace)

    def recent(self, limit: int = 50) -> tuple[ExecutionTraceRecord, ...]:
        require_pure_int(limit, "ProfilerRingBuffer.recent limit", min_val=0, max_val=INT64_MAX)
        if limit == 0:
            return ()
        with self._lock:
            return tuple(self._entries)[-limit:]

    def summarize(self) -> JsonObject:
        with self._lock:
            entries = tuple(self._entries)
        task_samples: dict[str, list[float]] = {}
        phase_samples: dict[str, list[float]] = {}
        for entry in entries:
            task_samples.setdefault(entry.task_id, []).append(entry.duration_ms)
            if entry.profiler_tree is not None:
                _collect_phase_timings(entry.profiler_tree, "", phase_samples)
        by_task: MutableJsonObject = {
            tid: _summarize_samples(vals) for tid, vals in sorted(task_samples.items())
        }
        phase_stats = [(path, _summarize_samples(vals)) for path, vals in phase_samples.items()]
        phase_stats.sort(key=lambda item: (-float(item[1]["max_ms"]), item[0]))
        top_phases: MutableJsonObject = {path: stat for path, stat in phase_stats[:20]}
        return {
            "total_traces": len(entries),
            "maxlen": self._maxlen,
            "by_task": by_task,
            "top_phases": top_phases,
        }


def _is_env_truthy(env: Optional[Mapping[str, str]], key: str) -> bool:
    if env is None:
        return False
    raw = env.get(key)
    return type(raw) is str and raw.strip().lower() in _TRUTHY_ENV_STRINGS


def _utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _validate_date_str(date_str: str) -> str:
    cleaned = require_pure_str(date_str, "date_str", non_empty=True).strip()
    if _DATE_STR_RE.fullmatch(cleaned) is None:
        raise ValueError(f"Expected YYYY-MM-DD date string, got {date_str!r}")
    date.fromisoformat(cleaned)
    return cleaned


def _extract_date_from_ts(ts_utc: str) -> str:
    if len(ts_utc) >= 10:
        cand = ts_utc[:10]
        if _DATE_STR_RE.fullmatch(cand) is not None:
            try:
                date.fromisoformat(cand)
                return cand
            except ValueError:
                pass
    return _utc_today_str()


def _unlink_log_and_sidecars(log_file: Path) -> None:
    parent_dir = log_file.parent
    base_name = log_file.name
    for cand in (log_file, parent_dir / f".{base_name}.lock"):
        try:
            if cand.exists() and not cand.is_symlink():
                os.unlink(cand)
        except OSError:
            pass
    hist_prefix = f"{base_name}."
    try:
        with os.scandir(parent_dir) as it:
            for entry in it:
                if entry.is_symlink() or not entry.name.startswith(hist_prefix):
                    continue
                suffix = entry.name[len(hist_prefix) :]
                if suffix.isdigit():
                    try:
                        os.unlink(entry.path)
                    except OSError:
                        pass
    except OSError:
        pass


def _prune_daemon_dir(daemon_dir: Path, *, max_files: int, active_name: str) -> None:
    if not daemon_dir.is_dir() or daemon_dir.is_symlink():
        return
    matched: list[str] = []
    try:
        with os.scandir(daemon_dir) as it:
            for entry in it:
                if not entry.is_symlink() and _DAEMON_LOG_NAME_RE.fullmatch(entry.name) is not None:
                    matched.append(entry.name)
    except OSError:
        return
    if len(matched) <= max_files:
        return
    matched.sort()
    excess = len(matched) - max_files
    removed = 0
    for name in matched:
        if removed >= excess:
            break
        if name == active_name:
            continue
        _unlink_log_and_sidecars(daemon_dir / name)
        removed += 1


def _prune_dated_dir(target_dir: Path, *, ref_date_str: str, retention_days: int) -> None:
    if not target_dir.is_dir() or target_dir.is_symlink():
        return
    try:
        ref_day = date.fromisoformat(ref_date_str)
    except ValueError:
        return
    cutoff = ref_day - timedelta(days=retention_days)
    try:
        with os.scandir(target_dir) as it:
            for entry in it:
                if entry.is_symlink() or not entry.name.endswith(".jsonl"):
                    continue
                stem = entry.name[:-6]
                if _DATE_STR_RE.fullmatch(stem) is None:
                    continue
                try:
                    file_day = date.fromisoformat(stem)
                except ValueError:
                    continue
                if file_day <= cutoff:
                    _unlink_log_and_sidecars(target_dir / entry.name)
    except OSError:
        return


class FlightLogRouter:
    """Unified 3+1 JSONL flight log router for daemon, daily, perf, and module streams."""

    def __init__(
        self,
        logs_root: HostPath,
        *,
        config: Optional[FlightLogConfig] = None,
        env: Optional[Mapping[str, str]] = None,
        daemon_boot_id: str = "",
    ) -> None:
        if not isinstance(logs_root, HostPath):
            raise ValueError(f"FlightLogRouter.logs_root must be HostPath, got {logs_root!r}")
        cfg = config if config is not None else FlightLogConfig()
        if not isinstance(cfg, FlightLogConfig):
            raise ValueError(f"FlightLogRouter.config must be FlightLogConfig or None, got {config!r}")
        if env is not None and not isinstance(env, Mapping):
            raise ValueError("FlightLogRouter.env must be Mapping[str, str] or None.")
        clean_boot = require_pure_str(daemon_boot_id, "FlightLogRouter.daemon_boot_id").strip()
        sandbox_active = _is_env_truthy(env, TEST_SANDBOX_ENV_KEY) or _is_env_truthy(env, _LEGACY_TEST_SANDBOX_ENV_KEY)
        force_enabled = _is_env_truthy(env, FORCE_FLIGHT_LOGS_ENV_KEY)
        suppressed = cfg.respect_sandbox and sandbox_active and (not force_enabled)
        self._logs_root = logs_root
        self._config = cfg
        self._daemon_boot_id = clean_boot
        self._enabled = cfg.enabled and (not suppressed)
        self._daemon_path: Optional[HostPath] = None
        if clean_boot:
            ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            boot8 = _BOOT_SAFE_CHAR_RE.sub("", clean_boot)[:8] or "00000000"
            self._daemon_path = logs_root.join("daemon", f"daemon_{ts_tag}_{os.getpid()}_{boot8}.jsonl")
        self._lock = threading.Lock()
        self._rotators: dict[str, tuple[HostPath, LogRotator]] = {}
        self._closed = False
        self._daemon_pruned = False
        self._last_daily_prune_date = ""
        self._last_perf_prune_date = ""

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def daemon_boot_id(self) -> str:
        return self._daemon_boot_id

    def daemon_log_path(self) -> Optional[HostPath]:
        return self._daemon_path

    def daily_log_path(self, *, date_str: Optional[str] = None) -> HostPath:
        eff_date = _validate_date_str(date_str) if date_str is not None else _utc_today_str()
        return self._logs_root.join("daily", f"{eff_date}.jsonl")

    def perf_log_path(self, *, date_str: Optional[str] = None) -> HostPath:
        eff_date = _validate_date_str(date_str) if date_str is not None else _utc_today_str()
        return self._logs_root.join("perf", f"{eff_date}.jsonl")

    def module_log_path(self, module_id: str) -> HostPath:
        clean_mod = ModuleId(module_id).value
        return self._logs_root.join("modules", f"{clean_mod}.jsonl")

    def _get_rotator_locked(self, stream_key: str, target_path: HostPath) -> LogRotator:
        existing = self._rotators.get(stream_key)
        if existing is not None:
            old_path, old_rot = existing
            if old_path == target_path:
                return old_rot
            old_rot.close()
        new_rot = LogRotator(
            target_path,
            max_bytes=self._config.max_bytes_per_file,
            max_history_files=self._config.max_history_files,
        )
        self._rotators[stream_key] = (target_path, new_rot)
        return new_rot

    def record_daemon(self, entry: DaemonLogRecord) -> None:
        if not isinstance(entry, DaemonLogRecord):
            raise ValueError(f"FlightLogRouter.record_daemon requires DaemonLogRecord, got {entry!r}")
        if not self._enabled or self._daemon_path is None:
            return
        redacted_detail = redact_sensitive_value(entry.detail)
        payload: MutableJsonObject = {
            "ts_utc": entry.ts_utc,
            "epoch_ms": entry.epoch_ms,
            "daemon_boot_id": entry.daemon_boot_id,
            "pid": entry.pid,
            "event": entry.event,
            "level": entry.level.value,
            "trace_id": entry.trace_id,
            "task_id": entry.task_id,
            "detail": redacted_detail if isinstance(redacted_detail, Mapping) else {},
        }
        try:
            with self._lock:
                if self._closed:
                    return
                rot = self._get_rotator_locked("daemon", self._daemon_path)
                rot.append_jsonl(payload)
                if not self._daemon_pruned:
                    self._daemon_pruned = True
                    _prune_daemon_dir(
                        self._daemon_path.path.parent,
                        max_files=self._config.max_daemon_files,
                        active_name=self._daemon_path.path.name,
                    )
        except (OSError, YscbError, ValueError):
            return

    def record_daily(self, entry: DailyEventRecord) -> None:
        if not isinstance(entry, DailyEventRecord):
            raise ValueError(f"FlightLogRouter.record_daily requires DailyEventRecord, got {entry!r}")
        if not self._enabled:
            return
        eff_date = _extract_date_from_ts(entry.ts_utc)
        redacted_fields = redact_sensitive_value(entry.fields)
        redacted_msg = redact_sensitive_value(entry.message)
        payload: MutableJsonObject = {
            "ts_utc": entry.ts_utc,
            "epoch_ms": entry.epoch_ms,
            "kind": entry.kind,
            "trace_id": entry.trace_id,
            "daemon_boot_id": entry.daemon_boot_id,
            "pid": entry.pid,
            "exec_mode": entry.exec_mode,
            "module": entry.module,
            "task_id": entry.task_id,
            "level": entry.level.value,
            "ok": entry.ok,
            "duration_ms": entry.duration_ms,
            "exit_code": entry.exit_code,
            "message": redacted_msg if isinstance(redacted_msg, str) else entry.message,
            "fields": redacted_fields if isinstance(redacted_fields, Mapping) else {},
        }
        try:
            target = self.daily_log_path(date_str=eff_date)
            with self._lock:
                if self._closed:
                    return
                rot = self._get_rotator_locked("daily", target)
                rot.append_jsonl(payload)
                if self._last_daily_prune_date != eff_date:
                    self._last_daily_prune_date = eff_date
                    _prune_dated_dir(
                        target.path.parent,
                        ref_date_str=eff_date,
                        retention_days=self._config.retention_days,
                    )
        except (OSError, YscbError, ValueError):
            return

    def record_perf(self, entry: ExecutionTraceRecord) -> None:
        if not isinstance(entry, ExecutionTraceRecord):
            raise ValueError(f"FlightLogRouter.record_perf requires ExecutionTraceRecord, got {entry!r}")
        if not self._enabled:
            return
        eff_date = _extract_date_from_ts(entry.ts_utc)
        redacted_args = list(redact_cli_args(entry.args))
        redacted_err = redact_sensitive_value(entry.error_detail) if entry.error_detail is not None else None
        redacted_snap = (
            redact_sensitive_value(entry.runtime_snapshot) if entry.runtime_snapshot is not None else None
        )
        payload: MutableJsonObject = {
            "ts_utc": entry.ts_utc,
            "epoch_ms": entry.epoch_ms,
            "trace_id": entry.trace_id,
            "daemon_boot_id": entry.daemon_boot_id,
            "pid": entry.pid,
            "task_id": entry.task_id,
            "args": redacted_args,
            "caller_mode": entry.caller_mode,
            "caller_cwd": entry.caller_cwd,
            "executed_hot": entry.executed_hot,
            "exit_code": entry.exit_code,
            "ok": entry.ok,
            "duration_ms": entry.duration_ms,
            "rss_kb": entry.rss_kb,
            "rss_delta_kb": entry.rss_delta_kb,
            "mem_tracked": entry.mem_tracked,
            "dispatched_tasks": list(entry.dispatched_tasks),
            "profiler_tree": (
                _encode_profiler_snapshot(entry.profiler_tree) if entry.profiler_tree is not None else None
            ),
            "error_code": entry.error_code,
            "error_detail": redacted_err if isinstance(redacted_err, Mapping) else None,
            "runtime_snapshot": redacted_snap if isinstance(redacted_snap, Mapping) else None,
        }
        try:
            target = self.perf_log_path(date_str=eff_date)
            with self._lock:
                if self._closed:
                    return
                rot = self._get_rotator_locked("perf", target)
                rot.append_jsonl(payload)
                if self._last_perf_prune_date != eff_date:
                    self._last_perf_prune_date = eff_date
                    _prune_dated_dir(
                        target.path.parent,
                        ref_date_str=eff_date,
                        retention_days=self._config.retention_days,
                    )
        except (OSError, YscbError, ValueError):
            return

    def read_recent_perf(
        self,
        *,
        limit: int = 100,
        date_str: Optional[str] = None,
    ) -> tuple[ExecutionTraceRecord, ...]:
        require_pure_int(limit, "FlightLogRouter.read_recent_perf limit", min_val=0, max_val=INT64_MAX)
        if limit == 0:
            return ()
        target = self.perf_log_path(date_str=date_str)
        if not target.path.exists():
            return ()
        rot = LogRotator(
            target,
            max_bytes=self._config.max_bytes_per_file,
            max_history_files=self._config.max_history_files,
        )
        try:
            raw_docs = rot.read_jsonl()
        except (OSError, YscbError, ValueError):
            return ()
        finally:
            rot.close()
        parsed_rev: list[ExecutionTraceRecord] = []
        for doc in reversed(raw_docs):
            rec = _parse_execution_trace_dict(doc)
            if rec is not None:
                parsed_rev.append(rec)
                if len(parsed_rev) >= limit:
                    break
        parsed_rev.reverse()
        return tuple(parsed_rev)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for _path, rot in self._rotators.values():
                rot.close()
            self._rotators.clear()
