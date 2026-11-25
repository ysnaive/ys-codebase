# 子模組架構設計規格：`core.foundation`（零外部依賴強型別底座、編解碼、JSON Schema、可觀測性與跨平台進程原語）

> **所屬功能域**：`Domain 1 — 基礎底座域 (foundation/)`
> **模組路徑**：`core_v2/source/core/core/foundation/`
> **內部模組職責切分**：`primitives.py`、`errors.py`、`codec.py`、`observability.py`、`proc.py`
> **依賴上限（Allowed Imports）**：`100% Python 3.11+ 標準庫`（同域依賴方向：`codec | observability | proc -> primitives | errors`）
> **禁止反向依賴（Forbidden Imports）**：`filesystem/*`、`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

## 1. 核心職責與設計不變量

1. **不可變基礎值物件、跨功能域識別符與跨平台路徑區段安全（`primitives.py`）**：提供 `ModuleId`、`TaskId`、`EventId`、`HostPath`、`SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash`、受控環境變數清冊（`PUBLIC_ENV_ALLOWLIST` / `PRIVATE_ENV_PREFIX`）、嚴格 int64/UTF-8/有限浮點 JSON 解析與複製原語、Windows 重解析點標籤判定（`IO_REPARSE_TAG_SYMLINK` / `IO_REPARSE_TAG_MOUNT_POINT` / `is_disallowed_reparse_tag`，僅攔截 Symlink 與 Mount Point／Junction 並放行 OneDrive／WOF），以及跨平台相對路徑區段守衛（`is_valid_relative_segment` / `validate_relative_segment`，統一封鎖 `..`、路徑分隔符、NTFS `:` 替代資料流、尾隨點號／空白別名與 Windows 保留裝置名稱）。
2. **結構化錯誤階層（`errors.py`）**：定義 `ErrorCode`、`ErrorDetail`、`YscbError`、`EventCycleError`、`CallCycleError` 與協作式 `TaskCancelledException`。
3. **純標準庫強型別編解碼器與 JSON Schema 導出器（`codec.py`）**：提供支援遞迴型別、基礎泛型參數替換、宣告序聯合型別解碼、全值物件雙向映射、嚴格欄位校驗與弱引用自動回收之 `DataclassCodec`、`infer_sequence_element_dataclass`，以及標準 JSON Schema Draft 2020-12 導出器 `SchemaExporter`。
4. **協作取消、截止時間守衛、結構化日誌輪替、多語系查表與標準輸出隔離（`observability.py`）**：提供 `CancellationToken`、`DeadlineGuard`、`ProgressEvent`、`guard_standard_streams`、`LogLevel`、`LogRecord`、`LogRotator`、`StructuredLogger`、`LocaleCatalog` 與 `SessionTelemetryWriter`。
5. **跨平台進程樹監管與主執行緒訊號協調（`proc.py`）**：提供 `ManagedProcessTree`（Windows Job Object 含 `BREAKAWAY_OK` / POSIX Session+PGID）、`spawn_detached`（經 `stdin` 安全傳遞負載）、防殭屍誤判之 `is_process_alive` / `get_process_start_tag`，以及基於單主執行緒 `signal.signal` 註冊與生命週期還原之 `SignalWakeupGuard`。

## 2. 公開契約規格 (`core.foundation.__all__` 完整快照)

```python
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Callable, ClassVar, Final, ForwardRef, Generic, NoReturn, Optional, Protocol, TextIO, TypeAlias, TypeVar, overload

_T = TypeVar("_T")
T = TypeVar("T")

