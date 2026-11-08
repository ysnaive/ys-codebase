"""
Pure-standard-library watcher coordination, in-process subscription registry,
`on_file_space_changed` (`emit_module="core"`) event broadcast, and cross-process
`watcher_state.json` / `.watcher_dirty` beacons for `core.space`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from core import vfs
from core.log import log_debug, log_warn

from .schema import resolve_semantic_or_rel_path

if TYPE_CHECKING:
    from .registry import SpaceRegistry
    from .scanner import ScanDiffResult

_SUBSCRIBER_LOCK = threading.RLock()
_SUBSCRIBERS: List[Tuple[Callable[[str, Any], Any], Optional[Set[str]]]] = []

_WATCHER_LOCK = threading.RLock()
_ACTIVE_WATCHER_WORKER: Optional[Any] = None


def subscribe(
    callback: Callable[[str, Any], Any],
    *,
    spaces: Optional[Iterable[str]] = None,
) -> Callable[[], None]:
    """
    Register an in-process callback invoked whenever a space snapshot generation advances.
    Supports filtering by `<owner>/<space>` qualified names or `<space>` short names.
    Returns an unsubscribe callable.
    """
    space_filter: Optional[Set[str]] = None
    if spaces is not None:
        cleaned = {str(s).strip() for s in spaces if str(s).strip()}
        space_filter = cleaned if cleaned else set()

    entry = (callback, space_filter)
    with _SUBSCRIBER_LOCK:
        _SUBSCRIBERS.append(entry)

    def _unsubscribe() -> None:
        with _SUBSCRIBER_LOCK:
            if entry in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(entry)

    return _unsubscribe


def clear_subscribers() -> None:
    """Remove all registered in-process space change subscribers."""
    with _SUBSCRIBER_LOCK:
        _SUBSCRIBERS.clear()


def _matches_space_filter(space_name: str, space_filter: Optional[Set[str]]) -> bool:
    if space_filter is None:
        return True
    if not space_filter:
        return False
    if "*" in space_filter or space_name in space_filter:
        return True
    short_name = space_name.split("/", 1)[-1] if "/" in space_name else space_name
    if short_name in space_filter:
        return True
    for item in space_filter:
        if "/" in item and item.split("/", 1)[-1] == short_name and "/" not in space_name:
            return True
    return False


def notify_subscribers(space_name: str, diff_result: "ScanDiffResult") -> None:
    """Invoke all matching in-process subscribers for `space_name`."""
    with _SUBSCRIBER_LOCK:
        current = list(_SUBSCRIBERS)

    for callback, space_filter in current:
        if not _matches_space_filter(space_name, space_filter):
            continue
        try:
            callback(space_name, diff_result)
        except Exception as exc:
            log_warn(
                f"Space subscriber callback failed for '{space_name}': {exc}",
                stream="stderr",
            )


def broadcast_file_space_changed(
    space_name: str, diff_result: "ScanDiffResult"
) -> Dict[str, Any]:
    """
    Broadcast `on_file_space_changed` via `core.events.broadcast(..., emit_module="core")`
    so modules with `scripts/hook.core.py` receive incremental space updates.
    """
    short_name = space_name.split("/", 1)[-1] if "/" in space_name else space_name
    spaces_list = [space_name]
    if short_name != space_name:
        spaces_list.append(short_name)

    payload: Dict[str, Any] = {
        "space_name": space_name,
        "short_name": short_name,
        "spaces": spaces_list,
        "from_generation": diff_result.from_generation,
        "to_generation": diff_result.to_generation,
        "merkle_root": diff_result.merkle_root,
        "added": diff_result.added,
        "modified": diff_result.modified,
        "deleted": diff_result.deleted,
        "added_count": diff_result.added_count,
        "modified_count": diff_result.modified_count,
        "deleted_count": diff_result.deleted_count,
        "diff_summary": diff_result.to_dict(),
    }
    try:
        from core import events as core_events

        core_events.broadcast(
            "on_file_space_changed", payload, emit_module="core"
        )
    except Exception as exc:
        log_debug(f"Event broadcast 'on_file_space_changed' skipped or failed: {exc}")
    return payload


def register_active_watcher(worker: Optional[Any]) -> None:
    """Register or clear the active in-process space watcher worker instance."""
    global _ACTIVE_WATCHER_WORKER
    with _WATCHER_LOCK:
        _ACTIVE_WATCHER_WORKER = worker


def get_active_watcher() -> Optional[Any]:
    """Return the active in-process space watcher worker instance if running."""
    with _WATCHER_LOCK:
        return _ACTIVE_WATCHER_WORKER


def notify_space_registered(space_name: str) -> None:
    """Notify the active in-process watcher when a space with `watch=True` is registered."""
    worker = get_active_watcher()
    if worker is not None and hasattr(worker, "sync_watched_directories"):
        try:
            worker.sync_watched_directories()
        except Exception as exc:
            log_debug(
                f"Failed to sync watched directories for space '{space_name}': {exc}"
            )


notify_ephemeral_space_registered = notify_space_registered


def resolve_watcher_cache_dir(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve `cache://core/space` directory anchored strictly inside `yscb_root/.cache/core/space`."""
    p_root = Path(os.path.abspath(str(project_root or Path.cwd())))
    y_dir = Path(os.path.abspath(str(yscb_dir))) if yscb_dir is not None else None
    res = resolve_semantic_or_rel_path("cache://core/space", p_root, y_dir)
    if res is not None:
        return res
    if y_dir is not None:
        return y_dir / ".cache" / "core" / "space"
    try:
        from core import uri

        return Path(uri.resolve_yscb_root()).resolve() / ".cache" / "core" / "space"
    except Exception:
        return p_root / "ys_codebase" / ".cache" / "core" / "space"


