"""
YS-Codebase VFS 作業系統本機後端實作 (OSBackend)。
100% Python 標準庫，提供跨平台路徑正規化、同分區原子寫入防護與沙盒防逃逸邊界檢驗。
"""

import os
import sys
import json
import errno
import stat
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, IO, Generator, Set

from core.context import get_runtime_context
from core.vfs.base import VFSBackend

_CONTRIB_CACHE_TRIGGER_FILES = frozenset({
    "contribute.json",
    "contributes.json",
    "contributes.merged.json",
    "contributes.meta.json",
    "core.json",
    "_format.json",
    "yscb.config.json",
    "config.project.json",
    "config.local.json",
})


def _maybe_invalidate_uri_cache(norm_path: str, is_dir_op: bool = False) -> None:
    """When contribute.json, config files, or directories are mutated via VFS, invalidate URI and contributes caches."""
    try:
        from core import uri
        get_runtime_context().contributes_json_file_cache.pop(norm_path, None)
        base = os.path.basename(norm_path)
        parent_base = os.path.basename(os.path.dirname(norm_path))
        if (
            is_dir_op
            or base in _CONTRIB_CACHE_TRIGGER_FILES
            or parent_base == "contributes"
            or base == "contributes"
        ):
            uri.invalidate_uri_cache()
    except Exception:
        pass


