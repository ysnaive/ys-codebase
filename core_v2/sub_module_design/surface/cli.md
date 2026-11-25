# 子模組架構設計規格：`core.surface.cli`（靜態索引零匯入命令列、1.x 成熟 Help 引擎與 4×3 安全守門）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/cli/`
> **建議內部切分**：`index.py`、`caller_mode.py`、`approval.py`、`parser.py`、`help_renderer.py`、`entrypoint.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`Domain 1 ~ 5`、`surface.sdk`
> **禁止反向依賴（Forbidden Imports）**：冷啟動 `--help`、拼寫建議與參數預驗階段嚴禁匯入任何 `module://` 業務源碼
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

> [!NOTE]
> **實作彈性邊界**：`tasks.index.json` 檔案 Schema、`CallerMode` 5 層環境分類、4×3 安全矩陣、兩段式單次 `--approve=<token>` 協議、全域統一旗標（`--help`/`-h`/`--json`/`--cold`/`--approve`/`--profile`/`--profile-mem`）與 1.x `HelpRenderer` 輸出特性屬硬契約；內部詞法解析器與排版輔助函式可由實作端微調。

---

## 1. 模組定位與核心目標

`core.surface.cli` 為 Domain 6 面向終端機之統一命令列轉接層，實現：
1. **零匯入毫秒級靜態路由與自省**：直讀隨包 `.modules/<mod>/tasks.index.json`（並由 `.cache/tasks.index.json` 聚合加速），於 `< 10ms` 內完成指令樹解析、正交選項衝突驗證、`-h` 說明卡片渲染與 `Did you mean` 拼寫建議，全程零載入任何業務模組 Python 代碼（對 Tier 1 模組尤為關鍵）。
2. **100% 承繼 1.x 成熟 `HelpRenderer` 體驗**：保留安全分級標籤、`ARGUMENTS`（含 choice 枚舉提示）、正交 `OPTIONS` 群組互斥標記、`RECOMMENDED USAGE (Pros)`、`RESTRICTIONS & GATES (Cons)`、模組別名、群組預設動作（`DN-13`）與模糊拼寫建議。
3. **5 層 `CallerMode` 運行環境辨識 + 4×3 安全守門**：解決 AI Agent 跑在 PTY 時 `isatty() == True` 誤判問題，並以兩段式單次確認碼 `--approve=<token>` 徹底根除 Compact 後的 `-y` 記憶慣性風險。
4. **雙軌輸出與非阻塞可觀測整合**：支援人類排版（`format_output`）與嚴格 `--json`（`TaskOutcome`），於入口／出口作為單一寫手寫入 `FlightLogRouter`（3+1 JSONL 飛航日誌）與根 `ProfilerSession`（`--profile`／`--profile-mem` 僅輸出 ImTK 樹至 `stderr`），並整合非阻塞 12 小時 `UpdateChecker`（`--json` / 沙盒 / 離線時自動靜音）。

---

## 2. `tasks.index.json` 靜態索引契約（由 `core` 統一編譯）

編譯函式 `compile_tasks_index(module_cls)` 歸屬 `core`（`dev build` 僅作為薄呼叫端產出隨包 `.modules/<mod>/tasks.index.json`）。工作區聚合檔 `.cache/tasks.index.json` 以各已安裝模組 `tasks.index.json` 之 `(mtime_ns, size)` 指紋為鍵按需自動重建。

```json
{
  "schema_version": 2,
  "module_id": "core",
  "module_aliases": [],
  "description": "YS-Codebase Core Microkernel",
  "tasks": [
    {
      "task_id": "core.remove",
      "command_path": ["remove"],
      "aliases": ["rm"],
      "summary": "Uninstall module(s) while preserving config and storage",
      "usage_pros": ["移除不再使用之擴充模組"],
      "usage_cons": ["若欲連同設定與資料永久清除，請改由人類終端執行 critical 指令 yscb purge"],
      "exposure": "cli_and_sdk",
      "security_tier": "gated",
      "dispatch_mode": "cold_only",
      "interactive_tty": false,
      "args": [
        {"field": "modules", "name": "module", "type": "list[str]", "required": true, "summary": "Target module ID(s)"}
      ],
      "options": [
        {"field": "clean", "long_name": "clean", "short": null, "type": "bool", "required": false, "default": false, "group": null, "choices": null, "summary": "Also clear cache:// and storage.local://"},
        {"field": "force", "long_name": "force", "short": "f", "type": "bool", "required": false, "default": false, "group": null, "choices": null, "summary": "Force removal"}
      ],
      "subscriptions": [],
      "periodic": null
    }
  ]
}
```

