"""
Declarative Read-Only File Lock Engine (`core.file_lock`).

Provides cross-platform (Linux, macOS, Windows) file-level read-only permission locking
driven by the `/readonly` logical file space (`spaces.readonly` declarations and
`on_register_file_spaces` hooks), along with transparent VFS pre-write unlock and
post-write relock helpers and a re-entrant `writable_scope` context manager.
100% Python Standard Library.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from core.context import bind_runtime_context, get_current_scope, get_runtime_context, get_virtual_cwd

PathLike = Union[str, Path]

_POSIX_WRITE_BITS: int = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_POSIX_OWNER_RW_BITS: int = stat.S_IWUSR | stat.S_IRUSR
_SKIP_EXT_SUFFIXES: Tuple[str, ...] = (".pyc", ".pyo", ".pyd", ".tmp")
_SKIP_DIR_SEGMENTS: frozenset[str] = frozenset({
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
})
_SKIP_BASENAME_PREFIXES: Tuple[str, ...] = (
    ".yscb_tmp_",
    ".yscb_probe_",
    ".yscb_restore_",
    ".old_",
    ".staging_",
)


@dataclass(frozen=True)
class FileLockMatchInfo:
    """Diagnostic match and physical permission status for a single target path."""

    path: str
    is_protected: bool
    matched_spaces: Tuple[str, ...] = ()
    exists: bool = False
    is_readonly: bool = False
    mode_octal: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileLockMatchInfo into a JSON-compatible dictionary."""
        return {
            "path": self.path,
            "is_protected": self.is_protected,
            "matched_spaces": list(self.matched_spaces),
            "exists": self.exists,
            "is_readonly": self.is_readonly,
            "mode_octal": self.mode_octal,
        }


