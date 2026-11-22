# 子模組架構設計規格：`core.filesystem.storage`（薄型 `sqlite3` WAL MVCC 持久化引擎與 `BlobVault`）

> **所屬功能域**：`Domain 2 — 檔案、空間與儲存域 (filesystem/)`
> **模組路徑**：`core_v2/source/core/core/filesystem/storage/`
> **建議內部切分**：`database.py`、`blob_vault.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{fs, vfs}`
> **禁止反向依賴（Forbidden Imports）**：`filesystem.space`、`metadata/*`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

> [!NOTE]
> **實作彈性邊界**：`ModuleDatabase`、`SnapshotReader`、`WriteTransaction`、`BlobVault` 之公開契約、WAL MVCC 語意、單向遷移規則與嚴格限縮於 `storage.local://` 之路徑守門屬硬契約；連線池細節與內部表格輔助函式可由遠端實作端微調。

---

## 1. 模組定位與核心設計原則

依據 [ROADMAP.md](../../ROADMAP.md) `DR-03`，`core.filesystem.storage` 專為索引型與狀態型模組（`core.space`、`ast`、`knowledge-db`、`gdrive-support`）提供**選配、零 ORM、100% Python 標準庫 `sqlite3` WAL MVCC 持久化底座**與外部大檔案 **`BlobVault`**：

1. **毫秒級零鎖讀取（MVCC Snapshot Isolation）**：前景查詢透過 `SnapshotReader` 讀取上一版已提交快照（`PRAGMA query_only=ON` + `BEGIN DEFERRED`），背景寫入進行期間前景絕不被阻塞，並以 $O(1)$ 讀取內建世代（`SnapshotGen`）與上游水位表判斷是否需要附帶「背景追平中」提示。
2. **根治 `SQLITE_BUSY` 升級死鎖（`BEGIN IMMEDIATE`）**：所有寫入必須透過 `WriteTransaction` 並一律以 `BEGIN IMMEDIATE` 起事務，徹底消除「兩連線先讀後升級寫」引發的不可恢復 SQLite 死鎖；支援在 `commit()` 前核驗 `CancellationToken`，遇取消或任何異常自動完整回滾。
3. **嚴格禁止 `cache://` 與 `storage://` 建庫（能力位元強制守門）**：
   - `cache://` 定義為隨時可丟棄之中繼快取，絕不可存放持久狀態庫。
   - `storage://` 定義為 Git 團隊追蹤空間，二進位 SQLite / WAL 檔嚴禁進入版本控制造成二進位衝突與膨脹。
   - 因此 `ModuleDatabase` 與 `BlobVault` 開啟前**強制檢核 VFS 能力位元**：目標 URI 必須同時滿足 `PERSISTENT | WRITABLE | PHYSICAL_PATH` 且 **不得包含 `GIT_TRACKED`**（即唯一合法落點為 **`storage.local://`**）；違反者立即拋出 `YscbError(ErrorCode.ACCESS_DENIED)`。
4. **零資源洩漏與跨平台句柄安全**：明確管理所有 `sqlite3.Connection` 生命週期，`close()` 同步釋放所有讀寫連線並於測試下保證 `0 ResourceWarning` 與 Windows 零鎖檔殘留（可立即 `rmtree` 測試目錄）。

---

## 2. 標準 SQLite PRAGMA 與內建系統中繼表

每條新開啟之連線強制執行以下標準初始化序列：

```sql
PRAGMA journal_mode = WAL;          -- 寫入連線開啟時設定（唯讀連線不重複切換）
PRAGMA synchronous = NORMAL;        -- WAL 模式下兼顧防崩潰與高速吞吐
PRAGMA foreign_keys = ON;           -- 強制外鍵完整性
PRAGMA temp_store = MEMORY;         -- 暫存排序表不落磁碟
PRAGMA busy_timeout = 5000;         -- 跨進程短暫鎖競爭等待（可透過選項調整）
PRAGMA wal_autocheckpoint = 1000;   -- 防止 WAL 檔無限膨脹
```

### 內建系統中繼表（自動於開庫初始化）
所有由 `ModuleDatabase` 管理的資料庫均自動建立兩張保留前綴 `_yscb_*` 系統表（業務表嚴禁使用 `_yscb_` 前綴）：

```sql
CREATE TABLE IF NOT EXISTS _yscb_generation (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    committed_gen INTEGER NOT NULL DEFAULT 0,
    updated_at_ns INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS _yscb_watermarks (
    watermark_key TEXT PRIMARY KEY,
    watermark_value TEXT NOT NULL,
    updated_at_ns INTEGER NOT NULL DEFAULT 0
);
```