### CLI DTO 解析與綁定規則
1. 標註 `Arg` 之位置欄位依宣告順序消耗位置參數；尾端帶 `Arg` 之 `Sequence[T]` 接收可變長位置參數。
2. 標註 `Option` 之具名欄位綁定 `--<long_name>`（預設轉 kebab-case）與選配 `-<short>`；純量 `bool` 欄位映射為 `--flag` / `--no-flag`（亦相容 `--flag=true|false`）；`Enum` / `Literal` 欄位自動轉為 `choices` 並在錯誤時報 `InvalidChoice`。
3. **正交群組互斥（承繼 1.x `OptionResolver`）**：同一 `Option.group`（非 `None`）下若同時傳入 2 個以上選項，於解析階段立即拒絕並列出衝突選項。
4. **群組無參數預設動作 vs 未知子命令（承繼 `DN-13`）**：若群組節點自身綁定預設任務（如 `plan` $\to$ `plan status`），無剩餘參數時執行該預設任務；但若傳入未知子命令且該預設任務不接受位置參數，強制阻斷並以 `difflib.get_close_matches` 輸出 `Did you mean '<cmd>'?`。

---

## 3. 5 層 `CallerMode` 環境辨識與 4×3 安全守門矩陣

### 3.1 `CallerMode` 確定性 5 層分類（高優先覆蓋低優先）
| 優先序 | 判定條件 | 判定結果 (`CallerMode`) |
| :---: | :--- | :--- |
| **1** | 環境變數 `YSCB_CALLER_MODE`（`agent` / `ci` / `non_tty` / `human`）；僅當真實雙向 TTY 且**無任何活躍 AI Agent 或 CI 標記**時才放行 `human`（嚴禁 Agent／CI 於 PTY 下自我降級）；`ci` 顯式覆寫保留最高權 | 顯式模式（受 TTY 與防降級守衛約束） |
| **2** | 命中精準 AI Agent 活躍 Session 鍵（`ANTIGRAVITY_AGENT`、`ANTIGRAVITY_CONVERSATION_ID`、`ANTIGRAVITY_TRAJECTORY_ID`、`ANTIGRAVITY_SESSION`、`AGY_AGENT`、`AGY_SESSION`、`CLAUDECODE`、`CLAUDE_CODE_ENTRYPOINT`、`CLAUDE_CODE_SESSION_ID`、`CLAUDE_CODE_SSE_PORT`、`CODEX_SANDBOX`、`CODEX_THREAD_ID`、`CODEX_CI`、`AIDER_SESSION`、`CURSOR_AGENT`、`WINDSURF_AGENT`、`GEMINI_CLI`、`OPENCODE`，以及 `config://core` 擴充之 `security.agent_env_prefixes`）——**優先於 `CI` 與 `isatty()`**，不誤判人類組態鍵（如 `CLAUDE_CODE_USE_VERTEX`、`CODEX_HOME`、`AIDER_MODEL`） | `AGENT` |
| **3** | 命中標準 CI 環境變數（`CI`、`GITHUB_ACTIONS`、`GITLAB_CI`、`JENKINS_URL`、`TF_BUILD`、`BUILDKITE`、`CIRCLECI`、`TRAVIS`、`BITBUCKET_BUILD_NUMBER`） | `CI_PIPELINE` |
| **4** | `not stdin.isatty()` 或 `not stdout.isatty()` 或 `TERM == "dumb"` | `NON_TTY` |
| **5** | 其餘條件（真實雙向互動終端且無 Agent／CI 標記） | `HUMAN_TTY` |

> `CallerMode` 偵測器同步為 `LocaleCatalog` 提供 AI 宿主 Dialect 辨識（如 `ANTIGRAVITY_AGENT`/`ANTIGRAVITY_SESSION` $\to$ `nouns-antigravity`、`CLAUDECODE`/`CLAUDE_CODE_SESSION_ID` $\to$ `nouns-claude`、`CODEX_SANDBOX`/`CODEX_THREAD_ID` $\to$ `nouns-codex`），全系統單一真理來源。