def _strip_lock_bits_safe(path: str) -> None:
    """Best-effort strip of read-only lock bits prior to VFS overwrite or delete (preserving directory traverse bits)."""
    try:
        from core import file_lock

        file_lock.strip_lock_bits(path)
    except Exception:
        try:
            st = os.lstat(path)
            if not stat.S_ISLNK(st.st_mode):
                mode = stat.S_IMODE(st.st_mode)
                if stat.S_ISDIR(st.st_mode):
                    req = (
                        (stat.S_IWRITE | stat.S_IREAD)
                        if os.name == "nt"
                        else (stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                    )
                    os.chmod(path, mode | req)
                else:
                    os.chmod(path, mode | stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


def _relock_if_protected_safe(path: str, root_dir: Optional[str] = None) -> None:
    """Best-effort re-application of `/readonly` lock bits after VFS mutation."""
    try:
        from core import file_lock

        file_lock.relock_if_protected(path, root_dir=root_dir)
    except Exception:
        pass


def _reconcile_copied_file_lock(src_path: str, dst_path: str, root_dir: Optional[str] = None) -> None:
    """
    Reconcile permission bits after `shutil.copy2(src_path, dst_path)`:
    - If `dst_path` is in `/readonly` (and not inside an active `writable_scope`), ensure it is locked.
    - Otherwise, strip read-only lock bits on `dst_path` (single `lstat` no-op if already writable)
      so unprotected copies never inherit `0o444`.
    """
    _ = src_path
    try:
        from core import file_lock

        if not file_lock.relock_if_protected(dst_path, root_dir=root_dir):
            file_lock.strip_lock_bits(dst_path)
    except Exception:
        pass


def _reconcile_tree_locks(dst_dir: str, root_dir: Optional[str] = None) -> None:
    """Reconcile read-only lock bits across all regular files inside a moved directory tree."""
    try:
        from core import file_lock

        for r_dir, _d_names, f_names in os.walk(dst_dir, followlinks=False):
            for fn in f_names:
                fp = os.path.join(r_dir, fn)
                if not os.path.islink(fp):
                    if not file_lock.relock_if_protected(fp, root_dir=root_dir):
                        file_lock.strip_lock_bits(fp)
    except Exception:
        pass


def robust_rmtree(path: str, ignore_errors: bool = False, max_retries: int = 5, retries: Optional[int] = None, retry_delay: float = 0.05) -> None:
    """
    Removes a directory tree across platforms, stripping read-only attributes on
    encountered files (such as Git packfiles on Windows) and retrying transient
    handle locks (`WinError 5` / `WinError 32`).
    """
    norm_path = os.path.normpath(os.path.abspath(path))
    if not (os.path.exists(norm_path) or os.path.lexists(norm_path)):
        return

    def _on_rm_error(func: Any, failed_path: str, exc_info: Any) -> None:
        exc = exc_info[1]
        if isinstance(exc, FileNotFoundError) or getattr(exc, "errno", None) == errno.ENOENT:
            return
        try:
            _strip_lock_bits_safe(failed_path)
            parent_p = os.path.dirname(failed_path)
            if parent_p and parent_p != failed_path:
                _strip_lock_bits_safe(parent_p)
            func(failed_path)
            return
        except Exception:
            if not ignore_errors:
                raise exc

    retries = max(1, retries if retries is not None else max_retries)
    for attempt in range(retries):
        try:
            if os.path.islink(norm_path) or os.path.isfile(norm_path):
                _strip_lock_bits_safe(norm_path)
                os.unlink(norm_path)
            elif os.path.exists(norm_path):
                shutil.rmtree(norm_path, onerror=_on_rm_error)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt < retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            if not ignore_errors:
                raise


def robust_replace(src: str, dst: str, max_retries: int = 10, root_dir: Optional[str] = None) -> None:
    """
    Atomically replaces ``dst`` with ``src`` across platforms, stripping read-only lock
    bits on ``dst`` prior to replacement, retrying transient Windows file locks
    (`PermissionError` / `WinError 5` / `WinError 32`), falling back to a same-directory
    staged copy + atomic replace on cross-filesystem (`errno.EXDEV`), and re-applying
    `/readonly` lock bits on ``dst`` afterward.
    """
    src_norm = os.path.normpath(os.path.abspath(src))
    dst_norm = os.path.normpath(os.path.abspath(dst))
    parent_dir = os.path.dirname(dst_norm)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    if os.path.exists(dst_norm) and not os.path.islink(dst_norm) and os.path.isfile(dst_norm):
        _strip_lock_bits_safe(dst_norm)

    retries = max(1, max_retries)
    for attempt in range(retries):
        try:
            os.replace(src_norm, dst_norm)
            _relock_if_protected_safe(dst_norm, root_dir=root_dir)
            return
        except OSError as err:
            if err.errno == errno.EXDEV:
                stage_name = f".{os.path.basename(dst_norm)}.exdev.{os.getpid()}_{uuid.uuid4().hex[:8]}"
                stage_path = os.path.join(parent_dir, stage_name) if parent_dir else stage_name
                try:
                    if os.path.isdir(src_norm) and not os.path.islink(src_norm):
                        shutil.copytree(src_norm, stage_path, symlinks=True)
                    else:
                        shutil.copy2(src_norm, stage_path, follow_symlinks=False)
                    if os.path.isdir(dst_norm) and not os.path.islink(dst_norm):
                        robust_rmtree(dst_norm, ignore_errors=True)
                    elif os.path.exists(dst_norm):
                        _strip_lock_bits_safe(dst_norm)
                    os.replace(stage_path, dst_norm)
                    if os.path.isdir(src_norm) and not os.path.islink(src_norm):
                        robust_rmtree(src_norm, ignore_errors=True)
                    elif os.path.exists(src_norm) or os.path.lexists(src_norm):
                        _strip_lock_bits_safe(src_norm)
                        os.remove(src_norm)
                    _relock_if_protected_safe(dst_norm, root_dir=root_dir)
                    return
                finally:
                    if os.path.exists(stage_path) or os.path.lexists(stage_path):
                        robust_rmtree(stage_path, ignore_errors=True)
            win_err = getattr(err, "winerror", None)
            is_transient = (
                isinstance(err, PermissionError)
                or err.errno in (errno.EACCES, errno.EPERM, errno.EBUSY)
                or win_err in (5, 32)
            )
            if is_transient and attempt < retries - 1:
                if os.path.exists(dst_norm):
                    _strip_lock_bits_safe(dst_norm)
                time.sleep(0.05 * (attempt + 1))
                continue
            raise


def _cleanup_stale_swap_dirs(parent_dir: str) -> None:
    """
    Sweeps and cleans up any residual .old_* or .staging_* directories inside parent_dir
    left behind by prior swaps or delayed handle releases.
    """
    if not parent_dir or not os.path.isdir(parent_dir):
        return
    try:
        entries = os.listdir(parent_dir)
    except Exception:
        return
    for entry in entries:
        if entry.startswith((".old_", ".staging_")):
            stale_path = os.path.join(parent_dir, entry)
            if os.path.isdir(stale_path):
                robust_rmtree(stale_path, ignore_errors=True, max_retries=3)


def _is_dir_handle_locked_for_rename(err: OSError, parent_dir: str, target_dir: str) -> bool:
    """
    Three-stage cross-platform discriminator to distinguish transient directory handle locking
    (e.g., Windows/virtiofs/WSL2/9p open directory handles by IDE/watchers) from genuine
    filesystem permission or I/O failures.
    """
    err_no = getattr(err, "errno", None)
    win_err = getattr(err, "winerror", None)
    if err_no not in (errno.EACCES, errno.EBUSY, errno.EPERM) and win_err not in (5, 32):
        return False

    if not os.path.isdir(parent_dir) or not os.path.isdir(target_dir):
        return False

    # Stage 1: Verify local OS access mode bits on both parent_dir and target_dir
    req_mode = os.W_OK if os.name == "nt" else (os.W_OK | os.X_OK)
    if not os.access(parent_dir, req_mode) or not os.access(target_dir, req_mode):
        return False

    # Stage 2: Execute a physical file-level write + atomic replace + unlink probe inside target_dir
    probe_src = os.path.join(target_dir, f".yscb_probe_src_{os.getpid()}_{int(time.time() * 1000)}")
    probe_dst = os.path.join(target_dir, f".yscb_probe_dst_{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(probe_src, "wb") as f:
            f.write(b"1")
            f.flush()
        os.replace(probe_src, probe_dst)
        os.remove(probe_dst)
        return True
    except Exception:
        return False
    finally:
        for p in (probe_src, probe_dst):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _inplace_atomic_sync_dir(staging_dir: str, target_dir: str) -> None:
    """
    Stage 3: All-or-nothing file-level atomic sync from staging_dir into target_dir when
    directory-level rename is blocked by host/virtiofs open directory handles.
    """
    staging_abs = os.path.abspath(staging_dir)
    target_abs = os.path.abspath(target_dir)
    parent_dir = os.path.dirname(target_abs)
    base_name = os.path.basename(target_abs)
    backup_dir = os.path.join(parent_dir, f".old_backup_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")

    existing_rel_files: Set[str] = set()
    os.makedirs(backup_dir, exist_ok=True)

    try:
        # 1. Snapshot all existing files in target_abs into backup_dir for all-or-nothing rollback
        for root, dirs, files in os.walk(target_abs):
            dirs[:] = [d for d in dirs if not d.startswith((".old_", ".staging_", ".yscb_probe_"))]
            rel_root = os.path.relpath(root, target_abs)
            if rel_root == ".":
                rel_root = ""
            for fname in files:
                if fname.startswith((".yscb_probe_", ".yscb_tmp_")):
                    continue
                rel_path = os.path.join(rel_root, fname) if rel_root else fname
                norm_rel = rel_path.replace("\\", "/")
                existing_rel_files.add(norm_rel)
                src_f = os.path.join(root, fname)
                bak_f = os.path.join(backup_dir, rel_path)
                os.makedirs(os.path.dirname(bak_f), exist_ok=True)
                shutil.copy2(src_f, bak_f)
                _strip_lock_bits_safe(bak_f)

        # 2. Atomically replace/create all files from staging_abs into target_abs
        staged_rel_files: Set[str] = set()
        for root, _dirs, files in os.walk(staging_abs):
            rel_root = os.path.relpath(root, staging_abs)
            if rel_root == ".":
                rel_root = ""
            target_sub = os.path.join(target_abs, rel_root) if rel_root else target_abs
            os.makedirs(target_sub, exist_ok=True)
            for fname in files:
                rel_path = os.path.join(rel_root, fname) if rel_root else fname
                norm_rel = rel_path.replace("\\", "/")
                staged_rel_files.add(norm_rel)
                src_f = os.path.join(root, fname)
                dst_f = os.path.join(target_abs, rel_path)
                tmp_dst = os.path.join(os.path.dirname(dst_f), f".yscb_tmp_{os.getpid()}_{fname}")
                try:
                    if os.path.exists(dst_f):
                        _strip_lock_bits_safe(dst_f)
                    shutil.copy2(src_f, tmp_dst)
                    os.replace(tmp_dst, dst_f)
                    _relock_if_protected_safe(dst_f)
                finally:
                    if os.path.exists(tmp_dst):
                        try:
                            _strip_lock_bits_safe(tmp_dst)
                            os.remove(tmp_dst)
                        except Exception:
                            pass

        # 3. Remove obsolete files that no longer exist in staging_abs
        obsolete_files = existing_rel_files - staged_rel_files
        for norm_rel in obsolete_files:
            obs_f = os.path.join(target_abs, norm_rel.replace("/", os.sep))
            if os.path.isfile(obs_f):
                _strip_lock_bits_safe(obs_f)
                os.remove(obs_f)

        # 4. Best-effort cleanup of empty obsolete subdirectories
        for root, dirs, _ in os.walk(target_abs, topdown=False):
            for d in dirs:
                d_abs = os.path.join(root, d)
                rel_d = os.path.relpath(d_abs, target_abs)
                staged_d = os.path.join(staging_abs, rel_d)
                if not os.path.exists(staged_d):
                    try:
                        if not os.listdir(d_abs):
                            os.rmdir(d_abs)
                    except OSError:
                        pass
    except Exception:
        # Full rollback from backup_dir if any file write/replace/unlink failed
        try:
            for root, _, files in os.walk(target_abs):
                rel_root = os.path.relpath(root, target_abs)
                if rel_root == ".":
                    rel_root = ""
                for fname in files:
                    rel_path = os.path.join(rel_root, fname) if rel_root else fname
                    norm_rel = rel_path.replace("\\", "/")
                    if norm_rel not in existing_rel_files:
                        target_f = os.path.join(root, fname)
                        _strip_lock_bits_safe(target_f)
                        try:
                            os.remove(target_f)
                        except Exception:
                            pass
            for norm_rel in existing_rel_files:
                rel_os = norm_rel.replace("/", os.sep)
                bak_f = os.path.join(backup_dir, rel_os)
                dst_f = os.path.join(target_abs, rel_os)
                if os.path.isfile(bak_f):
                    os.makedirs(os.path.dirname(dst_f), exist_ok=True)
                    tmp_restore = os.path.join(os.path.dirname(dst_f), f".yscb_restore_{os.getpid()}_{os.path.basename(dst_f)}")
                    shutil.copy2(bak_f, tmp_restore)
                    if os.path.exists(dst_f):
                        _strip_lock_bits_safe(dst_f)
                    os.replace(tmp_restore, dst_f)
                    _relock_if_protected_safe(dst_f)
        except Exception:
            pass
        raise
    finally:
        if os.path.exists(backup_dir):
            robust_rmtree(backup_dir, ignore_errors=True)


def atomic_swap_directory(
    staging_dir: str,
    target_dir: str,
    retries: int = 3,
    retry_delay: float = 0.05,
) -> None:
    """
    Atomically swaps `staging_dir` into `target_dir` within the same parent filesystem:
    1. Moves existing `target_dir` to a `.old_<name>_<pid>_<ts>` backup directory (falling back to
       3-stage handle-lock probe and all-or-nothing file-level sync when directory rename is locked).
    2. Moves `staging_dir` into `target_dir`.
    3. Rolls back `.old` into `target_dir` if step 2 fails (even if `target_dir` was partially created).
    4. Cleans up `.old`, `staging_dir`, and stale swap directories in `finally`.
    """
    _ = retry_delay
    target_abs = os.path.normpath(os.path.abspath(target_dir))
    staging_abs = os.path.normpath(os.path.abspath(staging_dir))
    parent_dir = os.path.dirname(target_abs)
    base_name = os.path.basename(target_abs)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    old_abs = os.path.join(parent_dir, f".old_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")

    moved_old = False
    swap_succeeded = False
    try:
        if os.path.exists(old_abs) or os.path.lexists(old_abs):
            robust_rmtree(old_abs, ignore_errors=True, max_retries=retries)
        if os.path.exists(target_abs) or os.path.lexists(target_abs):
            try:
                robust_replace(target_abs, old_abs, max_retries=retries)
                moved_old = True
            except OSError as rename_err:
                if _is_dir_handle_locked_for_rename(rename_err, parent_dir, target_abs):
                    _inplace_atomic_sync_dir(staging_abs, target_abs)
                    swap_succeeded = True
                    _maybe_invalidate_uri_cache(target_abs, is_dir_op=True)
                    _relock_if_protected_safe(target_abs)
                    return
                raise

        robust_replace(staging_abs, target_abs, max_retries=retries)
        swap_succeeded = True
        _maybe_invalidate_uri_cache(target_abs, is_dir_op=True)
    except BaseException:
        if moved_old and (os.path.exists(old_abs) or os.path.lexists(old_abs)):
            try:
                if os.path.exists(target_abs) or os.path.lexists(target_abs):
                    robust_rmtree(target_abs, ignore_errors=True, max_retries=retries)
                robust_replace(old_abs, target_abs, max_retries=retries)
            except Exception:
                pass
        raise
    finally:
        if swap_succeeded and (os.path.exists(old_abs) or os.path.lexists(old_abs)):
            robust_rmtree(old_abs, ignore_errors=True, max_retries=retries)
        if os.path.exists(staging_abs) or os.path.lexists(staging_abs):
            robust_rmtree(staging_abs, ignore_errors=True, max_retries=retries)
        if swap_succeeded:
            _cleanup_stale_swap_dirs(parent_dir)


class OSBackend(VFSBackend):
    """
    作業系統本機檔案系統後端。
    負責直接與底層 OS 檔案系統交互，提供高效、跨平台與原子寫入能力。
    """

    def __init__(self, root_dir: Optional[str] = None):
        """
        初始化 OSBackend。

        :param root_dir: 可選之授權安全根目錄邊界。若指定，則在此後端操作之所有路徑均嚴格防逃逸。
        """
        self.root_dir = os.path.normpath(os.path.abspath(root_dir)) if root_dir else None
        self._real_root_dir: Optional[str] = (
            os.path.normpath(os.path.realpath(self.root_dir)) if self.root_dir else None
        )

    def normalize_path(self, path: str) -> str:
        """
        規範化路徑，消除正反斜線混用、多餘分隔符與相對符號。

        :param path: 輸入路徑
        :return: 規範化後的絕對路徑
        """
        return os.path.normpath(os.path.abspath(path))

    def assert_safe_path(self, path: str, root: Optional[str] = None) -> str:
        """
        檢核目標路徑是否處於授權邊界內，防禦目錄穿越與符號連結逃逸攻擊。

        :param path: 目標路徑
        :param root: 指定根目錄 (若為 None 則使用實例之 self.root_dir)
        :return: 規範化之絕對路徑
        :raises PermissionError: 若路徑超出邊界則拋出異常
        """
        norm_target = self.normalize_path(path)
        if root is not None:
            boundary_root: Optional[str] = os.path.normpath(os.path.abspath(root))
            real_root: Optional[str] = os.path.normpath(os.path.realpath(boundary_root))
        else:
            boundary_root = self.root_dir
            real_root = self._real_root_dir
        if boundary_root and real_root:
            real_target = os.path.normpath(os.path.realpath(norm_target))
            is_real_same = real_target == real_root
            is_real_child = real_target.startswith(real_root + os.sep)
            if not (is_real_same or is_real_child):
                raise PermissionError(
                    f"Path traversal detected: target path '{norm_target}' "
                    f"escaped boundary root '{boundary_root}'."
                )
        return norm_target

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """讀取純文字檔案。"""
        norm_path = self.assert_safe_path(path)
        with open(norm_path, "r", encoding=encoding) as f:
            return f.read()

    def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """寫入純文字檔案 (預設 atomic 覆蓋)。

        換行符一律以 LF 原樣寫出（newline="\n"），不隨作業系統轉譯為 CRLF，
        確保受 Git 追蹤之檔案在 Windows 與 POSIX 間位元組一致；內容中顯式之 "\r\n" 亦原樣保留。
        """
        norm_path = self.assert_safe_path(path)
        if atomic:
            with self.atomic_write(norm_path, mode="w", encoding=encoding) as f:
                f.write(content)
        else:
            os.makedirs(os.path.dirname(norm_path), exist_ok=True)
            if os.path.exists(norm_path):
                _strip_lock_bits_safe(norm_path)
            with open(norm_path, "w", encoding=encoding, newline="\n") as f:
                f.write(content)
            _relock_if_protected_safe(norm_path, root_dir=self.root_dir)
        _maybe_invalidate_uri_cache(norm_path)

    def read_bytes(self, path: str) -> bytes:
        """讀取二進位資料。"""
        norm_path = self.assert_safe_path(path)
        with open(norm_path, "rb") as f:
            return f.read()

    def write_bytes(
        self,
        path: str,
        data: bytes,
        atomic: bool = True,
    ) -> None:
        """寫入二進位資料 (預設 atomic 覆蓋)。"""
        norm_path = self.assert_safe_path(path)
        if atomic:
            with self.atomic_write(norm_path, mode="wb", encoding=None) as f:
                f.write(data)
        else:
            os.makedirs(os.path.dirname(norm_path), exist_ok=True)
            if os.path.exists(norm_path):
                _strip_lock_bits_safe(norm_path)
            with open(norm_path, "wb") as f:
                f.write(data)
            _relock_if_protected_safe(norm_path, root_dir=self.root_dir)
        _maybe_invalidate_uri_cache(norm_path)

    def read_json(self, path: str, encoding: str = "utf-8") -> Any:
        """讀取並解析 JSON 檔案。"""
        norm_path = self.assert_safe_path(path)
        with open(norm_path, "r", encoding=encoding) as f:
            return json.load(f)

    def write_json(
        self,
        path: str,
        data: Any,
        indent: int = 2,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """序列化並寫入 JSON 檔案 (預設 atomic 覆蓋)。"""
        norm_path = self.assert_safe_path(path)
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        self.write_text(norm_path, content, encoding=encoding, atomic=atomic)

    def exists(self, path: str) -> bool:
        """檢查路徑是否存在。"""
        norm_path = self.assert_safe_path(path)
        try:
            return os.path.exists(norm_path)
        except Exception:
            return False

    def is_file(self, path: str) -> bool:
        """檢查是否為常規檔案。"""
        norm_path = self.assert_safe_path(path)
        try:
            return os.path.isfile(norm_path)
        except Exception:
            return False

    def is_dir(self, path: str) -> bool:
        """檢查是否為目錄。"""
        norm_path = self.assert_safe_path(path)
        try:
            return os.path.isdir(norm_path)
        except Exception:
            return False

    def listdir(self, path: str) -> List[str]:
        """列舉目錄內容並依字母排序。"""
        norm_path = self.assert_safe_path(path)
        return sorted(os.listdir(norm_path))

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """遞迴建立目錄樹。"""
        norm_path = self.assert_safe_path(path)
        os.makedirs(norm_path, exist_ok=exist_ok)

    def remove(self, path: str, missing_ok: bool = True) -> None:
        """刪除檔案或目錄 (若為目錄則遞迴清理)。"""
        try:
            norm_path = self.assert_safe_path(path)
        except PermissionError:
            raise
        except Exception:
            if missing_ok:
                return
            raise

        if not os.path.exists(norm_path):
            if not missing_ok:
                raise FileNotFoundError(f"Target path not found: '{norm_path}'")
            return

        is_dir = os.path.isdir(norm_path)
        if is_dir:
            robust_rmtree(norm_path, ignore_errors=False)
        else:
            try:
                _strip_lock_bits_safe(norm_path)
                os.remove(norm_path)
            except FileNotFoundError:
                if not missing_ok:
                    raise
        _maybe_invalidate_uri_cache(norm_path, is_dir_op=is_dir)

    def rmtree(self, path: str, ignore_errors: bool = False) -> None:
        """遞迴刪除目錄樹。"""
        norm_path = self.assert_safe_path(path)
        if os.path.exists(norm_path) or os.path.lexists(norm_path):
            robust_rmtree(norm_path, ignore_errors=ignore_errors)
        _maybe_invalidate_uri_cache(norm_path, is_dir_op=True)

    def _safe_copytree(self, src: str, dst: str, _root_dst: Optional[str] = None) -> None:
        """跨平台安全複製目錄樹，忽略暫態點目錄 (.old_* / .staging_*)，僅於大小寫不敏感系統跳過大小寫碰撞，並對 symlink 執行邊界校驗。"""
        if os.path.exists(dst) or os.path.lexists(dst):
            _strip_lock_bits_safe(dst)
        os.makedirs(dst, exist_ok=True)
        root_dst_norm = os.path.normpath(os.path.abspath(_root_dst or dst))
        is_case_insensitive = os.name == "nt" or sys.platform == "darwin" or (
            os.path.normcase("A") == os.path.normcase("a")
        )
        seen_lower: Set[str] = set()
        for item in sorted(os.listdir(src)):
            if item.startswith((".old_", ".staging_")):
                continue
            if is_case_insensitive:
                lower_key = item.lower()
                if lower_key in seen_lower:
                    continue
                seen_lower.add(lower_key)
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.islink(s):
                link_target = os.readlink(s)
                d_norm = os.path.normpath(os.path.abspath(d))
                if not os.path.isabs(link_target):
                    resolved_target = os.path.normpath(os.path.join(os.path.dirname(d_norm), link_target))
                    boundary = self._real_root_dir or root_dst_norm
                    if resolved_target != boundary and not resolved_target.startswith(boundary + os.sep):
                        raise PermissionError(
                            f"Symlink target '{link_target}' at '{d}' escaped boundary '{boundary}'."
                        )
                if os.path.lexists(d):
                    _strip_lock_bits_safe(d)
                    os.remove(d)
                os.symlink(link_target, d)
            elif os.path.isdir(s):
                self._safe_copytree(s, d, _root_dst=root_dst_norm)
            elif os.path.isfile(s):
                _strip_lock_bits_safe(d)
                shutil.copy2(s, d)
                _reconcile_copied_file_lock(s, d, root_dir=self.root_dir)

    def copy(self, src: str, dst: str) -> None:
        """複製檔案或目錄至目標路徑。"""
        src_norm = self.assert_safe_path(src)
        dst_norm = self.assert_safe_path(dst)
        src_real = os.path.normcase(os.path.realpath(src_norm))
        dst_real = os.path.normcase(os.path.realpath(dst_norm))
        if src_real == dst_real:
            return
        is_dir = os.path.isdir(src_norm) and not os.path.islink(src_norm)
        if os.path.islink(src_norm):
            os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
            if os.path.lexists(dst_norm):
                _strip_lock_bits_safe(dst_norm)
                os.remove(dst_norm)
            os.symlink(os.readlink(src_norm), dst_norm)
            if self.root_dir:
                self.assert_safe_path(dst_norm)
        elif is_dir:
            if dst_real.startswith(src_real + os.sep):
                raise ValueError(f"Cannot copy directory '{src_norm}' into its own subdirectory '{dst_norm}'.")
            if os.path.exists(dst_norm):
                robust_rmtree(dst_norm, ignore_errors=True)
            self._safe_copytree(src_norm, dst_norm)
        else:
            os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
            if os.path.exists(dst_norm):
                _strip_lock_bits_safe(dst_norm)
            shutil.copy2(src_norm, dst_norm)
            _reconcile_copied_file_lock(src_norm, dst_norm, root_dir=self.root_dir)
        _maybe_invalidate_uri_cache(dst_norm, is_dir_op=is_dir)

    def move(self, src: str, dst: str) -> None:
        """移動檔案或目錄至目標路徑。"""
        src_norm = self.assert_safe_path(src)
        dst_norm = self.assert_safe_path(dst)
        os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
        if os.path.exists(src_norm) and not os.path.islink(src_norm) and os.path.isfile(src_norm):
            _strip_lock_bits_safe(src_norm)
        if os.path.exists(dst_norm):
            _strip_lock_bits_safe(dst_norm)
        try:
            robust_replace(src_norm, dst_norm, root_dir=self.root_dir)
        except OSError:
            if os.path.isdir(src_norm) and not os.path.islink(src_norm):
                for r_dir, _d_names, f_names in os.walk(src_norm, followlinks=False):
                    for fn in f_names:
                        _strip_lock_bits_safe(os.path.join(r_dir, fn))
            shutil.move(src_norm, dst_norm)
        is_dir = os.path.isdir(dst_norm) and not os.path.islink(dst_norm)
        if is_dir:
            _reconcile_tree_locks(dst_norm, root_dir=self.root_dir)
        elif os.path.isfile(dst_norm) and not os.path.islink(dst_norm):
            _reconcile_copied_file_lock(src_norm, dst_norm, root_dir=self.root_dir)
        _maybe_invalidate_uri_cache(src_norm, is_dir_op=is_dir)
        _maybe_invalidate_uri_cache(dst_norm, is_dir_op=is_dir)

    @contextmanager
    def atomic_write(
        self,
        path: str,
        mode: str = "w",
        encoding: Optional[str] = "utf-8",
    ) -> Generator[IO, None, None]:
        """
        同目錄同分區原子寫入上下文管理器。
        寫入暫存檔、flush、sync，退出區塊時以 os.replace 原子覆蓋；
        異常時無條件移除暫存檔。
        """
        norm_target = self.assert_safe_path(path)
        parent_dir = os.path.dirname(norm_target)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        target_base = os.path.basename(norm_target)
        pid = os.getpid()
        tid = threading.get_ident()
        rand_token = uuid.uuid4().hex[:8]
        tmp_filename = f".{target_base}.tmp.{pid}_{tid}_{rand_token}"
        tmp_path = os.path.join(parent_dir, tmp_filename) if parent_dir else tmp_filename

        file_obj: Optional[IO] = None
        success = False
        try:
            if "b" in mode:
                file_obj = open(tmp_path, mode)
            else:
                # 文字模式固定 LF 換行，杜絕 Windows 平台自動轉譯為 CRLF
                file_obj = open(tmp_path, mode, encoding=encoding or "utf-8", newline="\n")

            yield file_obj

            file_obj.flush()
            try:
                os.fsync(file_obj.fileno())
            except (AttributeError, OSError):
                pass
            file_obj.close()
            file_obj = None

            # 原子替換 (針對 Windows 檔案鎖/索引競態提供漸進重試；若耗盡重試直接拋出異常以保護原檔並清理暫存檔)
            robust_replace(tmp_path, norm_target, max_retries=10, root_dir=self.root_dir)
            success = True
            _maybe_invalidate_uri_cache(norm_target)
        finally:
            if file_obj is not None and not file_obj.closed:
                try:
                    file_obj.close()
                except Exception:
                    pass
            if not success and os.path.exists(tmp_path):
                try:
                    _strip_lock_bits_safe(tmp_path)
                    os.remove(tmp_path)
                except Exception:
                    pass
