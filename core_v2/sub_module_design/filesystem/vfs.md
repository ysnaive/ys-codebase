# 子模組架構設計規格：`core.filesystem.vfs`（能力遮罩導向語意虛擬檔案系統與雙層唯讀守衛）

> **所屬功能域**：`Domain 2 — 檔案、空間與儲存域 (filesystem/)`
> **模組路徑**：`core_v2/source/core/core/filesystem/vfs/`
> **建議內部切分**：`capabilities.py`、`provider.py`、`mount.py`、`readonly.py`、`echo.py`、`scoped.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`
> **禁止反向依賴（Forbidden Imports）**：`filesystem.{space, storage}`、`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

> [!NOTE]
> **實作彈性邊界**：`VfsCapabilities`、`VfsStat`、`ScopedVfs` 公開操作語意、Scheme B 15 組標準協議與 `VfsEchoGuardPort` 結構相容性屬強制統一契約；內部檔案切分與 Provider 輔助實作細節可由實作端按需微調。

---

## 1. 模組定位、借鏡設計與 1.x $\to$ 2.0 減法清單

`core.filesystem.vfs` 為純機制層的**本地實體檔案代理與能力守門虛擬檔案系統**，結合 1.x 跨平台防坑教訓與兄弟倉 `uitk.net` 資產 VFS 的正交設計精華：
1. **能力位元遮罩驅動守門（`VfsCapabilities(Flag)`）**：每個協議掛載點宣告明確能力位元（`READABLE`、`WRITABLE`、`PERSISTENT`、`GIT_TRACKED`、`ENUMERABLE`、`PHYSICAL_PATH`），並支援按路徑動態評估 `get_capabilities(uri)`。上層能力約束（如 `storage.ModuleDatabase` 僅允許寫入非版控持久化本地空間 `storage.local://`）直接透過能力位元判定，零硬編碼協議名稱猜測。
2. **可抽換 `VfsProvider` 掛載架構**：生產環境預設全數掛載 `PhysicalDirectoryProvider`（1:1 沙盒目錄、全程走 `filesystem.fs` 原子寫入與無符號連結守衛）；內建純記憶體 `MemoryVfsProvider` 供上層單元測試零磁碟快速驗證，同時保留未來擴充唯讀物化來源的乾淨接縫。
3. **跨協議同實體路徑收斂**：當多組協議映射至同一實體檔（例如 `workflow.plans://a.md` 與 `project://plans/a.md`），`ReadonlyPolicy` 與 `VfsEchoGuard` 一律以正規化 `HostPath` 為鍵，確保唯讀防護與免回音抑制跨協議 100% 一致。

### 1.x $\to$ 2.0 明確減法（嚴禁帶回 2.0）
- **廢除**舊歷史別名（`*.root://`、`temp://`、`module.install://`），鎖定 Scheme B 15 組標準協議 + 模組宣告協議。
- **廢除** `uri.resolve()` 內的互動式 `!undefined` TTY 選單；未配置協議一律確定性拋出 `YscbError(ErrorCode.URI_UNDEFINED, ..., remediation="...")`，且嚴禁回退 `os.getcwd()`（`DN-01`）。
- **廢除**全域 `set_host_dir` / `set_yscb_root` / `uri_tls` 單例，全數改為建構子顯式 DI 注入 `VfsHub` / `ScopedVfs`。
- **不引入**圖形資產管線概念（無 `.meta` 伴隨檔、`AssetImporter`、LRU 資產池或無 scheme 隱式推導）。

---

## 2. Scheme B 15 組標準語意協議與預設能力矩陣

`UriMountTable` 由頂層組裝根依 `yscb_root`、`host_dir`、`project_root`（未設定時為 `None`）及模組貢獻之自訂協議（如 `workflow.plans://`）組裝。

