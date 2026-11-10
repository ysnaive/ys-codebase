"""
On-Demand Grammar Provisioner with strict stderr stream isolation and session-level negative cache.
Ensures `--json` output on stdout remains 100% pure even when dynamic grammar installation is attempted or fails offline.
"""

from contextlib import contextmanager
import importlib
import json
import time
import os
import subprocess
import sys
import tempfile
import threading
from types import MappingProxyType
from typing import Any, ClassVar, Dict, Iterator, List, Mapping, Optional, Set

from core.context import get_runtime_context
from core.log import log_debug, log_stream

try:
    import tree_sitter
except ImportError:
    tree_sitter = None

DEFAULT_GRAMMAR_PACKAGES: Mapping[str, str] = MappingProxyType({
    "tree_sitter_python": "tree-sitter-python",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "tree_sitter_cpp": "tree-sitter-cpp",
    "tree_sitter_c": "tree-sitter-c",
    "tree_sitter_javascript": "tree-sitter-javascript",
    "tree_sitter_typescript": "tree-sitter-typescript",
    "tree_sitter_markdown": "tree-sitter-markdown",
})


def _get_provisioner_state() -> Dict[str, Any]:
    state = get_runtime_context().get_module_state(
        "ast.provisioner.state",
        lambda: {
            "failed_packages": set(),
            "loaded_languages": {},
            "warnings": [],
            "inflight_events": {},
        },
    )
    if "inflight_events" not in state:
        state["inflight_events"] = {}
    return state


