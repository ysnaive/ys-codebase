# 子模組架構設計規格：`core.filesystem.vfs`（能力遮罩導向語意虛擬檔案系統與雙層唯讀守衛）

> **所屬功能域**：`Domain 2 — 檔案、空間與儲存域 (filesystem/)`
> **模組路徑**：`core_v2/source/core/core/filesystem/vfs/`
> **建議內部切分**：`capabilities.py`、`provider.py`、`mount.py`、`readonly.py`、`echo.py`、`scoped.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`
> **禁止反向依賴（Forbidden Imports）**：`filesystem.{space, storage}`、`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

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

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Flag, auto
from typing import BinaryIO, Callable, Iterator, Mapping, Optional, Protocol, Sequence

from core.filesystem.fs import BeforeReplaceHook
from core.foundation.primitives import HostPath, JsonObject, JsonValue, ModuleId, SemanticUri


class VfsCapabilities(Flag):
    NONE = 0
    READABLE = auto()
    WRITABLE = auto()
    PERSISTENT = auto()
    GIT_TRACKED = auto()
    ENUMERABLE = auto()
    PHYSICAL_PATH = auto()


@dataclass(frozen=True, slots=True)
class VfsStat:
    exists: bool
    is_dir: bool
    is_readonly: bool
    size_bytes: int
    mtime_ns: int
    ino: int


@dataclass(frozen=True, slots=True)
class MountRule:
    """純值物件掛載規則（由頂層組裝根建構，vfs 零匯入 metadata）。"""
    scheme: str
    target_path: Optional[HostPath] = None        # None 表示 !undefined
    target_uri: Optional[SemanticUri] = None      # 指向另一協議之子目錄（需防循環）
    capabilities: VfsCapabilities = VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE
    provider_module: Optional[ModuleId] = None    # 供 URI_UNDEFINED 生成 remediation
    config_binding: Optional[str] = None          # 供 URI_UNDEFINED 生成 remediation
    description: str = ""


class VfsProvider(Protocol):
    @property
    def scheme(self) -> str: ...
    @property
    def base_capabilities(self) -> VfsCapabilities: ...
    @property
    def description(self) -> str: ...
    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities: ...
    def exists(self, uri: SemanticUri) -> bool: ...
    def stat(self, uri: SemanticUri) -> VfsStat: ...
    def read_bytes(self, uri: SemanticUri) -> bytes: ...
    def open_read(self, uri: SemanticUri) -> BinaryIO: ...
    def write_bytes_atomic(
        self, uri: SemanticUri, data: bytes, *, before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None: ...
    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool: ...
    def move(self, src: SemanticUri, dst: SemanticUri) -> None: ...
    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None: ...
    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]: ...
    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]: ...
```


class PhysicalDirectoryProvider:
    """1:1 沙盒目錄 Provider：封裝 filesystem.fs 原子寫入、防穿越、LF 換行與跨平台重試。"""
    def __init__(
        self, scheme: str, root_dir: HostPath, *,
        base_capabilities: VfsCapabilities, description: str = "",
    ) -> None: ...


class MemoryVfsProvider:
    """純標準庫記憶體 Provider（無 PHYSICAL_PATH）：專供單元測試零磁碟隔離驗證。"""
    def __init__(
        self, scheme: str, *,
        base_capabilities: VfsCapabilities = VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE,
        description: str = "",
    ) -> None: ...


class UriMountTable:
    """語意 URI 路由與掛載表（零全域狀態；禁止 project:// 隱式回退 os.getcwd()）。"""
    def __init__(self, rules: Sequence[MountRule], *, providers: Optional[Mapping[str, VfsProvider]] = None) -> None: ...
    def list_rules(self) -> tuple[MountRule, ...]: ...
    def get_provider(self, scheme: str) -> VfsProvider: ...
    def resolve_physical(self, uri: SemanticUri) -> HostPath: ...
    def to_uri(self, abs_path: HostPath) -> Optional[SemanticUri]: ...
    def check_health(self) -> tuple[tuple[str, bool, str], ...]: ...


@dataclass(frozen=True, slots=True)
class ReadonlySyncResult:
    locked_count: int
    already_locked_count: int
    unlocked_count: int
    failed_paths: tuple[tuple[HostPath, str], ...] = ()


class ReadonlyPolicy:
    """雙層唯讀保護策略（以規範 HostPath 為鍵，跨協議一致；零匯入 filesystem.space）。"""
    def __init__(self, matcher: Optional[Callable[[HostPath], bool]] = None) -> None: ...
    def update_matcher(self, matcher: Callable[[HostPath], bool]) -> None: ...
    def is_protected(self, path: HostPath) -> bool: ...
    def is_os_readonly(self, path: HostPath) -> bool: ...
    def lock_file(self, path: HostPath) -> bool: ...
    def unlock_file(self, path: HostPath) -> bool: ...
    def sync_files(self, protected_paths: Sequence[HostPath]) -> ReadonlySyncResult: ...
    @contextmanager
    def authorized_write_tunnel(self, path: HostPath) -> Iterator[None]: ...


