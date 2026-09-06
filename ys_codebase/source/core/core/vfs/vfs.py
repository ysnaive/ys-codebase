"""
YS-Codebase VFS 核心中樞與派遣引擎 (VFS Hub)。
100% Python 標準庫，單向整合 core.uri.resolve 解算語意協議，並分派至對應 VFSBackend。
"""

import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, IO, Generator

from core.vfs.base import VFSBackend
from core.vfs.os_backend import OSBackend


class VFS:
    """
    虛擬檔案系統核心門面 (Unified Virtual File System Facade)。
    支援語意 URI (例 project://..., cache://...) 與實體檔案路徑，
    統一提供原子寫入、沙盒邊界安全防護與插槽化後端分派。
    """

    def __init__(self, default_backend: Optional[VFSBackend] = None):
        """
        初始化 VFS 核心實例。

        :param default_backend: 預設底層後端 (預設為 OSBackend)
        """
        self._default_backend: VFSBackend = default_backend or OSBackend()
        self._scheme_backends: Dict[str, VFSBackend] = {}

    def register_backend(self, scheme: str, backend: VFSBackend) -> None:
        """
        為指定 scheme 註冊專屬後端 (供未來 MemoryBackend 等擴充插槽使用)。

        :param scheme: 協議前綴 (例如 'mem', 'virtual')
        :param backend: VFSBackend 具體實例
        """
        self._scheme_backends[scheme] = backend

    def get_backend(self, path_or_uri: Union[str, Any]) -> VFSBackend:
        """
        依輸入目標獲取對應之 VFSBackend。

        :param path_or_uri: 輸入路徑或語意 URI
        :return: 對應之後端實例
        """
        raw = self._extract_raw_path(path_or_uri)
        if "://" in raw:
            scheme = raw.split("://", 1)[0]
            if scheme in self._scheme_backends:
                return self._scheme_backends[scheme]
        return self._default_backend

    def resolve_path(self, path_or_uri: Union[str, Any]) -> str:
        """
        將語意 URI 或實體路徑解算為底層實體規範路徑。
        單向相依於 core.uri.resolve；純字串協議由 core.uri 掌理。

        :param path_or_uri: 語意 URI 或路徑
        :return: 實體絕對規範路徑
        """
        raw = self._extract_raw_path(path_or_uri)
        if "://" in raw:
            scheme = raw.split("://", 1)[0]
            # 若為已獨立註冊之自訂 scheme 且非純 OS 映射，原樣返回供該 backend 處理
            if scheme in self._scheme_backends and scheme != "file":
                return raw

            # 單向依賴 core.uri.resolve (延遲引用徹底消除循環導入)
            from core import uri
            return uri.resolve(raw, interactive=False)

        return os.path.normpath(os.path.abspath(raw))

    def _extract_raw_path(self, path_or_uri: Any) -> str:
        """從 VirtualPath 或字串中提取原始路徑字串。"""
        if hasattr(path_or_uri, "_raw"):
            return str(path_or_uri._raw)
        return str(path_or_uri)

    # =========================================================================
    # 高階統一檔案與目錄操作 API
    # =========================================================================

    def read_text(self, path_or_uri: Union[str, Any], encoding: str = "utf-8") -> str:
        """讀取目標路徑之純文字內容。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        return backend.read_text(resolved, encoding=encoding)

    def write_text(
        self,
        path_or_uri: Union[str, Any],
        content: str,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """寫入純文字內容至目標路徑 (預設 atomic 覆蓋)。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.write_text(resolved, content, encoding=encoding, atomic=atomic)

    def read_bytes(self, path_or_uri: Union[str, Any]) -> bytes:
        """讀取目標路徑之二進位位元組串。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        return backend.read_bytes(resolved)

    def write_bytes(
        self,
        path_or_uri: Union[str, Any],
        data: bytes,
        atomic: bool = True,
    ) -> None:
        """寫入二進位位元組串至目標路徑 (預設 atomic 覆蓋)。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.write_bytes(resolved, data, atomic=atomic)

    def read_json(self, path_or_uri: Union[str, Any], encoding: str = "utf-8") -> Any:
        """讀取並解析 JSON 檔案。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        return backend.read_json(resolved, encoding=encoding)

    def write_json(
        self,
        path_or_uri: Union[str, Any],
        data: Any,
        indent: int = 2,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """序列化並寫入 JSON 檔案 (預設 atomic 覆蓋)。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.write_json(resolved, data, indent=indent, encoding=encoding, atomic=atomic)

    def exists(self, path_or_uri: Union[str, Any]) -> bool:
        """檢查目標是否存在。"""
        try:
            resolved = self.resolve_path(path_or_uri)
            backend = self.get_backend(path_or_uri)
            return backend.exists(resolved)
        except Exception:
            return False

    def is_file(self, path_or_uri: Union[str, Any]) -> bool:
        """檢查目標是否為常規檔案。"""
        try:
            resolved = self.resolve_path(path_or_uri)
            backend = self.get_backend(path_or_uri)
            return backend.is_file(resolved)
        except Exception:
            return False

    def is_dir(self, path_or_uri: Union[str, Any]) -> bool:
        """檢查目標是否為目錄。"""
        try:
            resolved = self.resolve_path(path_or_uri)
            backend = self.get_backend(path_or_uri)
            return backend.is_dir(resolved)
        except Exception:
            return False

    def listdir(self, path_or_uri: Union[str, Any]) -> List[str]:
        """列舉目標目錄內容清單。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        return backend.listdir(resolved)

    def makedirs(self, path_or_uri: Union[str, Any], exist_ok: bool = True) -> None:
        """遞迴建立目標目錄樹。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.makedirs(resolved, exist_ok=exist_ok)

    def remove(self, path_or_uri: Union[str, Any], missing_ok: bool = True) -> None:
        """刪除指定檔案或目錄。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.remove(resolved, missing_ok=missing_ok)

    def rmtree(self, path_or_uri: Union[str, Any], ignore_errors: bool = False) -> None:
        """遞迴刪除目標目錄樹。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        backend.rmtree(resolved, ignore_errors=ignore_errors)

    def copy(self, src: Union[str, Any], dst: Union[str, Any]) -> None:
        """複製檔案或目錄。"""
        src_resolved = self.resolve_path(src)
        dst_resolved = self.resolve_path(dst)
        backend = self.get_backend(src)
        backend.copy(src_resolved, dst_resolved)

    def move(self, src: Union[str, Any], dst: Union[str, Any]) -> None:
        """移動檔案或目錄。"""
        src_resolved = self.resolve_path(src)
        dst_resolved = self.resolve_path(dst)
        backend = self.get_backend(src)
        backend.move(src_resolved, dst_resolved)

    @contextmanager
    def atomic_write(
        self,
        path_or_uri: Union[str, Any],
        mode: str = "w",
        encoding: Optional[str] = "utf-8",
    ) -> Generator[IO, None, None]:
        """同目錄同分區原子寫入上下文管理器。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        with backend.atomic_write(resolved, mode=mode, encoding=encoding) as f:
            yield f

    def open(
        self,
        path_or_uri: Union[str, Any],
        mode: str = "r",
        encoding: Optional[str] = None,
    ) -> IO:
        """
        以原生檔案物件模式打開檔案。
        若開啟寫入模式，自動確保父目錄存在。
        """
        resolved = self.resolve_path(path_or_uri)
        if any(m in mode for m in ("w", "a", "x")):
            parent = os.path.dirname(resolved)
            if parent:
                os.makedirs(parent, exist_ok=True)
        if "b" in mode:
            return open(resolved, mode)
        return open(resolved, mode, encoding=encoding or "utf-8")

    def assert_safe_path(self, path_or_uri: Union[str, Any], root: Optional[str] = None) -> str:
        """檢查目標是否在授權安全邊界內。"""
        resolved = self.resolve_path(path_or_uri)
        backend = self.get_backend(path_or_uri)
        return backend.assert_safe_path(resolved, root=root)

    def path(self, raw_path_or_uri: Union[str, Any]) -> "VirtualPath":
        """建構 VirtualPath 物件導向操作實例。"""
        from core.vfs.path import VirtualPath
        return VirtualPath(raw_path_or_uri, vfs_instance=self)
