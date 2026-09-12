"""
YS-Codebase VirtualPath 物件導向虛擬路徑實作。
100% Python 標準庫，提供類似 pathlib.Path 的優雅鏈式操作與語意 URI 串接能力。
"""

import os
from typing import Optional, List, Any, Union, IO, Generator
from contextlib import contextmanager


class VirtualPath:
    """
    虛擬路徑物件導向介面 (Object-Oriented Virtual Path)。
    封裝語意 URI 或實體路徑，支援 `/` 串接運算子與全套 VFS 檔案操作。
    """

    def __init__(self, raw: Union[str, "VirtualPath"], vfs_instance: Optional[Any] = None):
        """
        初始化 VirtualPath 實例。

        :param raw: 原始語意 URI 或實體路徑字串
        :param vfs_instance: 綁定之 VFS 核心實例 (若為 None 則延遲綁定全域 vfs)
        """
        if isinstance(raw, VirtualPath):
            self._raw = raw._raw
            self._vfs = vfs_instance or raw._vfs
        else:
            self._raw = str(raw)
            self._vfs = vfs_instance

    @property
    def vfs(self) -> Any:
        """獲取綁定之 VFS 實例。"""
        if self._vfs is None:
            from core.vfs import vfs
            self._vfs = vfs
        return self._vfs

    @property
    def raw(self) -> str:
        """獲取未解析之原始路徑或語意 URI 字串。"""
        return self._raw

    @property
    def resolved(self) -> str:
        """獲取解算後之底層實體絕對路徑。"""
        return self.vfs.resolve_path(self._raw)

    @property
    def name(self) -> str:
        """獲取路徑最末端檔案或目錄名稱。"""
        raw_clean = self._raw.rstrip("/\\")
        if "://" in raw_clean:
            _, path_part = raw_clean.split("://", 1)
            return os.path.basename(path_part.replace("\\", "/"))
        return os.path.basename(raw_clean)

    @property
    def suffix(self) -> str:
        """獲取副檔名 (含點，例如 '.json')。"""
        return os.path.splitext(self.name)[1]

    @property
    def parent(self) -> "VirtualPath":
        """獲取父層 VirtualPath。"""
        raw_clean = self._raw.rstrip("/\\")
        if "://" in raw_clean:
            scheme, path_part = raw_clean.split("://", 1)
            parent_part = os.path.dirname(path_part.replace("\\", "/"))
            return VirtualPath(f"{scheme}://{parent_part}" if parent_part else f"{scheme}://", vfs_instance=self._vfs)
        parent_dir = os.path.dirname(raw_clean)
        return VirtualPath(parent_dir, vfs_instance=self._vfs)

    def __truediv__(self, other: Union[str, "VirtualPath"]) -> "VirtualPath":
        """
        使用 `/` 運算子串接子路徑。
        支援語意 URI 串接 (例 VirtualPath("project://docs") / "spec.md")。
        """
        sub = other._raw if isinstance(other, VirtualPath) else str(other)
        sub_clean = sub.lstrip("/\\")

        if "://" in self._raw:
            scheme, rest = self._raw.split("://", 1)
            rest_clean = rest.rstrip("/\\")
            if rest_clean:
                new_raw = f"{scheme}://{rest_clean}/{sub_clean}"
            else:
                new_raw = f"{scheme}://{sub_clean}"
            return VirtualPath(new_raw, vfs_instance=self._vfs)

        base_clean = self._raw.rstrip("/\\")
        return VirtualPath(os.path.join(base_clean, sub_clean), vfs_instance=self._vfs)

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"VirtualPath({self._raw!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, VirtualPath):
            return self._raw == other._raw
        if isinstance(other, str):
            return self._raw == other
        return False

    def __hash__(self) -> int:
        return hash(self._raw)

    # =========================================================================
    # 委派至 VFS 的檔案/目錄操作方法
    # =========================================================================

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.vfs.read_text(self, encoding=encoding)

    def write_text(self, content: str, encoding: str = "utf-8", atomic: bool = True) -> None:
        self.vfs.write_text(self, content, encoding=encoding, atomic=atomic)

    def read_bytes(self) -> bytes:
        return self.vfs.read_bytes(self)

    def write_bytes(self, data: bytes, atomic: bool = True) -> None:
        self.vfs.write_bytes(self, data, atomic=atomic)

    def read_json(self, encoding: str = "utf-8") -> Any:
        return self.vfs.read_json(self, encoding=encoding)

    def write_json(self, data: Any, indent: int = 2, encoding: str = "utf-8", atomic: bool = True) -> None:
        self.vfs.write_json(self, data, indent=indent, encoding=encoding, atomic=atomic)

    def exists(self) -> bool:
        return self.vfs.exists(self)

    def is_file(self) -> bool:
        return self.vfs.is_file(self)

    def is_dir(self) -> bool:
        return self.vfs.is_dir(self)

    def listdir(self) -> List[str]:
        return self.vfs.listdir(self)

    def mkdir(self, parents: bool = True, exist_ok: bool = True) -> None:
        self.vfs.makedirs(self, exist_ok=exist_ok)

    def unlink(self, missing_ok: bool = True) -> None:
        self.vfs.remove(self, missing_ok=missing_ok)

    def open(self, mode: str = "r", encoding: Optional[str] = None) -> IO:
        return self.vfs.open(self, mode=mode, encoding=encoding)

    @contextmanager
    def atomic_write(self, mode: str = "w", encoding: Optional[str] = "utf-8") -> Generator[IO, None, None]:
        with self.vfs.atomic_write(self, mode=mode, encoding=encoding) as f:
            yield f
