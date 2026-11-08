"""
ExecutionContext and RuntimeContext definition for YS-Codebase.
Single Source of Truth (SSOT) for execution context, isolated runtime caches,
virtual working directory (`virtual_cwd`), and scoped environment overrides (`env`).
100% Python Standard Library.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
import threading
import types
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set, Tuple, Union


class _SchemesCacheDict(dict):
    """Dictionary subclass for URI `_SCHEMES_CACHE` that also clears `token_map_cache` on `.clear()`."""

    def __init__(self, token_map_ref: Dict[str, Any]) -> None:
        super().__init__()
        self._token_map_ref = token_map_ref

    def clear(self) -> None:
        super().clear()
        self._token_map_ref.clear()


class _ThreadLocalSet(threading.local):
    """Thread-local set for cycle detection in `core.uri` token reconciliation."""

    def __init__(self) -> None:
        super().__init__()
        self.tokens: Set[str] = set()

    def add(self, item: str) -> None:
        self.tokens.add(item)

    def discard(self, item: str) -> None:
        self.tokens.discard(item)

    def clear(self) -> None:
        self.tokens.clear()

    def __contains__(self, item: object) -> bool:
        return item in self.tokens


@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface) - 單一真相來源 (SSOT)"""

    module_name: str
    command: Optional[str] = None
    args: Optional[Union[Tuple[str, ...], List[str]]] = ()
    metadata: Mapping[str, Any] = field(
        default_factory=lambda: types.MappingProxyType({}), compare=False
    )

    def __post_init__(self) -> None:
        if self.args is None:
            object.__setattr__(self, "args", None)
        elif not isinstance(self.args, tuple):
            object.__setattr__(self, "args", tuple(self.args))

        if self.metadata is None:
            object.__setattr__(self, "metadata", types.MappingProxyType({}))
        elif not isinstance(self.metadata, types.MappingProxyType):
            object.__setattr__(self, "metadata", types.MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class RuntimeScope:
    """
    Immutable per-task / per-thread scope bound via `ContextVar` (`bind_runtime_context`).
    Supports isolated `virtual_cwd`, request-scoped `env_overrides`, and URI root overrides.
    """

    virtual_cwd: Optional[str] = None
    env_overrides: Mapping[str, Optional[str]] = field(
        default_factory=lambda: types.MappingProxyType({}), compare=False
    )
    active_host_dir: Optional[str] = None
    active_yscb_dir: Optional[str] = None
    active_module: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.env_overrides, types.MappingProxyType):
            object.__setattr__(
                self, "env_overrides", types.MappingProxyType(dict(self.env_overrides))
            )


_ACTIVE_RUNTIME_SCOPE: ContextVar[Optional[RuntimeScope]] = ContextVar(
    "_ACTIVE_RUNTIME_SCOPE", default=None
)