HOST_DIR_ENV_KEY: Final[str] = '_YSCB_HOST_DIR'
INT64_MAX: Final[int] = (1 << 63) - 1
INT64_MIN: Final[int] = -(1 << 63)
IO_REPARSE_TAG_MOUNT_POINT: Final[int] = 0xA0000003
IO_REPARSE_TAG_SYMLINK: Final[int] = 0xA000000C
IS_WINDOWS: Final[bool] = sys.platform == 'win32'
MAX_LOCALE_INTERPOLATION_DEPTH: Final[int] = 5
MAX_SAFE_WAIT_SEC: Final[float] = min(86400.0 * 7.0, float(threading.TIMEOUT_MAX) * 0.5)
MAX_TIMEOUT_MS: Final[int] = int(MAX_SAFE_WAIT_SEC * 1000.0)
MAX_USER_JSON_DEPTH: Final[int] = 128
MAX_ENVELOPE_JSON_DEPTH: Final[int] = MAX_USER_JSON_DEPTH + 6
MAX_PARSE_JSON_DEPTH: Final[int] = MAX_ENVELOPE_JSON_DEPTH + 2
PRIVATE_ENV_PREFIX: Final[str] = '_YSCB_'
PUBLIC_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset({
    'YSCB_NO_DAEMON',
    'YSCB_FORCE_DAEMON',
    'YSCB_LOG_LEVEL',
    'YSCB_NO_UPDATE_CHECK',
    'YSCB_LOCALE',
    'YSCB_OFFLINE',
    'YSCB_CALLER_MODE',
    'YSCB_CI_APPROVE_GATED',
})
PYTHON_LAUNCHER_HIJACK_ENV_KEYS: Final[tuple[str, ...]] = ('__PYVENV_LAUNCHER__', 'PYTHONSTARTUP', 'PYTHONINSPECT')
ROOT_DIR_ENV_KEY: Final[str] = '_YSCB_ROOT_DIR'
TEST_SANDBOX_ENV_KEY: Final[str] = '_YSCB_TEST_SANDBOX'
TREE_ID_ENV_KEY: Final[str] = '_YSCB_TREE_ID'

JsonObject: TypeAlias = Mapping[str, JsonValue]

JsonPrimitive: TypeAlias = None | bool | int | float | str

JsonValue: TypeAlias = JsonPrimitive | Sequence['JsonValue'] | Mapping[str, 'JsonValue']

MutableJsonObject: TypeAlias = dict[str, JsonValue]

def build_isolated_python_env() -> dict[str, str]:
    ...

def clamp_positive_sec(val: object, *, min_sec: float, max_sec: float, default_sec: Optional[float]=None, label: str='seconds') -> float:
    ...

def clamp_wait_sec(timeout_sec: Optional[float], *, min_sec: float=0.0) -> Optional[float]:
    ...

def clone_strict_json_object(payload: object, *, max_depth: int=MAX_USER_JSON_DEPTH, label: str='payload') -> MutableJsonObject:
    ...

def decrement_ref_count(table: dict[_T, int], key: _T) -> int:
    ...

def get_process_start_tag(pid: int) -> Optional[str]:
    ...

@contextmanager
def guard_standard_streams(*, allow_interactive_tty: bool=False) -> Iterator[io.StringIO]:
    ...

def infer_sequence_element_dataclass(fn: object, *, strict_unresolved: bool) -> tuple[bool, Optional[object]]:
    ...

def invoke_observer_safely(fn: Callable[[], object]) -> None:
    ...

def is_disallowed_reparse_tag(reparse_tag: int) -> bool:
    ...

def is_fatal_error_code(code: ErrorCode) -> bool:
    ...

def is_process_alive(pid: int) -> bool:
    ...

def is_public_env_truthy(key: str) -> bool:
    ...

def is_valid_relative_segment(segment: str) -> bool:
    ...

def is_valid_type_annotation(tp_val: object) -> bool:
    ...

def ms_to_safe_sec(ms: int, *, min_sec: float=0.0) -> float:
    ...

def read_public_env_value(key: str) -> Optional[str]:
    ...

def require_non_negative_sec(timeout_sec: float, *, label: str='timeout_sec') -> float:
    ...

def require_non_none(val: Optional[_T], message: str='Expected non-None invariant') -> _T:
    ...

def require_pure_bool(val: object, label: str='value') -> bool:
    ...

def require_pure_int(val: object, label: str='value', *, min_val: Optional[int]=INT64_MIN, max_val: Optional[int]=INT64_MAX) -> int:
    ...

def require_pure_str(val: object, label: str='value', *, non_empty: bool=False) -> str:
    ...

def require_typed_frozenset(items: object, elem_type: type[_T], label: str='items') -> frozenset[_T]:
    ...

def require_typed_tuple(items: object, elem_type: type[_T], label: str='items') -> tuple[_T, ...]:
    ...

def resolve_dataclass_init_hints(dc_cls: type[object]) -> dict[str, object]:
    ...

def safe_exception_summary(exc: BaseException) -> str:
    ...