| 協議 Token | 預設物理路徑 | `READABLE` | `WRITABLE` | `PERSISTENT` | `GIT_TRACKED` | `ENUMERABLE` | `PHYSICAL_PATH` | 一般業務模組寫入權 (`ScopedVfs`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `yscb://` | `{yscb_root}` | Y | N | Y | Y | Y | Y | 唯讀 |
| `yscb.host://` | `{host_dir}` | Y | N | Y | Y | Y | Y | 唯讀 |
| `project://` | `config.project_root` | Y | Y | Y | Y | Y | Y | 允許（受 `ReadonlyPolicy` 約束） |
| `module://` | `yscb://.modules/` | Y | N | Y | N | Y | Y | 唯讀（僅 `KernelVfs` 可寫） |
| `module.source://` | `yscb://source/` | Y | Y | Y | Y | Y | Y | 預設唯讀（`dev` 等顯式授權可寫） |
| `module.build://` | `yscb://.build/` | Y | Y | N | N | Y | Y | 預設唯讀（`dev` 等顯式授權可寫） |
| `module.release://` | `yscb://release/` | Y | Y | Y | Y | Y | Y | 預設唯讀（`dev` 等顯式授權可寫） |
| `module.mirror://` | `yscb://.mirror/` | Y | N | Y | N | Y | Y | 唯讀（僅 `KernelVfs` 可寫） |
| `config://` | `yscb://config/` | Y | Y | Y | Y | Y | Y | 唯讀（經 `metadata.config` / `KernelVfs` 寫入） |
| `config.local://` | `yscb://.config.local/` | Y | Y | Y | N | Y | Y | 僅自身 `@/` 可寫 |
| `cache://` | `yscb://.cache/` | Y | Y | **N** | N | Y | Y | 僅自身 `@/` 可寫 |
| `storage://` | `yscb://storage/` | Y | Y | Y | **Y** | Y | Y | 僅自身 `@/` 可寫 |
| `storage.local://` | `yscb://.storage.local/` | Y | Y | **Y** | **N** | Y | Y | 僅自身 `@/` 可寫（`storage` DB 唯一合法空間） |
| `snapshot://` | `yscb://.snapshots/` | Y | N | Y | N | Y | Y | 唯讀（僅 `KernelVfs` 可寫） |
| `yscb.venv://` | `yscb://.venv/` | Y | N | Y | N | Y | Y | 唯讀（僅 `KernelVfs` 可寫） |

> **模組自訂協議（如 `workflow.plans://`）**：由 `MountRule` 宣告（支援指向 `project://...` 等既有協議之子路徑，支援循環依賴偵測 `URI_CYCLE`），其預設能力繼承底層目標掛載點並可進一步收緊（只能收緊、不可越權放大）。

---

## 3. 核心能力遮罩、Provider 契約與雙層唯讀守衛

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, Flag
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from typing import Annotated, BinaryIO, Callable, ClassVar, Final, Generic, Literal, Optional, Protocol, TextIO, TypeAlias, TypeVar, overload, runtime_checkable

from core.filesystem.fs import BeforeReplaceHook, MAX_JSON_FILE_BYTES, atomic_write_bytes, has_symlink_raw_path, is_atomic_staging_filename, is_contained_nonsymlink_path, is_symlink_or_reparse, read_nofollow_regular_bytes, resolve_contained_subpath, walk_nonsymlink_dir_tree
from core.foundation import ErrorCode, HostPath, IS_WINDOWS, JsonObject, JsonValue, MAX_USER_JSON_DEPTH, ModuleId, MutableJsonObject, SemanticUri, YscbError, clone_strict_json_object, is_valid_relative_segment, require_pure_bool, require_pure_int, require_pure_str, require_typed_frozenset, require_typed_tuple, safe_exception_summary, safe_real_to_float, validate_wire_json_object

def build_standard_mount_rules(host_dir: HostPath, yscb_root: HostPath, *, project_root: Optional[HostPath]=None, extra_rules: Sequence[MountRule]=()) -> tuple[MountRule, ...]:
    ...

@dataclass(frozen=True, slots=True)
class AccessPolicy:
    extra_writable_schemes: Mapping[ModuleId, frozenset[str]] = field(default_factory=dict)
    readonly_tunnel_modules: frozenset[ModuleId] = frozenset()

class KernelVfs(ScopedVfs):

    def write_bytes_through_readonly(self, uri: SemanticUri | str, data: bytes) -> None:
        ...

    def write_text_through_readonly(self, uri: SemanticUri | str, text: str, *, encoding: str='utf-8') -> None:
        ...

class MemoryVfsProvider:

    def __init__(self, scheme: str, *, base_capabilities: VfsCapabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE, description: str='') -> None:
        ...

    @property
    def scheme(self) -> str:
        ...

    @property
    def base_capabilities(self) -> VfsCapabilities:
        ...

    @property
    def description(self) -> str:
        ...

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        ...

    def exists(self, uri: SemanticUri) -> bool:
        ...

    def stat(self, uri: SemanticUri) -> VfsStat:
        ...

    def read_bytes(self, uri: SemanticUri) -> bytes:
        ...

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        ...

    def write_bytes_atomic(self, uri: SemanticUri, data: bytes, *, before_replace: Optional[BeforeReplaceHook]=None) -> None:
        ...

    def delete(self, uri: SemanticUri, *, recursive: bool=False) -> bool:
        ...

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        ...

    def mkdir(self, uri: SemanticUri, *, parents: bool=True) -> None:
        ...

    def iter_entries(self, uri: SemanticUri, *, recursive: bool=False) -> Iterator[SemanticUri]:
        ...

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        ...

@dataclass(frozen=True, slots=True)
class MountHealthEntry:
    scheme: str
    healthy: bool
    detail: str

@dataclass(frozen=True, slots=True)
class MountRule:
    scheme: str
    target_path: Optional[HostPath] = None
    target_uri: Optional[SemanticUri] = None
    capabilities: VfsCapabilities = VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE
    provider_module: Optional[ModuleId] = None
    config_binding: Optional[str] = None
    description: str = ''

class PhysicalDirectoryProvider:

    def __init__(self, scheme: str, root_dir: HostPath, *, base_capabilities: VfsCapabilities, description: str='') -> None:
        ...

    @property
    def scheme(self) -> str:
        ...

    @property
    def base_capabilities(self) -> VfsCapabilities:
        ...

    @property
    def description(self) -> str:
        ...

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        ...

    def exists(self, uri: SemanticUri) -> bool:
        ...

    def stat(self, uri: SemanticUri) -> VfsStat:
        ...

    def read_bytes(self, uri: SemanticUri) -> bytes:
        ...

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        ...

    def write_bytes_atomic(self, uri: SemanticUri, data: bytes, *, before_replace: Optional[BeforeReplaceHook]=None) -> None:
        ...

    def delete(self, uri: SemanticUri, *, recursive: bool=False) -> bool:
        ...

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        ...

    def mkdir(self, uri: SemanticUri, *, parents: bool=True) -> None:
        ...

    def iter_entries(self, uri: SemanticUri, *, recursive: bool=False) -> Iterator[SemanticUri]:
        ...

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        ...

class ReadonlyPolicy:

    def __init__(self, matcher: Optional[Callable[[HostPath], bool]]=None) -> None:
        ...

    def update_matcher(self, matcher: Callable[[HostPath], bool]) -> None:
        ...

    def is_protected(self, path: HostPath) -> bool:
        ...

    def is_os_readonly(self, path: HostPath) -> bool:
        ...

    def lock_file(self, path: HostPath) -> bool:
        ...

    def unlock_file(self, path: HostPath) -> bool:
        ...

    def sync_files(self, protected_paths: Sequence[HostPath]) -> ReadonlySyncResult:
        ...

    @contextmanager
    def authorized_write_tunnel(self, path: HostPath) -> Iterator[None]:
        ...

@dataclass(frozen=True, slots=True)
class ReadonlySyncResult:
    locked_count: int
    already_locked_count: int
    unlocked_count: int
    failed_paths: tuple[tuple[HostPath, str], ...] = ()

class ScopedVfs:

    @property
    def module_id(self) -> ModuleId:
        ...

    def bind_uri(self, uri: SemanticUri | str) -> SemanticUri:
        ...

    def get_capabilities(self, uri: SemanticUri | str) -> VfsCapabilities:
        ...

    def can_read(self, uri: SemanticUri | str) -> bool:
        ...

    def can_write(self, uri: SemanticUri | str) -> bool:
        ...

    def exists(self, uri: SemanticUri | str) -> bool:
        ...

    def stat(self, uri: SemanticUri | str) -> VfsStat:
        ...

    def read_bytes(self, uri: SemanticUri | str) -> bytes:
        ...

    def read_text(self, uri: SemanticUri | str, *, encoding: str='utf-8') -> str:
        ...

    def read_json(self, uri: SemanticUri | str) -> JsonValue:
        ...

    def open_read(self, uri: SemanticUri | str) -> BinaryIO:
        ...

    def write_bytes(self, uri: SemanticUri | str, data: bytes) -> None:
        ...

    def write_text(self, uri: SemanticUri | str, text: str, *, encoding: str='utf-8', normalize_lf: bool=True) -> None:
        ...

    def write_json(self, uri: SemanticUri | str, payload: JsonObject, *, indent: int=2) -> None:
        ...

    def mkdir(self, uri: SemanticUri | str, *, parents: bool=True) -> None:
        ...

    def delete(self, uri: SemanticUri | str, *, recursive: bool=False) -> bool:
        ...

    def move(self, src: SemanticUri | str, dst: SemanticUri | str) -> None:
        ...

    def iter_entries(self, uri: SemanticUri | str, *, recursive: bool=False) -> Iterator[SemanticUri]:
        ...

    def try_get_physical_path(self, uri: SemanticUri | str) -> Optional[HostPath]:
        ...

class UriMountTable:

    def __init__(self, rules: Sequence[MountRule], *, providers: Optional[Mapping[str, VfsProvider]]=None) -> None:
        ...

    def list_rules(self) -> tuple[MountRule, ...]:
        ...

    def get_provider(self, scheme: str) -> VfsProvider:
        ...

    def resolve_physical(self, uri: SemanticUri) -> HostPath:
        ...

    def to_uri(self, abs_path: HostPath) -> Optional[SemanticUri]:
        ...

    def iter_covering_mounts(self, host_path: HostPath) -> tuple[tuple[str, SemanticUri], ...]:
        ...

    def check_health(self) -> tuple[MountHealthEntry, ...]:
        ...

class VfsCapabilities(Flag):
    NONE = 0
    READABLE = 1
    WRITABLE = 2
    PERSISTENT = 4
    GIT_TRACKED = 8
    ENUMERABLE = 16
    PHYSICAL_PATH = 32

class VfsEchoGuard:

    def __init__(self, *, ttl_sec: float=5.0, max_entries: int=2048) -> None:
        ...

    def record_write(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> None:
        ...

    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> bool:
        ...

class VfsHub:

    def __init__(self, mount_table: UriMountTable, *, readonly_policy: Optional[ReadonlyPolicy]=None, echo_guard: Optional[VfsEchoGuard]=None, access_policy: Optional[AccessPolicy]=None) -> None:
        ...

    @property
    def mount_table(self) -> UriMountTable:
        ...

    @property
    def readonly_policy(self) -> ReadonlyPolicy:
        ...

    @property
    def echo_guard(self) -> VfsEchoGuard:
        ...

    def for_module(self, module_id: ModuleId) -> ScopedVfs:
        ...

    def for_kernel(self) -> KernelVfs:
        ...

class VfsProvider(Protocol):

    @property
    def scheme(self) -> str:
        ...

    @property
    def base_capabilities(self) -> VfsCapabilities:
        ...

    @property
    def description(self) -> str:
        ...

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        ...

    def exists(self, uri: SemanticUri) -> bool:
        ...

    def stat(self, uri: SemanticUri) -> VfsStat:
        ...

    def read_bytes(self, uri: SemanticUri) -> bytes:
        ...

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        ...

    def write_bytes_atomic(self, uri: SemanticUri, data: bytes, *, before_replace: Optional[BeforeReplaceHook]=None) -> None:
        ...

    def delete(self, uri: SemanticUri, *, recursive: bool=False) -> bool:
        ...

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        ...

    def mkdir(self, uri: SemanticUri, *, parents: bool=True) -> None:
        ...

    def iter_entries(self, uri: SemanticUri, *, recursive: bool=False) -> Iterator[SemanticUri]:
        ...

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        ...

@dataclass(frozen=True, slots=True)
class VfsStat:
    exists: bool
    is_dir: bool
    is_readonly: bool
    size_bytes: int
    mtime_ns: int
    ino: int

__all__: tuple[str, ...] = (
    "AccessPolicy",
    "KernelVfs",
    "MemoryVfsProvider",
    "MountHealthEntry",
    "MountRule",
    "PhysicalDirectoryProvider",
    "ReadonlyPolicy",
    "ReadonlySyncResult",
    "ScopedVfs",
    "UriMountTable",
    "VfsCapabilities",
    "VfsEchoGuard",
    "VfsHub",
    "VfsProvider",
    "VfsStat",
    "build_standard_mount_rules",
)
```

---

## 4. 關鍵安全與跨平台不變量（承襲 `DN-01`, `DN-07`, `DN-12`）

1. **`project://` 零隱式回退與明確自癒指令**：當 `MountRule.target_path` 為 `None`（未設定）時，所有解析與讀寫一律拋出 `YscbError(ErrorCode.URI_UNDEFINED, ..., remediation=...)`（如 `yscb config set core project_root ./`），嚴禁猜測 `os.getcwd()` 或向上爬樹。
2. **成對 `realpath` + `+ os.sep` 防同前綴兄弟目錄逃逸**：`PhysicalDirectoryProvider` 除 `SemanticUri` 靜態區段檢核外，底層仍強制對 `root` 與目標路徑執行 `fs.resolve_contained_subpath` 與無符號連結／Windows 重解析點攔截，杜絕 `cache://../.cache_hack` 繞過。
3. **原子寫入、LF 預設換行與 Windows 句柄重試**：
   - 所有檔案寫入統一經 `fs.atomic_write_bytes`（同目錄 `.tmp_*` + `fsync` + `os.replace`，嚴禁使用系統 `/tmp` 防 `EXDEV`），並透傳 `before_replace` 回呼向 `VfsEchoGuard` 登記 `(canonical_host_path, mtime_ns, size, ino)`。
   - `write_text` 預設將純文字以 UTF-8 LF（`\n`）寫出，杜絕跨 Windows / Linux 版控檔換行符飄移。
   - 刪除與搬移內建跨平台重試（剝離 `.git` 唯讀屬性防 Windows `WinError 5`、對短暫句柄鎖 `WinError 32` 有限退避重試）。
4. **雙層唯讀防護與跨協議一致**：
   - **層 1（VFS 守衛）**：一般 `ScopedVfs` 寫入受 `ReadonlyPolicy` 保護之 `HostPath` 一律拋 `YscbError(ErrorCode.READONLY_VIOLATION)`。
   - **層 2（OS 唯讀位元 + 授權穿隧）**：`ReadonlyPolicy` 以 POSIX `0o444` / Windows `FILE_ATTRIBUTE_READONLY` 保護實體檔案，防外部工具或 AI Agent 繞過 VFS 誤改編譯產物；具授權（`AccessPolicy.readonly_tunnel_modules` 或 `KernelVfs`）之寫入於 `authorized_write_tunnel` 內自動執行「解鎖 $\to$ 原子替換 $\to$ `finally` 強制重鎖」。
5. **全覆蓋掛載最嚴格寫入守門與跨模組讀寫隔離**：
   - `UriMountTable.iter_covering_mounts(host_path)` 列舉所有實體根覆蓋目標路徑之掛載（含基礎協議與別名）；`ScopedVfs` 執行任何寫入前檢驗所有覆蓋掛載並採最嚴格權限（封堵同址工作區 `project://yscb.py` 等宿主控制檔覆寫與唯讀別名穿透，拋 `ACCESS_DENIED` 或 `READONLY_VIOLATION`）。
   - `ScopedVfs(mod)` 對 `config.local://`、`cache://`、`storage://`、`storage.local://` 僅允許寫入首段等於 `mod.value` 之子路徑（含 `@/` 展開），且對 `config.local://` 與 `storage.local://`（含別名終點與跨協議覆蓋路徑）同步強制跨模組**讀取隔離**（涵蓋 `read_bytes`/`read_text`/`read_json`/`open_read`/`exists`/`stat`/`iter_entries` 與 `try_get_physical_path`，特例保留 `try_get_physical_path(SemanticUri("storage.local", ""))` 空相對路徑供 `storage` 模組驗界）；違規一律拋 `YscbError(ErrorCode.ACCESS_DENIED)`。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **能力遮罩與 15 協議契約**：驗證 15 組標準協議之 `VfsCapabilities` 矩陣（特別是 `storage.local://` vs `cache://` vs `storage://` 區分），以及 `MountRule` 循環引用拋 `URI_CYCLE`、`!undefined` 拋 `URI_UNDEFINED` 且零 `os.getcwd()` 依賴。
2. **路徑防穿越與雙層唯讀測試**：同前綴兄弟目錄逃逸攔截、符號連結拒絕、未授權寫入 `/readonly` 拋 `READONLY_VIOLATION`、授權穿隧寫入後 OS 唯讀位元保持鎖定、Windows 唯讀檔 `robust_rmtree` 清理。
3. **跨協議同實體路徑一致與免回音抑制**：透過 `workflow.plans://a.md` 寫入後，以 `project://plans/a.md` 對應實體 `HostPath` 查詢 `VfsEchoGuard.is_suppressed(...)` 命中 `True`，且 `ReadonlyPolicy` 雙向皆生效。
4. **`ScopedVfs` 隔離與 `MemoryVfsProvider` 等價測試**：模組 A 寫入 `storage.local://b/x` 拋 `ACCESS_DENIED`；寫入 `storage.local://@/x` 成功映射至 `storage.local://a/x`；`MemoryVfsProvider` 完整通過同套基礎讀寫列舉契約測試。
