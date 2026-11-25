# 子模組架構設計規格：頂層組裝根（`core.surface.bootstrap`）、內建系統管理 `Task` 與 `core_v2/yscb.py`

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)` + 宿主入口 `core_v2/yscb.py`
> **模組路徑**：`core_v2/source/core/core/surface/bootstrap/`（`factory.py`、`system_module.py`、`__init__.py`）、`core_v2/yscb.py`
> **依賴上限（Allowed Imports）**：組裝根與系統 `Task` 允許依賴 `Domain 1 ~ 6`（為全系統唯一跨六域轉接點）；`core_v2/yscb.py` **嚴格僅限 100% Python 3.11+ 標準庫**
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

> [!NOTE]
> **實作彈性邊界**：本文件鎖定跨六域 Port 轉接拓撲、內建系統管理 `Task` 指令與編排時序、`yscb.py` 雙原語自舉邊界與遠端實作驗收閘門；內部檔案拆分與輔助類別名稱可由實作端微調。

---

## 1. 頂層組裝根（Composition Root — `core.surface.bootstrap`）

依據 [ROADMAP.md](../../ROADMAP.md) §3「消費端定義 Port、組裝根負責轉接」鐵律，底層 5 大功能域彼此嚴格遵守單向 DAG 且零反向匯入，全系統對象組裝唯一收斂於 `core.surface.bootstrap.WorkspaceKernelFactory`：

```text
[host_dir, yscb_root]
   │
   ├── 1. metadata.config.ConfigStore + SnapshotVault  (實作 ConfigViewPort!)
   ├── 2. metadata.contributes.ContributesAggregator   (聚合 uri_schemes / spaces / locales)
   ├── 3. filesystem.vfs: UriMountTable + ReadonlyPolicy + VfsEchoGuard + VfsHub
   │        (VfsEchoGuard 實作 VfsEchoGuardPort!)
   ├── 4. filesystem.storage.ModuleDatabase("storage.local://core/space/state.db")
   ├── 5. filesystem.space: SpaceRegistry + SpaceScanner + GitignoreMaterializer
   │        (將編譯後 /readonly 匹配器回綁至 ReadonlyPolicy!)
   ├── 6. packaging.env.ImmutableVenvPool + packaging.installer.OfflinePackageEngine
   ├── 7. ModuleProviderAdapter (轉接 manifests + EnvPool + tasks.index.json -> ModuleProviderPort!)
   ├── 8. ModuleRuntimeServicesFactory (為各模組生成 ScopedVfs / Logger / Locale / Config / Contributes)
   ├── 9. execution.runtime.RuntimeDispatcher (載入 CoreSystemModule + 已安裝模組)
   └── 10. (Daemon 模式) execution.daemon.WorkspaceDaemon
            (注入 echo_guard, space_watch_roots=SpaceRegistry.collect_watch_roots(),
             config_watch_roots=(config/, .config.local/, yscb.config.json),
             on_space_changed_task=TaskId("core.watcher"),
             on_config_changed_task=TaskId("core.config.on_changed"))