def safe_real_to_float(val: object, *, label: str='value') -> float:
    ...

def sanitize_utf8_text(text: str) -> str:
    ...

def spawn_detached(argv: Sequence[str], *, cwd: HostPath, extra_env: Optional[Mapping[str, str]]=None) -> int:
    ...

def strict_parse_json_object(raw_text: str) -> MutableJsonObject:
    ...

def validate_json_primitive(val: object, label: str='payload') -> JsonPrimitive:
    ...

def validate_min_sec(min_sec: float) -> float:
    ...

def validate_non_negative_sec(timeout_sec: Optional[float], *, label: str='timeout_sec') -> Optional[float]:
    ...

def validate_relative_segment(segment: str, *, label: str='path segment') -> str:
    ...

def validate_wire_json_object(payload: object, *, max_depth: int=MAX_ENVELOPE_JSON_DEPTH, label: str='payload') -> None:
    ...

class CallCycleError(YscbError):

    def __init__(self, message: str, *, remediation: Optional[str]=None, source_task: Optional[str]=None) -> None:
        ...

class CancellationToken:

    def __init__(self) -> None:
        ...

    @property
    def is_cancelled(self) -> bool:
        ...

    @property
    def is_preempted(self) -> bool:
        ...

    @property
    def reason(self) -> str:
        ...

    def cancel_deferred(self, *, preempted: bool=False, reason: str='cancelled') -> tuple[Callable[[], None], ...]:
        ...

    @staticmethod
    def run_callbacks(thunks: Sequence[Callable[[], None]]) -> None:
        ...

    def cancel(self, *, preempted: bool=False, reason: str='cancelled') -> None:
        ...

    def register_callback(self, fn: Callable[[bool, str], None]) -> Callable[[], None]:
        ...

    def wait(self, timeout_sec: Optional[float]=None) -> bool:
        ...

    @staticmethod
    def combine(*tokens: Optional[CancellationToken]) -> tuple[CancellationToken, Callable[[], None]]:
        ...

    def raise_if_cancelled(self) -> None:
        ...

class DataclassCodec:

    @staticmethod
    def encode(obj: object) -> JsonValue:
        ...

    @staticmethod
    def encode_typed(expected_type: object, obj: object) -> JsonValue:
        ...

    @staticmethod
    def encode_object(obj: object, *, expected_type: Optional[object]=None) -> MutableJsonObject:
        ...

    @staticmethod
    def encode_envelope(obj: object) -> MutableJsonObject:
        ...

    @staticmethod
    def decode_envelope(target_cls: type[T], raw: JsonValue) -> T:
        ...

    @overload
    @staticmethod
    def decode(target_cls: type[T], raw: JsonValue, *, localns: Optional[Mapping[str, object]]=None) -> T:
        ...

    @overload
    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]]=None) -> object:
        ...

    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]]=None) -> object:
        ...

    @staticmethod
    def canonical_hash(raw: object) -> str:
        ...

    @staticmethod
    def evict_module_prefix(module_prefix: str) -> None:
        ...

@dataclass(frozen=True, slots=True)
class DeadlineGuard:
    cancel_token: Optional[CancellationToken] = None
    deadline: Optional[float] = None

    @staticmethod
    def from_timeout_ms(timeout_ms: Optional[int], cancel_token: Optional[CancellationToken]=None) -> DeadlineGuard:
        ...

    def remaining_ms(self, default_ms: Optional[int]=None, *, expired_message: str='Operation timed out.') -> Optional[int]:
        ...

@dataclass(frozen=True, slots=True)
class EnvHash:
    value: str

    def short(self, length: int=16) -> str:
        ...

    def __str__(self) -> str:
        ...

