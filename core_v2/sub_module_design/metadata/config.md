# 子模組架構設計規格：`core.metadata.config`（`manifest.json` 2.0、2×2 強型別組態矩陣、原地補齊與智能 `SnapshotVault`）

> **所屬功能域**：`Domain 3 — 組態與擴充域 (metadata/)`
> **模組路徑**：`core_v2/source/core/core/metadata/config/`
> **建議內部切分**：`manifest.py`、`matrix.py`、`infill.py`、`snapshot.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`
> **禁止反向依賴（Forbidden Imports）**：`filesystem.{vfs, space, storage}`、`metadata.contributes`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

> [!NOTE]
> **實作彈性邊界**：`manifest.json` 2.0 磁碟格式、2×2 組態檔路徑與覆疊語意、`ConfigViewPort` 結構相容性與 `SnapshotVault` 備份邊界屬硬契約；內部資料結構與輔助方法可由遠端實作端微調。

---

## 1. 模組定位與跨分類解耦鐵律

`core.metadata.config` 專責解析與原子維護宿主設定、模組清單（`manifest.json` 2.0）、2×2 強型別組態矩陣與配置保險庫：
1. **純機制離線讀寫（零匯入 `vfs` / `space` / `execution`）**：直接接收顯式 `host_dir: HostPath` 與 `yscb_root: HostPath`，透過 `filesystem.fs` 執行原子讀寫與路徑防穿越，**100% 與 `project://` 解耦**（`DN-03`），確保新專案尚未設定 `project_root` 前仍能正常讀寫組態、安裝模組與建立快照。
2. **嚴禁向上攀爬目錄樹（`DN-04`）**：僅從顯式傳入之 `host_dir` / `yscb_root` 定位 `yscb.config.json`，嚴禁任何 `while parent != curr` 或 `os.getcwd()` 猜測。
3. **對稱 `Contributes 2.0` 的強型別組態 SSOT**：各模組以不可變 `@dataclass(frozen=True, slots=True)` 作為自身組態契約與預設值唯一真理來源；由 `core` 統一導出靜態 `config.schema.json`（供 IDE 補全與 `config set` 寫前型別驗證），升級時由 `DeepInfiller` 原地補齊新增缺失鍵。

---

## 2. `manifest.json` 2.0 與宿主組態格式

### 2.1 `manifest.json` 2.0 欄位規範
移除 1.x 與 `id` 重複的 `name` 及歷史殘留 `uris`，與 Wave 1.1 `ModuleDescriptor` 完全對齊：

```json
{
  "schema_version": 2,
  "id": "ast",
  "version": "2.0.0.0",
  "description": "YS-Codebase 靜態語法樹與雙向呼叫圖譜引擎",
  "entry": "module_entry.py",
  "dependencies": { "core": ">=2.0.0.0" },
  "optional": {
    "knowledge-db": { "version": ">=2.0.0", "hint": "啟用跨空間混合語意檢索" }
  },
  "pip_dependencies": { "tree-sitter": ">=0.23.0" },
  "venv_group": "code_intel",
  "eager_warmup": false,
  "onboarding": ["yscb ast status"],
  "release": { "type": "minor", "urgency": "recommended", "summary": "..." }
}
```

- **Tier 判定不變量**：`pip_dependencies` 為空對應 **Tier 0**（內核同進程零 `.venv`）；非空對應 **Tier 1**（經 `packaging.env` 建置雜湊 `.venv` 並由子進程池調度）。

### 2.2 2×2 組態矩陣與覆疊優先序
| 維度 | 團隊版控（Git Tracked） | 本機個人（Git Ignored） |
| :--- | :--- | :--- |
| **全域層級** | `{host_dir}/yscb.config.json`（`yscb_root`、`default_provider`、`installed_modules`） | `{host_dir}/yscb.config.local.json`（本機覆寫如 `default_provider`、Daemon TTL） |
| **模組層級** | `{yscb_root}/config/<mod>/config.project.json` | `{yscb_root}/.config.local/<mod>/config.local.json`（本機覆寫與私密憑證） |

- **有效值解析順序**：`模組 @dataclass 預設值` $\longrightarrow$ `config.project.json` $\longrightarrow$ `config.local.json`（遞迴物件合併；純量與清單直接覆寫）。
- **寫入與 `configurable/` 部署規則（`DN-06` 進化）**：
  - `config.project.json` 升級部署採 `DeepInfiller` 遞迴鍵級補齊（**僅補缺失鍵，使用者已改值 100% 原地保留**）；預設值可由隨包 `config.schema.json` 或 `configurable/config.project.json.tmpl` 提供。
  - 模組包內 `configurable/` 所有預設模板強制採 **`*.tmpl` 副檔名**（如 `contribute.json.tmpl`），非主組態檔採「**目標不存在才去 `.tmpl` 複製、存在則絕不覆蓋**」。
  - 部署完畢後，`packaging.installer` 於 Staging 目錄內**無條件整目錄剝離 `configurable/` 與 `.yscbignore`**（靜態編譯契約 `config.schema.json` 置於套件根目錄不受影響），確保 `.modules/<mod>/` 零模板殘留。

