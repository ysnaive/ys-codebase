# 子模組架構設計規格：`core.foundation`（Wave 1.2 擴充設計書）

> **所屬功能域**：`Domain 1 — 基礎底座域 (foundation/)`
> **模組路徑**：`core_v2/source/core/core/foundation/`（擴充既有 `primitives.py`、`errors.py`、`codec.py`、`observability.py`；可按需拆出內部模組如 `version.py`、`env.py`、`locale.py`）
> **依賴上限（Allowed Imports）**：`100% Python 3.11+ 標準庫`（同域依賴方向：`codec | observability | proc -> primitives | errors`）
> **禁止反向依賴（Forbidden Imports）**：`filesystem/*`、`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`（實作完成並接入 Gate 0 後，公開簽名併入 Active Living Spec [foundation.md](./foundation.md)）

> [!NOTE]
> **實作彈性邊界（External SDK vs. Internal API）**：本規格書中標記為 **SDK / 跨功能域公開契約** 的值物件語意、錯誤碼、序列化格式與環境變數憲法必須嚴格統一；純內核內部輔助函式、檔案切分與私有方法命名，遠端實作端可依實際代碼結構微調。

---

## 1. Wave 1.2 擴充定位與 1.x $\to$ 2.0 減法清單

Wave 1.1 已於 [foundation.md](./foundation.md) 落地執行內核子集。Wave 1.2 補齊其餘 4 項跨功能域純底座能力：
1. **跨功能域不可變值物件**：`SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash`。
2. **受控環境變數清冊與錯誤碼補完**：落實 [foundation.md](./foundation.md) §3 憲法，將 `YSCB_WORKER_AUTH_TOKEN` 統一更名為 `_YSCB_WORKER_AUTH_TOKEN`，並建立 `YSCB_*` 公開白名單與 `_YSCB_*` 內部前綴封殺常數。
3. **純標準庫 JSON Schema 導出器（`SchemaExporter`）**：自 `@dataclass(frozen=True, slots=True)` 導出 JSON Schema Draft 2020-12，供 `Contributes 2.0` 與 IDE 補全使用。
4. **顯式 DI 可觀測性與多語系引擎**：`LogRotator`、`StructuredLogger`、`LocaleCatalog`（供全生態系模組使用）與極簡 `SessionTelemetryWriter`。

### 1.x $\to$ 2.0 明確減法（嚴禁帶回 2.0）
- **廢除**全域 `core.log` / `DebouncedIOStreamer` 隱式 `ContextVar` 串流劫持（2.0 業務輸出統一走 `TaskOutcome` / `ctx.report_progress` / 顯式注入 `StructuredLogger`）。
- **廢除** `core.locale` 內部的磁碟檔案讀取與 `os.environ` 嗅探（`LocaleCatalog` 僅保留純記憶體查表與插值；語系載入與 AI IDE Dialect 嗅探移至 `metadata` / `surface` 層）。
- **下沉** `DeepInfiller` 至 `Domain 3 (metadata.config)`，不膨脹 `foundation.codec`。

---

## 2. 受控環境變數憲法與命名對齊

延續 [foundation.md](./foundation.md) §3，所有跨進程與使用者覆寫環境變數集中宣告於 `core.foundation`：

| 類別 | 變數名 | 用途與邊界 |
| :--- | :--- | :--- |
| **公開白名單 (`YSCB_*`)** | `YSCB_NO_DAEMON` | `"1"` 強制停用 Daemon 自動拉起與熱派發 |
| | `YSCB_FORCE_DAEMON` | `"1"` 覆寫環境探測誤判，允許常駐 Daemon |
| | `YSCB_LOG_LEVEL` | 覆寫日誌等級（`debug` / `info` / `warning` / `error`） |
| | `YSCB_NO_UPDATE_CHECK` | `"1"` 停用 12 小時背景更新檢查 |
| | `YSCB_LOCALE` | 逗號分隔之顯式語系鏈覆寫（如 `en,zh`） |
| | `YSCB_OFFLINE` | `"1"` 強制全域離線模式（阻斷遠端 Provider 網路存取） |
| | `YSCB_CALLER_MODE` | 顯式指定呼叫端模式（`agent` / `ci` / `human`，無 TTY 時禁止覆寫為 `human`） |
| | `YSCB_CI_APPROVE_GATED` | `"1"` 僅於同時命中 `CI_PIPELINE` 特徵時，允許 CI 管線放行 `GATED` 任務（不開放予 Agent） |
| **內核私有 (`_YSCB_*`)** | `_YSCB_TREE_ID` | 已落地：`ManagedProcessTree` 進程樹標記 |
| | `_YSCB_WORKER_AUTH_TOKEN` | **Wave 1.2 改名**（取代既有 `YSCB_WORKER_AUTH_TOKEN`） |
| | `_YSCB_TEST_SANDBOX` | `"1"` 標記隔離測試沙盒（自動停用遙測與更新提示） |
| | `_YSCB_HOST_DIR` / `_YSCB_ROOT_DIR` | 沙盒與子進程顯式根目錄覆寫（僅內核自舉消費） |