class ErrorCode(Enum):
    TASK_NOT_FOUND = 'task_not_found'
    EXPOSURE_DENIED = 'exposure_denied'
    SECURITY_GATED = 'security_gated'
    TTY_REQUIRED = 'tty_required'
    COLD_DISPATCH_FORBIDDEN = 'cold_dispatch_forbidden'
    DAEMON_UNAVAILABLE = 'daemon_unavailable'
    HOT_MUTATION_FORBIDDEN = 'hot_mutation_forbidden'
    CALL_CYCLE_DETECTED = 'call_cycle_detected'
    EVENT_CYCLE_DETECTED = 'event_cycle_detected'
    ILLEGAL_LOCK_REENTRANCY = 'illegal_lock_reentrancy'
    TASK_CANCELLED = 'task_cancelled'
    TASK_PREEMPTED = 'task_preempted'
    TASK_TIMEOUT = 'task_timeout'
    TRANSPORT_LOST = 'transport_lost'
    PAYLOAD_TOO_LARGE = 'payload_too_large'
    CODEC_VALIDATION_FAILED = 'codec_validation_failed'
    WORKER_CRASHED = 'worker_crashed'
    MODULE_DEGRADED = 'module_degraded'
    TEARDOWN_ERROR = 'teardown_error'
    BUSINESS_FAILURE = 'business_failure'
    URI_UNDEFINED = 'uri_undefined'
    URI_CYCLE = 'uri_cycle'
    ACCESS_DENIED = 'access_denied'
    READONLY_VIOLATION = 'readonly_violation'
    SPACE_CYCLE = 'space_cycle'
    SPACE_NOT_FOUND = 'space_not_found'
    STORAGE_CORRUPT = 'storage_corrupt'
    SCHEMA_MIGRATION_ERROR = 'schema_migration_error'
    CONFIG_INVALID = 'config_invalid'
    CONTRIBUTES_INVALID = 'contributes_invalid'
    DEPENDENCY_CONFLICT = 'dependency_conflict'
    PACKAGE_INTEGRITY_ERROR = 'package_integrity_error'
    ENV_BUILD_FAILED = 'env_build_failed'

@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: ErrorCode
    message: str
    remediation: Optional[str] = None
    source_task: Optional[str] = None

    def with_fallback_task(self, task_id: str) -> ErrorDetail:
        ...

    def raise_as_exception(self) -> NoReturn:
        ...

class EventCycleError(YscbError):

    def __init__(self, message: str, *, remediation: Optional[str]=None, source_task: Optional[str]=None) -> None:
        ...

@dataclass(frozen=True, slots=True)
class EventId:
    value: str

    @property
    def module_id(self) -> ModuleId:
        ...

    def __str__(self) -> str:
        ...

@dataclass(frozen=True, slots=True)
class HostPath:
    path: Path
    comparison_key: str

    def __init__(self, raw: str | os.PathLike[str] | Path) -> None:
        ...

    def join(self, *parts: str) -> HostPath:
        ...

    def resolve_caller_relative(self, target: str | os.PathLike[str]) -> HostPath:
        ...

    def __str__(self) -> str:
        ...

    def __eq__(self, other: object) -> bool:
        ...

    def __hash__(self) -> int:
        ...

class LocaleCatalog:

    def __init__(self, dictionaries_by_module: Mapping[ModuleId, Mapping[str, Mapping[str, str]]], *, default_chain: Sequence[str]=('zh',)) -> None:
        ...

    def translate(self, key: str, *, caller_module: Optional[ModuleId]=None, chain: Optional[Sequence[str]]=None, params: Optional[Mapping[str, object]]=None) -> str:
        ...

class LogLevel(Enum):
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'

@dataclass(frozen=True, slots=True)
class LogRecord:
    ts_utc: str
    level: LogLevel
    logger_name: str
    message: str
    fields: JsonObject = field(default_factory=dict)

class LogRotator:

    def __init__(self, log_path: HostPath, *, max_bytes: int=524288, max_lines: Optional[int]=None, keep_lines: Optional[int]=None, max_history_files: int=5) -> None:
        ...

    def append_line(self, line: str) -> None:
        ...

    def append_jsonl(self, payload: JsonObject) -> None:
        ...

    def read_tail_lines(self, limit: int=100) -> tuple[str, ...]:
        ...

    def read_jsonl(self, *, limit: Optional[int]=None) -> tuple[MutableJsonObject, ...]:
        ...

    def close(self) -> None:
        ...

class ManagedProcessTree:

    def __init__(self, argv: Sequence[str], *, cwd: HostPath, env: Optional[Mapping[str, str]]=None, inherit_tty: bool=False) -> None:
        ...

    def __enter__(self) -> ManagedProcessTree:
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

    @property
    def pid(self) -> int:
        ...

    def snapshot_descendants(self) -> None:
        ...

    def peek_alive(self) -> bool:
        ...

    def poll(self) -> Optional[int]:
        ...

    def terminate_tree(self, *, grace_sec: float=0.5) -> None:
        ...

    def kill_tree_now(self) -> None:
        ...