```

### 1.1 四大消費端 Port 轉接契約核對
| Port 介面（定義於 `execution.runtime`） | 具體實作來源 | 組裝根轉接職責 |
| :--- | :--- | :--- |
| **`ConfigViewPort`** | `metadata.config.ConfigStore` | 直接結構滿足（`get_module_value`、`fingerprint`、`reload`），零轉接樣板 |
| **`VfsEchoGuardPort`** | `filesystem.vfs.VfsEchoGuard` | 直接結構滿足（`is_suppressed`），並作為 `DaemonWatcherConfig.echo_guard` 注入 |
| **`ModuleProviderPort`** | `ModuleProviderAdapter`（組裝根薄類別） | 讀取 `ConfigStore` 已安裝模組之 `ModuleManifest`、`ImmutableVenvPool.get_python_executable` 與 `tasks.index.json`，合成 `ModuleDescriptor` 清單（並固定將 `CoreSystemModule` 註冊為內建 Tier 0 模組） |
| **`DaemonSpawner`** | `execution.daemon.SingleFlightDaemonSpawner` | 以 `[sys.executable, str(yscb_py_path), "daemon", "start", "--console"]` 或內核子進程參數建構拉起命令 |

### 1.2 `Core` 內建系統重載聯動（`core.config.on_changed` / `core.watcher`）
- **`core.watcher`（`INTERNAL_TRIGGER`）**：收到 `WorkspaceDaemon` 傳入之 `dirty_paths` 或 `startup_catchup=True` $\to$ 呼叫 `SpaceScanner.patch_paths()`（或 `scan()`） $\to$ 若 `batch.has_changes` 則發射 `core.space_updated` 事件（`UNORDERED`），由 `ast` / `knowledge-db` 訂閱追平。
- **`core.config.on_changed`（`INTERNAL_TRIGGER`）**：組態或模組變更時依序重載 `ConfigStore` $\to$ `ContributesAggregator` $\to$ `UriMountTable` $\to$ `SpaceRegistry` $\to$ 回綁 `ReadonlyPolicy` 匹配器與 `GitignoreMaterializer.sync()` $\to$ 同步更新 `LocaleCatalog`。

---

## 2. 內建系統管理 `Task` 清冊（`CoreSystemModule`）

全數實作為 `core` 模組之宣告式 `Module` + `TaskGroup`，100% 經 `RuntimeDispatcher` 派發；`1 Task = 1 固定 SecurityTier`：

| 指令群 | 子指令 | `SecurityTier` | `DispatchMode` | `SelfMutationScope` | 關鍵編排說明 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`daemon`** | `daemon status` | `SAFE` | `COLD_ONLY` | `NONE` | 透過 `query_daemon_control(CONTROL_STATUS)` 查詢，不續命 TTL |
| | `daemon start [--console\|-d]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 單實例鎖啟動 `WorkspaceDaemon`（`-d` 走 `SingleFlightDaemonSpawner`） |
| | `daemon stop [--force]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 發送 `CONTROL_STOP` 並回報 `teardown_diagnostics` |
| | `daemon reload [modules...]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 發送 `CONTROL_RELOAD` 觸發熱重載或 `core` 交棒 |
| **套件管理** | `list [--remote]` / `status` | `SAFE` | `HYBRID` | `NONE` | 檢視已安裝模組、版本、Tier 與 `.venv` 狀態 |
| | `reload` | `CONDITIONAL` | `COLD_ONLY` | `MUTATES_MODULES` | 依 `QUIESCE -> reload_from_mirror -> RESUME` 重物化與同步 |
| | `install <mod[@ver]...>` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` / `MUTATES_CORE` | 完整編排見 §2.1（支援 `--provider`/`--force`/`--offline`/`--ignore-sha256`） |
| | `update [mods...]` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` / `MUTATES_CORE` | 同 Major 鎖定升級 + `core` 先行 + 相依交集自癒 |
| | `restore` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` | 依 `yscb.config.json` 還原全模組（含 `pruned` 同三元組補位） |
| | `remove <mods...> [--clean]` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` | 卸載模組（保留 `config://` & `storage://`），自動清動態空間與 `.gitignore` |
| | `purge <mods...>` | **`CRITICAL`** | `COLD_ONLY` | `MUTATES_MODULES` | **獨立高危任務**：卸載並永久清除五大資料空間（限人類互動終端確認） |
| | `rollback [snap_id]` | **`CRITICAL`** | `COLD_ONLY` | `MUTATES_CORE` | **獨立高危任務**：還原 `SnapshotVault` 並由不可變鏡像重物化（限人類終端） |
| **組態擴充** | `config list\|get\|inspect` | `SAFE` | `HYBRID` | `NONE` | 讀取 2×2 組態矩陣與型別 Schema 說明 |
| | `config set\|unset\|reload` | `CONDITIONAL` | `HYBRID` | `NONE` | 寫前 Schema 驗證、單檔原子寫入並發射 `core.config_changed` |
| | `contributes list\|check\|inspect` | `SAFE` | `HYBRID` | `NONE` | 零匯入自省、`Strict Egress` 校驗與 `--provenance` 溯源檢視 |
| **URI／唯讀** | `uri list\|resolve\|to-uri\|check` | `SAFE` | `HYBRID` | `NONE` | 檢視 Scheme B 15 協議與模組自訂協議健康狀態 |
| | `file-lock status` | `SAFE` | `HYBRID` | `NONE` | 診斷 `/readonly` 空間與單檔 OS 唯讀鎖狀態 |
| | `file-lock sync\|lock` | `CONDITIONAL` | `HYBRID` | `NONE` | 同步施加 OS 唯讀屬性 |
| | `file-lock unlock` | `GATED` | `HYBRID` | `NONE` | 緊急維護解除受管唯讀鎖 |
| **空間／忽略** | `fs spaces\|match\|ls\|hash\|status\|diff\|ack-cursor` | `SAFE` | `HYBRID` | `NONE` | SQLite WAL 唯讀快照查詢、規則來源診斷與 6 欄 CAS 游標確認（`core.space.ack_cursor`） |
| | `fs scan\|clean` / `gitignore sync` | `CONDITIONAL` | `HYBRID` | `NONE` | 執行增量掃描、清游標或手動同步 `project://.gitignore` |
| | `gitignore status` | `SAFE` | `HYBRID` | `NONE` | 檢視各模組 `# [<owner>]` 分組忽略規則 |
| **虛擬環境** | `env list\|check [--deep]` | `SAFE` | `HYBRID` | `NONE` | 檢視 `.venv` 池狀態、快檢或子進程深檢 |
| | `env repair\|gc [--all]` | `CONDITIONAL` | `COLD_ONLY` | `MUTATES_MODULES` | 修復損毀環境或執行孤兒環境回收 |


### 2.1 套件異動標準編排時序（`install` / `update` / `restore` / `remove` / `purge` / `rollback`）
所有改變 `.modules/` 或組態矩陣之內建系統 `Task` 統一執行以下防撕裂閉環：
1. **前置守門與單向鎖階層**：確認為頂層前景冷呼叫（`COLD_ONLY` + `SelfMutationScope`），由 `RuntimeDispatcher` 自變異守門先取得最外層跨進程 `.cache/locks/installer.lock` 排他鎖，進入交易編排時再由 `WorkspaceKernel.installer_transaction_lock()` 取得中層 `.cache/locks/tx_orchestrator.lock` （底層 `OfflinePackageEngine` 內層則持有 `.cache/locks/package_engine.lock`，嚴格遵循 `installer.lock -> tx_orchestrator.lock -> package_engine.lock` 單向無環鎖序）。
2. **通知線上 Daemon 全域靜默**：若探測到線上 Daemon，發送 `CONTROL_QUIESCE(lease_sec=...)` 排空非核心在途任務（`finally` 中必然發送 `CONTROL_RESUME`，若更新了 `core` 則觸發 Daemon 自重啟交棒）。
3. **移除前置事件（僅 `remove` / `purge`）**：先向將卸載之模組發射 `MODULE_REMOVING_EVENT_ID`（`ORDERED`），並呼叫 `SpaceRegistry.clear_dynamic_spaces(mod)` 清除其動態空間。
4. **純離線套件引擎執行**：委派 `packaging.installer.OfflinePackageEngine` 完成 `SnapshotVault` 保護快照 $\to$ 依賴求解 $\to$ 下載校驗 $\to$ Tier 1 `.venv` 建置 $\to$ Staging 物化與 `*.tmpl` 整目錄剝離 $\to$ 原子目錄替換。
5. **跨版資料遷移 `Task` 派發**：依 `DeploymentReport.transitions` 中 `is_upgrade == True` 且目標模組宣告 `@on_migrate` 者，經 `RuntimeDispatcher` 派發內部遷移任務（帶 `MigrationRequest(old_version, new_version)`）；**任一遷移失敗立即觸發 `SnapshotVault.restore_snapshot()` 與鏡像重物化回滾**。
6. **收尾同步與通知**：重建 `.cache/tasks.index.json`、重載 `ContributesAggregator` / `SpaceRegistry`、執行 `GitignoreMaterializer.sync()` 與 `ReadonlyPolicy.sync_files()`、執行 `EnvGarbageCollector.collect()`、發射 `MODULE_INSTALLED_EVENT_ID` / `WORKSPACE_RELOADED_EVENT_ID`，於 `CONTROL_RESUME` 喚醒 Daemon 後依序釋放中層 `tx_orchestrator.lock` 與最外層 `installer.lock`。