### 3.2 4×3 安全守門矩陣（`SecurityTier` × `CallerMode`）
| `SecurityTier` | `HUMAN_TTY` | `AGENT` / `NON_TTY` | `CI_PIPELINE` |
| :---: | :--- | :--- | :--- |
| **`SAFE`** | 直接執行 | 直接執行 | 直接執行 |
| **`CONDITIONAL`** | 直接執行 | 前景本倉直接執行 | 前景本倉直接執行 |
| **`GATED`** | 印出影響摘要 + 互動 `[y/N]` 確認，同意後簽發 `approval_scope` | **嚴禁靜態 `-y`！** 強制兩段式單次確認碼 `--approve=<token>`（見 §3.3） | 預設阻斷；僅當命中 `CI_PIPELINE` 且組態或 `YSCB_CI_APPROVE_GATED=1` 顯式授權時放行（或走 `--approve`） |
| **`CRITICAL`** | 印出醒目警告 + **要求輸入明確確認詞**（如目標模組名或 `CONFIRM`，Enter 預設取消） | **一律硬阻斷**（不簽發 `--approve` 碼，提示交由開發者於人類終端親自執行） | **預設一律硬阻斷**（防 CI 腳本誤刪永久資料） |

### 3.3 兩段式單次確認碼協議（`ApprovalTokenStore`，防 Compact `-y` 記憶慣性）
1. 當 `AGENT` 或 `NON_TTY` 呼叫 `SecurityTier.GATED` 任務且未攜帶有效 `--approve=<token>` 時：
   - 計算本次請求正規化指紋：`args_hash = SHA-256(canonical_json({task_id, normalized_input}))`。
   - 產生 6~8 碼隨機十六進位單次權杖 `token`，原子寫入 `cache://core/pending_approvals.json`（記錄 `token`、`task_id`、`args_hash`、`expires_at_epoch = now + 300.0`，並順手清理過期條目）。
   - 立即以非零退出碼退出並輸出結構化 `ErrorCode.SECURITY_GATED` 錯誤與警語：明確列出本次操作影響摘要，指示 Agent **先向開發者請示取得當次授權**，獲准後帶 `--approve=<token>` 單行重跑。
2. 當再次帶入 `--approve=<token>` 執行時：
   - 驗證 `token` 存在、未過期且 `(task_id, args_hash)` 100% 一致；驗證通過後**立即自 `pending_approvals.json` 刪除該權杖（用過即焚）**，將 `task_id` 寫入 `InvokeRequest.approval_scope` 放行至 `RuntimeDispatcher`。
   - 若組態設定 `security.allow_noninteractive_approve = false`，則 `AGENT`/`NON_TTY` 連確認碼亦不簽發，全面退回人類終端執行。

---

## 4. 統一入口旗標、1.x `HelpRenderer` 特性與出口管線

### 4.1 全域統一保留旗標
| 旗標 | 行為說明 |
| :--- | :--- |
| `--help` / `-h` | 零匯入業務源碼，依 `tasks.index.json` 渲染完整 1.x 風格幫助卡並以退出碼 `0` 結束 |
| `--json` | 強制於 `stdout` 輸出嚴格單一 JSON 物件（編碼自 `TaskOutcome`），壓制人類排版與更新提示；退出碼仍依 `ExitCodeProvider` 或錯誤碼映射 |
| `--cold` | 注入 `ClientRoutingPolicy.FORCE_COLD` 強制本地冷派發 |
| `--approve=<token>` | 消費 `ApprovalTokenStore` 單次確認碼以授權單次 `GATED` 任務 |
| `--profile` | 強制於 `stderr` 輸出 ImTK 風格跨進程耗時瀑布樹（絕不污染 `stdout` / `--json`） |
| `--profile-mem` | 啟用 `tracemalloc` 記憶體配置追蹤（同 `YSCB_PROFILE_MEM=1`），並於 `stderr` 輸出含記憶體欄之瀑布樹 |

