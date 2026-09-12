"""
YS-Codebase VFS 作業系統本機後端實作 (OSBackend)。
100% Python 標準庫，提供跨平台路徑正規化、同分區原子寫入防護與沙盒防逃逸邊界檢驗。
"""

import os
import sys
import json
import shutil
import threading
import uuid
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, IO, Generator

from core.vfs.base import VFSBackend


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

    def normalize_path(self, path: str) -> str:
        """
        規範化路徑，消除正反斜線混用、多餘分隔符與相對符號。

        :param path: 輸入路徑
        :return: 規範化後的絕對路徑
        """
        return os.path.normpath(os.path.abspath(path))

    def assert_safe_path(self, path: str, root: Optional[str] = None) -> str:
        """
        檢核目標路徑是否處於授權邊界內，防禦目錄穿越與逃逸攻擊。

        :param path: 目標路徑
        :param root: 指定根目錄 (若為 None 則使用實例之 self.root_dir)
        :return: 規範化之絕對路徑
        :raises PermissionError: 若路徑超出邊界則拋出異常
        """
        norm_target = self.normalize_path(path)
        boundary_root = os.path.normpath(os.path.abspath(root)) if root else self.root_dir
        if boundary_root:
            is_same = norm_target == boundary_root
            is_child = norm_target.startswith(boundary_root + os.sep)
            if not (is_same or is_child):
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
        """寫入純文字檔案 (預設 atomic 覆蓋)。"""
        norm_path = self.assert_safe_path(path)
        if atomic:
            with self.atomic_write(norm_path, mode="w", encoding=encoding) as f:
                f.write(content)
        else:
            os.makedirs(os.path.dirname(norm_path), exist_ok=True)
            with open(norm_path, "w", encoding=encoding) as f:
                f.write(content)

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
        try:
            norm_path = self.normalize_path(path)
            return os.path.exists(norm_path)
        except Exception:
            return False

    def is_file(self, path: str) -> bool:
        """檢查是否為常規檔案。"""
        try:
            norm_path = self.normalize_path(path)
            return os.path.isfile(norm_path)
        except Exception:
            return False

    def is_dir(self, path: str) -> bool:
        """檢查是否為目錄。"""
        try:
            norm_path = self.normalize_path(path)
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

        if os.path.isdir(norm_path):
            shutil.rmtree(norm_path, ignore_errors=missing_ok)
        else:
            try:
                os.remove(norm_path)
            except FileNotFoundError:
                if not missing_ok:
                    raise

    def rmtree(self, path: str, ignore_errors: bool = False) -> None:
        """遞迴刪除目錄樹。"""
        norm_path = self.assert_safe_path(path)
        if os.path.exists(norm_path):
            shutil.rmtree(norm_path, ignore_errors=ignore_errors)

    def _safe_copytree(self, src: str, dst: str) -> None:
        """跨平台大小寫不敏感安全複製目錄樹。"""
        os.makedirs(dst, exist_ok=True)
        seen_lower = set()
        for item in sorted(os.listdir(src)):
            if item.lower() in seen_lower:
                continue
            seen_lower.add(item.lower())
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                self._safe_copytree(s, d)
            else:
                shutil.copy2(s, d)

    def copy(self, src: str, dst: str) -> None:
        """複製檔案或目錄至目標路徑。"""
        src_norm = self.assert_safe_path(src)
        dst_norm = self.assert_safe_path(dst)
        if os.path.isdir(src_norm):
            if os.path.exists(dst_norm):
                shutil.rmtree(dst_norm, ignore_errors=True)
            self._safe_copytree(src_norm, dst_norm)
        else:
            os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
            shutil.copy2(src_norm, dst_norm)

    def move(self, src: str, dst: str) -> None:
        """移動檔案或目錄至目標路徑。"""
        src_norm = self.assert_safe_path(src)
        dst_norm = self.assert_safe_path(dst)
        os.makedirs(os.path.dirname(dst_norm), exist_ok=True)
        shutil.move(src_norm, dst_norm)

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
                file_obj = open(tmp_path, mode, encoding=encoding or "utf-8")

            yield file_obj

            file_obj.flush()
            try:
                os.fsync(file_obj.fileno())
            except (AttributeError, OSError):
                pass
            file_obj.close()
            file_obj = None

            # 原子替換 (針對 Windows 檔案鎖/索引競態提供漸進重試與回退防護)
            if sys.platform == "win32":
                import time
                max_retries = 10
                for attempt in range(max_retries):
                    try:
                        os.replace(tmp_path, norm_target)
                        success = True
                        break
                    except (PermissionError, OSError):
                        if attempt < max_retries - 1:
                            time.sleep(0.05 * (attempt + 1))
                        else:
                            try:
                                if os.path.exists(norm_target):
                                    os.remove(norm_target)
                                os.replace(tmp_path, norm_target)
                                success = True
                            except Exception:
                                shutil.copy2(tmp_path, norm_target)
                                try:
                                    os.remove(tmp_path)
                                except Exception:
                                    pass
                                success = True
            else:
                os.replace(tmp_path, norm_target)
                success = True
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