### 2.2 供下游模組呼叫之內核空間寫入系統 `Task`
- `core.space.set_dynamic(owner, name, spec)` / `core.space.clear_dynamic(owner, name=None)`（`SDK_ONLY`）：檢核呼叫來源模組僅能修改自身 `owner`，寫入 `storage.local://core/space/state.db` 後立即觸發 `.gitignore` / `/readonly` 同步並發射 `core.space_registry_changed`。
- `core.space.ack_cursor`（`CLI_AND_SDK` / `fs ack-cursor`）：接收 `SpaceAckCursorInput` 六欄 CAS 參數薄封裝 `SpaceScanner.ack_cursor()`，精準推進單一 consumer 游標。

---

## 3. `core_v2/yscb.py` 超薄自舉啟動器規格

延續 1.x Thin Host 紀律（`DN-12`, `DN-14`），`core_v2/yscb.py` 維持 100% Python 3.11+ 純標準庫自包含單檔啟動器，嚴禁堆疊任何下游業務模組邏輯：

1. **唯二無依賴冷自舉原語與非互動環境守門**：
   - `yscb init [--provider=<url_or_path>] [--yscb-root=<rel>] [--fix] [--allow-bootstrap-mutation]`：建立或修復 `yscb.config.json`，向 Provider 探測並下載驗證 `core` 套件（SHA-256 + CRC + Zip Slip），原子物化至 `.modules/core/`。空工作區全新 `init` 免阻擋；`--fix` 修復模式於非人類互動 TTY（`AGENT`/`CI`/`NON_TTY`）下須顯式傳入 `--allow-bootstrap-mutation`，否則回傳 `security_gated`（退出碼 `4`）。
   - `yscb self-update [--url=<url>] [--sha256=<hex>] [--ignore-sha256] [--allow-bootstrap-mutation]`：使用與 `DEFAULT_PROVIDER_URL` 物理獨立之 `DEFAULT_SELF_UPDATE_URL`（指向 `releases` 孤兒分支），驗證伴隨 `.sha256` 與 AST 結構完整性後原子替換自身 `yscb.py`；於非人類互動 TTY 下須顯式傳入 `--allow-bootstrap-mutation`，否則回傳 `security_gated`（退出碼 `4`）。
   - Windows 重解析點守門僅攔截 `IO_REPARSE_TAG_SYMLINK`（`0xA000000C`）與 `IO_REPARSE_TAG_MOUNT_POINT`（`0xA0000003`），放行 OneDrive／WOF 重解析點。
2. **新環境缺失 `.modules/core` 確定性自舉還原（`DN-12`, `DN-14`）**：
   - 當 `yscb.config.json` 存在但 `.modules/core` 缺失（或版本不健康）時，嚴格依組態中的確定性 `provider` 與 `installed_modules["core"]["version"]`（支援 `pruned` 同三元組最高 `active` 補位並同步更新 `yscb.config.json`）拉取還原 `core`。
   - **零盲猜紅線**：探測或來源失敗時明確印出修復指引並退出，**嚴禁硬編碼預設版本號或私自 fallback 至官方遠端 URL**。
3. **100% 委派微內核**：
   - 其餘所有指令（包含 `yscb --help`、`daemon`、`install` 與全部業務模組指令），僅將 `{yscb_root}/.modules/core` 置於 `sys.path` 首位（絕不注入任何業務模組或 `.venv` 至宿主進程），傳入顯式 `(argv, host_dir, yscb_root)` 呼叫 `core.surface.cli.main(...)` 並原樣透傳退出碼。

---

## 4. 公開契約與門面簽名（1:1 Parity）

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

from core.execution.daemon import DaemonQuiesceControl, DaemonReloadControl, DaemonResumeControl, DaemonRunState, DaemonStopControl, DaemonWatcherConfig, SingleFlightDaemonSpawner, WorkspaceDaemon, query_daemon_control
from core.execution.lifecycle import ContainerState
from core.execution.rpc import DAEMON_SUBDIR, DaemonConnectionConfig, FrameKind, call_ephemeral_daemon_rpc, probe_daemon_endpoint, read_daemon_endpoint_file
from core.execution.runtime import BoundTask, CONFIG_CHANGED_EVENT_ID, CORE_MODULE_ID, CallPropagationContext, CallerSurface, ClientRoutingPolicy, ConfigViewPort, DEFAULT_CACHE_DIRNAME, DaemonRpcInvokeReply, DispatchMode, DispatcherHostOptions, ExecutionPriority, InvokeRequest, LOCKS_SUBDIR, MODULES_DIRNAME, MODULE_INSTALLED_EVENT_ID, MODULE_REMOVING_EVENT_ID, ModuleDescriptor, ModuleProviderPort, ModuleRuntimeServices, ProtectedModuleLoader, RuntimeDispatcher, SecurityTier, SelfMutationScope, TaskContext, TaskExposure, TaskMetadata, TaskRouteSpec, WORKSPACE_RELOADED_EVENT_ID, YscbModule, build_workspace_module_services_factory, resolve_active_call_tree_id, resolve_active_caller_module
from core.filesystem.fs import FileLock, MAX_JSON_FILE_BYTES, assert_no_symlink_raw_path, atomic_write_json, has_symlink_raw_path, is_symlink_or_reparse, read_json_dict, read_nofollow_regular_bytes, resolve_contained_subpath, try_resolve_contained_subpath
from core.filesystem.space import GitignoreMaterializer, HashPolicy, SpaceDiffBatch, SpaceMatchExplain, SpaceRegistry, SpaceScanner, SpaceSpec
from core.filesystem.storage import ModuleDatabase
from core.filesystem.vfs import KernelVfs, MountRule, ReadonlyPolicy, UriMountTable, VfsCapabilities, VfsEchoGuard, VfsHub, build_standard_mount_rules
from core.foundation import CancellationToken, DataclassCodec, ErrorCode, HostPath, INT64_MAX, INT64_MIN, IS_WINDOWS, JsonObject, JsonValue, LocaleCatalog, ModuleId, MutableJsonObject, SemanticUri, SnapshotGen, SpaceId, SpacePath, TEST_SANDBOX_ENV_KEY, TaskId, YscbError, build_isolated_python_env, guard_standard_streams, is_process_alive, is_public_env_truthy, read_public_env_value, require_non_none, require_pure_bool, require_pure_int, require_pure_str, safe_real_to_float, strict_parse_json_object
from core.metadata.config import ConfigStore, ModuleManifest, SnapshotVault, parse_manifest_dict, register_compiled_module_surface_meta
from core.metadata.contributes import AggregatedContributes, ContributesAggregator, CoreSpaceContribution, CoreUriSchemeContribution, ExtensionPointSpec, ProvenanceGraph, ResolvedProjectRoot, bind_locale_getter_dialect, bind_locale_getter_owner, core_builtin_extension_points, discover_installed_manifests_map, extract_parsed_space_contributions, extract_validated_uri_schemes, hash_workspace_surface_trees, is_active_cross_workspace_call, is_control_plane_reserved_path, is_permitted_contributed_mount_root, load_workspace_locale_catalog, probe_workspace_host_dir, register_managed_child_dispatcher, register_sdk_core_post_call_hook, register_sdk_core_session_factory, resolve_sdk_core_dispatcher_binder, resolve_workspace_project_root, unbind_locale_getter_dialect, unbind_locale_getter_owner
from core.packaging.env import EnvGarbageCollector, EnvHealthProbe, EnvSpec, ImmutableVenvPool, acquire_env_lease_for_python, touch_env_last_used
from core.packaging.installer import DeploymentReport, OfflinePackageEngine, PackageRequest, ProviderClient, PurgeLevel
from core.surface.cli import CLI_DEFAULT_PROVIDER_URL, CLI_DEFAULT_SELF_UPDATE_URL, CliKernelSession, IndexedTaskEntry, ModuleTasksIndex, WorkspaceTasksIndexCache, compile_tasks_index, register_cli_kernel_factory
from core.surface.sdk import Arg, ClearDynamicSpaceInput, Empty, ExitCodeProvider, HumanRenderable, InMemoryModule, MigrationRequest, Module, Option, SPACE_REGISTRY_CHANGED_EVENT_ID_STR, SPACE_UPDATED_EVENT_ID_STR, SetDynamicSpaceInput, SpaceAckCursorInput, SpaceScanInput, TaskGroup, define_event, format_output, task