def resolve_watcher_state_path(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Return path to `cache://core/space/watcher_state.json`."""
    return resolve_watcher_cache_dir(project_root, yscb_dir) / "watcher_state.json"


def resolve_watcher_dirty_path(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Return path to `cache://core/space/.watcher_dirty`."""
    return resolve_watcher_cache_dir(project_root, yscb_dir) / ".watcher_dirty"


def write_watcher_state(
    *,
    watched_spaces: List[str],
    watchdog_running: bool,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    state_file: Optional[Union[str, Path]] = None,
) -> Path:
    """Atomically write `watcher_state.json` via `core.vfs`."""
    target = (
        Path(os.path.abspath(str(state_file)))
        if state_file is not None
        else resolve_watcher_state_path(project_root, yscb_dir)
    )
    payload = {
        "pid": os.getpid(),
        "watchdog_running": bool(watchdog_running),
        "watched_spaces": sorted(set(watched_spaces)),
        "updated_at": time.time(),
    }
    try:
        vfs.makedirs(str(target.parent), exist_ok=True)
        vfs.write_json(str(target), payload, indent=2, atomic=True)
    except Exception as exc:
        log_debug(f"Failed to write watcher_state.json: {exc}")
    return target


def remove_watcher_state(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    state_file: Optional[Union[str, Path]] = None,
) -> None:
    """Remove `watcher_state.json` on watcher shutdown."""
    target = (
        Path(os.path.abspath(str(state_file)))
        if state_file is not None
        else resolve_watcher_state_path(project_root, yscb_dir)
    )
    if target.exists():
        try:
            vfs.remove(str(target), missing_ok=True)
        except Exception:
            try:
                target.unlink()
            except OSError:
                pass


def read_watcher_state(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    state_file: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Read and parse `watcher_state.json` if present."""
    target = (
        Path(os.path.abspath(str(state_file)))
        if state_file is not None
        else resolve_watcher_state_path(project_root, yscb_dir)
    )
    if not target.is_file():
        return None
    try:
        raw = vfs.read_text(str(target), encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        from core.platform.process import is_process_alive

        return bool(is_process_alive(pid))
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def is_watcher_active(
    space_query: Optional[str] = None,
    *,
    registry: Optional["SpaceRegistry"] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    state_file: Optional[Union[str, Path]] = None,
) -> bool:
    """
    Return True if a space watcher is actively monitoring `space_query` (either in-process
    or in a live daemon process recorded in `watcher_state.json`).
    """
    from .registry import get_default_registry

    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    try:
        spaces = reg.resolve_spaces(space_query)
    except Exception:
        return False
    if not spaces or not all(s.watch for s in spaces):
        return False

    worker = get_active_watcher()
    if worker is not None:
        is_alive_fn = getattr(worker, "is_alive", None)
        if callable(is_alive_fn) and is_alive_fn():
            return True

    state = read_watcher_state(
        project_root=reg.project_root,
        yscb_dir=reg.yscb_dir,
        state_file=state_file,
    )
    if not state or not state.get("watchdog_running"):
        return False
    pid = int(state.get("pid", 0) or 0)
    if not _is_pid_alive(pid):
        return False

    watched_set = set(state.get("watched_spaces", []))

    def _space_covered(s: "SpaceConfig") -> bool:
        if s.qualified_name in watched_set or s.short_name in watched_set:
            return True
        if s.owner == "" and not s.entries and s.compose:
            try:
                pos_c, _neg_c = reg._split_compose_children(s, ())
                if pos_c:
                    return all(
                        c.qualified_name in watched_set or c.short_name in watched_set
                        for c in pos_c
                    )
            except Exception:
                pass
        return False

    return all(_space_covered(s) for s in spaces)