- **單向 Schema 遷移（`PRAGMA user_version`）**：
  - 建構 `ModuleDatabase` 時傳入依 `version` 遞增排列的 `Sequence[SchemaMigration]`（版本號嚴格從 `1` 起算遞增無跳號）。
  - 開庫時在獨佔 `BEGIN IMMEDIATE` 事務內比對磁碟 `PRAGMA user_version`：
    - `db_ver == target_ver`：零開銷直接放行。
    - `db_ver < target_ver`：依序執行 `(db_ver, target_ver]` 遷移步驟並更新 `PRAGMA user_version`。
    - `db_ver > target_ver`：**立即拋出 `YscbError(ErrorCode.SCHEMA_MIGRATION_ERROR)`**，嚴禁靜默降級破壞高版資料。

---

## 3. 核心公開契約規格 (`core/filesystem/storage/`)

```python
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO, Callable, Iterator, Optional, Sequence, TypeAlias

from core.filesystem.vfs import ScopedVfs
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, SemanticUri, SnapshotGen

SqlParam: TypeAlias = None | bool | int | float | str | bytes
SqlParams: TypeAlias = Sequence[SqlParam]
SqlRow: TypeAlias = tuple[SqlParam, ...]


@dataclass(frozen=True, slots=True)
class StorageOpenOptions:
    busy_timeout_ms: int = 5000
    wal_autocheckpoint_pages: int = 1000
    read_only_pool_size: int = 4


@dataclass(frozen=True, slots=True)
class SchemaMigration:
    """單向增量 Schema 遷移步驟（嚴禁降級）。"""
    version: int
    description: str
    sql_statements: tuple[str, ...] = ()
    migrate_fn: Optional[Callable[[WriteTransaction], None]] = None


class SnapshotReader:
    """唯讀 MVCC 快照讀取器（毫秒零阻塞；離開 with 區塊自動結束讀取快照並歸還連線）。"""
    def committed_gen(self) -> SnapshotGen: ...
    def get_watermark(self, key: str) -> Optional[str]: ...
    def list_watermarks(self) -> dict[str, str]: ...
    def query_one(self, sql: str, params: SqlParams = ()) -> Optional[SqlRow]: ...
    def query_all(self, sql: str, params: SqlParams = ()) -> list[SqlRow]: ...
    def iter_rows(self, sql: str, params: SqlParams = (), *, batch_size: int = 256) -> Iterator[SqlRow]: ...


class WriteTransaction:
    """序列化寫入事務（BEGIN IMMEDIATE；遇異常或 CancellationToken 取消自動回滾）。"""
    @property
    def current_gen(self) -> SnapshotGen: ...
    def execute(self, sql: str, params: SqlParams = ()) -> int: ...
    def executemany(self, sql: str, param_seq: Sequence[SqlParams]) -> int: ...
    def query_one(self, sql: str, params: SqlParams = ()) -> Optional[SqlRow]: ...
    def query_all(self, sql: str, params: SqlParams = ()) -> list[SqlRow]: ...
    def get_watermark(self, key: str) -> Optional[str]: ...
    def set_watermark(self, key: str, value: str) -> None: ...
    def delete_watermark(self, key: str) -> None: ...
    def mark_generation_bumped(self) -> SnapshotGen: ...
```


class ModuleDatabase:
    """模組級 SQLite WAL MVCC 持久化引擎（強制僅允許落點於 storage.local://）。"""
    def __init__(
        self,
        vfs: ScopedVfs,
        db_uri: SemanticUri | str,
        *,
        migrations: Sequence[SchemaMigration] = (),
        options: StorageOpenOptions = StorageOpenOptions(),
    ) -> None: ...

    @property
    def db_uri(self) -> SemanticUri: ...
    @property
    def physical_path(self) -> HostPath: ...
    @property
    def schema_version(self) -> int: ...
    @property
    def is_closed(self) -> bool: ...

    @contextmanager
    def read_snapshot(self) -> Iterator[SnapshotReader]: ...

    @contextmanager
    def write_transaction(
        self, *, cancel_token: Optional[CancellationToken] = None,
    ) -> Iterator[WriteTransaction]: ...

    def committed_gen(self) -> SnapshotGen: ...
    def get_watermark(self, key: str) -> Optional[str]: ...
    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int]: ...
    def verify_integrity(self) -> bool: ...
    def close(self) -> None: ...
    def __enter__(self) -> ModuleDatabase: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class BlobVault:
    """外部二進位大檔保險庫（強制落點於 storage.local://，避免大型向量／快取撐爆 SQLite WAL）。"""
    def __init__(self, vfs: ScopedVfs, root_uri: SemanticUri | str) -> None: ...
    @property
    def root_uri(self) -> SemanticUri: ...
    def put_content_addressed(self, data: bytes) -> str: ...
    def put_keyed(self, key: str, data: bytes) -> str: ...
    def exists(self, ref: str) -> bool: ...
    def get_bytes(self, ref: str) -> Optional[bytes]: ...
    def open_read(self, ref: str) -> Optional[BinaryIO]: ...
    def delete(self, ref: str) -> bool: ...
    def gc_unreferenced(self, live_refs: frozenset[str]) -> int: ...