DEFAULT_PROVIDER_URL: Final[str] = CLI_DEFAULT_PROVIDER_URL
DEFAULT_SELF_UPDATE_URL: Final[str] = CLI_DEFAULT_SELF_UPDATE_URL

def bind_system_kernel(yscb_root: HostPath, kernel: SystemKernelPort) -> None:
    ...

def lookup_active_system_kernel(yscb_root: HostPath) -> Optional[SystemKernelPort]:
    ...

def unbind_system_kernel(yscb_root: HostPath, kernel: SystemKernelPort) -> None:
    ...

@dataclass(frozen=True, slots=True)
class ConfigChangedEventPayload:
    changed_paths: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ConfigChangedTriggerInput:
    changed_paths: tuple[str, ...] = ()

class ConfigContributesTaskGroup(TaskGroup):

    def config_list(self, req: ConfigModuleOptInput, ctx: TaskContext) -> SystemResultView:
        ...

    def config_get(self, req: ConfigGetInput, ctx: TaskContext) -> SystemResultView:
        ...

    def config_inspect(self, req: ConfigInspectInput, ctx: TaskContext) -> SystemResultView:
        ...

    def config_set(self, req: ConfigSetInput, ctx: TaskContext) -> SystemResultView:
        ...

    def config_unset(self, req: ConfigUnsetInput, ctx: TaskContext) -> SystemResultView:
        ...

    def config_reload(self, ctx: TaskContext) -> SystemResultView:
        ...

    def contributes_list(self, req: ConfigModuleOptInput, ctx: TaskContext) -> SystemResultView:
        ...

    def contributes_check(self, req: ContributesCheckInput, ctx: TaskContext) -> SystemResultView:
        ...

    def contributes_inspect(self, req: ContributesInspectInput, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class ConfigGetInput:
    module: Annotated[str, Arg(name='module', summary='Target module ID')]
    key: Annotated[str, Arg(name='key', summary='Dotted configuration key')]

@dataclass(frozen=True, slots=True)
class ConfigInspectInput:
    module: Annotated[str, Arg(name='module', summary='Target module ID')]

@dataclass(frozen=True, slots=True)
class ConfigModuleOptInput:
    module: Annotated[Optional[str], Arg(name='module', summary='Optional target module ID')] = None

@dataclass(frozen=True, slots=True)
class ConfigSetInput:
    module: Annotated[str, Arg(name='module', summary='Target module ID')]
    key: Annotated[str, Arg(name='key', summary='Dotted configuration key')]
    value: Annotated[str, Arg(name='value', summary='JSON value or string literal')]
    local: Annotated[bool, Option(summary='Write to machine-local .config.local/ layer')] = False

@dataclass(frozen=True, slots=True)
class ConfigUnsetInput:
    module: Annotated[str, Arg(name='module', summary='Target module ID')]
    key: Annotated[str, Arg(name='key', summary='Dotted configuration key')]
    local: Annotated[bool, Option(summary='Remove from machine-local .config.local/ layer')] = False

@dataclass(frozen=True, slots=True)
class ContributesCheckInput:
    strict: Annotated[bool, Option(summary='Treat validation issues as strict errors')] = True

@dataclass(frozen=True, slots=True)
class ContributesInspectInput:
    module: Annotated[str, Arg(name='module', summary='Target module ID')]
    provenance: Annotated[bool, Option(summary='Include field-level ProvenanceGraph')] = False

class CoreSystemModule(Module):

    def __init__(self, kernel: Optional[SystemKernelPort]=None) -> None:
        ...

    @property
    def kernel(self) -> Optional[SystemKernelPort]:
        ...

    def set_dynamic_space(self, req: SetDynamicSpaceInput, ctx: TaskContext) -> bool:
        ...

    def clear_dynamic_space(self, req: ClearDynamicSpaceInput, ctx: TaskContext) -> int:
        ...

    def scan_space(self, req: SpaceScanInput, ctx: TaskContext) -> tuple[SpaceDiffBatch, ...]:
        ...

    def on_watcher_dirty(self, req: WatcherTriggerInput, ctx: TaskContext) -> None:
        ...

    def on_config_changed(self, req: ConfigChangedTriggerInput, ctx: TaskContext) -> None:
        ...

    def on_dynamic_space_mutated(self, ctx: TaskContext) -> tuple[str, ...]:
        ...

    def to_yscb_module(self) -> YscbModule:
        ...

@dataclass(frozen=True, slots=True)
class DaemonReloadInput:
    modules: Annotated[tuple[str, ...], Arg(name='module', summary='Optional module IDs to reload')] = ()

@dataclass(frozen=True, slots=True)
class DaemonStartInput:
    console: Annotated[bool, Option(summary='Run daemon supervisor in foreground console mode', group='mode')] = False
    detach: Annotated[bool, Option(short='d', summary='Spawn detached background daemon', group='mode')] = False
    supervisor: Annotated[bool, Option(long_name='supervisor', summary='Internal detached background daemon supervisor entry', group='mode')] = False

@dataclass(frozen=True, slots=True)
class DaemonStopInput:
    force: Annotated[bool, Option(short='f', summary='Force immediate shutdown without draining')] = False

class DaemonTaskGroup(TaskGroup):

    def daemon_status(self, ctx: TaskContext) -> SystemResultView:
        ...

    def daemon_start(self, req: DaemonStartInput, ctx: TaskContext) -> SystemResultView:
        ...

    def daemon_stop(self, req: DaemonStopInput, ctx: TaskContext) -> SystemResultView:
        ...

    def daemon_reload(self, req: DaemonReloadInput, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class EnvCheckInput:
    module: Annotated[Optional[str], Arg(name='module', summary='Optional module ID to check')] = None
    deep: Annotated[bool, Option(summary='Run subprocess deep import probe')] = False

@dataclass(frozen=True, slots=True)
class EnvGcInput:
    all_inactive: Annotated[bool, Option(long_name='all', summary='Purge all inactive environments ignoring grace window')] = False

@dataclass(frozen=True, slots=True)
class EnvRepairInput:
    module: Annotated[str, Arg(name='module', summary='Target Tier 1 module ID to repair')]
    offline: Annotated[bool, Option(summary='Repair using cached wheels only')] = False

class EnvTaskGroup(TaskGroup):

    def env_list(self, ctx: TaskContext) -> SystemResultView:
        ...

    def env_check(self, req: EnvCheckInput, ctx: TaskContext) -> SystemResultView:
        ...

    def env_repair(self, req: EnvRepairInput, ctx: TaskContext) -> SystemResultView:
        ...

    def env_gc(self, req: EnvGcInput, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class FileLockPathOptInput:
    path: Annotated[Optional[str], Arg(name='path', summary='Optional target file path or URI')] = None

@dataclass(frozen=True, slots=True)
class FileLockPathReqInput:
    path: Annotated[str, Arg(name='path', summary='Target file path or URI')]

@dataclass(frozen=True, slots=True)
class FsCleanInput:
    space_id: Annotated[Optional[str], Arg(name='space-id', summary='Optional space (<owner>/<name>)')] = None
    consumer: Annotated[Optional[str], Option(summary='Optional consumer cursor to clear')] = None

@dataclass(frozen=True, slots=True)
class FsDiffInput:
    space_id: Annotated[str, Arg(name='space-id', summary='Target space (<owner>/<name>)')]
    consumer: Annotated[str, Option(summary='Consumer cursor identifier')] = 'cli'

@dataclass(frozen=True, slots=True)
class FsHashInput:
    space_id: Annotated[str, Arg(name='space-id', summary='Target space (<owner>/<name>)')]
    rel_path: Annotated[str, Arg(name='rel-path', summary='Relative path inside space')]

@dataclass(frozen=True, slots=True)
class FsLsInput:
    space_id: Annotated[str, Arg(name='space-id', summary='Target space (<owner>/<name>)')]
    pattern: Annotated[Optional[str], Option(summary='Optional glob filter pattern')] = None

@dataclass(frozen=True, slots=True)
class FsMatchInput:
    space_id: Annotated[str, Arg(name='space-id', summary='Target space (<owner>/<name>)')]
    target: Annotated[str, Arg(name='target', summary='Target physical path or URI')]

@dataclass(frozen=True, slots=True)
class FsScanInput:
    space_id: Annotated[Optional[str], Arg(name='space-id', summary='Optional space (<owner>/<name>)')] = None
    force: Annotated[bool, Option(short='f', summary='Force full content re-hash')] = False

@dataclass(frozen=True, slots=True)
class FsSpaceOptInput:
    space_id: Annotated[Optional[str], Arg(name='space-id', summary='Optional space (<owner>/<name>)')] = None

@dataclass(frozen=True, slots=True)
class FsSpacesInput:
    owner: Annotated[Optional[str], Option(summary='Filter spaces by owner module ID')] = None

@dataclass(frozen=True, slots=True)
class ModuleLifecycleEventPayload:
    modules: tuple[str, ...] = ()

class ModuleProviderAdapter(ModuleProviderPort):

    def __init__(self, *, yscb_root: HostPath, env_pool: ImmutableVenvPool, core_route_specs: Sequence[TaskRouteSpec], on_reload: Optional[Callable[[], None]]=None) -> None:
        ...

    @property
    def pending_evicted(self) -> frozenset[ModuleId]:
        ...

    def set_pending_evicted(self, modules: frozenset[ModuleId]) -> None:
        ...

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        ...

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        ...

    def invalidate_cache(self) -> None:
        ...

    def reload(self) -> None:
        ...

@dataclass(frozen=True, slots=True)
class PackageInstallInput:
    specs: Annotated[tuple[str, ...], Arg(name='spec', summary='Package spec(s) <module[@constraint]>')]
    provider: Annotated[Optional[str], Option(summary='Override package provider URL or path')] = None
    force: Annotated[bool, Option(short='f', summary='Force reinstall even if version matches')] = False
    offline: Annotated[bool, Option(summary='Install strictly from local mirror/cache')] = False
    ignore_sha256: Annotated[bool, Option(summary='Skip archive SHA-256 verification')] = False

@dataclass(frozen=True, slots=True)
class PackageListInput:
    remote: Annotated[bool, Option(summary='Also query remote provider index')] = False

@dataclass(frozen=True, slots=True)
class PackagePurgeInput:
    modules: Annotated[tuple[str, ...], Arg(name='module', summary='Target module ID(s) to permanently purge')]
    force: Annotated[bool, Option(short='f', summary='Force purge despite reverse dependencies')] = False

@dataclass(frozen=True, slots=True)
class PackageRemoveInput:
    modules: Annotated[tuple[str, ...], Arg(name='module', summary='Target module ID(s)')]
    clean: Annotated[bool, Option(summary='Also clear cache:// and storage.local://')] = False
    force: Annotated[bool, Option(short='f', summary='Force removal despite reverse dependencies')] = False

@dataclass(frozen=True, slots=True)
class PackageRestoreInput:
    provider: Annotated[Optional[str], Option(summary='Override package provider URL or path')] = None
    force: Annotated[bool, Option(short='f', summary='Force rematerialization of all modules')] = False
    offline: Annotated[bool, Option(summary='Restore strictly from local mirror')] = False
    ignore_sha256: Annotated[bool, Option(summary='Skip archive SHA-256 verification')] = False

@dataclass(frozen=True, slots=True)
class PackageRollbackInput:
    snapshot_id: Annotated[Optional[str], Arg(name='snapshot-id', summary='Optional snapshot ID (defaults to latest)')] = None

class PackageTaskGroup(TaskGroup):

    def list_modules(self, req: PackageListInput, ctx: TaskContext) -> SystemResultView:
        ...

    def workspace_status(self, ctx: TaskContext) -> SystemResultView:
        ...

    def reload_workspace(self, ctx: TaskContext) -> SystemResultView:
        ...

    def install_packages(self, req: PackageInstallInput, ctx: TaskContext) -> SystemResultView:
        ...

    def update_packages(self, req: PackageUpdateInput, ctx: TaskContext) -> SystemResultView:
        ...

    def restore_packages(self, req: PackageRestoreInput, ctx: TaskContext) -> SystemResultView:
        ...

    def remove_packages(self, req: PackageRemoveInput, ctx: TaskContext) -> SystemResultView:
        ...

    def purge_packages(self, req: PackagePurgeInput, ctx: TaskContext) -> SystemResultView:
        ...

    def rollback_workspace(self, req: PackageRollbackInput, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class PackageUpdateInput:
    modules: Annotated[tuple[str, ...], Arg(name='module', summary='Optional module ID(s) to update')] = ()
    provider: Annotated[Optional[str], Option(summary='Override package provider URL or path')] = None
    offline: Annotated[bool, Option(summary='Update strictly from local mirror')] = False
    ignore_sha256: Annotated[bool, Option(summary='Skip archive SHA-256 verification')] = False

class SpaceGitignoreTaskGroup(TaskGroup):

    def fs_spaces(self, req: FsSpacesInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_match(self, req: FsMatchInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_ls(self, req: FsLsInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_hash(self, req: FsHashInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_status(self, req: FsSpaceOptInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_diff(self, req: FsDiffInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_scan(self, req: FsScanInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_clean(self, req: FsCleanInput, ctx: TaskContext) -> SystemResultView:
        ...

    def fs_ack_cursor(self, req: SpaceAckCursorInput, ctx: TaskContext) -> SystemResultView:
        ...

    def gitignore_status(self, ctx: TaskContext) -> SystemResultView:
        ...

    def gitignore_sync(self, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class SpaceUpdatedEventPayload:
    spaces: tuple[str, ...] = ()

class SystemKernelPort(Protocol):

    @property
    def is_closed(self) -> bool:
        ...

    @property
    def is_closing(self) -> bool:
        ...

    @property
    def is_managed_child(self) -> bool:
        ...

    @property
    def host_dir(self) -> HostPath:
        ...

    @property
    def yscb_root(self) -> HostPath:
        ...

    @property
    def cache_dir(self) -> HostPath:
        ...

    @property
    def config_store(self) -> ConfigStore:
        ...

    @property
    def snapshot_vault(self) -> SnapshotVault:
        ...

    @property
    def contributes_aggregator(self) -> ContributesAggregator:
        ...

    @property
    def mount_table(self) -> UriMountTable:
        ...

    @property
    def readonly_policy(self) -> ReadonlyPolicy:
        ...

    @property
    def kernel_vfs(self) -> KernelVfs:
        ...

    @property
    def space_registry(self) -> SpaceRegistry:
        ...

    @property
    def space_scanner(self) -> SpaceScanner:
        ...

    @property
    def gitignore_materializer(self) -> GitignoreMaterializer:
        ...

    @property
    def env_pool(self) -> ImmutableVenvPool:
        ...

    @property
    def env_probe(self) -> EnvHealthProbe:
        ...

    @property
    def env_gc(self) -> EnvGarbageCollector:
        ...

    @property
    def package_engine(self) -> OfflinePackageEngine:
        ...

    def list_route_specs(self) -> Sequence[TaskRouteSpec]:
        ...

    def ensure_installed_tasks_indices(self, module_ids: Optional[Iterable[ModuleId]]=None) -> None:
        ...

    def resolve_module_config_type(self, module_id: ModuleId) -> Optional[type[object]]:
        ...

    def invoke_internal_migration(self, module_id: ModuleId, mig_req: MigrationRequest, call_tree_id: Optional[str], *, cancel_token: Optional[CancellationToken]=None) -> None:
        ...

    def installer_transaction_lock(self, cancel_token: Optional[CancellationToken]=None) -> AbstractContextManager[None]:
        ...

    def space_sync_guard(self) -> AbstractContextManager[None]:
        ...

    def has_running_daemon(self) -> bool:
        ...

    def is_daemon_quiesced(self) -> bool:
        ...

    def refresh_dynamic_spaces_only(self) -> tuple[str, ...]:
        ...

    def reload_config_only(self, changed_paths: Sequence[str]=()) -> bool:
        ...

    def evict_local_modules_before_remove(self, modules: Sequence[ModuleId]) -> None:
        ...

    def reload_workspace_metadata(self) -> None:
        ...

    def schedule_post_close_daemon_sync(self, *, quiesced: bool, quiesce_epoch: Optional[int], core_handoff: bool=False) -> None:
        ...

    def flush_pending_daemon_sync(self) -> None:
        ...

    def rebuild_tasks_index_cache(self) -> None:
        ...

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        ...

    def clear_dynamic_spaces(self, owner: ModuleId, name: Optional[str]=None, *, sync: bool=True) -> int:
        ...

    def is_reserved_control_plane_path(self, hp: HostPath, *, owner: Optional[str]=None, allow_any_module_storage: bool=False) -> bool:
        ...

    def sync_gitignore_and_readonly(self) -> JsonObject:
        ...

    def collect_active_env_specs(self) -> tuple[EnvSpec, ...]:
        ...

    def discover_installed_manifests(self) -> Mapping[ModuleId, ModuleManifest]:
        ...

    def spawn_or_run_daemon(self, *, console: bool, detach: bool, supervisor: bool=False) -> JsonObject:
        ...

@dataclass(frozen=True, slots=True)
class SystemResultView(HumanRenderable, ExitCodeProvider):
    summary: str
    data: JsonObject = field(default_factory=dict)
    code: int = 0

    def render_text(self) -> str:
        ...

    def exit_code(self) -> int:
        ...

@dataclass(frozen=True, slots=True)
class UriFromPathInput:
    path: Annotated[str, Arg(name='path', summary='Physical path to convert to SemanticUri')]

@dataclass(frozen=True, slots=True)
class UriResolveInput:
    uri: Annotated[str, Arg(name='uri', summary='Semantic URI to resolve')]

class VfsReadonlyTaskGroup(TaskGroup):

    def uri_list(self, ctx: TaskContext) -> SystemResultView:
        ...

    def uri_resolve(self, req: UriResolveInput, ctx: TaskContext) -> SystemResultView:
        ...

    def uri_from_path(self, req: UriFromPathInput, ctx: TaskContext) -> SystemResultView:
        ...

    def uri_check(self, ctx: TaskContext) -> SystemResultView:
        ...

    def file_lock_status(self, req: FileLockPathOptInput, ctx: TaskContext) -> SystemResultView:
        ...

    def file_lock_sync(self, ctx: TaskContext) -> SystemResultView:
        ...

    def file_lock_lock(self, req: FileLockPathReqInput, ctx: TaskContext) -> SystemResultView:
        ...

    def file_lock_unlock(self, req: FileLockPathReqInput, ctx: TaskContext) -> SystemResultView:
        ...

@dataclass(frozen=True, slots=True)
class WatcherTriggerInput:
    changed_paths: tuple[str, ...] = ()
    startup_catchup: bool = False

class WorkspaceKernel(SystemKernelPort, CliKernelSession):

    def __init__(self, *, host_dir: HostPath, yscb_root: HostPath, is_daemon_host: bool, force_cold: bool, extra_modules: Sequence[YscbModule], yscb_script_path: Optional[HostPath], dialect: Optional[str]=None, extra_config_types: Mapping[ModuleId, type[object]]=MappingProxyType({}), extra_live_specs: Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]]=MappingProxyType({}), allow_deferred_daemon_console: bool=False, is_managed_child: bool=False, allow_auto_spawn: bool=True, inherit_host_env_locale: bool=True, raw_env_locale_override: Optional[str]=None) -> None:
        ...

    def resolve_module_config_type(self, module_id: ModuleId) -> Optional[type[object]]:
        ...

    def apply_caller_dialect(self, dialect: Optional[str], raw_env_locale: Optional[str]=None) -> None:
        ...

    def consume_post_close_exit_code(self) -> Optional[int]:
        ...

    def is_reserved_control_plane_path(self, hp: HostPath, *, owner: Optional[str]=None, allow_any_module_storage: bool=False) -> bool:
        ...

    @property
    def is_closed(self) -> bool:
        ...

    @property
    def is_closing(self) -> bool:
        ...

    @property
    def is_managed_child(self) -> bool:
        ...

    @property
    def is_daemon_host(self) -> bool:
        ...

    @property
    def is_force_cold(self) -> bool:
        ...

    @property
    def has_extra_modules(self) -> bool:
        ...

    @property
    def host_dir(self) -> HostPath:
        ...

    @property
    def yscb_root(self) -> HostPath:
        ...

    @property
    def cache_dir(self) -> HostPath:
        ...

    @property
    def config_store(self) -> ConfigStore:
        ...

    @property
    def snapshot_vault(self) -> SnapshotVault:
        ...

    @property
    def contributes_aggregator(self) -> ContributesAggregator:
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

    @property
    def kernel_vfs(self) -> KernelVfs:
        ...

    @property
    def space_registry(self) -> SpaceRegistry:
        ...

    @property
    def space_scanner(self) -> SpaceScanner:
        ...

    @property
    def gitignore_materializer(self) -> GitignoreMaterializer:
        ...

    @property
    def env_pool(self) -> ImmutableVenvPool:
        ...

    @property
    def env_probe(self) -> EnvHealthProbe:
        ...

    @property
    def env_gc(self) -> EnvGarbageCollector:
        ...

    @property
    def package_engine(self) -> OfflinePackageEngine:
        ...

    @property
    def module_provider(self) -> ModuleProviderAdapter:
        ...

    @property
    def dispatcher(self) -> RuntimeDispatcher:
        ...

    def resolve_task_output_type(self, task_id: TaskId) -> Optional[object]:
        ...

    def resolve_task_presentation(self, task_entry: IndexedTaskEntry, raw_value: JsonValue, *, render_human: bool) -> tuple[Optional[str], Optional[int]]:
        ...

    def list_route_specs(self) -> Sequence[TaskRouteSpec]:
        ...

    def ensure_installed_tasks_indices(self, module_ids: Optional[Iterable[ModuleId]]=None) -> None:
        ...

    def discover_installed_manifests(self) -> Mapping[ModuleId, ModuleManifest]:
        ...

    def collect_active_env_specs(self) -> tuple[EnvSpec, ...]:
        ...

    @contextmanager
    def installer_transaction_lock(self, cancel_token: Optional[CancellationToken]=None) -> Iterator[None]:
        ...

    def is_daemon_quiesced(self) -> bool:
        ...

    def on_config_view_reload_requested(self) -> None:
        ...

    def has_running_daemon(self) -> bool:
        ...

    def refresh_dynamic_spaces_only(self) -> tuple[str, ...]:
        ...

    def config_and_contributes_fingerprint(self) -> str:
        ...

    def reload_config_only(self, changed_paths: Sequence[str]=()) -> bool:
        ...

    def evict_local_modules_before_remove(self, modules: Sequence[ModuleId]) -> None:
        ...

    def reload_workspace_metadata(self) -> None:
        ...

    def schedule_post_close_daemon_sync(self, *, quiesced: bool, quiesce_epoch: Optional[int], core_handoff: bool=False) -> None:
        ...

    def flush_pending_daemon_sync(self) -> None:
        ...

    def rebuild_tasks_index_cache(self) -> None:
        ...

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        ...

    def clear_dynamic_spaces(self, owner: ModuleId, name: Optional[str]=None, *, sync: bool=True) -> int:
        ...

    @contextmanager
    def space_sync_guard(self) -> Iterator[None]:
        ...

    def sync_gitignore_and_readonly(self) -> JsonObject:
        ...

    def invoke_internal_migration(self, module_id: ModuleId, mig_req: MigrationRequest, call_tree_id: Optional[str], *, cancel_token: Optional[CancellationToken]=None) -> None:
        ...

    def build_daemon(self, *, watcher_debounce_sec: float=0.5, self_restart_argv: Optional[Sequence[str]]=None) -> WorkspaceDaemon:
        ...

    def has_deferred_daemon(self) -> bool:
        ...

    def run_deferred_daemon(self, *, on_ready: Optional[Callable[[], None]]=None) -> tuple[bool, int]:
        ...

    def spawn_or_run_daemon(self, *, console: bool, detach: bool, supervisor: bool=False) -> JsonObject:
        ...

    def close(self) -> None:
        ...

class WorkspaceKernelFactory:

    @staticmethod
    def create(host_dir: HostPath, yscb_root: HostPath, *, is_daemon_host: bool=False, force_cold: bool=False, extra_modules: Sequence[Module | InMemoryModule | YscbModule]=(), yscb_script_path: Optional[HostPath]=None, dialect: Optional[str]=None) -> WorkspaceKernel:
        ...

    @staticmethod
    def open_cli_session(host_dir: HostPath, yscb_root: HostPath, force_cold: bool=False, *, yscb_script_path: Optional[HostPath]=None) -> CliKernelSession:
        ...

    @staticmethod
    def open_sdk_core_session(host_dir: HostPath, yscb_root: HostPath) -> tuple[object, Callable[[], None]]:
        ...

    @staticmethod
    def builtin_cli_indices() -> tuple[ModuleTasksIndex, ...]:
        ...

__all__: tuple[str, ...] = (
    "ClearDynamicSpaceInput",
    "ConfigChangedEventPayload",
    "ConfigChangedTriggerInput",
    "ConfigContributesTaskGroup",
    "ConfigGetInput",
    "ConfigInspectInput",
    "ConfigModuleOptInput",
    "ConfigSetInput",
    "ConfigUnsetInput",
    "ContributesCheckInput",
    "ContributesInspectInput",
    "CoreSpaceContribution",
    "CoreSystemModule",
    "CoreUriSchemeContribution",
    "DEFAULT_PROVIDER_URL",
    "DEFAULT_SELF_UPDATE_URL",
    "DaemonReloadInput",
    "DaemonStartInput",
    "DaemonStopInput",
    "DaemonTaskGroup",
    "EnvCheckInput",
    "EnvGcInput",
    "EnvRepairInput",
    "EnvTaskGroup",
    "FileLockPathOptInput",
    "FileLockPathReqInput",
    "FsCleanInput",
    "FsDiffInput",
    "FsHashInput",
    "FsLsInput",
    "FsMatchInput",
    "FsScanInput",
    "FsSpaceOptInput",
    "FsSpacesInput",
    "ModuleLifecycleEventPayload",
    "ModuleProviderAdapter",
    "PackageInstallInput",
    "PackageListInput",
    "PackagePurgeInput",
    "PackageRemoveInput",
    "PackageRestoreInput",
    "PackageRollbackInput",
    "PackageTaskGroup",
    "PackageUpdateInput",
    "SPACE_REGISTRY_CHANGED_EVENT_ID_STR",
    "SPACE_UPDATED_EVENT_ID_STR",
    "SetDynamicSpaceInput",
    "SpaceAckCursorInput",
    "SpaceGitignoreTaskGroup",
    "SpaceScanInput",
    "SpaceUpdatedEventPayload",
    "SystemKernelPort",
    "SystemResultView",
    "UriFromPathInput",
    "UriResolveInput",
    "VfsReadonlyTaskGroup",
    "WatcherTriggerInput",
    "WorkspaceKernel",
    "WorkspaceKernelFactory",
    "bind_system_kernel",
    "lookup_active_system_kernel",
    "unbind_system_kernel",
)
```

---

## 5. 必測驗收門檻與活規格守門 (Verification Gate)

1. **對外門面與磁碟契約一致性**：`core.surface.sdk`（[sdk.md](./sdk.md)）、基礎值物件與觀測底座（[foundation.md](../foundation/foundation.md)）、磁碟 JSON 格式（`manifest.json` 2.0、`tasks.index.json`、`contributes/_schema.json`、`config.schema.json`、`*.tmpl`、`yscb.config.json`）與六域單向 DAG 均經 `Gate 0` 1:1 強制守門。
2. **跨領域物理拔除驗證（`--suite unplug`）**：由頂向下依序物理移除 `surface` $\to$ `execution` $\to$ `packaging` $\to$ `metadata` $\to$ `filesystem.{space,storage,vfs,fs}`，驗證底層各域零反向耦合且獨立執行全數通過。
3. **自舉與套件異動端到端閉環（`--suite surface_cli_e2e`）**：驗證 `yscb.py init` $\to$ `pruned` 同三元組確定性還原 $\to$ `install` $\to$ `daemon` 熱派發與線上 `core` 交棒 $\to$ `@on_migrate` 成功升級與失敗自動快照回滾，全程 `0 ResourceWarning`、`0 Any`。
