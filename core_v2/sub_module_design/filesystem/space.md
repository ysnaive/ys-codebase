# 子模組架構設計規格：`core.filesystem.space`（統一邏輯檔案空間、動態空間、SQLite WAL 增量快照與 `.gitignore` 收斂器）

> **所屬功能域**：`Domain 2 — 檔案、空間與儲存域 (filesystem/)`
> **模組路徑**：`core_v2/source/core/core/filesystem/space/`
> **建議內部切分**：`rules.py`、`registry.py`、`hasher.py`、`scanner.py`、`gitignore.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{fs, vfs, storage}`
> **禁止反向依賴（Forbidden Imports）**：`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

> [!NOTE]
> **實作彈性邊界**：`SpaceSpec`、`HashPolicy`、`SpaceFileEntry`、`SpaceDiffBatch`、`SpaceMatchExplain`、規則對稱／剪枝／差集不變量與動態空間隔離語意屬強制統一契約；SQLite 內部表結構與掃描批次細節可由實作端按需微調。

---

## 1. 模組定位與 1.x $\to$ 2.0 核心演化

`core.filesystem.space` 承接 1.x 經實戰驗證的統一邏輯檔案空間代數與 `.gitignore` 安全物化器，並於 2.0 執行兩項根因架構收斂：
1. **快照與游標收斂至 `filesystem.storage`（SQLite WAL MVCC）**：
   - 徹底淘汰 1.x 自製二進位 `YFP2` 檔案、`cursors/<consumer>.json`、`watcher_state.json`、`.watcher_dirty` 與 `sync_dependent_snapshots` 多檔同步鎖拼圖。
   - 統一於單一 `ModuleDatabase`（`storage.local://core/space/state.db`）內以單一 ACID 事務原子維護「持久化動態空間定義 + 空間檔案指紋表 + 變更日誌 + 單調世代 + 多消費者游標」，從根本杜絕 1.x 雙鎖死鎖與多檔撕裂。
2. **動態空間 2.0（無全域單例、支援冷熱與 Tier 0/1）**：
   - 保留 `agents-workflow` 等輸出路徑依組態變動之模組所需的動態空間能力（如動態宣告 `agents-workflow/gitignore`、`agents-workflow/readonly`）。
   - 廢除 1.x `on_register_file_spaces` 可變 Hook 與進程內全域 `register_space` 單例，改由 `SpaceRegistry.set_dynamic_space(owner, name, spec)` / `clear_dynamic_spaces(owner)` 原子寫入 `state.db`（由內核系統 `Task` 暴露，僅允許模組寫入自身 `<owner>` 命名空間，並於模組卸載 `MODULE_REMOVING` 時自動清空並重同步 `.gitignore` / `/readonly`）。

---

## 2. 空間編譯與代數剛性不變量（繼承 `DN-17`, `DN-20`, `DN-21`）

### 2.1 三源兩趟編譯拓撲
`SpaceRegistry` 透過顯式 DI 接收靜態定義並與 `state.db` 內的動態定義合併編譯（零匯入 `metadata`）：
1. **收集來源（優先合併層）**：
   - 來源 1：各模組 `contributes` 宣告之靜態 `SpaceSpec`（由組裝根轉換注入）。
   - 來源 2：專案組態 `project` 覆寫與補充之 `SpaceSpec`。
   - 來源 3：`state.db` 內持久化之動態空間 `dynamic_spaces`（以及選配呼叫期測試用 `with_overlay(...)`）。
2. **Pass 1（同名 `<owner>/<name>` 規則層絕對聯集）**：
   - 同一 `(owner, name)` 若有多份來源宣告，其 `entries`、`include`、`exclude`、`presets`、`compose` 取保序去重聯集；`include` 滿足 `["*"] ∪ [any] = ["*"]`。
3. **Pass 2（無擁有者合成聯集空間 `/<name>`）**：
   - 自動為每個曾出現之 `<name>` 合成 `SpaceId(owner="", name=<name>)`（別名查詢 `<name>` 或 `/<name>`），其 `compose` 自動匯聚所有 `<owner>/<name>`。
4. **內建三大核心空間**：
   - `core/gitignore`（與 `/gitignore`）：正向定義 Git 忽略集合（`entries: ("project://",)`、`watch: False`）；驅動 `GitignoreMaterializer` 並可供其他空間以 `presets: ("!gitignore",)` 或 `compose: ("!gitignore",)` 排除。
   - `core/workspace`（與 `/workspace`）：專案遞迴掃描最外層邊界（`entries: ("project://",)`、`include: ("*",)`、排除系統中繼目錄），作為未指定空間時之預設目標。
   - `/readonly`（合成空間，由各模組靜態或動態貢獻 `<owner>/readonly`）：宣告受唯讀保護之物化產物集合，編譯後餵入 `vfs.ReadonlyPolicy`。