**剛性不變量**：
- `PRIVATE_ENV_PREFIX: Final[str] = "_YSCB_"`；`execution.runtime.sanitize_caller_env` 必須依前綴整批過濾所有 `_YSCB_*` 外部注入鍵。
- 改名 `YSCB_WORKER_AUTH_TOKEN -> _YSCB_WORKER_AUTH_TOKEN` 時須同步更新 `execution/runtime/{contracts,worker_entry,worker_pool}.py`、`execution/runtime.md` 與 `tests/`。

---

## 3. 新增錯誤碼 (`ErrorCode` 擴充)

於 `core.foundation.errors.ErrorCode` 追加以下標準枚舉值（既有 20 個枚舉值名稱與字串值維持 100% 不變）：

| ErrorCode | 字串值 | 適用域與語意 |
| :--- | :--- | :--- |
| `URI_UNDEFINED` | `"uri_undefined"` | `vfs`：語意協議未設定（`!undefined`），必須附帶 `remediation` 指令 |
| `URI_CYCLE` | `"uri_cycle"` | `vfs`：語意掛載規則存在循環引用 |
| `ACCESS_DENIED` | `"access_denied"` | `vfs` / `storage`：越權路徑穿越、跨模組非法寫入或對非 `storage.local://` 建庫 |
| `READONLY_VIOLATION` | `"readonly_violation"` | `vfs`：未授權寫入受 `/readonly` 保護之檔案或唯讀掛載 |
| `SPACE_CYCLE` | `"space_cycle"` | `space`：`presets` 或 `compose` 存在循環引用 |
| `SPACE_NOT_FOUND` | `"space_not_found"` | `space`：請求之邏輯空間不存在 |
| `STORAGE_CORRUPT` | `"storage_corrupt"` | `storage`：SQLite 資料庫損毀或完整性檢核失敗 |
| `SCHEMA_MIGRATION_ERROR` | `"schema_migration_error"` | `storage`：資料庫版本高於程式支援版本或遷移失敗 |
| `CONFIG_INVALID` | `"config_invalid"` | `metadata.config`：組態 JSON 損毀或型別驗證失敗 |
| `CONTRIBUTES_INVALID` | `"contributes_invalid"` | `metadata.contributes`：擴充宣告違反 Host 端型別契約或合併衝突 |
| `DEPENDENCY_CONFLICT` | `"dependency_conflict"` | `packaging.installer`：模組版本相依約束無交集 |
| `PACKAGE_INTEGRITY_ERROR` | `"package_integrity_error"` | `packaging.installer`：Zip CRC、SHA-256 或 Zip Slip 校驗失敗 |
| `ENV_BUILD_FAILED` | `"env_build_failed"` | `packaging.env`：Tier 1 `.venv` 建立或 `--only-binary=:all:` 安裝失敗 |

---

## 4. 新增核心公開值物件與服務契約

> 下列簽名標示為 Wave 1.2 設計基準；凡暴露予下游模組之值物件（`SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash`、`LogLevel`、`StructuredLogger`、`LocaleCatalog`）其公開語意與 `DataclassCodec` 字串編解碼格式屬硬契約。

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Final, Mapping, Optional, Protocol, Sequence

from core.foundation.primitives import HostPath, JsonObject, ModuleId, MutableJsonObject

PUBLIC_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset({
    "YSCB_NO_DAEMON",
    "YSCB_FORCE_DAEMON",
    "YSCB_LOG_LEVEL",
    "YSCB_NO_UPDATE_CHECK",
    "YSCB_LOCALE",
    "YSCB_OFFLINE",
    "YSCB_CALLER_MODE",
    "YSCB_CI_APPROVE_GATED",
})
PRIVATE_ENV_PREFIX: Final[str] = "_YSCB_"
MAX_LOCALE_INTERPOLATION_DEPTH: Final[int] = 5


