"""
On-Demand Grammar Provisioner with strict stderr stream isolation and session-level negative cache.
Ensures `--json` output on stdout remains 100% pure even when dynamic grammar installation is attempted or fails offline.
"""

from contextlib import contextmanager
import importlib
import logging
import os
import subprocess
import sys
import tempfile
import threading
from typing import Any, ClassVar, Dict, Iterator, List, Optional, Set

try:
    import tree_sitter
except ImportError:
    tree_sitter = None

logger = logging.getLogger("ast.provisioner")

DEFAULT_GRAMMAR_PACKAGES: Dict[str, str] = {
    "tree_sitter_python": "tree-sitter-python",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "tree_sitter_cpp": "tree-sitter-cpp",
    "tree_sitter_c": "tree-sitter-c",
    "tree_sitter_javascript": "tree-sitter-javascript",
    "tree_sitter_typescript": "tree-sitter-typescript",
    "tree_sitter_markdown": "tree-sitter-markdown",
}


class GrammarProvisioner:
    """
    On-demand Tree-sitter grammar loader and pip provisioner.
    Enforces 100% stderr redirection for any installation subprocess and maintains
    a session-scoped `_FAILED_PACKAGES` negative cache to prevent repeated retries in offline environments.
    """

    _LOCK: ClassVar[threading.RLock] = threading.RLock()
    _lock: ClassVar[threading.RLock] = _LOCK
    _FAILED_PACKAGES: ClassVar[Set[str]] = set()
    _LOADED_LANGUAGES: ClassVar[Dict[str, Any]] = {}
    warnings: ClassVar[List[str]] = []
    auto_install_enabled: ClassVar[bool] = False
    _instance: ClassVar[Optional["GrammarProvisioner"]] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "GrammarProvisioner":
        with cls._LOCK:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    @classmethod
    def reset_cache(cls) -> None:
        """Clear negative cache, loaded language cache, and accumulated warnings."""
        with cls._LOCK:
            cls._FAILED_PACKAGES.clear()
            cls._LOADED_LANGUAGES.clear()
            cls.warnings.clear()

    @classmethod
    def get_warnings(cls, clear: bool = False) -> List[str]:
        """Return accumulated grammar provisioning warnings."""
        with cls._LOCK:
            out = list(cls.warnings)
            if clear:
                cls.warnings.clear()
            return out

    @classmethod
    def _emit_warning(cls, pkg_label: str) -> str:
        msg = f"[ast:warn] Grammar package '{pkg_label}' is unavailable; skipping AST parse."
        with cls._LOCK:
            if msg not in cls.warnings:
                cls.warnings.append(msg)
                print(msg, file=sys.stderr, flush=True)
                logger.warning(msg)
        return msg

    @classmethod
    @contextmanager
    def _provision_lock(cls) -> Iterator[None]:
        """Acquires a cross-process file lock around JIT grammar installation."""
        lock_obj = None
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
            try:
                lock_obj = InterProcessLock(lock_path, timeout=60.0)
            except TypeError:
                lock_obj = InterProcessLock(lock_path)
            try:
                lock_obj.acquire(blocking=True, timeout=60.0)
            except TypeError:
                try:
                    lock_obj.acquire(timeout=60.0)
                except TypeError:
                    lock_obj.acquire()
        except Exception:
            lock_obj = None
        try:
            yield
        finally:
            if lock_obj is not None:
                try:
                    lock_obj.release()
                except Exception:
                    pass

    @classmethod
    def _try_pip_install(cls, pkg_name: str, module_name: Optional[str] = None) -> bool:
        """
        Attempt to install a missing grammar package via pip with stdout and stderr strictly redirected to sys.stderr.
        Synchronizes across processes and performs a double-checked import check after acquiring the lock.
        """
        with cls._LOCK:
            if pkg_name in cls._FAILED_PACKAGES:
                return False

        with cls._provision_lock():
            with cls._LOCK:
                if pkg_name in cls._FAILED_PACKAGES:
                    return False
                if module_name:
                    importlib.invalidate_caches()
                    try:
                        importlib.import_module(module_name)
                        return True
                    except ImportError:
                        pass

                try:
                    cmd = [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--quiet",
                        "--disable-pip-version-check",
                        pkg_name,
                    ]
                    proc = subprocess.run(
                        cmd,
                        stdout=sys.stderr,
                        stderr=sys.stderr,
                        timeout=30,
                        check=False,
                    )
                    if proc.returncode == 0:
                        importlib.invalidate_caches()
                        return True
                except Exception as exc:
                    logger.debug(f"GrammarProvisioner pip install failed for '{pkg_name}': {exc}")

                cls._FAILED_PACKAGES.add(pkg_name)
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
        If the grammar module is missing and `auto_install_pkg` is provided (or mapped),
        optionally attempts a one-shot pip install with output isolated to `sys.stderr`.
        On failure, records the package in `_FAILED_PACKAGES`, emits `[ast:warn]` to `sys.stderr`, and returns `None`.
        """
        with cls._LOCK:
            if ":" in module_name:
                module_name, func_name = module_name.split(":", 1)

            cache_key = f"{lang_key}:{module_name}:{func_name}"
            if cache_key in cls._LOADED_LANGUAGES:
                return cls._LOADED_LANGUAGES[cache_key]

            pkg_name = auto_install_pkg or DEFAULT_GRAMMAR_PACKAGES.get(module_name) or module_name.replace("_", "-")
            if pkg_name in cls._FAILED_PACKAGES or module_name in cls._FAILED_PACKAGES:
                cls._emit_warning(pkg_name)
                return None

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

            if mod is None:
                cls._FAILED_PACKAGES.add(pkg_name)
                cls._FAILED_PACKAGES.add(module_name)
                cls._emit_warning(pkg_name)
                return None

            if tree_sitter is None:
                cls._FAILED_PACKAGES.add("tree-sitter")
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
                cls._LOADED_LANGUAGES[cache_key] = ts_lang
                return ts_lang
            except Exception as exc:
                logger.debug(f"GrammarProvisioner failed initializing '{module_name}:{func_name}': {exc}")
                cls._FAILED_PACKAGES.add(pkg_name)
                cls._FAILED_PACKAGES.add(module_name)
                cls._emit_warning(pkg_name)
                return None


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