### 4.2 1.x 成熟 `HelpRenderer` 必備特性（100% 攜帶至 2.0）
- **頂部標頭**：完整命令路徑、任務摘要、`Security : [SAFE] / [CONDITIONAL] / [GATED] / [CRITICAL]`、`Dispatch : [HYBRID] / [COLD_ONLY] / [DAEMON_ONLY]`。
- **`ARGUMENTS` 區塊**：標示 `<required>` / `[optional]`、`choices` 枚舉（`<mode=[auto | safe]>`）與說明。
- **`OPTIONS` 區塊**：按 `Option.group` 分組渲染，標註同組互斥規則、短/長旗標別名（`-f, --force`）、型別、預設值與 `choices`。
- **`RECOMMENDED USAGE (Pros)` & `RESTRICTIONS & GATES (Cons)`**：直接渲染 `@task(usage_pros=..., usage_cons=...)`。
- **子命令與別名**：頂層與群組 `-h` 列出子命令摘要表與 `aliases`；`CallerMode.AGENT` / `NON_TTY` 採純 ASCII 精簡排版節約 Token，`HUMAN_TTY` 採對齊視覺排版。

### 4.3 執行與出口管線
```text
argv -> CallerMode 5 層分類 -> 萃取全域旗標 (--help / --json / --cold / --approve / --profile / --profile-mem)
     -> 零匯入載入 tasks.index.json (核對指紋自動重建 .cache/tasks.index.json)
     -> 解析 command_path / 群組預設動作 / 拼寫建議 / DTO 參數與互斥檢核
     -> 依 4×3 安全矩陣執行授權守門 (TTY 互動確認 或 --approve 單次確認碼)
     -> 開啟根 ProfilerSession 與 FlightLogRouter，寫入 daily/[IN]
     -> 組裝 InvokeRequest(caller_surface=CallerSurface.CLI, external_flight_owner=True, active_profiler=root_profiler, ...) -> RuntimeDispatcher.invoke()
     -> 雙軌渲染 (--json 或 format_output) + stderr 進度串流
     -> 寫入 daily/[OUT] 與 perf/ 合併後 ExecutionTraceRecord (沙盒 / --help / 未初始化工作區略過)；--profile/--profile-mem 輸出瀑布樹至 stderr
     -> 若非 --json / 非沙盒 / 非離線：檢查 UpdateChecker 12h 節流並輸出非阻塞更新提示至 stderr
     -> 以語意退出碼 (0 / ExitCodeProvider / ErrorCode 映射，取消為 130) 結束
```

---

## 5. 公開契約與門面簽名（1:1 Parity）

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
from core.execution.event import normalize_payload_filter
from core.execution.rpc import read_daemon_endpoint_file
from core.execution.runtime import BoundTask, CORE_MODULE_ID, CallPropagationContext, CallerSurface, CliBindingSpec, ClientRoutingPolicy, ConcurrencyMode, DEFAULT_CACHE_DIRNAME, DispatchMode, InvokeRequest, LOCKS_SUBDIR, MODULES_DIRNAME, PeriodicScheduleSpec, RuntimeDispatcher, SecurityTier, SelfMutationScope, SubscriptionRouteSpec, TaskExposure, TaskMetadata, TaskOutcome, TaskRouteSpec, YscbModule, sanitize_caller_env
from core.filesystem.fs import FileLock, MAX_JSON_FILE_BYTES, atomic_write_json, has_symlink_raw_path, is_symlink_or_reparse, read_json_dict, read_nofollow_regular_bytes, resolve_contained_subpath, try_resolve_contained_subpath
from core.foundation import CancellationToken, DailyEventRecord, DataclassCodec, EnvHash, ErrorCode, ErrorDetail, EventId, ExecutionTraceRecord, FlightLogConfig, FlightLogRouter, HostPath, INT64_MAX, INT64_MIN, JsonObject, JsonPrimitive, JsonValue, LogLevel, MemoryTrackingGuard, ModuleId, MutableJsonObject, ProfilerNodeSnapshot, ProfilerSession, SemVer4, SemanticUri, SignalWakeupGuard, SnapshotGen, SpaceId, SpacePath, TEST_SANDBOX_ENV_KEY, TaskId, VersionConstraint, YscbError, clamp_positive_sec, clone_strict_json_object, guard_standard_streams, read_process_rss_kb, redact_cli_args, redact_sensitive_value, render_profiler_tree, require_pure_bool, require_pure_int, require_pure_str, require_typed_frozenset, require_typed_tuple, resolve_dataclass_init_hints, safe_exception_summary, safe_real_to_float, strict_parse_json_object
from core.metadata.config import ConfigStore, lookup_compiled_module_root_default_tasks, lookup_compiled_module_surface_meta, parse_locale_chain_tokens
from core.packaging.installer import ProviderClient, UpdateCheckReport, UpdateChecker
from core.surface.sdk import Arg, Empty, ExitCodeProvider, HumanRenderable, Module, Option, format_output
CLI_DEFAULT_PROVIDER_URL: Final[str] = 'https://raw.githubusercontent.com/ysnaive/ys-codebase/releases'
CLI_DEFAULT_SELF_UPDATE_URL: Final[str] = 'https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py'
CliKernelFactoryFn = Callable[[HostPath, HostPath, bool], CliKernelSession]
TASKS_INDEX_SCHEMA_VERSION: Final[int] = 2

