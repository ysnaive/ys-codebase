# API 與介面規格書 (API & Interface Specification)

> 功能名稱：core_vfs_unified_virtual_file_system  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `VFSBackend` | `core/core/vfs/base.py` | Public | 虛擬檔案系統後端抽象基類，定義標準原語介面 |
| `OSBackend` | `core/core/vfs/os_backend.py` | Public | 實體作業系統檔案後端，實作跨平台正規化、原子寫入與沙盒防逃逸 |
| `VFS` | `core/core/vfs/vfs.py` | Public | VFS 核心中樞，整合 `core.uri.resolve` 解析語意 URI 並派遣後端 |
| `VirtualPath` | `core/core/vfs/path.py` | Public | 物件導向虛擬路徑物件，支援 `/` 串接語法與鏈式檔案操作 |
| `vfs` (Singleton) | `core/core/vfs/__init__.py` | Public | 全域單例實例，並以模組層級函式導出便捷 API |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, IO, Generator

# =========================================================================
# 1. VFSBackend (Abstract Interface)
# =========================================================================
class VFSBackend(ABC):
    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...

    @abstractmethod
    def write_text(self, path: str, content: str, encoding: str = "utf-8", atomic: bool = True) -> None: ...

    @abstractmethod
    def read_bytes(self, path: str) -> bytes: ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes, atomic: bool = True) -> None: ...

    @abstractmethod
    def read_json(self, path: str, encoding: str = "utf-8") -> Any: ...

    @abstractmethod
    def write_json(self, path: str, data: Any, indent: int = 2, encoding: str = "utf-8", atomic: bool = True) -> None: ...

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def is_file(self, path: str) -> bool: ...

    @abstractmethod
    def is_dir(self, path: str) -> bool: ...

    @abstractmethod
    def listdir(self, path: str) -> List[str]: ...

    @abstractmethod
    def makedirs(self, path: str, exist_ok: bool = True) -> None: ...

    @abstractmethod
    def remove(self, path: str, missing_ok: bool = True) -> None: ...

    @abstractmethod
    def rmtree(self, path: str, ignore_errors: bool = False) -> None: ...

    @abstractmethod
    def copy(self, src: str, dst: str) -> None: ...

    @abstractmethod
    def move(self, src: str, dst: str) -> None: ...

    @abstractmethod
    @contextmanager
    def atomic_write(self, path: str, mode: str = "w", encoding: Optional[str] = "utf-8") -> Generator[IO, None, None]: ...

    @abstractmethod
    def assert_safe_path(self, path: str, root: Optional[str] = None) -> str: ...


# =========================================================================
# 2. OSBackend (Concrete Implementation)
# =========================================================================
class OSBackend(VFSBackend):
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir  # None 表示不限制，或指定授權專案邊界

    def normalize_path(self, path: str) -> str:
        """跨平台路徑規範化，消除混用反斜線與多餘點記號。"""
        ...


# =========================================================================
# 3. VFS (Core Dispatcher & URI Integration)
# =========================================================================
class VFS:
    def __init__(self, default_backend: Optional[VFSBackend] = None):
        self._default_backend = default_backend or OSBackend()
        self._backends: Dict[str, VFSBackend] = {}

    def resolve_path(self, path_or_uri: Union[str, "VirtualPath"]) -> str:
        """
        單向相依於 core.uri.resolve：若傳入語意 URI 則調用 core.uri 解析為實體路徑；
        若為實體路徑則執行規範化。
        """
        ...

    def read_text(self, path_or_uri: Union[str, "VirtualPath"], encoding: str = "utf-8") -> str: ...
    def write_text(self, path_or_uri: Union[str, "VirtualPath"], content: str, encoding: str = "utf-8", atomic: bool = True) -> None: ...
    def read_bytes(self, path_or_uri: Union[str, "VirtualPath"]) -> bytes: ...
    def write_bytes(self, path_or_uri: Union[str, "VirtualPath"], data: bytes, atomic: bool = True) -> None: ...
    def read_json(self, path_or_uri: Union[str, "VirtualPath"], encoding: str = "utf-8") -> Any: ...
    def write_json(self, path_or_uri: Union[str, "VirtualPath"], data: Any, indent: int = 2, encoding: str = "utf-8", atomic: bool = True) -> None: ...
    def exists(self, path_or_uri: Union[str, "VirtualPath"]) -> bool: ...
    def is_file(self, path_or_uri: Union[str, "VirtualPath"]) -> bool: ...
    def is_dir(self, path_or_uri: Union[str, "VirtualPath"]) -> bool: ...
    def listdir(self, path_or_uri: Union[str, "VirtualPath"]) -> List[str]: ...
    def makedirs(self, path_or_uri: Union[str, "VirtualPath"], exist_ok: bool = True) -> None: ...
    def remove(self, path_or_uri: Union[str, "VirtualPath"], missing_ok: bool = True) -> None: ...
    def rmtree(self, path_or_uri: Union[str, "VirtualPath"], ignore_errors: bool = False) -> None: ...
    def copy(self, src: Union[str, "VirtualPath"], dst: Union[str, "VirtualPath"]) -> None: ...
    def move(self, src: Union[str, "VirtualPath"], dst: Union[str, "VirtualPath"]) -> None: ...
    
    @contextmanager
    def atomic_write(self, path_or_uri: Union[str, "VirtualPath"], mode: str = "w", encoding: Optional[str] = "utf-8") -> Generator[IO, None, None]: ...


# =========================================================================
# 4. VirtualPath (Object-Oriented Abstraction)
# =========================================================================
class VirtualPath:
    def __init__(self, raw: str, vfs_instance: Optional[VFS] = None):
        self._raw = str(raw)
        self._vfs = vfs_instance or vfs

    def __truediv__(self, other: Union[str, "VirtualPath"]) -> "VirtualPath": ...
    def read_text(self, encoding: str = "utf-8") -> str: ...
    def write_text(self, content: str, encoding: str = "utf-8", atomic: bool = True) -> None: ...
    def read_bytes(self) -> bytes: ...
    def write_bytes(self, data: bytes, atomic: bool = True) -> None: ...
    def read_json(self, encoding: str = "utf-8") -> Any: ...
    def write_json(self, data: Any, indent: int = 2, encoding: str = "utf-8", atomic: bool = True) -> None: ...
    def exists(self) -> bool: ...
    def is_file(self) -> bool: ...
    def is_dir(self) -> bool: ...
    def mkdir(self, parents: bool = True, exist_ok: bool = True) -> None: ...
    def unlink(self, missing_ok: bool = True) -> None: ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. [Base & Abstraction]
   core/core/vfs/base.py (VFSBackend 抽象基類，零外部依賴)

2. [Concrete OS Backend]
   core/core/vfs/os_backend.py (OSBackend 實作原子寫入、邊界防護與標準 IO)

3. [Core Engine & Dispatcher]
   core/core/vfs/vfs.py (VFS 實作，單向引用 core.uri.resolve)

4. [OO Facade & Package Export]
   core/core/vfs/path.py (VirtualPath)
   core/core/vfs/__init__.py (導出 vfs, VirtualPath 與快捷函式)

5. [Core Interop & Backward Compatibility]
   core/core/__init__.py (頂層導出 vfs)
   core/core/uri.py (舊 IO helpers 轉發至 core.vfs)

6. [AST Scanner & Ecosystem Migration]
   scripts/scan_native_io.py (全模組掃描腳本)
   core 模組內部原生 open 遷移
```