---

## 3. 核心公開契約規格 (`core/metadata/config/`)

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

from core.filesystem.fs import FileLock, IGNORED_FS_PREFIXES, MAX_JSON_FILE_BYTES, assert_no_symlink_raw_path, atomic_write_bytes, atomic_write_json, has_symlink_raw_path, hash_nofollow_regular_sha256, is_atomic_staging_filename, is_symlink_or_reparse, read_json_dict, read_nofollow_regular_bytes, resolve_contained_subpath, silent_unlink, walk_nonsymlink_dir_tree
from core.foundation import DataclassCodec, ErrorCode, HostPath, IS_WINDOWS, JsonObject, JsonValue, MAX_USER_JSON_DEPTH, ModuleId, MutableJsonObject, SemVer4, TaskId, VersionConstraint, YscbError, clone_strict_json_object, is_process_alive, is_valid_relative_segment, require_pure_bool, require_pure_int, require_pure_str, require_typed_tuple, resolve_dataclass_init_hints, safe_exception_summary, safe_real_to_float, strict_parse_json_object, validate_relative_segment

TConfig = TypeVar('TConfig')

def lookup_compiled_module_root_default_tasks(yscb_module: object) -> frozenset[TaskId]:
    ...

def lookup_compiled_module_surface_meta(yscb_module: object) -> tuple[tuple[str, ...], str]:
    ...

def parse_locale_chain_tokens(raw_env_locale: Optional[str], cfg_store: ConfigStore, *, dialect: Optional[str]=None) -> tuple[str, ...]:
    ...

def parse_manifest_dict(raw: Mapping[str, object], *, expected_id: Optional[ModuleId]=None) -> ModuleManifest:
    ...

def register_compiled_module_surface_meta(yscb_module: object, *, aliases: tuple[str, ...]=(), description: str='', root_default_tasks: frozenset[TaskId]=frozenset()) -> None:
    ...

class ConfigStore:

    def __init__(self, *, host_dir: HostPath, yscb_root: HostPath) -> None:
        ...

    def load_host_config(self) -> HostConfig:
        ...

    def save_host_config(self, config: HostConfig) -> None:
        ...

    def get_module_dict(self, module_id: ModuleId) -> MutableJsonObject:
        ...

    def get_module_value(self, module_id: ModuleId, key: str, default: JsonValue=None) -> JsonValue:
        ...

    def load_typed(self, module_id: ModuleId, config_cls: type[TConfig]) -> TConfig:
        ...

    def set_value(self, module_id: ModuleId, key: str, value: JsonValue, *, local: bool=False, schema_cls: Optional[type[object]]=None) -> None:
        ...

    def unset_value(self, module_id: ModuleId, key: str, *, local: bool=False) -> bool:
        ...

    def get_module_local_dict(self, module_id: ModuleId) -> MutableJsonObject:
        ...

    def get_module_redacted_dict(self, module_id: ModuleId, *, schema_cls: Optional[type[object]]=None) -> MutableJsonObject:
        ...

    def deploy_configurable(self, module_id: ModuleId, staging_configurable_dir: HostPath, *, default_config_template: Optional[JsonObject]=None) -> tuple[str, ...]:
        ...

    def fingerprint(self) -> str:
        ...

    def reload(self) -> None:
        ...

class DeepInfiller:

    @staticmethod
    def infill(existing: JsonObject, template: JsonObject) -> tuple[MutableJsonObject, tuple[str, ...]]:
        ...

@dataclass(frozen=True, slots=True)
class HostConfig:
    yscb_root: str
    default_provider: str
    installed_modules: Mapping[ModuleId, InstalledModuleRecord]

@dataclass(frozen=True, slots=True)
class InstalledModuleRecord:
    version: SemVer4
    installed_at: str
    provider: str

@dataclass(frozen=True, slots=True)
class ModuleManifest:
    id: ModuleId
    version: SemVer4
    description: str
    schema_version: int = 2
    entry: str = 'module_entry.py'
    dependencies: Mapping[ModuleId, VersionConstraint] = field(default_factory=dict)
    optional: Mapping[ModuleId, OptionalDependencySpec] = field(default_factory=dict)
    pip_dependencies: Mapping[str, str] = field(default_factory=dict)
    venv_group: Optional[str] = None
    eager_warmup: bool = False
    onboarding: tuple[str, ...] = ()
    release: Optional[ReleaseMeta] = None

    @property
    def is_tier1(self) -> bool:
        ...

@dataclass(frozen=True, slots=True)
class OptionalDependencySpec:
    version: VersionConstraint
    hint: str = ''

@dataclass(frozen=True, slots=True)
class ReleaseMeta:
    release_type: str = 'patch'
    urgency: ReleaseUrgency = ReleaseUrgency.RECOMMENDED
    summary: str = ''

class ReleaseUrgency(Enum):
    OPTIONAL = 'optional'
    RECOMMENDED = 'recommended'
    CRITICAL = 'critical'

@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    snapshot_id: str
    created_at_utc: str
    created_epoch_sec: float
    tag: str
    state_fingerprint: str
    reused: bool = False

