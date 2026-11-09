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
        from core import uri, contributes
        contributes._JSON_FILE_CACHE.pop(norm_path, None)
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


def robust_rmtree(path: str, ignore_errors: bool = False, max_retries: int = 5) -> None:
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
            os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
            func(failed_path)
            return
        except Exception:
            if not ignore_errors:
                raise exc

    retries = max(1, max_retries)
    for attempt in range(retries):
        try:
            if os.path.islink(norm_path) or os.path.isfile(norm_path):
                try:
                    os.chmod(norm_path, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
                os.unlink(norm_path)
            elif os.path.exists(norm_path):
                shutil.rmtree(norm_path, onerror=_on_rm_error)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt < retries - 1:
                time.sleep(0.05 * (attempt + 1))
                continue
            if not ignore_errors:
                raise


def robust_replace(src: str, dst: str, max_retries: int = 10) -> None:
    """
    Atomically replaces ``dst`` with ``src`` across platforms, retrying transient
    Windows file locks (`PermissionError` / `WinError 5` / `WinError 32`) and
    falling back to a same-directory staged copy + atomic replace when ``src``
    and ``dst`` reside on different filesystems (`errno.EXDEV`).
    """
    src_norm = os.path.normpath(os.path.abspath(src))
    dst_norm = os.path.normpath(os.path.abspath(dst))
    parent_dir = os.path.dirname(dst_norm)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    retries = max(1, max_retries)
    for attempt in range(retries):
        try:
            os.replace(src_norm, dst_norm)
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
                    os.replace(stage_path, dst_norm)
                    if os.path.isdir(src_norm) and not os.path.islink(src_norm):
                        robust_rmtree(src_norm, ignore_errors=True)
                    elif os.path.exists(src_norm) or os.path.lexists(src_norm):
                        os.remove(src_norm)
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
                try:
                    if os.path.exists(dst_norm):
                        os.chmod(dst_norm, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
                time.sleep(0.05 * (attempt + 1))
                continue
            raise


def atomic_swap_directory(
    staging_dir: str,
    target_dir: str,
    retries: int = 3,
    retry_delay: float = 0.05,
) -> None:
    """
    Atomically swaps `staging_dir` into `target_dir` within the same parent filesystem:
    1. Moves existing `target_dir` to a `.old_<name>_<pid>_<ts>` backup directory.
    2. Moves `staging_dir` into `target_dir`.
    3. Rolls back `.old` into `target_dir` if step 2 fails (even if `target_dir` was partially created).
    4. Cleans up `.old` and `staging_dir` in `finally`.
    """
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
            robust_replace(target_abs, old_abs, max_retries=retries)
            moved_old = True

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
            with open(norm_path, "w", encoding=encoding, newline="\n") as f:
                f.write(content)
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
            with open(norm_path, "wb") as f:
                f.write(data)
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
                try:
                    os.chmod(norm_path, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
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

    def _safe_copytree(self, src: str, dst: str) -> None:
        """跨平台安全複製目錄樹，忽略暫態點目錄 (.old_* / .staging_*)，僅於大小寫不敏感系統跳過大小寫碰撞，並對 symlink 執行邊界校驗。"""
        os.makedirs(dst, exist_ok=True)
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
                dst_root_norm = os.path.normpath(os.path.abspath(dst))
                d_norm = os.path.normpath(os.path.abspath(d))
                if d_norm != dst_root_norm and not d_norm.startswith(dst_root_norm + os.sep):
                    raise PermissionError(f"Symlink destination '{d}' escaped target tree '{dst}'.")
                if os.path.lexists(d):
                    os.remove(d)
                os.symlink(link_target, d)
            elif os.path.isdir(s):
                self._safe_copytree(s, d)
            elif os.path.isfile(s):
                shutil.copy2(s, d)

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
            shutil.copy2(src_norm, dst_norm)
        _maybe_invalidate_uri_cache(dst_norm, is_dir_op=is_dir)

    def move(self, src: str, dst: str) -> None:
        """移動檔案或目錄至目標路徑。"""
        src_norm = self.assert_safe_path(src)
        dst_norm = self.assert_safe_path(dst)
        os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
        try:
            robust_replace(src_norm, dst_norm)
        except OSError:
            shutil.move(src_norm, dst_norm)
        is_dir = os.path.isdir(dst_norm)
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
            robust_replace(tmp_path, norm_target, max_retries=10)
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
                    os.remove(tmp_path)
                except Exception:
                    pass