@dataclass(frozen=True, slots=True)
class SemVer4:
    """四段式語意版本：major.minor.patch.revision[-prerelease] 或 major.minor.patch.build。"""
    major: int
    minor: int
    patch: int
    revision: int = 0
    is_build: bool = False
    prerelease: str = ""

    @classmethod
    def parse(cls, raw: str) -> SemVer4: ...
    def triple(self) -> tuple[int, int, int]: ...
    def compare_precedence(self, other: SemVer4) -> int: ...
    def __lt__(self, other: SemVer4) -> bool: ...
    def __le__(self, other: SemVer4) -> bool: ...
    def __gt__(self, other: SemVer4) -> bool: ...
    def __ge__(self, other: SemVer4) -> bool: ...
    def __str__(self) -> str: ...
```


@dataclass(frozen=True, slots=True)
class VersionConstraint:
    """相依版本約束（支援 ==, =, !=, >, >=, <, <=, ~=, ^, * 及逗號合取）。"""
    raw: str

    @classmethod
    def parse(cls, raw: str) -> VersionConstraint: ...
    @classmethod
    def compatible_same_major(cls, ver: SemVer4) -> VersionConstraint: ...
    def satisfies(self, ver: SemVer4) -> bool: ...
    def __str__(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SemanticUri:
    """不可變語意 URI 值物件（強制顯式 scheme://，禁止隱式預設協議與路徑穿越）。"""
    scheme: str
    rel_path: str = ""

    @classmethod
    def parse(cls, raw: str) -> SemanticUri: ...
    @property
    def uses_module_placeholder(self) -> bool: ...
    @property
    def name(self) -> str: ...
    @property
    def suffix(self) -> str: ...
    @property
    def parent(self) -> Optional[SemanticUri]: ...
    def bind_module(self, module_id: ModuleId) -> SemanticUri: ...
    def join(self, *parts: str) -> SemanticUri: ...
    def __truediv__(self, part: str) -> SemanticUri: ...
    def __str__(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SpaceId:
    """邏輯檔案空間識別碼：具名擁有者 '<owner>/<name>' 或合成聯集空間 '/<name>' (owner='')。"""
    owner: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> SpaceId: ...
    @property
    def is_synthetic(self) -> bool: ...
    def __str__(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SpacePath:
    """邏輯空間內之標準化 POSIX 相對路徑（無前導斜線，區段經 validate_relative_segment 驗證）。"""
    rel_path: str

    @classmethod
    def parse(cls, raw: str) -> SpacePath: ...
    def __str__(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SnapshotGen:
    """單調遞增非負整數快照世代（>= 0）。"""
    value: int

    def next(self) -> SnapshotGen: ...
    def __lt__(self, other: SnapshotGen) -> bool: ...
    def __le__(self, other: SnapshotGen) -> bool: ...


@dataclass(frozen=True, slots=True)
class EnvHash:
    """不可變虛擬環境雜湊識別符（小寫 hex，16~64 字元）。"""
    value: str

    def short(self, length: int = 16) -> str: ...
    def __str__(self) -> str: ...


class SchemaExporter:
    """純標準庫 JSON Schema (Draft 2020-12) 導出器，供 Contributes 2.0 與 IDE 補全使用。"""
    @staticmethod
    def export(target_cls: type[object], *, title: Optional[str] = None) -> MutableJsonObject: ...


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LogRecord:
    ts_utc: str
    level: LogLevel
    logger_name: str
    message: str
    fields: JsonObject = ...


class LogRotator:
    """純標準庫滾動檔案紀錄器（支援位元組／行數上限原子輪替、崩潰殘留恢復、歷史保留數上限與 FD 不可繼承）。"""
    def __init__(
        self, log_path: HostPath, *, max_bytes: int = 512 * 1024, max_lines: Optional[int] = None,
        keep_lines: Optional[int] = None, max_history_files: int = 5,
    ) -> None: ...
    def append_line(self, line: str) -> None: ...
    def append_jsonl(self, payload: JsonObject) -> None: ...
    def read_tail_lines(self, limit: int = 100) -> tuple[str, ...]: ...
    def read_jsonl(self, *, limit: Optional[int] = None) -> tuple[MutableJsonObject, ...]: ...
    def close(self) -> None: ...


class StructuredLogger(Protocol):
    """顯式注入之結構化日誌協定（供內核與下游業務模組經 TaskContext/ModuleEnv 消費）。"""
    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def debug(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def info(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def warning(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def error(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...


class LocaleCatalog:
    """純記憶體多語系與宿主專有名詞查表引擎（零磁碟 I/O、零環境嗅探；顯式語系鏈與有界遞迴插值）。"""
    def __init__(
        self, dictionaries_by_module: Mapping[ModuleId, Mapping[str, Mapping[str, str]]],
        *, default_chain: Sequence[str] = ("zh",),
    ) -> None: ...
    def translate(
        self, key: str, *, caller_module: Optional[ModuleId] = None,
        chain: Optional[Sequence[str]] = None, params: Optional[Mapping[str, object]] = None,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class SessionTelemetryRecord:
    ts_utc: str
    epoch_ms: int
    task_id: str
    args: tuple[str, ...]
    exit_code: int
    duration_ms: int
    executed_hot: bool
    caller_cwd: str
    error_hint: str = ""


class SessionTelemetryWriter:
    """輕量 CLI 飛行紀錄器（基於 LogRotator 寫入 cache://core/telemetry.jsonl；沙盒模式預設停用）。"""
    def __init__(self, rotator: LogRotator, *, enabled: bool = True) -> None: ...
    def record(self, entry: SessionTelemetryRecord) -> None: ...
    def read_recent(self, limit: int = 100) -> tuple[SessionTelemetryRecord, ...]: ...
```