def build_cli_command_tree(indices: Sequence[ModuleTasksIndex]) -> CliCommandNode:
    ...

def compile_tasks_index(module_source: type[Module] | Module | YscbModule) -> ModuleTasksIndex:
    ...

def compute_approval_args_hash(task_id: TaskId, normalized_input: JsonObject) -> str:
    ...

def detect_caller_environment(*, env: Optional[Mapping[str, str]]=None, stdin_stream: Optional[CliInputStream]=None, stdout_stream: Optional[CliOutputStream]=None, extra_agent_env_prefixes: Sequence[str]=()) -> CallerEnvironment:
    ...

def detect_caller_mode(*, env: Optional[Mapping[str, str]]=None, stdin_stream: Optional[CliInputStream]=None, stdout_stream: Optional[CliOutputStream]=None, extra_agent_env_prefixes: Sequence[str]=()) -> CallerMode:
    ...

def evaluate_security_gate(*, task_id: TaskId, security_tier: SecurityTier, caller_mode: CallerMode, normalized_input: JsonObject, summary: str, token_store: ApprovalTokenStore, approve_token: Optional[str]=None, allow_noninteractive_approve: bool=True, ci_approve_gated: bool=False, stdin_stream: Optional[CliInputStream]=None, stderr_stream: Optional[CliOutputStream]=None) -> SecurityGateResult:
    ...

def extract_global_flags(argv: Sequence[str]) -> GlobalCliFlags:
    ...

def main(argv: Sequence[str], *, host_dir: HostPath, yscb_root: HostPath, caller_cwd: Optional[HostPath]=None, env: Optional[Mapping[str, str]]=None, stdin_stream: Optional[CliInputStream]=None, stdout_stream: Optional[CliOutputStream]=None, stderr_stream: Optional[CliOutputStream]=None, kernel_factory: Optional[CliKernelFactoryFn]=None, builtin_indices: Optional[Sequence[ModuleTasksIndex]]=None, install_signal_guard: bool=True, boot_start_ns: Optional[int]=None) -> int:
    ...

def register_cli_kernel_factory(factory: Optional[CliKernelFactoryFn], *, builtin_indices_fn: Optional[Callable[[], Sequence[ModuleTasksIndex]]]=None) -> None:
    ...

def render_task_help(task_entry: IndexedTaskEntry, *, caller_mode: CallerMode=CallerMode.HUMAN_TTY, module_prefix: Optional[str]=None) -> str:
    ...

def resolve_cli_invocation(flags: GlobalCliFlags, indices: Sequence[ModuleTasksIndex]) -> CliRouteResolution:
    ...

class ApprovalTokenStore:

    def __init__(self, cache_dir: HostPath, *, ttl_sec: float=...) -> None:
        ...

    def issue_token(self, task_id: TaskId, normalized_input: JsonObject, *, summary: str='', now_epoch: Optional[float]=None) -> PendingApprovalRecord:
        ...

    def consume_token(self, token: str, task_id: TaskId, normalized_input: JsonObject, *, now_epoch: Optional[float]=None) -> PendingApprovalRecord:
        ...