@dataclass(frozen=True, slots=True)
class ModuleId:
    value: str

    def __str__(self) -> str:
        ...

@dataclass(frozen=True, slots=True)
class ProgressEvent:
    phase: str
    completed: int
    total: int
    message: str = ''

class SchemaExporter:

    @staticmethod
    def export(target_cls: type[object], *, title: Optional[str]=None) -> MutableJsonObject:
        ...

@dataclass(frozen=True, slots=True)
class SemVer4:
    major: int
    minor: int
    patch: int
    revision: int = 0
    is_build: bool = False
    prerelease: str = ''

    @classmethod
    def parse(cls, raw: str) -> SemVer4:
        ...

    def triple(self) -> tuple[int, ...]:
        ...

    def compare_precedence(self, other: SemVer4) -> int:
        ...

    def __lt__(self, other: SemVer4) -> bool:
        ...

    def __le__(self, other: SemVer4) -> bool:
        ...

    def __gt__(self, other: SemVer4) -> bool:
        ...

    def __ge__(self, other: SemVer4) -> bool:
        ...

    def __str__(self) -> str:
        ...

@dataclass(frozen=True, slots=True)
class SemanticUri:
    scheme: str
    rel_path: str = ''

    @classmethod
    def parse(cls, raw: str) -> SemanticUri:
        ...

    @property
    def uses_module_placeholder(self) -> bool:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def suffix(self) -> str:
        ...

    @property
    def parent(self) -> Optional[SemanticUri]:
        ...

    def bind_module(self, module_id: ModuleId) -> SemanticUri:
        ...

    def join(self, *parts: str) -> SemanticUri:
        ...

    def __truediv__(self, part: str) -> SemanticUri:
        ...

    def __str__(self) -> str:
        ...

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
    error_hint: str = ''

class SessionTelemetryWriter:

    def __init__(self, rotator: LogRotator, *, enabled: bool=True, env: Optional[Mapping[str, str]]=None) -> None:
        ...

    def record(self, entry: SessionTelemetryRecord) -> None:
        ...

    def read_recent(self, limit: int=100) -> tuple[SessionTelemetryRecord, ...]:
        ...

class SignalWakeupGuard:

    def __init__(self, sig_nums: Sequence[int], on_signal: Callable[[], None], *, on_second_signal: Optional[Callable[[], None]]=None) -> None:
        ...

    def __enter__(self) -> SignalWakeupGuard:
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

    def install(self) -> None:
        ...

    def close(self) -> None:
        ...

@dataclass(frozen=True, slots=True)
class SnapshotGen:
    value: int

    def next(self) -> SnapshotGen:
        ...

    def __lt__(self, other: SnapshotGen) -> bool:
        ...

    def __le__(self, other: SnapshotGen) -> bool:
        ...

@dataclass(frozen=True, slots=True)
class SpaceId:
    owner: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> SpaceId:
        ...

    @property
    def is_synthetic(self) -> bool:
        ...

    def __str__(self) -> str:
        ...

@dataclass(frozen=True, slots=True)
class SpacePath:
    rel_path: str

    @classmethod
    def parse(cls, raw: str) -> SpacePath:
        ...

    def __str__(self) -> str:
        ...

class StructuredLogger(Protocol):

    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject]=None) -> None:
        ...

    def debug(self, message: str, *, fields: Optional[JsonObject]=None) -> None:
        ...

    def info(self, message: str, *, fields: Optional[JsonObject]=None) -> None:
        ...

    def warning(self, message: str, *, fields: Optional[JsonObject]=None) -> None:
        ...

    def error(self, message: str, *, fields: Optional[JsonObject]=None) -> None:
        ...

class TaskCancelledException(YscbError):

    def __init__(self, message: str='Task execution cancelled.', *, preempted: bool=False, remediation: Optional[str]=None, source_task: Optional[str]=None) -> None:
        ...

@dataclass(frozen=True, slots=True)
class TaskId:
    value: str

    @property
    def module_id(self) -> ModuleId:
        ...

    def __str__(self) -> str:
        ...