@dataclass(frozen=True, slots=True)
class SnapshotRetentionPolicy:
    max_snapshots: int = 3
    max_age_days: float = 7.0
    coalesce_window_sec: float = 60.0

class SnapshotVault:

    def __init__(self, *, host_dir: HostPath, yscb_root: HostPath, policy: SnapshotRetentionPolicy=SnapshotRetentionPolicy()) -> None:
        ...

    def create_snapshot(self, tag: str, *, force: bool=False) -> SnapshotMeta:
        ...

    def list_snapshots(self) -> tuple[SnapshotMeta, ...]:
        ...

    def restore_snapshot(self, snapshot_id: Optional[str]=None) -> SnapshotMeta:
        ...

    def prune(self) -> tuple[str, ...]:
        ...

__all__: tuple[str, ...] = (
    "ConfigStore",
    "DeepInfiller",
    "HostConfig",
    "InstalledModuleRecord",
    "ModuleManifest",
    "OptionalDependencySpec",
    "ReleaseMeta",
    "ReleaseUrgency",
    "SnapshotMeta",
    "SnapshotRetentionPolicy",
    "SnapshotVault",
    "lookup_compiled_module_root_default_tasks",
    "lookup_compiled_module_surface_meta",
    "parse_locale_chain_tokens",
    "parse_manifest_dict",
    "register_compiled_module_surface_meta",
)
```

---

## 4. 智能 `SnapshotVault` 演算法與行為不變量

1. **觸發時機與備份範圍（`DN-19`）**：
   - 預設僅於**套件生命週期變更**（`install` / `update` / `remove` / `rollback`）前自動觸發；單鍵 `config set` / `unset` 僅走單檔 `fs.atomic_write_json`（寫前若模組具組態 Schema 則先驗證型別，非法即拋 `YscbError(ErrorCode.CONFIG_INVALID)`）。
   - 備份內容精準涵蓋：`{host_dir}/yscb.config.json`、`{yscb_root}/config/`、`{yscb_root}/storage/`；**嚴禁包含 `.config.local/`、`.storage.local/` 與 `.cache/`**（`.config.local/` 屬本機私密層且採 `0o600` 檔案權限，避免於 `.snapshots/` 留下長期明文副本）。
2. **三階段智能防重複與自動清理**：
   - **① 內容指紋去重（Zero-Diff Short-Circuit）**：計算目標 3 區與宿主組態之確定性 `state_fingerprint`（SHA-256）；若最新一份快照之指紋完全一致且 `force=False`，直接復用並回傳 `SnapshotMeta(..., reused=True)`，0 磁碟寫入。
   - **② 短時窗連點折疊（Burst Coalesce Window）**：若最新快照建立距今 `< coalesce_window_sec`（預設 `60s`）且 `force=False`，**保留該連續操作窗口起點的原始乾淨快照**並回傳 `reused=True`，避免短時間連續跑多條 `install`/`update` 塞滿 3 份槽位、擠掉真正早期的安全回滾點。
   - **③ 雙維度自動淘汰（Age + Count Pruning）**：每次建立快照或呼叫 `prune()` 時，自動移除「超過 `max_age_days`（預設 `7` 天）」以及「按建立時間排序超出最新 `max_snapshots`（預設 `3` 份）」之舊快照目錄（永不刪除當次剛建立／復用之快照），所有快照均先寫入 `.snapshots/.tmp_<id>` 再原子更名為 `.snapshots/snap_<ts>_<seq>`。
3. **原子回滾閉環**：
   - `restore_snapshot(snapshot_id)` 預設還原最新一份有效快照：先以臨時 staging 目錄覆蓋還原 `yscb.config.json`、`config/` 與 `storage/`（不觸及本機私密 `.config.local/`），完成後交由上層 `packaging.installer` 依還原後的 `yscb.config.json` 從不可變鏡像重新物化 `.modules/`。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **`manifest.json` 2.0 解析與驗證**：由單一權威 `parse_manifest_dict` 精準解碼合法 12 欄位（含 `SemVer4`、`VersionConstraint`、`is_tier1` 判定與 `release.type` / `release.release_type` 相容正規化）；缺必填鍵、同時提供 `type` 與 `release_type`、非法 `ModuleId`、`expected_id` 不符或含未知鍵拋 `CONFIG_INVALID`。
2. **2×2 覆疊與 `DeepInfiller`**：`config.local.json` 遞迴覆疊 `config.project.json` 且不覆寫其他兄弟鍵；`DeepInfiller` 補齊新增巢狀鍵同時 100% 保留使用者修改值；`ConfigStore.fingerprint()` 隨任一檔變動即時更新；零依賴 `project://`（`project_root = "!undefined"` 仍可完整讀寫）。
3. **智能 `SnapshotVault`**：
   - 狀態無變動重複呼叫 `create_snapshot` 回傳 `reused=True` 且目錄數不變；
   - 60 秒內連續變更觸發不擠掉早期槽位，`force=True` 可強制另存；
   - 超過 `max_snapshots=3` 自動淘汰最舊者；超過 `7` 天自動清除；
   - 嚴格驗證 `.storage.local/` 與 `.cache/` 絕不被備份或回滾覆寫。
