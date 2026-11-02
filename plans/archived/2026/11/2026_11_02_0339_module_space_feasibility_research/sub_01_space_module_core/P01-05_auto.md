# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`module:space` 通用檔案空間、分級指紋快取與背景監聽底座模組 (`v1.0.0.0`) 實作  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_01_space_module_core  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 雙軌空間配置聚合與動態空間 (`SpaceManager`) | 聚合各已安裝模組 `contributes/space.json` 與宿主 `config://space/contribute.json`；列表型欄位（`include`/`exclude`/`file_patterns`）附加合併去重，純量欄位（`hash_policy`/`large_file_threshold_mb`/`follow_symlinks`/`watch`）宿主覆寫；支援 `define_ephemeral_space()` 動態空間註冊，且具備 `resolve_file_path()`、`iter_space_files()` 與 `file_belongs_to_space()` 公開查詢接口。 | P0 | [P00:DR-01] |
| **FR-02** | 雙階段門檻與四模分級雜湊 (`FingerprintScanner`) | Stage 1 透過 `os.scandir()` 比對 `(mtime_ns, size)` 與 10ms Racy-Clean 時間窗防護；Stage 2 支援四種 `hash_policy`：`adaptive`（`< large_file_threshold_mb` 全量 `blake2b(digest_size=20)`，`>=` 採頭/中/尾各 64KB 共 192KB 稀疏抽樣並帶 `sample2b:` 前綴）、`full_hash`、`stat_only`（`stat:{size}:{mtime_ns}`）、`lazy_stabilized`（背景監聽下對 `time.time() - mtime < 2.0` 大檔標記 `pending_stabilization` 延遲雜湊）。 | P0 | [P00:DR-01] |
| **FR-03** | 二進位快照 (`YFP2`)、Merkle Root 與多消費者獨立游標 | 快照持久化於 `cache://space/snapshots/<space_name>.yfp2.bin`（含 Magic `YFP2`、`head_generation`、`merkle_root`、每檔 `created_gen`/`updated_gen`/`is_deleted` 墓碑紀錄與 `os.replace` 原子寫入）；消費者水位線持久化於 `cache://space/cursors/<consumer_id>.json`，提供 `diff()`、`ack()`、`reset_cursor()`、`consume_diff()` context manager 與 `merkle_root()` O(1) 查詢。 | P0 | [P00:DR-03] |
| **FR-04** | 原生 `watchdog` 背景監聽 (`SpaceWatcherServiceWorker`) | 於 `manifest.json` 宣告 `"pip_dependencies": {"watchdog": ">=4.0.0"}`，於 `contributes/server.json` 註冊 `space-watcher`；支援 500ms 防抖批次收斂、`.yscb.lock` 交易鎖讓路、更新 `YFP2` 快照並透過 `core.events.broadcast("on_space_changed", payload, emit_module="space")` 與程序內 `subscribe()` 派發事件。 | P0 | [P00:DR-02] |
| **FR-05** | 5 個標準 CLI 指令 (`scripts/cli.py`) | 提供 `python yscb.py space {status, scan, files, diff, clean}`，全數支援 `--json` 結構化輸出與 `--space` 動態補全 (`space.providers:get_space_names`)。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 10ms 內快速連續改檔且檔案大小不變 (Racy-Clean) | 當 `abs(scan_start_ns - mtime_ns) < 10_000_000` 時，即使 `(mtime_ns, size)` 與快照一致，強制穿透 Stage 1 重算內容雜湊，且不將該不穩定時間戳鎖死於乾淨快取。 |
| **EC-02** | 二進位快照 `YFP2` 截斷、損毀或空間 `config_hash` 變更 | 讀取失敗或 Magic/Version 不符時拋出 `FingerprintCorruptedError`（上層 `refresh`/`consume_diff` 自動降級全量重建並遞增世代）；若空間 `config_hash` 變更則自動觸發該空間全量重掃並重置游標為全量變更。 |
| **EC-03** | 多消費者中某消費者在 `consume_diff()` 區塊內拋出未處理例外 | `consume_diff()` Context Manager 捕捉例外時**不執行 `ack()`**，保留原 `acked_gen` 水位線，確保下次重試仍能取得相同差異集（At-Least-Once 語意），同時不影響其他已 `ack` 消費者。 |
| **EC-04** | 符號連結循環或路徑穿越 (`..`) | 預設 `follow_symlinks=False`；開啟時以 `(st_dev, st_ino)` 集合追蹤已走訪目錄防範無窮迴圈；`resolve_file_path` 嚴格校驗目標位於空間合法 `include` 根目錄內。 |
| **EC-05** | 宿主執行模組安裝/卸載持有 `.yscb.lock` 期間發生大量檔案事件 | `SpaceWatcherServiceWorker` 偵測到 `.yscb.lock` 存在時延遲防抖批次，待鎖釋放後一次性收斂掃描並派發單次 `on_space_changed`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 | 無變更熱快取下 5,000 檔空間執行 `refresh()` / `merkle_root()` 耗時 `< 30ms`（0 檔案開啟讀取，純 `os.scandir` 記憶體比對）。 |
| **NFR-02** | 依賴與合規 | 僅依賴 Python 標準庫、`core` 與宣告於 `manifest.json` 之 `watchdog>=4.0.0`；100% 通過 `python yscb.py dev check space`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `core.uri.resolve("cache://space", interactive=False)` 用於取得模組快取目錄；所有跨平台相對路徑於快照與事件 Payload 中一律正規化為 POSIX 正斜線（`/`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[contributes/space.json] + [config://space/contribute.json]
                     │
                     ▼
             ┌───────────────┐
             │ SpaceManager  │ (雙軌聚合、URI 解算、iter_space_files)
             └───────┬───────┘
                     │
                     ▼
           ┌────────────────────┐
           │ FingerprintScanner │ (Stage 1: scandir+RacyClean / Stage 2: 4 hash_policy)
           └─────────┬──────────┘
                     │
                     ▼
     ┌───────────────────────────────┐
     │ BinarySnapshotManager (YFP2)  │ ──► cache://space/snapshots/<space>.yfp2.bin
     │ & Multi-Consumer Cursor Store │ ──► cache://space/cursors/<consumer_id>.json
     └───────────────┬───────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
[consume_diff / SDK]    [SpaceWatcherServiceWorker] ──► core.events.broadcast("on_space_changed")
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/space/manifest.json` | New | 模組宣告（`v1.0.0.0`），依賴 `core>=1.2.0` 與 `pip_dependencies: {"watchdog": ">=4.0.0"}`，宣告 `space.storage://` URI |
| `ys_codebase/source/space/README.md` | New | 模組隨包文檔（架構、SDK 用法與 5 個 CLI 說明） |
| `ys_codebase/source/space/contributes/_format.json` | New | `spaces` 擴充點 Schema（含 `hash_policy`、`large_file_threshold_mb`、`watch` 等） |
| `ys_codebase/source/space/contributes/core.json` | New | 註冊 `yscb.py space {status, scan, files, diff, clean}` CLI |
| `ys_codebase/source/space/contributes/server.json` | New | 註冊 `space-watcher` (`space.service:SpaceWatcherServiceWorker`) |
| `ys_codebase/source/space/contributes/agents-workflow.json` | New | 註冊 `skills/how-to-yscb/space_guide.md` 注入 |
| `ys_codebase/source/space/skills/how-to-yscb/space_guide.md` | New | `space` 模組 CLI 與 SDK 速查指南 |
| `ys_codebase/source/space/space/__init__.py` | New | 模組公開門面 API 匯出（`SpaceManager`, `FingerprintScanner`, `BinarySnapshotManager`, `consume_diff`, `diff`, `ack`, `merkle_root` 等） |
| `ys_codebase/source/space/space/exceptions.py` | New | `SpaceError`, `SpaceNotFoundError`, `InvalidSpaceConfigError`, `FingerprintCorruptedError` |
| `ys_codebase/source/space/space/schema.py` | New | `SpaceOrigin`, `HashPolicy`, `SpaceConfig`, `FileFingerprint`, `ScanDiffDetail`, `ScanDiffResult` 資料模型 |
| `ys_codebase/source/space/space/manager.py` | New | `SpaceManager` 雙軌配置聚合、URI 解算、檔案走訪與歸屬判定 |
| `ys_codebase/source/space/space/scanner.py` | New | `BinarySnapshotManager (YFP2)`、多消費者游標管理與 `FingerprintScanner` 四模分級雜湊 |
| `ys_codebase/source/space/space/service.py` | New | `SpaceWatcherServiceWorker` (`watchdog` 監聽、500ms 防抖、`.yscb.lock` 讓路、`on_space_changed` 廣播) |
| `ys_codebase/source/space/space/providers.py` | New | CLI 動態參數補全 `get_space_names(context)` |
| `ys_codebase/source/space/scripts/cli.py` | New | `status`, `scan`, `files`, `diff`, `clean` CLI 實作 |
| `ys_codebase/source/space/scripts/hook.dev.py` | New | `dev` 沙盒環境初始化鉤子 |
| `ys_codebase/source/space/tests/test_space_manager.py` | New | 雙軌空間配置聚合、宿主覆寫、URI 邊界與 `iter_space_files` 單元測試 |
| `ys_codebase/source/space/tests/test_scanner_and_cursors.py` | New | 四模分級雜湊、Racy-Clean、`YFP2` 快照損毀自癒、`merkle_root` 與多消費者獨立水位線隔離測試 |
| `ys_codebase/source/space/tests/test_service_and_cli.py` | New | `SpaceWatcherServiceWorker` 防抖與事件廣播、以及 5 個 CLI 指令整合測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 統一快照與空間級快照支援**：同時支援單一空間快照（`<space_name>.yfp2.bin`）與跨空間統一視圖，並將世代號（`head_generation`）與檔案墓碑（`is_deleted`）內嵌於 `YFP2` 紀錄中，使任一 `consumer_id` 皆能依據自身 `acked_gen` O(N) 計算出精確的 `(added, modified, deleted)` 集合，且同時向下相容直接傳入 `SpaceManager` + `FingerprintScanner` 的低階調用。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# space/schema.py
class SpaceOrigin(str, Enum):
    BUILTIN = "builtin"
    HOST = "host"
    MERGED = "merged"
    EPHEMERAL = "ephemeral"

class HashPolicy(str, Enum):
    ADAPTIVE = "adaptive"
    FULL_HASH = "full_hash"
    STAT_ONLY = "stat_only"
    LAZY_STABILIZED = "lazy_stabilized"

@dataclass
class SpaceConfig:
    name: str
    include: List[Path]
    exclude: List[str] = field(default_factory=list)
    file_patterns: List[str] = field(default_factory=list)
    description: str = ""
    hash_policy: str = "adaptive"
    large_file_threshold_mb: int = 10
    follow_symlinks: bool = False
    watch: bool = True
    weight: float = 1.0
    origin: SpaceOrigin = SpaceOrigin.BUILTIN
    owner_modules: List[str] = field(default_factory=list)
    raw_include_uris: List[str] = field(default_factory=list)

@dataclass
class FileFingerprint:
    path: str
    mtime_ns: int
    size: int
    content_hash: str
    source_root: str = ""
    created_gen: int = 1
    updated_gen: int = 1
    is_deleted: bool = False
    pending_stabilization: bool = False

@dataclass
class ScanDiffDetail:
    added: Set[str] = field(default_factory=set)
    modified: Set[str] = field(default_factory=set)
    deleted: Set[str] = field(default_factory=set)
    unchanged: Set[str] = field(default_factory=set)

    @property
    def dirty_files(self) -> Set[str]: ...
    @property
    def has_changes(self) -> bool: ...

@dataclass
class ScanDiffResult:
    has_changes: bool
    added_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    detail: ScanDiffDetail = field(default_factory=ScanDiffDetail)
    from_generation: int = 0
    to_generation: int = 0
    merkle_root: str = ""

# space/manager.py
class SpaceManager:
    def __init__(
        self,
        context: Optional[Any] = None,
        project_root: Optional[Path] = None,
        storage_dir: Optional[Path] = None,
        custom_spaces: Optional[Dict[str, Any]] = None,
    ) -> None: ...
    def load_spaces(self) -> Dict[str, SpaceConfig]: ...
    def list_spaces(self) -> Dict[str, SpaceConfig]: ...
    def get_space(self, name: str) -> SpaceConfig: ...
    def define_ephemeral_space(self, name: str, config: Dict[str, Any]) -> SpaceConfig: ...
    def iter_space_files(self, name: Optional[str] = None) -> List[Tuple[str, Path, Path]]: ...
    def file_belongs_to_space(self, rel_or_abs_path: Union[str, Path], space_cfg: SpaceConfig) -> bool: ...
    def resolve_file_path(self, rel_path: str, space_name: Optional[str] = None) -> Optional[Path]: ...

# space/scanner.py & space/__init__.py
def refresh(space_name: Optional[str] = None, *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None, force_full_hash: bool = False) -> ScanDiffResult: ...
def snapshot(space_name: Optional[str] = None, *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None, auto_refresh: bool = False) -> Dict[str, FileFingerprint]: ...
def merkle_root(space_name: Optional[str] = None, *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None, auto_refresh: bool = True) -> str: ...
def diff(space_name: Optional[str] = None, consumer_id: str = "default", *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None, auto_refresh: bool = True) -> ScanDiffResult: ...
def ack(space_name: Optional[str] = None, consumer_id: str = "default", generation: Optional[int] = None, *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None) -> None: ...
def reset_cursor(space_name: Optional[str] = None, consumer_id: str = "default", *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None) -> None: ...
@contextmanager
def consume_diff(space_name: Optional[str] = None, consumer_id: str = "default", *, context: Optional[Any] = None, space_manager: Optional[SpaceManager] = None, auto_refresh: bool = True) -> Iterator[ScanDiffResult]: ...
def subscribe(callback: Callable[[Dict[str, Any]], None], *, spaces: Optional[List[str]] = None) -> Callable[[], None]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SpaceNotFoundError`：查詢未註冊之 `space_name` 時拋出。
  - `InvalidSpaceConfigError`：空間配置缺失 `include`、型別錯誤或欄位值非法時拋出。
  - `FingerprintCorruptedError`：`YFP2` 快照 Magic/Version/CRC 不符或截斷時拋出。
- **階段決策紀錄**：`[P03:DR-01]` 頂層函數（`refresh`, `diff`, `ack`, `consume_diff`, `merkle_root`）之 `space_name` 支援傳入特定空間名或 `None`（代表 `"unified"` 全空間聚合視圖），完美支援 `knowledge-db` 統一索引與單空間消費者兩種模式。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：當一個檔案在 `gen=2` 新增、又在 `gen=3` 被刪除，若某個 `consumer_id` 的 `acked_gen=1`，計算 `diff` 時會如何表現？*
  - *答*：由於 `created_gen (2) > acked_gen (1)` 且當前 `is_deleted=True`，該短命檔案對 `acked_gen=1` 的消費者而言從未存在過，計算器自動將其抵銷（既不列入 `added` 也不列入 `deleted`）；若 `created_gen (1) <= acked_gen (1)` 且 `updated_gen (3) > acked_gen (1)` 且 `is_deleted=True`，則精確歸入 `deleted`！

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/space/README.md` | New | `module:space` 隨包模組手冊與 CLI/SDK 說明 |
| **專題手冊** | `docs/Architecture/README.md` | Modify | 於 Phase 7 結案時補充 `space` 底座模組架構定位 |
| **設計決策** | `docs/Architecture/DESIGN_NOTES.md` | Modify | 於 Phase 7 登記 `YFP2` 多消費者游標隔離與分級雜湊設計決策 |
| **微觀註解** | 源碼檔案 Docstrings | New | 完整編寫公開類別與函式 Docstrings（零工單編號噪音） |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 記錄新增 `space` 模組與 `knowledge-db` 遷移摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_01` 規格定案，進入實作與測試。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `ys_codebase/source/space/` 模組配置與擴充點契約（`manifest.json`、`contributes/{_format,core,server,agents-workflow}.json`、`README.md`、`skills/how-to-yscb/space_guide.md`）
- [x] **TASK-02**：實作 `space/{exceptions,schema,manager,scanner,service,providers,__init__}.py` 及 `scripts/{cli,hook.dev}.py`
- [x] **TASK-03**：撰寫 `ys_codebase/source/space/tests/` 單元與整合測試套件，執行 `dev check space`、`dev test space` 與 `module install space@build`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