@dataclass(frozen=True, slots=True)
class VersionConstraint:
    raw: str

    @classmethod
    def parse(cls, raw: str) -> VersionConstraint:
        ...

    @classmethod
    def compatible_same_major(cls, ver: SemVer4) -> VersionConstraint:
        ...

    def satisfies(self, ver: SemVer4) -> bool:
        ...

    def __str__(self) -> str:
        ...

class YscbError(Exception):

    def __init__(self, code: ErrorCode, message: str, *, remediation: Optional[str]=None, source_task: Optional[str]=None) -> None:
        ...
```

---

## 3. OS 環境變數與系統常數命名憲法（Env & Constant Naming Constitution）

為避免隨 Wave 1.2（`cli` / `config` / `packaging` / `dev 2.0`）擴張造成 OS 環境變數與魔術旗標混雜，全生態系統一遵守以下三條命名與存取邊界（後續納入 `Gate 0` / `dev check 2.0` 靜態守門）：

| 分類 | 命名慣例 | 語意定位與存取規範 |
| :--- | :--- | :--- |
| **公開環境覆寫旗標** | `YSCB_*`（無前導底線） | **僅限使用者或 CI 在讀取組態前需要生效之極少數覆寫開關**（如停用常駐、除錯日誌層級，見 `PUBLIC_ENV_ALLOWLIST`）。須集中登記於受控清冊，未登記者禁止任意 `os.environ.get()`；一般業務開關一律優先走 `config` 或強型別 `Enum`。 |
| **內核／工具私有變數** | `_YSCB_*`（前導底線） | **僅供內核與工具鏈跨進程傳遞之內部訊號、憑證或沙盒標記**（如 `_YSCB_TREE_ID`、`_YSCB_WORKER_AUTH_TOKEN`、`_YSCB_TEST_SANDBOX`、`_YSCB_HOST_DIR`、`_YSCB_ROOT_DIR`）。`sanitize_caller_env` 依 `PRIVATE_ENV_PREFIX`（`"_YSCB_"`）前綴整批封殺外部注入。 |
| **模組常數與上限門檻** | `_UPPER_CASE` / `Final[...]` | 單檔內部調校門檻維持 `_UPPER_CASE` 私有；跨檔共享之協定、系統目錄／檔名與保留識別符須顯式宣告 `Final[...]` 並收錄於所屬功能域 Living Spec。 |

---

## 4. Wave 1.2 核心值物件與觀測引擎行為不變量

1. **`SemVer4` 與 `VersionConstraint`（承襲 1.x `SEMVER.md`）**：
   - 三段輸入（`"1.2.3"`）自動正規化為 `SemVer4(1, 2, 3, 0)`；`"1.2.3.build"` 設 `is_build=True, revision=0`；數值 `revision` 優先於 `.build`（`1.2.3.0 > 1.2.3.build`）；正式版優先於預發佈版（`1.2.3.0 > 1.2.3.0-beta.1`）。
   - `^X.Y.Z` 與 `~=X.Y.Z` 鎖定同 Major（`>=X.Y.Z.0, <(X+1).0.0.0`），數值型 `revision` 不破壞同 `(major, minor, patch)` 相容性。
2. **`SemanticUri` 與 `DataclassCodec` 雙向對稱**：
   - 強制顯式 `scheme://`（無隱式預設協議），逐區段經 `validate_relative_segment` 校驗（僅首段允許 `@` 代表模組自省並由 `bind_module` 展開）。
   - `DataclassCodec` 原生支援 `SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash` 雙向編解碼。
3. **`SchemaExporter`、`LogRotator` 與 `LocaleCatalog`**：
   - `SchemaExporter` 輸出標準 JSON Schema Draft 2020-12（`$defs`、物件預設 `additionalProperties: False`、`Annotated` 描述萃取）。
   - `LogRotator` 強制以 `\n` 切行（避免 `\u2028`/`\u2029` 破壞 JSONL）、設定 `os.set_inheritable(fd, False)` 並以同目錄原子 `os.replace` 輪替。
   - `LocaleCatalog.translate` 嚴格依顯式語系鏈查找（零隱式父語系猜測），`{placeholder}` 遞迴解析深度上限為 `5`（防環不崩潰）並支援 `{{` / `}}` 轉義。