@dataclass(frozen=True, slots=True)
class CallerEnvironment:
    mode: CallerMode
    dialect: Optional[str] = None
    stdin_isatty: bool = False
    stdout_isatty: bool = False

class CallerMode(Enum):
    HUMAN_TTY = 'human'
    NON_TTY = 'non_tty'
    AGENT = 'agent'
    CI_PIPELINE = 'ci'

@dataclass(frozen=True, slots=True)
class CliArgSpec:
    field: str
    name: str
    type_name: str
    required: bool
    summary: str = ''
    choices: Optional[tuple[str, ...]] = None
    default: JsonValue = None

    @property
    def is_variadic(self) -> bool:
        ...

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliArgSpec:
        ...

@dataclass(slots=True)
class CliCommandNode:
    canonical_path: tuple[str, ...]
    summary: str = ''
    aliases: tuple[str, ...] = ()
    owner_module: Optional[ModuleId] = None
    default_task: Optional[IndexedTaskEntry] = None
    children: dict[str, CliCommandNode] = field(default_factory=dict)
    alias_to_child: dict[str, str] = field(default_factory=dict)

class CliInputStream(Protocol):

    def isatty(self) -> bool:
        ...

    def readline(self) -> str:
        ...

class CliKernelSession(Protocol):

    @property
    def dispatcher(self) -> RuntimeDispatcher:
        ...

    @property
    def config_store(self) -> Optional[ConfigStore]:
        ...

    def apply_caller_dialect(self, dialect: Optional[str], raw_env_locale: Optional[str]=None) -> None:
        ...

    def resolve_task_output_type(self, task_id: TaskId) -> Optional[object]:
        ...

    def resolve_task_presentation(self, task_entry: IndexedTaskEntry, raw_value: JsonValue, *, render_human: bool) -> tuple[Optional[str], Optional[int]]:
        ...

    def has_deferred_daemon(self) -> bool:
        ...

    def run_deferred_daemon(self, *, on_ready: Optional[Callable[[], None]]=None) -> tuple[bool, int]:
        ...

    def consume_post_close_exit_code(self) -> Optional[int]:
        ...

    def close(self) -> None:
        ...

@dataclass(frozen=True, slots=True)
class CliOptionSpec:
    field: str
    long_name: str
    short: Optional[str]
    type_name: str
    required: bool
    default: JsonValue = None
    group: Optional[str] = None
    choices: Optional[tuple[str, ...]] = None
    summary: str = ''

    @property
    def is_multi(self) -> bool:
        ...

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliOptionSpec:
        ...

class CliOutputStream(Protocol):

    def isatty(self) -> bool:
        ...

    def write(self, s: str) -> object:
        ...

    def flush(self) -> None:
        ...

class CliRouteKind(Enum):
    HELP = 'help'
    TASK = 'task'

@dataclass(frozen=True, slots=True)
class CliRouteResolution:
    kind: CliRouteKind
    node: CliCommandNode
    task_entry: Optional[IndexedTaskEntry] = None
    normalized_input: JsonObject = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class CliSubscriptionSpec:
    event_id: EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliSubscriptionSpec:
        ...

@dataclass(frozen=True, slots=True)
class GlobalCliFlags:
    help_requested: bool = False
    json_output: bool = False
    force_cold: bool = False
    approve_token: Optional[str] = None
    remaining_args: tuple[str, ...] = ()
    profile: bool = False
    profile_mem: bool = False

class HelpRenderer:

    def __init__(self, caller_mode: CallerMode=CallerMode.HUMAN_TTY) -> None:
        ...

    @property
    def compact_mode(self) -> bool:
        ...

    def render_node(self, node: CliCommandNode) -> str:
        ...