### 2.2 規則對稱、局部子樹剪枝與純檔案集差集（`DN-20` 紅線）
1. **`CompiledRuleSet` 正反向 100% 對稱**：`include` 與 `exclude` 統一採 `allow_dir_prefix=True` 與 `match_any_segment_for_name=True`，支援語意 URI 前綴、含 `/` 相對路徑（對齊 `project_rel` 與 `entry_rel`）與純檔名／目錄區段名。
2. **`!<preset>` 局部子樹安全剪枝**：走訪目錄 $D$ 若命中負向 preset $T$ 的 `include` 且未命中 $T.\text{exclude}$，**唯有當 `T.compiled_exclude.has_potential_descendant_match(D)` 為 `False`** 時方可提前剪枝跳過 $D$；若存在可能命中 $D$ 子樹之豁免規則，必須進入 $D$ 逐檔判斷。
3. **`compose` 純檔案集代數（零母空間二次過濾）**：
   $$\text{Files}(S) = \Big(\text{OwnEntries}(S) \;\cup\; \bigcup_{P \in \text{PosCompose}(S)} \text{Files}(P)\Big) \;\setminus\; \bigcup_{N \in \text{NegCompose}(S)} \text{Files}(N)$$
   母空間自身之 `include`/`exclude` **僅過濾母空間自身之 `entries`**，絕不對 `compose` 子空間結果二次過濾；展開 `presets` 與 `compose` 時執行 DFS 環路偵測，遇環立即拋出 `YscbError(ErrorCode.SPACE_CYCLE)`。

---

## 3. 核心公開值物件與契約規格 (`core/filesystem/space/`)

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

from core.filesystem.fs import IGNORED_FS_PREFIXES, has_symlink_raw_path, is_atomic_staging_filename, is_symlink_or_reparse
from core.filesystem.storage import ModuleDatabase, SnapshotReader, WriteTransaction
from core.filesystem.vfs import KernelVfs
from core.foundation import CancellationToken, DataclassCodec, ErrorCode, HostPath, IS_WINDOWS, ModuleId, Profiler, SemanticUri, SnapshotGen, SpaceId, SpacePath, YscbError, is_valid_relative_segment, require_non_none, require_pure_bool, require_pure_int, require_pure_str, strict_parse_json_object

@dataclass(frozen=True, slots=True)
class ConsumerCursor:
    consumer_id: str
    space_id: SpaceId
    acked_gen: SnapshotGen
    config_hash: str
    merkle_root: str

class GitignoreMaterializer:
    BEGIN_MARKER: str = '# === YSCB MANAGED GITIGNORE BEGIN ==='
    END_MARKER: str = '# === YSCB MANAGED GITIGNORE END ==='

    def __init__(self, registry: SpaceRegistry, vfs: KernelVfs) -> None:
        ...

    def render_managed_block(self) -> tuple[str, dict[str, tuple[str, ...]]]:
        ...

    def sync(self) -> GitignoreSyncResult:
        ...

@dataclass(frozen=True, slots=True)
class GitignoreSyncResult:
    changed: bool
    target_uri: SemanticUri
    groups: Mapping[str, tuple[str, ...]]

class HashPolicy(Enum):
    STAT_ONLY = 'stat_only'
    ADAPTIVE = 'adaptive'
    FULL_HASH = 'full_hash'

@dataclass(frozen=True, slots=True)
class SpaceDiffBatch:
    space_id: SpaceId
    from_gen: SnapshotGen
    to_gen: SnapshotGen
    config_hash: str
    merkle_root: str
    added: tuple[SpacePath, ...] = ()
    modified: tuple[SpacePath, ...] = ()
    deleted: tuple[SpacePath, ...] = ()

    @property
    def has_changes(self) -> bool:
        ...

    @property
    def dirty_files(self) -> tuple[SpacePath, ...]:
        ...

@dataclass(frozen=True, slots=True)
class SpaceFileEntry:
    rel_path: SpacePath
    abs_path: HostPath
    size_bytes: int
    mtime_ns: int
    content_hash: str

@dataclass(frozen=True, slots=True)
class SpaceMatchExplain:
    space_id: SpaceId
    matched: bool
    matched_entry: Optional[SemanticUri] = None
    matched_include: Optional[str] = None
    matched_exclude: Optional[str] = None
    source_space: Optional[SpaceId] = None
    reason: str = ''