class RuntimeContext:
    """
    Centralized runtime state and cache container for `module:core`.
    Eliminates top-level mutable module caches and `global` variables while preserving
    in-place dictionary identity for white-box unit test compatibility.
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()

        # 1. core.uri state & caches
        self.uri_tls = threading.local()
        self.uri_reconciling_tokens = _ThreadLocalSet()
        self.uri_reentrancy = threading.local()
        self.uri_token_map_cache: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}
        self.uri_schemes_cache: Dict[str, Tuple[float, float, List[Dict[str, Any]]]] = (
            _SchemesCacheDict(self.uri_token_map_cache)
        )

        # 2. core.config caches
        self.config_cache: Dict[Any, Dict[str, Any]] = {}
        self.config_mtimes: Dict[Any, Tuple[float, float]] = {}

        # 3. core.contributes caches
        self.contributes_merged_cache: Dict[Tuple[str, str], Tuple[float, float, Dict[str, Any]]] = {}
        self.contributes_json_file_cache: Dict[str, Tuple[int, int, Any]] = {}
        self.contributes_last_clean_scan_ts: Dict[str, Tuple[float, float]] = {}

        # 4. core.locale caches
        self.locale_file_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self.locale_module_base_dir_cache: Dict[Any, str] = {}
        self.locale_safe_subpath_cache: Dict[Tuple[str, str], Tuple[bool, str]] = {}

        # 5. core.symbols & core.loader caches
        self.symbols_callable_cache: Dict[Any, Callable[..., Any]] = {}
        self.loader_lock = threading.RLock()
        # module_key -> (norm_file_path, mtime_ns, size, module_obj)
        self.loaded_modules_cache: Dict[str, Tuple[str, int, int, types.ModuleType]] = {}

        # 6. core.gitignore caches
        self.gitignore_custom_root_store: Dict[str, Dict[str, List[str]]] = {}

        # 7. core.validator cache
        self.validator_signature_cache: Dict[str, Dict[str, Any]] = {}

        # 8. core.commands.dispatcher state & caches
        self.dispatcher_global_registry: Optional[Any] = None
        self.dispatcher_global_registry_root: Optional[str] = None
        self.dispatcher_module_cache: Dict[str, Any] = {}
        self.dispatcher_auto_spawn_warned: bool = False

        # 9. core.platform state & caches
        self.process_can_spawn_daemon_cache: Optional[bool] = None
        self.venv_active_test_source_paths: List[Tuple[str, str]] = []

        # 10. core.space state & caches
        self.space_registries_lock = threading.RLock()
        self.space_default_registries: Dict[Tuple[str, str], Any] = {}
        self.space_scanners_lock = threading.RLock()
        self.space_default_scanners: Dict[Tuple[str, str, str], Any] = {}
        self.space_subscriber_lock = threading.RLock()
        self.space_subscribers: List[Tuple[Callable[[str, Any], Any], Optional[Set[str]]]] = []
        self.space_watcher_lock = threading.RLock()
        self.space_active_watcher_worker: Optional[Any] = None

        # 11. core.log fallback state
        self.log_error_lock = threading.RLock()
        self.log_error_chunks: List[str] = []
        self.log_file_op_lock = threading.RLock()

        # 12. server.service touch activity state
        self.server_touch_lock = threading.Lock()
        self.server_last_touch_by_root: Dict[str, float] = {}

        # 13. Upper-layer domain module states (`get_module_state` / `set_module_state`)
        self.module_states_lock = threading.RLock()
        self.module_states: Dict[str, Any] = {}

    def get_module_state(self, key: str, default_factory: Optional[Callable[[], Any]] = None) -> Any:
        """Thread-safely retrieves or initializes a domain module state entry by `key`."""
        with self.module_states_lock:
            if key not in self.module_states and default_factory is not None:
                self.module_states[key] = default_factory()
            return self.module_states.get(key)

    def set_module_state(self, key: str, value: Any) -> None:
        """Thread-safely sets a domain module state entry by `key`."""
        with self.module_states_lock:
            self.module_states[key] = value

    def reset_all_caches(self) -> None:
        """
        Clears all mutable caches in-place so existing dictionary/list references held
        by callers or white-box unit tests remain valid and empty.
        """
        with self.lock:
            self.uri_tls.__dict__.clear()
            self.uri_reentrancy.__dict__.clear()
            self.uri_reconciling_tokens.clear()
            self.uri_schemes_cache.clear()
            self.uri_token_map_cache.clear()
            self.config_cache.clear()
            self.config_mtimes.clear()
            self.contributes_merged_cache.clear()
            self.contributes_json_file_cache.clear()
            self.contributes_last_clean_scan_ts.clear()
            self.locale_file_cache.clear()
            self.locale_module_base_dir_cache.clear()
            self.locale_safe_subpath_cache.clear()
            self.symbols_callable_cache.clear()
            from core.loader import clear_loaded_modules

            clear_loaded_modules()
            self.gitignore_custom_root_store.clear()
            self.validator_signature_cache.clear()
            self.dispatcher_global_registry = None
            self.dispatcher_global_registry_root = None
            self.dispatcher_module_cache.clear()
            self.dispatcher_auto_spawn_warned = False
            self.process_can_spawn_daemon_cache = None
            self.venv_active_test_source_paths.clear()
            with self.space_registries_lock:
                self.space_default_registries.clear()
            with self.space_scanners_lock:
                self.space_default_scanners.clear()
            with self.space_subscriber_lock:
                self.space_subscribers.clear()
            with self.space_watcher_lock:
                self.space_active_watcher_worker = None
            with self.log_error_lock:
                self.log_error_chunks.clear()
            with self.server_touch_lock:
                self.server_last_touch_by_root.clear()
            with self.module_states_lock:
                self.module_states.clear()


@lru_cache(maxsize=1)
def get_runtime_context() -> RuntimeContext:
    """Returns the process-wide `RuntimeContext` instance (lazily constructed without top-level mutable globals)."""
    return RuntimeContext()


def reset_runtime_context() -> None:
    """Clears all caches on the active `RuntimeContext` in-place."""
    get_runtime_context().reset_all_caches()


def get_current_scope() -> Optional[RuntimeScope]:
    """Returns the currently active `RuntimeScope` bound via `ContextVar`, or None."""
    return _ACTIVE_RUNTIME_SCOPE.get()


@contextmanager
def bind_runtime_context(
    *,
    virtual_cwd: Optional[Union[str, Path]] = None,
    env: Optional[Mapping[str, Optional[str]]] = None,
    host_dir: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    module_name: Optional[str] = None,
) -> Iterator[RuntimeScope]:
    """
    Context manager binding request-scoped `virtual_cwd`, `env` overrides,
    and active URI scope (`host_dir`, `yscb_dir`, `module_name`) via `ContextVar`.
    """
    parent = _ACTIVE_RUNTIME_SCOPE.get()

    eff_cwd: Optional[str] = parent.virtual_cwd if parent else None
    if virtual_cwd is not None:
        cwd_str = str(virtual_cwd).strip()
        eff_cwd = os.path.normpath(os.path.abspath(cwd_str)) if cwd_str else None

    merged_env: Dict[str, Optional[str]] = (
        dict(parent.env_overrides) if parent and parent.env_overrides else {}
    )
    if env is not None:
        for k, v in env.items():
            merged_env[str(k)] = str(v) if v is not None else None

    eff_host: Optional[str] = parent.active_host_dir if parent else None
    if host_dir is not None:
        eff_host = (
            os.path.normpath(os.path.abspath(str(host_dir))) if str(host_dir).strip() else None
        )

    eff_yscb: Optional[str] = parent.active_yscb_dir if parent else None
    if yscb_dir is not None:
        y_str = str(yscb_dir).strip()
        if y_str:
            if eff_host and not os.path.isabs(y_str):
                eff_yscb = os.path.normpath(os.path.join(eff_host, y_str))
            else:
                eff_yscb = os.path.normpath(os.path.abspath(y_str))
        else:
            eff_yscb = None

    eff_mod: Optional[str] = parent.active_module if parent else None
    if module_name is not None:
        eff_mod = str(module_name).strip() or None

    new_scope = RuntimeScope(
        virtual_cwd=eff_cwd,
        env_overrides=types.MappingProxyType(merged_env),
        active_host_dir=eff_host,
        active_yscb_dir=eff_yscb,
        active_module=eff_mod,
    )
    token: Token = _ACTIVE_RUNTIME_SCOPE.set(new_scope)
    try:
        yield new_scope
    finally:
        _ACTIVE_RUNTIME_SCOPE.reset(token)


def get_virtual_cwd(fallback: Optional[Union[str, Path]] = None) -> str:
    """
    Single sanctioned authority for resolving the current logical working directory.
    Priority:
      1. Active `RuntimeScope.virtual_cwd` bound via `bind_runtime_context`.
      2. Physical `os.getcwd()` (falling back to `fallback`, `YSCB_HOST_DIR`, or `""` if directory was deleted).
    """
    scope = _ACTIVE_RUNTIME_SCOPE.get()
    if scope is not None and scope.virtual_cwd:
        return scope.virtual_cwd

    try:
        return os.getcwd()
    except OSError:
        if fallback is not None:
            return str(fallback)
        host_env = get_env("YSCB_HOST_DIR")
        if host_env:
            return host_env
        return ""


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Reads an environment variable respecting active `RuntimeScope.env_overrides` before `os.environ`.
    If a key is mapped to `None` in `env_overrides`, it is treated as unset and returns `default`.
    """
    scope = _ACTIVE_RUNTIME_SCOPE.get()
    if scope is not None and key in scope.env_overrides:
        val = scope.env_overrides[key]
        return default if val is None else val
    return os.environ.get(key, default)


def get_env_snapshot() -> Mapping[str, str]:
    """Returns a read-only `MappingProxyType` merging `os.environ` with active `RuntimeScope.env_overrides`."""
    merged = dict(os.environ)
    scope = _ACTIVE_RUNTIME_SCOPE.get()
    if scope is not None and scope.env_overrides:
        for k, v in scope.env_overrides.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
    return types.MappingProxyType(merged)


__all__ = (
    "ExecutionContext",
    "RuntimeScope",
    "RuntimeContext",
    "get_runtime_context",
    "reset_runtime_context",
    "get_current_scope",
    "bind_runtime_context",
    "get_virtual_cwd",
    "get_env",
    "get_env_snapshot",
)