---

## 5. 關鍵語意與行為不變量

1. **`SemVer4` 與 `VersionConstraint`（承襲 1.x `SEMVER.md`）**：
   - 三段輸入（`"1.2.3"`）自動正規化為 `SemVer4(1, 2, 3, 0)`；`"1.2.3.build"` 設 `is_build=True, revision=0`；數值 revision 優先於 `.build`（`1.2.3.0 > 1.2.3.build`）；正式版優先於預發布版（`1.2.3.0 > 1.2.3.0-beta.1`）。
   - 依賴比較與 `==1.2.0` 精確三元約束維持同 1.x：數值型 `revision` 為構建修訂號，不破壞同 `(major, minor, patch)` 相容性；`^X.Y.Z` / `~=X.Y.Z` 鎖定同 Major（`>=X.Y.Z.0, <(X+1).0.0.0`）。
2. **`SemanticUri` 防呆不變量**：
   - 嚴格要求含 `"://"`；無 `scheme` 或空 `scheme` 立即拋出 `ValueError`。
   - `rel_path` 將 `\` 正規化為 `/`，剝除頭尾 `/` 與重複 `//`，逐段經 `validate_relative_segment` 校驗（僅允許第 1 段為字面 `"@"` 表示當前模組自省）；`bind_module(mod)` 將前導 `@` 確定性展開為 `mod.value`。
   - `DataclassCodec` 必須原生支援 `SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash` 作為 JSON 字串／整數雙向編解碼。
3. **`SchemaExporter` 輸出契約**：
   - 輸出標準 JSON Schema Draft 2020-12（含 `"$schema": "https://json-schema.org/draft/2020-12/schema"`、`$defs`、物件預設 `"additionalProperties": False`）。
   - `Optional[T]` 映射為 `anyOf: [<T>, {"type": "null"}]`；`Enum` 映射為 `"enum": [...]`；支援 `Annotated[T, metadata]` 萃取描述文字。
4. **`LogRotator` 與 `LocaleCatalog` 不變量**：
   - `LogRotator` 輪替切割文字行強制使用 `.split("\n")`（避免 `\u2028`/`\u2029` 切壞 JSONL）、`os.set_inheritable(fd, False)` 防子進程繼承句柄，並於滾動截斷時使用同目錄暫存檔 + `os.replace`。
   - `LocaleCatalog.translate` 嚴格按顯式 `chain` 順序查找（**不做 `-` 連字號隱式父語系猜測**）；無 `<module>:` 前綴時先查 `caller_module` 再依模組字母序穿透查找；`{placeholder}` 先查 `params` 再視為專有名詞鍵遞迴解析（深度上限 `5`，超過或遇環即原樣保留不崩潰），並保護 `{{` / `}}` 轉義。

---

## 6. 必測驗收門檻 (Verification Gate)

1. **環境變數憲法與 Gate 0 同步**：`sanitize_caller_env` 整批剔除 `_YSCB_*`（含更名後之 `_YSCB_WORKER_AUTH_TOKEN`），未登記之 `os.environ` 讀取被靜態檢查攔截。
2. **值物件與 `DataclassCodec` 往返**：`SemVer4`（三段／四段／`.build`／prerelease／`^` 同 Major 鎖定）、`SemanticUri`（`..`／NTFS `:`／保留字攔截與 `@/` 展開）、`SpaceId`（具名與 `/short` 合成）皆通過正負向單測與 Codec 往返。
3. **`SchemaExporter`**：對嵌套 `@dataclass`、`Enum`、`Optional`、自訂值物件與遞迴型別導出合法 Draft 2020-12 Schema。
4. **`LogRotator` / `LocaleCatalog` / `SessionTelemetryWriter`**：含 `\u2028` JSONL 輪替不破損、無句柄洩漏（`0 ResourceWarning`）、`LocaleCatalog` 顯式鏈與深度 5 防環、沙盒模式自動停用遙測寫入。