class SpaceRegistry:

    def __init__(self, vfs: KernelVfs, db: ModuleDatabase, *, static_specs: Sequence[SpaceSpec]=()) -> None:
        ...

    def reload(self, static_specs: Optional[Sequence[SpaceSpec]]=None) -> None:
        ...

    def with_overlay(self, extra_specs: Sequence[SpaceSpec]) -> SpaceRegistry:
        ...

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        ...

    def remove_dynamic_space(self, owner: ModuleId, name: str) -> bool:
        ...

    def clear_dynamic_spaces(self, owner: ModuleId) -> int:
        ...

    def list_spaces(self, *, owner: Optional[str]=None) -> tuple[SpaceSpec, ...]:
        ...

    def get_space(self, space_id: SpaceId | str) -> SpaceSpec:
        ...

    def config_hash(self, space_id: SpaceId | str) -> str:
        ...

    def match_path(self, space_id: SpaceId | str, target: HostPath | SemanticUri) -> SpaceMatchExplain:
        ...

    def iter_files(self, space_id: SpaceId | str, *, pattern: Optional[str]=None) -> Iterator[SpaceFileEntry]:
        ...

    def resolve_file_path(self, space_id: SpaceId | str, rel_path: SpacePath | str) -> HostPath:
        ...

    def collect_watch_roots(self) -> tuple[HostPath, ...]:
        ...

    @staticmethod
    def build_stateless_readonly_matcher(vfs: KernelVfs, *, static_specs: Sequence[SpaceSpec]=(), dynamic_db_path: Optional[HostPath]=None, reserved_filter: Optional[Callable[[HostPath, str], bool]]=None) -> Callable[[HostPath], bool]:
        ...

class SpaceScanner:

    def __init__(self, registry: SpaceRegistry, db: ModuleDatabase, *, profiler: Optional[Profiler]=None) -> None:
        ...

    def status(self, space_id: SpaceId | str) -> SpaceStatusSnapshot:
        ...

    def scan(self, space_id: SpaceId | str, *, force: bool=False, cancel_token: Optional[CancellationToken]=None) -> SpaceDiffBatch:
        ...

    def patch_paths(self, dirty_paths: frozenset[HostPath], *, cancel_token: Optional[CancellationToken]=None) -> tuple[SpaceDiffBatch, ...]:
        ...

    def diff(self, space_id: SpaceId | str, consumer_id: str) -> SpaceDiffBatch:
        ...

    def ack_cursor(self, space_id: SpaceId | str, consumer_id: str, batch: SpaceDiffBatch) -> bool:
        ...

    @contextmanager
    def consume_diff(self, space_id: SpaceId | str, consumer_id: str) -> Iterator[SpaceDiffBatch]:
        ...

    def clean(self, space_id: Optional[SpaceId | str]=None, *, consumer_id: Optional[str]=None) -> int:
        ...

