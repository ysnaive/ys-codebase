"""Shared test utilities, dynamic script module loaders, and configuration/workspace state snapshot helper for agents-workflow tests."""

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Sequence, Tuple

TESTS_DIR: Path = Path(__file__).resolve().parent
PKG_ROOT: Path = TESTS_DIR.parent

_STORAGE_LOCAL_MANIFEST_URIS: Tuple[str, ...] = (
    "storage.local://agents-workflow/project_release_manifest.json",
    "storage.local://agents-workflow/release_manifest.json",
    "storage.local://agents-workflow/source_sha1_cache.json",
)


def ensure_pkg_root_on_path() -> Path:
    """Ensure the agents-workflow package root is at the front of sys.path."""
    pkg_str = str(PKG_ROOT)
    if pkg_str not in sys.path:
        sys.path.insert(0, pkg_str)
    return PKG_ROOT


def _load_script_module(module_name: str, rel_parts: Sequence[str]) -> ModuleType:
    """Dynamically load a Python script under PKG_ROOT by relative path components."""
    ensure_pkg_root_on_path()
    script_path = PKG_ROOT.joinpath(*rel_parts)
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_cli_module(module_name: str = "agents_workflow_cli_test") -> ModuleType:
    """Load scripts/cli.py as an isolated module."""
    return _load_script_module(module_name, ("scripts", "cli.py"))


def load_hook_core_module(module_name: str = "agents_workflow_hook_core_test") -> ModuleType:
    """Load scripts/hook.core.py as an isolated module."""
    return _load_script_module(module_name, ("scripts", "hook.core.py"))


def load_hook_dev_module(module_name: str = "agents_workflow_hook_dev_test") -> ModuleType:
    """Load scripts/hook.dev.py as an isolated module."""
    return _load_script_module(module_name, ("scripts", "hook.dev.py"))


def load_migration_module(
    version: str = "1.2.4.x",
    module_name: str = "agents_workflow_migration_test",
) -> ModuleType:
    """Load scripts/migrations/<version>.py as an isolated module."""
    filename = version if version.endswith(".py") else f"{version}.py"
    return _load_script_module(module_name, ("scripts", "migrations", filename))