class VfsEchoGuard:
    """實作 execution.runtime.VfsEchoGuardPort 協定（結構匹配，零匯入 execution）。"""
    def __init__(self, *, ttl_sec: float = 5.0, max_entries: int = 2048) -> None: ...
    def record_write(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> None: ...
    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """模組級寫入權限白名單策略（支援特例模組如 dev 獲授 module.{source,build,release}:// 寫權）。"""
    extra_writable_schemes: Mapping[ModuleId, frozenset[str]] = ...
    readonly_tunnel_modules: frozenset[ModuleId] = frozenset()


class VfsHub:
    """工作區級 VFS 協調根（顯式建構子注入，供頂層組裝根派生 ScopedVfs 與 KernelVfs）。"""
    def __init__(
        self, mount_table: UriMountTable, *,
        readonly_policy: Optional[ReadonlyPolicy] = None,
        echo_guard: Optional[VfsEchoGuard] = None,
        access_policy: Optional[AccessPolicy] = None,
    ) -> None: ...
    @property
    def mount_table(self) -> UriMountTable: ...
    @property
    def readonly_policy(self) -> ReadonlyPolicy: ...
    @property
    def echo_guard(self) -> VfsEchoGuard: ...
    def for_module(self, module_id: ModuleId) -> ScopedVfs: ...
    def for_kernel(self) -> KernelVfs: ...


class ScopedVfs:
    """面向業務模組之受限 VFS 門面（自動展開 @/、強制跨模組寫入隔離與唯讀保護）。"""
    @property
    def module_id(self) -> ModuleId: ...
    def bind_uri(self, uri: SemanticUri | str) -> SemanticUri: ...
    def get_capabilities(self, uri: SemanticUri | str) -> VfsCapabilities: ...
    def can_read(self, uri: SemanticUri | str) -> bool: ...
    def can_write(self, uri: SemanticUri | str) -> bool: ...
    def exists(self, uri: SemanticUri | str) -> bool: ...
    def stat(self, uri: SemanticUri | str) -> VfsStat: ...
    def read_bytes(self, uri: SemanticUri | str) -> bytes: ...
    def read_text(self, uri: SemanticUri | str, *, encoding: str = "utf-8") -> str: ...
    def read_json(self, uri: SemanticUri | str) -> JsonValue: ...
    def write_bytes(self, uri: SemanticUri | str, data: bytes) -> None: ...
    def write_text(self, uri: SemanticUri | str, text: str, *, encoding: str = "utf-8", normalize_lf: bool = True) -> None: ...
    def write_json(self, uri: SemanticUri | str, payload: JsonObject, *, indent: int = 2) -> None: ...
    def mkdir(self, uri: SemanticUri | str, *, parents: bool = True) -> None: ...
    def delete(self, uri: SemanticUri | str, *, recursive: bool = False) -> bool: ...
    def move(self, src: SemanticUri | str, dst: SemanticUri | str) -> None: ...
    def iter_entries(self, uri: SemanticUri | str, *, recursive: bool = False) -> Iterator[SemanticUri]: ...
    def try_get_physical_path(self, uri: SemanticUri | str) -> Optional[HostPath]: ...


class KernelVfs(ScopedVfs):
    """內核特權 VFS（供 installer / config / gitignore / file-lock 等內建系統任務使用）。"""
    def write_bytes_through_readonly(self, uri: SemanticUri | str, data: bytes) -> None: ...
    def write_text_through_readonly(self, uri: SemanticUri | str, text: str, *, encoding: str = "utf-8") -> None: ...
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
5. **跨模組寫入邊界隔離**：`ScopedVfs(mod)` 對 `config.local://`、`cache://`、`storage://`、`storage.local://` 僅允許寫入首段等於 `mod.value` 之子路徑（含 `@/` 展開），寫入他模組目錄或唯讀核心協議一律拋 `YscbError(ErrorCode.ACCESS_DENIED)`。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **能力遮罩與 15 協議契約**：驗證 15 組標準協議之 `VfsCapabilities` 矩陣（特別是 `storage.local://` vs `cache://` vs `storage://` 區分），以及 `MountRule` 循環引用拋 `URI_CYCLE`、`!undefined` 拋 `URI_UNDEFINED` 且零 `os.getcwd()` 依賴。
2. **路徑防穿越與雙層唯讀測試**：同前綴兄弟目錄逃逸攔截、符號連結拒絕、未授權寫入 `/readonly` 拋 `READONLY_VIOLATION`、授權穿隧寫入後 OS 唯讀位元保持鎖定、Windows 唯讀檔 `robust_rmtree` 清理。
3. **跨協議同實體路徑一致與免回音抑制**：透過 `workflow.plans://a.md` 寫入後，以 `project://plans/a.md` 對應實體 `HostPath` 查詢 `VfsEchoGuard.is_suppressed(...)` 命中 `True`，且 `ReadonlyPolicy` 雙向皆生效。
4. **`ScopedVfs` 隔離與 `MemoryVfsProvider` 等價測試**：模組 A 寫入 `storage.local://b/x` 拋 `ACCESS_DENIED`；寫入 `storage.local://@/x` 成功映射至 `storage.local://a/x`；`MemoryVfsProvider` 完整通過同套基礎讀寫列舉契約測試。