@dataclass(frozen=True, slots=True)
class SpaceSpec:
    space_id: SpaceId
    entries: tuple[SemanticUri, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    compose: tuple[str, ...] = ()
    watch: bool = True
    hash_policy: HashPolicy = HashPolicy.ADAPTIVE
    description: str = ''

@dataclass(frozen=True, slots=True)
class SpaceStatusSnapshot:
    space_id: SpaceId
    generation: SnapshotGen
    config_hash: str
    merkle_root: str
    file_count: int
    cursors: tuple[ConsumerCursor, ...] = ()

__all__: tuple[str, ...] = (
    "ConsumerCursor",
    "GitignoreMaterializer",
    "GitignoreSyncResult",
    "HashPolicy",
    "SpaceDiffBatch",
    "SpaceFileEntry",
    "SpaceMatchExplain",
    "SpaceRegistry",
    "SpaceScanner",
    "SpaceSpec",
    "SpaceStatusSnapshot",
)
```

---

## 4. `storage.local://core/space/state.db` 建議資料表結構與關鍵行為

1. **五張核心表（同一個 `ModuleDatabase` 內 ACID 更新）**：
   - `dynamic_spaces(owner TEXT, name TEXT, spec_json TEXT, updated_at_ns INTEGER, PRIMARY KEY (owner, name))`
   - `space_snapshots(target_key TEXT PRIMARY KEY, generation INTEGER NOT NULL, config_hash TEXT NOT NULL, merkle_root TEXT NOT NULL, file_count INTEGER NOT NULL, updated_at_ns INTEGER NOT NULL)`
   - `space_files(target_key TEXT NOT NULL, rel_path TEXT NOT NULL, abs_path TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, content_hash TEXT NOT NULL, updated_gen INTEGER NOT NULL, PRIMARY KEY (target_key, rel_path))`
   - `space_change_log(target_key TEXT NOT NULL, gen INTEGER NOT NULL, rel_path TEXT NOT NULL, op TEXT NOT NULL, PRIMARY KEY (target_key, gen, rel_path))`（`op IN ('A', 'M', 'D')`，供多消費者精準計算 `from_gen -> to_gen` 差異，並於所有游標推進後自動裁減過期紀錄）
   - `consumer_cursors(consumer_id TEXT NOT NULL, target_key TEXT NOT NULL, acked_gen INTEGER NOT NULL, config_hash TEXT NOT NULL, merkle_root TEXT NOT NULL, updated_at_ns INTEGER NOT NULL, PRIMARY KEY (consumer_id, target_key))`
2. **雙階段增量掃描與 Racy-Clean 防護**：
   - Stage 1 透過 `os.scandir` + `DirEntry.stat()` 比對 `(mtime_ns, size_bytes)`，並對距今 `< 10ms` 之新近修改套用 Racy-Clean 重算防護。
   - Stage 2 依 `HashPolicy`（`STAT_ONLY` / `ADAPTIVE` / `FULL_HASH`）計算決定性 16-byte Blake2b 雜湊與排序後之空間 `merkle_root`。
   - 當空間 `config_hash` 變更（如新增 `exclude` 規則）時，自動將前世代存在但新集合中不再匹配的檔案全數標記為 `deleted` 並推進世代。
3. **無變動寫入短路（`DN-21`）與 At-Least-Once 消費**：
   - `ack_cursor` 於發起 `WriteTransaction` 前先透過 `SnapshotReader` 核對 `(acked_gen, config_hash, merkle_root)`；若與磁碟游標完全一致則立即返回 `False`，零寫入、零 `fsync`。
   - `consume_diff(space_id, consumer_id)` 僅於 `with` 區塊正常結束時提交 `ack_cursor`，若消費端拋出例外則保持原游標不推進，確保 At-Least-Once 語意。
4. **`GitignoreMaterializer` 排序與 Zero-Touch 不變量（`DN-17`）**：
   - 收集所有 `<owner>/gitignore`（靜態 + 動態）：`effective_include` 轉相對 `project://` 錨定規則、`effective_exclude` 轉 `!<pattern>` 豁免規則。
   - 分組輸出 `# [<owner>]`：`core` 置頂、其餘模組按字母序、`project` 置底；若渲染後全檔位元組與現有 `project://.gitignore` 一致則跳過寫入（Zero-Touch）。
5. **跨層事件介面（由上層內核系統 `Task` 發射，本子模組零匯入 `execution`）**：
   - `core.space_updated`（`UNORDERED`）：由 `core.watcher` / `core.space.scan` 任務在 `SpaceDiffBatch.has_changes` 為真時發射，供 `ast`、`knowledge-db` 等訂閱消費。
   - `core.space_registry_changed`（`UNORDERED`）：於 `set_dynamic_space` / `clear_dynamic_spaces` / 組態重載後發射，觸發 `.gitignore` 同步、`/readonly` 更新與 Daemon 監視目錄重載。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **`DN-20` 規則對稱與剪枝測試**：`include`/`exclude` 對稱目錄前綴匹配、`!<preset>` 在有子樹豁免規則（`build/keep.txt`）時禁止提前剪枝、無豁免時 $O(1)$ 剪枝；`compose` 零母空間二次過濾與 `!<space>` 差集精準性；環路拋 `SPACE_CYCLE`。
2. **動態空間全生命週期測試**：`set_dynamic_space(ModuleId("agents-workflow"), "gitignore", ...)` 持久化於 `state.db`，重啟實例仍生效、即時反映於 `GitignoreMaterializer` 與 `/readonly` 合成空間；`clear_dynamic_spaces` 後自動自 `.gitignore` 清除。
3. **SQLite WAL 並發與游標語意測試**：多消費者（如 `ast`、`kdb`）獨立水位各自推進互不干擾；`consume_diff` 消費失敗不推進游標；無變動 `ack_cursor` 零寫盤短路；`config_hash` 變更正確產出 `deleted` 清單；全測試 `0 ResourceWarning`。
4. **`GitignoreMaterializer` 測試**：保留使用者託管區塊外內容、`# [<owner>]` 確定性排序、Zero-Touch 不改 `mtime`。