```

---

## 4. 關鍵生命週期、並發與防錯不變量

1. **能力位元剛性守門（唯獨 `storage.local://` 合法）**：
   - `ModuleDatabase.__init__` 與 `BlobVault.__init__` 建構第一步即查詢 `caps = vfs.get_capabilities(uri)`：
     - 必須具備 `READABLE | WRITABLE | PERSISTENT | PHYSICAL_PATH`；
     - **嚴禁具備 `GIT_TRACKED`**（阻擋 `storage://`、`config://`、`project://`）；
     - 欠缺 `PERSISTENT`（阻擋 `cache://`、`MemoryVfsProvider` 非持久空間）或無實體路徑（SQLite 需 OS 檔案鎖與 WAL shm）一律立即拋出 `YscbError(ErrorCode.ACCESS_DENIED)`。
   - 若傳入 `ScopedVfs(mod)` 同時受跨模組寫權限約束，故模組 A 僅能在 `storage.local://a/...` 下建立自身資料庫與 `BlobVault`。
2. **寫事務取消與異常回滾保證**：
   - `write_transaction(cancel_token=...)` 開始前先檢查 `cancel_token.raise_if_cancelled()`，進入 `BEGIN IMMEDIATE` 後若業務代碼拋錯或於提交前 `cancel_token.is_cancelled` 為真，一律執行 `ROLLBACK` 並拋出對應例外（`TaskCancelledException` 或原異常），`_yscb_generation` 與所有業務表 100% 保持原狀。
   - `mark_generation_bumped()` 僅於 `COMMIT` 成功時使世代永久遞增；同一事務內重複呼叫為冪等（單一事務最多推進 `1` 個世代）。
3. **唯讀快照連線生命週期與 Windows 句柄清理**：
   - `read_snapshot()` 內部以 `PRAGMA query_only = ON` + `BEGIN DEFERRED` 確保快照一致，於 `finally` 執行 `ROLLBACK` 釋放讀取快照鎖（避免長開讀取事務卡住 WAL checkpoint 導致 `-wal` 檔無限增長）。
   - `close()` 關閉寫連線與所有池化唯讀連線，確保在 `Module.on_close()` / LIFO Teardown 後 Windows 可零衝突刪除資料庫目錄且 Python 測試零 `ResourceWarning`。
4. **損毀偵測與不靜默吞錯**：
   - 遭遇 `sqlite3.DatabaseError`（如磁碟頁損毀 `database disk image is malformed`）時，統一封裝為 `YscbError(ErrorCode.STORAGE_CORRUPT, ..., remediation=...)`，交由上層決定重建索引或報錯，絕不靜默刪庫或吞異常。
5. **`BlobVault` 原子寫入與分片**：
   - `put_content_addressed(data)` 以 SHA-256 十六進位為鍵、前 2 字元作為子目錄分片（`<root>/<h[:2]>/<h>.blob`），若檔案已存在則內容定址冪等短路；寫入一律走 `fs.atomic_write_bytes`，`gc_unreferenced(live_refs)` 安全跳過 `.tmp_*` 暫存檔。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **能力位元守門測試**：對 `cache://@/test.db`、`storage://@/test.db`、`project://test.db` 建構 `ModuleDatabase` / `BlobVault` 一律拋 `YscbError(ErrorCode.ACCESS_DENIED)`；僅 `storage.local://@/test.db` 合法通過。
2. **WAL MVCC 並發讀寫零阻塞測試**：背景執行緒持有長時間 `WriteTransaction` 寫入千筆資料期間，前景多執行緒並發呼叫 `read_snapshot()` 恆定毫秒級讀回上一版已提交快照（0 `SQLITE_BUSY`、0 髒讀），待提交後立即見新 `SnapshotGen` 與新資料。
3. **`BEGIN IMMEDIATE` 序列化與 `CancellationToken` 回滾測試**：雙執行緒並發進入 `write_transaction` 無升級死鎖；事務中途觸發 `cancel_token.cancel()` 完整回滾且 `committed_gen` 不變。
4. **單向遷移與防降級測試**：`v1 -> v2 -> v3` 增量升級成功；以舊版遷移清冊（僅含 `v1`）開啟 `v3` 庫立即拋 `SCHEMA_MIGRATION_ERROR`。
5. **`BlobVault` 原子寫入、GC 與資源釋放測試**：內容定址冪等寫入、`gc_unreferenced` 精準回收孤兒 Blob、全測試於 `-W error::ResourceWarning` 與 Windows 立即 `rmtree` 100% 通過。