@dataclass(frozen=True)
class FileLockSyncResult:
    """Summary result of a space or path lock/unlock synchronization operation."""

    target_space: str
    scanned_count: int
    locked_count: int
    already_locked_count: int
    unlocked_count: int
    skipped_count: int
    error_count: int
    elapsed_ms: float
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileLockSyncResult into a JSON-compatible dictionary."""
        return {
            "target_space": self.target_space,
            "scanned_count": self.scanned_count,
            "locked_count": self.locked_count,
            "already_locked_count": self.already_locked_count,
            "unlocked_count": self.unlocked_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "errors": list(self.errors),
        }


def _resolve_target_path(path: PathLike, root_dir: Optional[PathLike] = None) -> str:
    """Resolve a semantic URI or relative/absolute path into a normalized physical path."""
    raw = str(path or "").strip()
    if not raw:
        base = str(root_dir) if root_dir is not None else get_virtual_cwd()
        return os.path.normpath(os.path.abspath(base))

    if "://" in raw:
        try:
            if root_dir is not None:
                from core.space.registry import SpaceRegistry
                from core.space.schema import resolve_semantic_or_rel_path

                eff_proj, eff_yscb = SpaceRegistry._resolve_roots(root_dir, None)
                res_p = resolve_semantic_or_rel_path(raw, eff_proj, eff_yscb)
                if res_p is not None:
                    return os.path.normpath(os.path.abspath(str(res_p)))
            else:
                from core import uri as core_uri

                resolved = core_uri.resolve(raw, interactive=False)
                if resolved and not str(resolved).startswith("!undefined"):
                    return os.path.normpath(os.path.abspath(str(resolved)))
        except Exception:
            pass

    if os.path.isabs(raw):
        return os.path.normpath(raw)

    base_dir = str(root_dir) if root_dir is not None else get_virtual_cwd()
    return os.path.normpath(os.path.abspath(os.path.join(base_dir, raw)))


def _quick_exclude_path(norm_abs: str) -> bool:
    """Fast string-level filter for transient temp files, bytecode, and VCS directories."""
    if not norm_abs:
        return True
    norm_posix = os.path.normcase(norm_abs).replace("\\", "/")
    if norm_posix.endswith(_SKIP_EXT_SUFFIXES):
        return True
    base = norm_posix.rsplit("/", 1)[-1]
    if (
        ".tmp." in base
        or ".tmp_" in base
        or ".exdev." in base
        or ".conflict." in base
        or ".remote_conflict." in base
        or base.startswith(_SKIP_BASENAME_PREFIXES)
    ):
        return True
    parts = norm_posix.split("/")
    for seg in parts:
        if seg in _SKIP_DIR_SEGMENTS or seg.startswith((".old_", ".staging_")):
            return True
    return False


def _get_active_writable_scopes() -> Dict[str, int]:
    tls = get_runtime_context().file_lock_tls
    scopes: Optional[Dict[str, int]] = getattr(tls, "active_scopes", None)
    if scopes is None:
        scopes = {}
        tls.active_scopes = scopes
    return scopes


def _canonical_scope_key(norm_abs: str) -> str:
    """Normalize `norm_abs` resolving ancestor directory symlinks while preserving leaf symlinks."""
    norm_p = os.path.normpath(norm_abs)
    parent = os.path.dirname(norm_p)
    base = os.path.basename(norm_p)
    if parent:
        try:
            real_parent = os.path.realpath(parent)
            norm_p = os.path.join(real_parent, base) if base else real_parent
        except OSError:
            pass
    return os.path.normcase(os.path.normpath(norm_p))


def _is_in_writable_scope(norm_abs: str) -> bool:
    """Check whether `norm_abs` or any of its parent directories is inside an active `writable_scope`."""
    tls = get_runtime_context().file_lock_tls
    scopes: Optional[Dict[str, int]] = getattr(tls, "active_scopes", None)
    if not scopes:
        return False
    norm_key = _canonical_scope_key(norm_abs)
    if scopes.get(norm_key, 0) > 0:
        return True
    for scope_key, depth in scopes.items():
        if depth > 0:
            prefix = scope_key if scope_key.endswith(os.sep) else scope_key + os.sep
            if norm_key.startswith(prefix):
                return True
    return False


def is_file_readonly(path: PathLike) -> bool:
    """
    Return True if `path` is an existing regular file (not a symlink or directory)
    whose OS write permission bits are stripped. Uses a single `os.lstat` syscall.
    """
    norm_p = _resolve_target_path(path)
    try:
        st = os.lstat(norm_p)
    except OSError:
        return False

    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return False

    if os.name == "nt":
        return (st.st_mode & stat.S_IWRITE) == 0
    return (st.st_mode & _POSIX_WRITE_BITS) == 0


def _apply_lock_bits_state(norm_p: str, *, skip_quick_check: bool = False) -> str:
    """
    Internal helper that applies read-only bits to a single normalized path using a single `os.lstat`.
    Returns one of: `"locked"`, `"already_locked"`, `"skipped"`, or `"error"`.
    """
    if not skip_quick_check and _quick_exclude_path(norm_p):
        return "skipped"
    try:
        st = os.lstat(norm_p)
    except OSError:
        return "skipped"

    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return "skipped"

    mode = stat.S_IMODE(st.st_mode)
    if os.name == "nt":
        if (mode & stat.S_IWRITE) == 0:
            return "already_locked"
        try:
            os.chmod(norm_p, stat.S_IREAD)
            return "locked"
        except OSError:
            return "error"

    if (mode & _POSIX_WRITE_BITS) == 0:
        return "already_locked"
    new_mode = mode & ~_POSIX_WRITE_BITS
    if (new_mode & stat.S_IRUSR) == 0:
        new_mode |= stat.S_IRUSR
    try:
        os.chmod(norm_p, new_mode)
        return "locked"
    except OSError:
        return "error"


def _strip_lock_bits_state(norm_p: str) -> str:
    """
    Internal helper that restores owner write bits on a single normalized path using a single `os.lstat`.
    Returns one of: `"unlocked"`, `"already_unlocked"`, `"skipped"`, or `"error"`.
    """
    try:
        st = os.lstat(norm_p)
    except OSError:
        return "skipped"

    if stat.S_ISLNK(st.st_mode):
        return "skipped"

    mode = stat.S_IMODE(st.st_mode)
    if stat.S_ISDIR(st.st_mode):
        if os.name == "nt":
            if (mode & stat.S_IWRITE) != 0:
                return "already_unlocked"
            try:
                os.chmod(norm_p, mode | stat.S_IREAD | stat.S_IWRITE)
                return "unlocked"
            except OSError:
                return "error"
        req_dir_bits = stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR
        if (mode & req_dir_bits) == req_dir_bits:
            return "already_unlocked"
        try:
            os.chmod(norm_p, mode | req_dir_bits)
            return "unlocked"
        except OSError:
            return "error"

    if not stat.S_ISREG(st.st_mode):
        return "skipped"

    if os.name == "nt":
        if (mode & stat.S_IWRITE) != 0:
            return "already_unlocked"
        try:
            os.chmod(norm_p, mode | stat.S_IREAD | stat.S_IWRITE)
            return "unlocked"
        except OSError:
            return "error"

    if (mode & stat.S_IWUSR) != 0:
        return "already_unlocked"
    try:
        os.chmod(norm_p, mode | _POSIX_OWNER_RW_BITS)
        return "unlocked"
    except OSError:
        return "error"


def apply_lock_bits(path: PathLike) -> bool:
    """
    Strip write permission bits on `path` (preserving execute bits on POSIX).
    Returns True if the file is now read-only (newly locked or already locked).
    """
    norm_p = _resolve_target_path(path)
    state = _apply_lock_bits_state(norm_p)
    return state in ("locked", "already_locked")


def strip_lock_bits(path: PathLike) -> bool:
    """
    Restore owner write permission bits on `path` if it exists and is read-only.
    Returns True if the file is now writable (newly unlocked or already writable).
    """
    norm_p = _resolve_target_path(path)
    state = _strip_lock_bits_state(norm_p)
    return state in ("unlocked", "already_unlocked")


def _is_protected_norm(
    norm_abs: str,
    root_dir: Optional[PathLike] = None,
    registry: Optional[Any] = None,
) -> bool:
    """
    Zero-stat fast boolean check evaluating whether `norm_abs` is governed by `/readonly`.
    """
    if _quick_exclude_path(norm_abs):
        return False
    try:
        if os.path.islink(norm_abs):
            return False
    except OSError:
        pass

    tls = get_runtime_context().file_lock_tls
    if getattr(tls, "in_lock_op", False):
        return False

    tls.in_lock_op = True
    try:
        if registry is None:
            from core.space.registry import get_default_registry

            reg = get_default_registry(project_root=root_dir)
        else:
            reg = registry
        if not reg.has_space("/readonly"):
            return False
        return bool(reg.is_path_matched_fast(norm_abs, space_query="/readonly", is_dir=False))
    except Exception:
        return False
    finally:
        tls.in_lock_op = False


def is_protected(path: PathLike, root_dir: Optional[PathLike] = None) -> bool:
    """Return True if `path` matches the `/readonly` logical space (fast path, $< 0.2\text{ms}$)."""
    norm_abs = _resolve_target_path(path, root_dir=root_dir)
    return _is_protected_norm(norm_abs, root_dir=root_dir)


def inspect_path(path: PathLike, root_dir: Optional[PathLike] = None) -> FileLockMatchInfo:
    """
    Evaluate whether `path` is governed by the `/readonly` union space and inspect its
    current physical permission state on disk.
    """
    norm_abs = _resolve_target_path(path, root_dir=root_dir)
    exists = False
    is_ro = False
    is_dir_actual = False
    mode_octal = ""
    try:
        st = os.lstat(norm_abs)
        if not stat.S_ISLNK(st.st_mode):
            is_dir_actual = stat.S_ISDIR(st.st_mode)
            if stat.S_ISREG(st.st_mode):
                exists = True
                mode_octal = oct(stat.S_IMODE(st.st_mode))
                if os.name == "nt":
                    is_ro = (st.st_mode & stat.S_IWRITE) == 0
                else:
                    is_ro = (st.st_mode & _POSIX_WRITE_BITS) == 0
            elif is_dir_actual:
                exists = True
                mode_octal = oct(stat.S_IMODE(st.st_mode))
    except OSError:
        pass

    if _quick_exclude_path(norm_abs):
        return FileLockMatchInfo(
            path=norm_abs,
            is_protected=False,
            matched_spaces=(),
            exists=exists,
            is_readonly=is_ro,
            mode_octal=mode_octal,
        )

    tls = get_runtime_context().file_lock_tls
    if getattr(tls, "in_lock_op", False):
        return FileLockMatchInfo(
            path=norm_abs,
            is_protected=False,
            matched_spaces=(),
            exists=exists,
            is_readonly=is_ro,
            mode_octal=mode_octal,
        )

    tls.in_lock_op = True
    try:
        from core.space.registry import get_default_registry

        reg = get_default_registry(project_root=root_dir)
        if not reg.has_space("/readonly"):
            return FileLockMatchInfo(
                path=norm_abs,
                is_protected=False,
                matched_spaces=(),
                exists=exists,
                is_readonly=is_ro,
                mode_octal=mode_octal,
            )
        match_res = reg.match_path(norm_abs, space_query="/readonly", is_dir=is_dir_actual)
        return FileLockMatchInfo(
            path=norm_abs,
            is_protected=bool(match_res.matched),
            matched_spaces=tuple(match_res.matched_spaces),
            exists=exists,
            is_readonly=is_ro,
            mode_octal=mode_octal,
        )
    except Exception:
        return FileLockMatchInfo(
            path=norm_abs,
            is_protected=False,
            matched_spaces=(),
            exists=exists,
            is_readonly=is_ro,
            mode_octal=mode_octal,
        )
    finally:
        tls.in_lock_op = False


def relock_if_protected(path: PathLike, root_dir: Optional[PathLike] = None) -> bool:
    """
    If `path` is not inside an active `writable_scope` and matches `/readonly`,
    apply read-only lock bits (supporting both single files and directories).
    """
    norm_abs = _resolve_target_path(path, root_dir=root_dir)
    if _quick_exclude_path(norm_abs) or _is_in_writable_scope(norm_abs):
        return False

    tls = get_runtime_context().file_lock_tls
    if getattr(tls, "in_lock_op", False):
        return False

    try:
        st = os.lstat(norm_abs)
    except OSError:
        return False

    if stat.S_ISLNK(st.st_mode):
        return False
    if stat.S_ISDIR(st.st_mode):
        base = os.path.basename(norm_abs)
        if base.startswith(_SKIP_BASENAME_PREFIXES):
            return False
        res = lock_path(norm_abs, force=False, root_dir=root_dir)
        return (res.locked_count + res.already_locked_count) > 0
    if not stat.S_ISREG(st.st_mode):
        return False

    if _is_protected_norm(norm_abs, root_dir=root_dir):
        return _apply_lock_bits_state(norm_abs, skip_quick_check=True) in ("locked", "already_locked")
    return False


@contextmanager
def writable_scope(*paths: PathLike, root_dir: Optional[PathLike] = None) -> Iterator[None]:
    """
    Re-entrant context manager that temporarily strips read-only lock bits on `*paths`
    (files or directories) and suppresses intermediate VFS relocking until the outermost
    scope for each path exits, then automatically re-applies `/readonly` locks.
    """
    resolved_targets: List[Tuple[str, str]] = []
    scopes = _get_active_writable_scopes()

    try:
        for p in paths:
            norm_p = _resolve_target_path(p, root_dir=root_dir)
            norm_key = _canonical_scope_key(norm_p)
            scopes[norm_key] = scopes.get(norm_key, 0) + 1
            resolved_targets.append((norm_p, norm_key))
            try:
                st = os.lstat(norm_p)
                if not stat.S_ISLNK(st.st_mode):
                    if stat.S_ISDIR(st.st_mode):
                        _strip_lock_bits_state(norm_p)
                        for r_dir, d_names, f_names in os.walk(norm_p):
                            d_names[:] = [d for d in d_names if d not in _SKIP_DIR_SEGMENTS]
                            for fn in f_names:
                                _strip_lock_bits_state(os.path.join(r_dir, fn))
                    elif stat.S_ISREG(st.st_mode):
                        _strip_lock_bits_state(norm_p)
            except OSError:
                pass
        yield
    finally:
        to_relock: List[str] = []
        for norm_p, norm_key in resolved_targets:
            rem = scopes.get(norm_key, 1) - 1
            if rem <= 0:
                scopes.pop(norm_key, None)
                to_relock.append(norm_p)
            else:
                scopes[norm_key] = rem

        for norm_p in to_relock:
            if not _is_in_writable_scope(norm_p):
                relock_if_protected(norm_p, root_dir=root_dir)


def _normalize_readonly_space_query(target_space: Optional[str], reg: Any) -> str:
    raw = str(target_space or "/readonly").strip()
    if not raw or raw in ("readonly", "/readonly"):
        return "/readonly"
    if raw.startswith("/"):
        return raw
    if "/" not in raw:
        cand = f"{raw}/readonly"
        if reg.has_space(cand):
            return cand
    return raw


def _is_explicit_readonly_space_query(raw_str: str) -> bool:
    """Return True if `raw_str` explicitly names the `/readonly` or `<owner>/readonly` space."""
    return raw_str in ("", "/readonly", "readonly") or (
        "://" not in raw_str and raw_str.endswith("/readonly")
    )


def lock_path(
    path: PathLike,
    *,
    force: bool = False,
    root_dir: Optional[PathLike] = None,
) -> FileLockSyncResult:
    """
    Apply read-only lock bits to a single file, recursively across a directory,
    or across a logical `readonly` space.
    When `force=False` (default), only locks files that match `/readonly`.
    When `force=True`, locks all non-excluded regular files under `path`.
    """
    raw_str = str(path or "").strip()
    if not force and _is_explicit_readonly_space_query(raw_str):
        return sync(target_space=raw_str or "/readonly", root_dir=root_dir, emit_event=False)

    t0 = time.perf_counter()
    norm_abs = _resolve_target_path(path, root_dir=root_dir)

    if not force and not os.path.exists(norm_abs) and "://" not in raw_str and "/" not in raw_str:
        try:
            from core.space.registry import get_default_registry

            reg_cand = get_default_registry(project_root=root_dir)
            q_cand = _normalize_readonly_space_query(raw_str, reg_cand)
            if reg_cand.has_space(q_cand):
                return sync(target_space=q_cand, root_dir=root_dir, emit_event=False)
        except Exception:
            pass

    scanned = 0
    locked = 0
    already_locked = 0
    skipped = 0
    err_count = 0
    errors: List[str] = []

    reg_instance: Optional[Any] = None
    if not force:
        tls = get_runtime_context().file_lock_tls
        if not getattr(tls, "in_lock_op", False):
            tls.in_lock_op = True
            try:
                from core.space.registry import get_default_registry

                reg_instance = get_default_registry(project_root=root_dir)
            except Exception:
                reg_instance = None
            finally:
                tls.in_lock_op = False

    if os.path.isdir(norm_abs) and not os.path.islink(norm_abs):
        for r_dir, d_names, f_names in os.walk(norm_abs):
            d_names[:] = [
                d
                for d in d_names
                if d not in _SKIP_DIR_SEGMENTS and not d.startswith(_SKIP_BASENAME_PREFIXES)
            ]
            for fn in sorted(f_names):
                f_abs = os.path.join(r_dir, fn)
                if _quick_exclude_path(f_abs) or _is_in_writable_scope(f_abs):
                    skipped += 1
                    continue
                scanned += 1
                if not force and not _is_protected_norm(
                    f_abs, root_dir=root_dir, registry=reg_instance
                ):
                    skipped += 1
                    continue
                st_res = _apply_lock_bits_state(f_abs, skip_quick_check=True)
                if st_res == "locked":
                    locked += 1
                elif st_res == "already_locked":
                    already_locked += 1
                elif st_res == "error":
                    err_count += 1
                    errors.append(f_abs)
                else:
                    skipped += 1
    elif os.path.exists(norm_abs):
        scanned = 1
        if _quick_exclude_path(norm_abs) or _is_in_writable_scope(norm_abs):
            skipped = 1
        elif not force and not _is_protected_norm(
            norm_abs, root_dir=root_dir, registry=reg_instance
        ):
            skipped = 1
        else:
            st_res = _apply_lock_bits_state(norm_abs, skip_quick_check=True)
            if st_res == "locked":
                locked = 1
            elif st_res == "already_locked":
                already_locked = 1
            elif st_res == "error":
                err_count = 1
                errors.append(norm_abs)
            else:
                skipped = 1

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return FileLockSyncResult(
        target_space=str(path),
        scanned_count=scanned,
        locked_count=locked,
        already_locked_count=already_locked,
        unlocked_count=0,
        skipped_count=skipped,
        error_count=err_count,
        elapsed_ms=elapsed_ms,
        errors=tuple(errors),
    )


def unlock_path(
    path: PathLike,
    *,
    root_dir: Optional[PathLike] = None,
) -> FileLockSyncResult:
    """
    Strip read-only lock bits from a file, directory, or logical `readonly` space.
    """
    t0 = time.perf_counter()
    raw_str = str(path or "").strip()
    norm_abs = _resolve_target_path(path, root_dir=root_dir) if raw_str else ""

    scanned = 0
    unlocked = 0
    skipped = 0
    err_count = 0
    errors: List[str] = []

    is_explicit_space = _is_explicit_readonly_space_query(raw_str)
    if is_explicit_space or (not os.path.exists(norm_abs) and "://" not in raw_str):
        tls = get_runtime_context().file_lock_tls
        if not getattr(tls, "in_lock_op", False):
            tls.in_lock_op = True
            try:
                from core.space.registry import get_default_registry

                reg = get_default_registry(project_root=root_dir)
                q_space = _normalize_readonly_space_query(raw_str, reg)
                if reg.has_space(q_space):
                    entries = reg.iter_space_files(q_space)
                    for entry in entries:
                        scanned += 1
                        st_res = _strip_lock_bits_state(str(entry.abs_path))
                        if st_res == "unlocked":
                            unlocked += 1
                        elif st_res == "error":
                            err_count += 1
                            errors.append(str(entry.abs_path))
                        else:
                            skipped += 1
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    return FileLockSyncResult(
                        target_space=q_space,
                        scanned_count=scanned,
                        locked_count=0,
                        already_locked_count=0,
                        unlocked_count=unlocked,
                        skipped_count=skipped,
                        error_count=err_count,
                        elapsed_ms=elapsed_ms,
                        errors=tuple(errors),
                    )
            except Exception:
                pass
            finally:
                tls.in_lock_op = False

    if norm_abs and os.path.isdir(norm_abs) and not os.path.islink(norm_abs):
        _strip_lock_bits_state(norm_abs)
        for r_dir, d_names, f_names in os.walk(norm_abs):
            d_names[:] = [d for d in d_names if d not in _SKIP_DIR_SEGMENTS]
            for fn in sorted(f_names):
                f_abs = os.path.join(r_dir, fn)
                scanned += 1
                st_res = _strip_lock_bits_state(f_abs)
                if st_res == "unlocked":
                    unlocked += 1
                elif st_res == "error":
                    err_count += 1
                    errors.append(f_abs)
                else:
                    skipped += 1
    elif norm_abs and os.path.exists(norm_abs):
        scanned = 1
        st_res = _strip_lock_bits_state(norm_abs)
        if st_res == "unlocked":
            unlocked = 1
        elif st_res == "error":
            err_count = 1
            errors.append(norm_abs)
        else:
            skipped = 1

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return FileLockSyncResult(
        target_space=raw_str or "/readonly",
        scanned_count=scanned,
        locked_count=0,
        already_locked_count=0,
        unlocked_count=unlocked,
        skipped_count=skipped,
        error_count=err_count,
        elapsed_ms=elapsed_ms,
        errors=tuple(errors),
    )


def sync(
    target_space: str = "/readonly",
    *,
    root_dir: Optional[PathLike] = None,
    emit_event: bool = True,
) -> FileLockSyncResult:
    """
    Scan `target_space` (defaulting to the `/readonly` union space) via `SpaceRegistry`
    and apply OS read-only lock bits to all matched files.
    """
    t0 = time.perf_counter()
    tls = get_runtime_context().file_lock_tls
    if getattr(tls, "in_lock_op", False):
        return FileLockSyncResult(
            target_space=target_space,
            scanned_count=0,
            locked_count=0,
            already_locked_count=0,
            unlocked_count=0,
            skipped_count=0,
            error_count=0,
            elapsed_ms=0.0,
        )

    scanned = 0
    locked = 0
    already_locked = 0
    skipped = 0
    err_count = 0
    errors: List[str] = []
    q_space = str(target_space or "/readonly").strip() or "/readonly"

    tls.in_lock_op = True
    try:
        from core.space.registry import get_default_registry

        reg = get_default_registry(project_root=root_dir)
        q_space = _normalize_readonly_space_query(q_space, reg)
        if not reg.has_space(q_space):
            return FileLockSyncResult(
                target_space=q_space,
                scanned_count=0,
                locked_count=0,
                already_locked_count=0,
                unlocked_count=0,
                skipped_count=0,
                error_count=0,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        entries = reg.iter_space_files(q_space)
        for entry in entries:
            f_abs = str(entry.abs_path)
            scanned += 1
            if _quick_exclude_path(f_abs) or _is_in_writable_scope(f_abs):
                skipped += 1
                continue
            st_res = _apply_lock_bits_state(f_abs, skip_quick_check=True)
            if st_res == "locked":
                locked += 1
            elif st_res == "already_locked":
                already_locked += 1
            elif st_res == "error":
                err_count += 1
                errors.append(f_abs)
            else:
                skipped += 1
    except Exception as exc:
        err_count += 1
        errors.append(str(exc))
    finally:
        tls.in_lock_op = False

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    result = FileLockSyncResult(
        target_space=q_space,
        scanned_count=scanned,
        locked_count=locked,
        already_locked_count=already_locked,
        unlocked_count=0,
        skipped_count=skipped,
        error_count=err_count,
        elapsed_ms=elapsed_ms,
        errors=tuple(errors),
    )

    if emit_event:
        try:
            from core import events as core_events

            core_events.broadcast(
                "on_file_lock_synced",
                result.to_dict(),
                emit_module="core",
            )
        except Exception:
            pass

    return result


def status(
    target: Optional[str] = None,
    *,
    root_dir: Optional[PathLike] = None,
) -> Dict[str, Any]:
    """
    Inspect `/readonly` lock synchronization status across all `<owner>/readonly` spaces
    or diagnose a single target path / space.
    """
    from core.space.registry import get_default_registry

    tls = get_runtime_context().file_lock_tls
    was_in_lock = bool(getattr(tls, "in_lock_op", False))
    tls.in_lock_op = True
    try:
        reg = get_default_registry(project_root=root_dir)
        raw_target = str(target or "").strip()

        if raw_target:
            q_cand = _normalize_readonly_space_query(raw_target, reg)
            if not reg.has_space(q_cand):
                tls.in_lock_op = was_in_lock
                info = inspect_path(raw_target, root_dir=root_dir)
                return {
                    "mode": "path",
                    **info.to_dict(),
                }
            if q_cand == "/readonly":
                target_spaces = [
                    s
                    for s in reg.list_spaces()
                    if s.owner != "" and s.short_name == "readonly"
                ]
            else:
                target_spaces = [
                    s
                    for s in reg.list_spaces()
                    if s.qualified_name == q_cand
                ]
        else:
            q_cand = "/readonly"
            target_spaces = [
                s
                for s in reg.list_spaces()
                if s.owner != "" and s.short_name == "readonly"
            ]

        space_reports: List[Dict[str, Any]] = []
        total_files = 0
        total_locked = 0
        total_unlocked = 0
        phys_ro_cache: Dict[str, bool] = {}

        with reg.batch_walk_session():
            for s_cfg in target_spaces:
                s_files = reg.iter_space_files(s_cfg.qualified_name)
                s_total = 0
                s_locked = 0
                s_unlocked = 0
                unlocked_sample: List[str] = []
                for entry in s_files:
                    f_abs = str(entry.abs_path)
                    if _quick_exclude_path(f_abs):
                        continue
                    s_total += 1
                    phys_k = os.path.normcase(f_abs)
                    if phys_k in phys_ro_cache:
                        ro = phys_ro_cache[phys_k]
                    else:
                        ro = is_file_readonly(f_abs)
                        phys_ro_cache[phys_k] = ro
                        total_files += 1
                        if ro:
                            total_locked += 1
                        else:
                            total_unlocked += 1

                    if ro:
                        s_locked += 1
                    else:
                        s_unlocked += 1
                        if len(unlocked_sample) < 10:
                            unlocked_sample.append(entry.rel_path)

                space_reports.append({
                    "space": s_cfg.qualified_name,
                    "owner": s_cfg.owner,
                    "description": s_cfg.description,
                    "entries": list(s_cfg.entries),
                    "include": list(s_cfg.include),
                    "exclude": list(s_cfg.exclude),
                    "total_files": s_total,
                    "locked_files": s_locked,
                    "unlocked_files": s_unlocked,
                    "in_sync": s_total == s_locked,
                    "unlocked_sample": unlocked_sample,
                })
    finally:
        tls.in_lock_op = was_in_lock

    return {
        "mode": "space",
        "target_space": q_cand,
        "total_spaces": len(space_reports),
        "total_files": total_files,
        "locked_files": total_locked,
        "unlocked_files": total_unlocked,
        "in_sync": total_files == total_locked,
        "spaces": space_reports,
    }


__all__ = (
    "FileLockMatchInfo",
    "FileLockSyncResult",
    "is_protected",
    "inspect_path",
    "is_file_readonly",
    "apply_lock_bits",
    "strip_lock_bits",
    "relock_if_protected",
    "writable_scope",
    "lock_path",
    "unlock_path",
    "sync",
    "status",
)