@dataclass(frozen=True, slots=True)
class IndexedTaskEntry:
    task_id: TaskId
    command_path: tuple[str, ...]
    aliases: tuple[str, ...]
    summary: str
    usage_pros: tuple[str, ...]
    usage_cons: tuple[str, ...]
    exposure: TaskExposure
    security_tier: SecurityTier
    dispatch_mode: DispatchMode
    interactive_tty: bool
    args: tuple[CliArgSpec, ...] = ()
    options: tuple[CliOptionSpec, ...] = ()
    subscriptions: tuple[CliSubscriptionSpec, ...] = ()
    periodic: Optional[PeriodicScheduleSpec] = None
    mutation_scope: SelfMutationScope = SelfMutationScope.NONE
    resource_key: Optional[str] = None
    concurrency_mode: ConcurrencyMode = ConcurrencyMode.PARALLEL
    timeout_ms: Optional[int] = None
    void_output: bool = False
    custom_render: bool = False
    custom_exit_code: bool = False

    def to_route_spec(self) -> TaskRouteSpec:
        ...

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> IndexedTaskEntry:
        ...

@dataclass(frozen=True, slots=True)
class ModuleTasksIndex:
    module_id: ModuleId
    module_aliases: tuple[str, ...] = ()
    description: str = ''
    tasks: tuple[IndexedTaskEntry, ...] = ()
    schema_version: int = TASKS_INDEX_SCHEMA_VERSION

    def to_route_specs(self) -> tuple[TaskRouteSpec, ...]:
        ...

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> ModuleTasksIndex:
        ...

@dataclass(frozen=True, slots=True)
class PendingApprovalRecord:
    token: str
    task_id: TaskId
    args_hash: str
    expires_at_epoch: float
    summary: str = ''

    def to_json_dict(self) -> JsonObject:
        ...

    @classmethod
    def try_from_json(cls, doc: object) -> Optional[PendingApprovalRecord]:
        ...

@dataclass(frozen=True, slots=True)
class SecurityGateResult:
    approval_scope: frozenset[TaskId] = frozenset()

class WorkspaceTasksIndexCache:

    def __init__(self, yscb_root: HostPath, *, builtin_indices: Sequence[ModuleTasksIndex]=()) -> None:
        ...

    def load_all(self, *, force_rebuild: bool=False) -> tuple[ModuleTasksIndex, ...]:
        ...
__all__: tuple[str, ...] = ('ApprovalTokenStore', 'CLI_DEFAULT_PROVIDER_URL', 'CLI_DEFAULT_SELF_UPDATE_URL', 'CallerEnvironment', 'CallerMode', 'CliArgSpec', 'CliCommandNode', 'CliInputStream', 'CliKernelFactoryFn', 'CliKernelSession', 'CliOptionSpec', 'CliOutputStream', 'CliRouteKind', 'CliRouteResolution', 'CliSubscriptionSpec', 'GlobalCliFlags', 'HelpRenderer', 'IndexedTaskEntry', 'ModuleTasksIndex', 'PendingApprovalRecord', 'SecurityGateResult', 'TASKS_INDEX_SCHEMA_VERSION', 'WorkspaceTasksIndexCache', 'build_cli_command_tree', 'compile_tasks_index', 'compute_approval_args_hash', 'detect_caller_environment', 'detect_caller_mode', 'evaluate_security_gate', 'extract_global_flags', 'main', 'register_cli_kernel_factory', 'render_task_help', 'resolve_cli_invocation')
```

---

## 6. 必測驗收門檻 (Verification Gate)

1. **零匯入冷自省驗證**：於測試中攔截所有非 `core` 模組 `import`，驗證 `yscb --help`、`yscb <mod> -h`、未知指令拼寫建議與非法參數報錯全程零匯入任何業務模組。
2. **1.x `HelpRenderer` 完整對齊**：驗證 `Security` 標籤、正交互斥群組碰撞報錯、`Pros`/`Cons` 區塊、群組預設動作（`DN-13`）與 `Did you mean` 建議。
3. **`CallerMode` 與 4×3 安全矩陣**：模擬 PTY（`isatty=True`）搭配 `ANTIGRAVITY_SESSION=1` / `CLAUDECODE=1` 必判為 `AGENT` 而絕不呼叫 `input()`；模擬 `GATED` 兩段式 `--approve=<tok>` 正常放行、重放第二次失敗（用過即焚）、改參數 `args_hash` 不符失敗、過期失敗；`CRITICAL` 於 `AGENT` / `NON_TTY` / `CI_PIPELINE` 一律硬阻斷。
4. **`--json` 純淨度**：驗證 `--json` 模式下 `stdout` 100% 為合法單一 JSON，進度事件與更新提示絕不污染 `stdout`。