class ConfigStateSnapshot:
    """
    Captures and restores dual-tier configuration files (`agents-workflow` and `core`),
    the 3 `storage.local://` release/SHA-1 cache manifests, and host workspace files
    (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.gitignore`, `.github/copilot-instructions.md`).
    """

    def __init__(self, proj_root: Optional[ str | os.PathLike ] = None) -> None:
        self._explicit_proj_root = Path(proj_root).resolve() if proj_root else None
        self._config_snapshots: Dict[str, Tuple[bool, Optional[bytes]]] = {}
        self._manifest_snapshots: Dict[str, Tuple[bool, Optional[bytes], Optional[str]]] = {}
        self._file_snapshots: Dict[Path, Tuple[bool, Optional[bytes]]] = {}
        self._dir_snapshots: Dict[Path, Tuple[bool, Dict[str, bytes]]] = {}
        self.proj_root: Path = self._resolve_proj_root()
        self.capture()

    def _resolve_proj_root(self) -> Path:
        if self._explicit_proj_root is not None:
            return self._explicit_proj_root
        try:
            from core import uri
            resolved = uri.resolve("project://", interactive=False)
            if resolved and not str(resolved).startswith("!"):
                return Path(resolved).resolve()
        except Exception:
            pass
        return Path.cwd().resolve()

    @staticmethod
    def _read_file_state(path: Path) -> Tuple[bool, Optional[bytes]]:
        if path.is_file():
            try:
                return True, path.read_bytes()
            except OSError:
                return False, None
        return False, None

    @staticmethod
    def _restore_file_state(path: Path, state: Tuple[bool, Optional[bytes]]) -> None:
        existed, raw_bytes = state
        if existed and raw_bytes is not None:
            try:
                if not path.is_file() or path.read_bytes() != raw_bytes:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw_bytes)
            except OSError:
                pass
        else:
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _capture_dir_state(dir_path: Path) -> Tuple[bool, Dict[str, bytes]]:
        if not dir_path.is_dir():
            return False, {}
        files_map: Dict[str, bytes] = {}
        for root, _, files in os.walk(dir_path):
            for fname in files:
                fpath = Path(root) / fname
                rel = str(fpath.relative_to(dir_path)).replace("\\", "/")
                try:
                    files_map[rel] = fpath.read_bytes()
                except OSError:
                    pass
        return True, files_map

    @staticmethod
    def _restore_dir_state(dir_path: Path, state: Tuple[bool, Dict[str, bytes]]) -> None:
        existed, files_map = state
        if not existed:
            if dir_path.exists():
                shutil.rmtree(dir_path, ignore_errors=True)
            return

        dir_path.mkdir(parents=True, exist_ok=True)
        existing_rels = set()
        for root, _, files in os.walk(dir_path):
            for fname in files:
                fpath = Path(root) / fname
                rel = str(fpath.relative_to(dir_path)).replace("\\", "/")
                existing_rels.add(rel)
                if rel not in files_map:
                    try:
                        fpath.unlink()
                    except OSError:
                        pass

        for rel, raw_bytes in files_map.items():
            target_f = dir_path / rel
            try:
                if not target_f.is_file() or target_f.read_bytes() != raw_bytes:
                    target_f.parent.mkdir(parents=True, exist_ok=True)
                    target_f.write_bytes(raw_bytes)
            except OSError:
                pass

        for root, dirs, files in os.walk(dir_path, topdown=False):
            for dname in dirs:
                dpath = Path(root) / dname
                try:
                    if dpath.is_dir() and not any(dpath.iterdir()):
                        dpath.rmdir()
                except OSError:
                    pass

    def capture(self) -> "ConfigStateSnapshot":
        """Take a snapshot of configuration files, manifests, and workspace artifacts."""
        self._config_snapshots.clear()
        self._manifest_snapshots.clear()
        self._file_snapshots.clear()
        self._dir_snapshots.clear()

        try:
            from core import config
            for mod_name in ("agents-workflow", "core"):
                for is_local in (False, True):
                    cfg_path = config.get_config_path(mod_name, local=is_local)
                    if cfg_path:
                        self._config_snapshots[cfg_path] = self._read_file_state(Path(cfg_path))
        except Exception:
            pass

        try:
            from core import uri, vfs
            for m_uri in _STORAGE_LOCAL_MANIFEST_URIS:
                resolved_p: Optional[str] = None
                try:
                    resolved_p = uri.resolve(m_uri, interactive=False)
                except Exception:
                    resolved_p = None
                if resolved_p and not str(resolved_p).startswith("!"):
                    existed, raw_b = self._read_file_state(Path(resolved_p))
                    self._manifest_snapshots[m_uri] = (existed, raw_b, resolved_p)
                elif vfs and vfs.exists(m_uri):
                    try:
                        raw_txt = vfs.read_text(m_uri)
                        self._manifest_snapshots[m_uri] = (True, raw_txt.encode("utf-8"), None)
                    except Exception:
                        self._manifest_snapshots[m_uri] = (False, None, None)
                else:
                    self._manifest_snapshots[m_uri] = (False, None, resolved_p)
        except Exception:
            pass

        for rel_file in ("AGENTS.md", "CLAUDE.md", ".gitignore", ".github/copilot-instructions.md"):
            f_path = self.proj_root / rel_file
            self._file_snapshots[f_path] = self._read_file_state(f_path)

        for rel_dir in (".claude", ".agents"):
            d_path = self.proj_root / rel_dir
            self._dir_snapshots[d_path] = self._capture_dir_state(d_path)

        return self

    def restore(self) -> None:
        """Restore all captured configuration files, manifests, and workspace artifacts."""
        for cfg_path_str, state in self._config_snapshots.items():
            self._restore_file_state(Path(cfg_path_str), state)

        try:
            from core import vfs
        except Exception:
            vfs = None

        for m_uri, (existed, raw_b, resolved_p) in self._manifest_snapshots.items():
            if resolved_p:
                self._restore_file_state(Path(resolved_p), (existed, raw_b))
            elif vfs is not None:
                try:
                    if existed and raw_b is not None:
                        vfs.write_text(m_uri, raw_b.decode("utf-8"), atomic=True)
                    elif vfs.exists(m_uri):
                        vfs.remove(m_uri)
                except Exception:
                    pass

        for f_path, state in self._file_snapshots.items():
            self._restore_file_state(f_path, state)
            if not state[0] and f_path.parent != self.proj_root:
                try:
                    if f_path.parent.is_dir() and not any(f_path.parent.iterdir()):
                        f_path.parent.rmdir()
                except OSError:
                    pass

        for d_path, dir_state in self._dir_snapshots.items():
            self._restore_dir_state(d_path, dir_state)

        try:
            from core import config
            config.reload()
        except Exception:
            pass

    def __enter__(self) -> "ConfigStateSnapshot":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.restore()


__all__: List[str] = [
    "TESTS_DIR",
    "PKG_ROOT",
    "ensure_pkg_root_on_path",
    "load_cli_module",
    "load_hook_core_module",
    "load_hook_dev_module",
    "load_migration_module",
    "ConfigStateSnapshot",
]