class GrammarProvisioner:
    """
    On-demand Tree-sitter grammar loader and pip provisioner.
    Enforces 100% stderr redirection for any installation subprocess, single-flight per-language
    events so slow installations never block cached languages, and a session-scoped
    negative cache to prevent repeated retries in offline environments.
    """

    _LOCK: ClassVar[threading.RLock] = threading.RLock()
    _lock: ClassVar[threading.RLock] = _LOCK
    auto_install_enabled: ClassVar[bool] = False
    _instance: ClassVar[Optional["GrammarProvisioner"]] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "GrammarProvisioner":
        with cls._LOCK:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    @classmethod
    def get_failed_packages(cls) -> Set[str]:
        """Return the set of failed grammar package names in the current runtime context."""
        return _get_provisioner_state()["failed_packages"]

    @classmethod
    def get_loaded_languages(cls) -> Dict[str, Any]:
        """Return the map of loaded Tree-sitter languages in the current runtime context."""
        return _get_provisioner_state()["loaded_languages"]

    @classmethod
    def reset_cache(cls) -> None:
        """Clear negative cache, loaded language cache, inflight events, and accumulated warnings."""
        with cls._LOCK:
            state = _get_provisioner_state()
            state["failed_packages"].clear()
            state["loaded_languages"].clear()
            state["warnings"].clear()
            for ev in state["inflight_events"].values():
                ev.set()
            state["inflight_events"].clear()
        p = cls._neg_cache_path()
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass

    @classmethod
    def get_warnings(cls, clear: bool = False) -> List[str]:
        """Return accumulated grammar provisioning warnings."""
        with cls._LOCK:
            warnings_list: List[str] = _get_provisioner_state()["warnings"]
            out = list(warnings_list)
            if clear:
                warnings_list.clear()
            return out

    @classmethod
    def _emit_warning(cls, pkg_label: str) -> str:
        msg = f"[ast:warn] Grammar package '{pkg_label}' is unavailable; skipping AST parse."
        with cls._LOCK:
            warnings_list: List[str] = _get_provisioner_state()["warnings"]
            if msg not in warnings_list:
                warnings_list.append(msg)
                log_stream(msg + "\n", stream="stderr")
        return msg

    @classmethod
    @contextmanager
    def _provision_lock(cls, timeout_sec: float = 60.0) -> Iterator[bool]:
        """Acquires a cross-process file lock around JIT grammar installation."""
        lock_obj = None
        acquired = False
        try:
            from core import uri
            from core.platform.lock import InterProcessLock

            try:
                yscb_root = uri.resolve_yscb_root()
                lock_dir = os.path.join(yscb_root, ".venv")
            except Exception:
                lock_dir = tempfile.gettempdir()
            os.makedirs(lock_dir, exist_ok=True)
            lock_path = os.path.join(lock_dir, ".pip_install.lock")
            lock_obj = InterProcessLock(lock_path)
            acquired = bool(lock_obj.acquire(blocking=True, timeout_sec=float(timeout_sec)))
        except Exception as lock_exc:
            log_debug(f"GrammarProvisioner failed acquiring pip lock: {lock_exc}")
            lock_obj = None
            acquired = False
        try:
            yield acquired
        finally:
            if lock_obj is not None and acquired:
                try:
                    lock_obj.release()
                except Exception:
                    pass

    @classmethod
    def _neg_cache_path(cls) -> Optional[str]:
        try:
            from core import uri
            yscb_root = uri.resolve_yscb_root()
            if yscb_root:
                p = os.path.join(yscb_root, ".cache", "ast", "provision_failed.json")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                return p
        except Exception:
            pass
        return None

    @classmethod
    def _is_persisted_failed(cls, pkg_name: str, ttl_sec: float = 3600.0) -> bool:
        p = cls._neg_cache_path()
        if not p or not os.path.isfile(p):
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                ts = float(data.get(pkg_name) or 0.0)
                if ts > 0.0 and (time.time() - ts) < ttl_sec:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def _record_persisted_failed(cls, pkg_name: str) -> None:
        p = cls._neg_cache_path()
        if not p:
            return
        try:
            data: Dict[str, float] = {}
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data = {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}
            data[pkg_name] = time.time()
            from core import vfs
            vfs.write_json(p, data, indent=2, atomic=True)
        except Exception:
            pass

    @classmethod
    def _try_pip_install(cls, pkg_name: str, module_name: Optional[str] = None, lock_timeout_sec: float = 60.0) -> bool:
        """
        Attempt to install a missing grammar package via pip with stdout and stderr strictly redirected to sys.stderr.
        Synchronizes across processes via `InterProcessLock(..., timeout_sec=60.0)` and persists offline failure TTL.
        """
        with cls._LOCK:
            if pkg_name in _get_provisioner_state()["failed_packages"]:
                return False
        if cls._is_persisted_failed(pkg_name):
            with cls._LOCK:
                _get_provisioner_state()["failed_packages"].add(pkg_name)
            return False

        with cls._provision_lock(timeout_sec=lock_timeout_sec) as lock_acquired:
            if not lock_acquired:
                log_stream(f"[ast:warn] Timed out acquiring pip lock while provisioning '{pkg_name}'.\n", stream="stderr")
                return False
            with cls._LOCK:
                if pkg_name in _get_provisioner_state()["failed_packages"]:
                    return False
            if cls._is_persisted_failed(pkg_name):
                with cls._LOCK:
                    _get_provisioner_state()["failed_packages"].add(pkg_name)
                return False

            if module_name:
                importlib.invalidate_caches()
                try:
                    importlib.import_module(module_name)
                    return True
                except ImportError:
                    pass

            try:
                log_stream(f"[ast] Provisioning missing grammar package '{pkg_name}'...\n", stream="stderr")
                cmd = [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--retries=1",
                    "--timeout=5",
                    pkg_name,
                ]
                proc = subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=sys.stderr,
                    stderr=sys.stderr,
                    timeout=30,
                    check=False,
                )
                if proc.returncode == 0:
                    importlib.invalidate_caches()
                    return True
            except Exception as exc:
                log_debug(f"GrammarProvisioner pip install failed for '{pkg_name}': {exc}")

            with cls._LOCK:
                _get_provisioner_state()["failed_packages"].add(pkg_name)
            cls._record_persisted_failed(pkg_name)
            return False

    @classmethod
    def load_language(
        cls,
        lang_key: str,
        module_name: str,
        func_name: str = "language",
        auto_install_pkg: Optional[str] = None,
        attempt_auto_install: Optional[bool] = None,
    ) -> Optional[Any]:
        """
        Load a `tree_sitter.Language` instance for `(lang_key, module_name, func_name)`.
        Uses lock-decoupled single-flight coordination per `cache_key` so slow pip installations
        never block concurrent lookups of cached languages or `get_warnings()`.
        """
        if ":" in module_name:
            module_name, func_name = module_name.split(":", 1)

        cache_key = f"{lang_key}:{module_name}:{func_name}"
        pkg_name = auto_install_pkg or DEFAULT_GRAMMAR_PACKAGES.get(module_name) or module_name.replace("_", "-")

        wait_event: Optional[threading.Event] = None
        is_leader = False

        with cls._LOCK:
            state = _get_provisioner_state()
            loaded_langs = state["loaded_languages"]
            failed_pkgs = state["failed_packages"]
            inflight = state["inflight_events"]
            if cache_key in loaded_langs:
                return loaded_langs[cache_key]
            if pkg_name in failed_pkgs or module_name in failed_pkgs:
                cls._emit_warning(pkg_name)
                return None
            if cache_key in inflight:
                wait_event = inflight[cache_key]
            else:
                wait_event = threading.Event()
                inflight[cache_key] = wait_event
                is_leader = True

        if not is_leader and wait_event is not None:
            wait_event.wait(timeout=95.0)
            with cls._LOCK:
                loaded_langs = _get_provisioner_state()["loaded_languages"]
                if cache_key in loaded_langs:
                    return loaded_langs[cache_key]
                cls._emit_warning(pkg_name)
                return None

        try:
            mod = None
            try:
                mod = importlib.import_module(module_name)
            except ImportError:
                should_install = (
                    attempt_auto_install
                    if attempt_auto_install is not None
                    else (cls.auto_install_enabled or bool(auto_install_pkg))
                )
                if should_install and cls._try_pip_install(pkg_name, module_name=module_name):
                    try:
                        mod = importlib.import_module(module_name)
                    except Exception:
                        mod = None

            with cls._LOCK:
                state = _get_provisioner_state()
                failed_pkgs = state["failed_packages"]
                loaded_langs = state["loaded_languages"]
                if mod is None:
                    failed_pkgs.add(pkg_name)
                    failed_pkgs.add(module_name)
                    cls._emit_warning(pkg_name)
                    return None

                if tree_sitter is None:
                    failed_pkgs.add("tree-sitter")
                    cls._emit_warning("tree-sitter")
                    return None

                try:
                    if hasattr(mod, func_name):
                        lang_fn = getattr(mod, func_name)
                    elif hasattr(mod, f"language_{lang_key}"):
                        lang_fn = getattr(mod, f"language_{lang_key}")
                    else:
                        raise AttributeError(f"Module '{module_name}' has no function '{func_name}'")

                    raw_lang = lang_fn()
                    ts_lang = raw_sitter_language(raw_lang)
                    loaded_langs[cache_key] = ts_lang
                    return ts_lang
                except Exception as exc:
                    log_debug(f"GrammarProvisioner failed initializing '{module_name}:{func_name}': {exc}")
                    failed_pkgs.add(pkg_name)
                    failed_pkgs.add(module_name)
                    cls._emit_warning(pkg_name)
                    return None
        finally:
            with cls._LOCK:
                _get_provisioner_state()["inflight_events"].pop(cache_key, None)
            if wait_event is not None:
                wait_event.set()


def raw_sitter_language(raw_lang: Any) -> Any:
    """Wrap raw capsule or language pointer into tree_sitter.Language if needed."""
    if tree_sitter is None:
        return None
    if isinstance(raw_lang, tree_sitter.Language):
        return raw_lang
    return tree_sitter.Language(raw_lang)


__all__ = [
    "DEFAULT_GRAMMAR_PACKAGES",
    "GrammarProvisioner",
    "raw_sitter_language",
]
