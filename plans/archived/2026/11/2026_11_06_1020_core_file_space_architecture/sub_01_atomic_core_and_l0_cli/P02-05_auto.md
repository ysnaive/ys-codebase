# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_01_atomic_core_and_l0_cli  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 已於 [P01_requirements_spec.md](./P01_requirements_spec.md) 完成定案並經盲眼審查通過（`FR-01` ~ `FR-07`, `EC-01` ~ `EC-06`, `NFR-01` ~ `NFR-03`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[contributes/core.json] (各已安裝模組) + [config/core/contribute.json] (專案)
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ core.space.registry (SpaceRegistry)                                      │
│  1. 收集 Raw Presets (<owner>/<preset>) 與 Raw Spaces (<owner>/<space>)   │
│  2. 展開顯式 presets (含內建 @gitignore 解析器)                            │
│  3. 建構 SpaceConfig (含預編譯三座標匹配器 CompiledSpaceFilter)            │
│  4. 提供雙粒度查詢：精準 (<owner>/<name>) 與短名自動聯集 (<name>)          │
└──────────────────┬───────────────────────────────┬───────────────────────┘
                   │                               │
                   ▼                               ▼
┌─────────────────────────────────────┐ ┌──────────────────────────────────┐
│ core.space.matcher & walker         │ │ core.space.hasher                │
│  • match_path(): 單點三座標判定與解釋│ │  • compute_file_hash():          │
│    (URI / project_rel+entry_rel /   │ │    stat_only / adaptive / full   │
│     basename or segment)            │ │  • hash_target():                │
│  • iter_space_files(): os.scandir   │ │    單檔指紋或空間級 Merkle Root   │
│    目錄級剪枝 + DirEntry.stat() 複用 │ │    (Blake2b 16-byte hex digest)  │
└──────────────────┬──────────────────┘ └──────────────────┬───────────────┘
                   └───────────────────┬───────────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L0 CLI (scripts/cli.py & core/commands/dispatcher.py)                    │
│  • 路由：yscb.py core file-space <subcmd> | yscb.py fs <subcmd>          │
│  • 子命令：spaces | presets | match | ls | hash (支援 --json)             │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/space/__init__.py` | New | 匯出 `core.space` 公共原子 API 與資料結構（`SpaceRegistry`, `SpaceConfig`, `PresetConfig`, `HashPolicy`, `SpaceFileEntry`, `MatchExplainResult`, `SpaceError`, `SpaceNotFoundError`, `match_path`, `iter_space_files`, `compute_file_hash`, `hash_space_or_path`） |
| `ys_codebase/source/core/core/space/exceptions.py` | New | 定義 `SpaceError` 與 `SpaceNotFoundError` 結構化例外階層 |
| `ys_codebase/source/core/core/space/schema.py` | New | 定義 `HashPolicy`、`PresetConfig`、`SpaceConfig`、`RuleItem`、`CompiledRuleSet` 與三座標預編譯規則匹配引擎（URI / `project_rel`+`entry_rel` / 名稱區段）及 `@gitignore` 解析器 |
| `ys_codebase/source/core/core/space/registry.py` | New | 實作 `SpaceRegistry`：載入 `<module>/<name>` 與 `project/<name>` 空間與預設集定義、展開顯式 `presets`、提供精準與短名聯集查詢、單點 `match_path` 解釋器與 `iter_space_files` 零冗餘 `scandir` 剪枝走訪器 |
| `ys_codebase/source/core/core/space/hasher.py` | New | 實作 `compute_file_hash`（`stat_only`/`adaptive`/`full_hash` Blake2b）與 `hash_target`（單檔或空間級指紋與決定性 `merkle_root` 計算） |
| `ys_codebase/source/core/core/__init__.py` | Modify | 暴露 `space` 子模組至 `core.__all__` |
| `ys_codebase/source/core/contributes/_format.json` | Modify | 新增 `PresetDef`、`SpaceDef` 型別定義與頂層 `presets`、`spaces` 擴充點 |
| `ys_codebase/source/core/contributes/core.json` | Modify | 新增 `file-space` 與 `fs` L0 CLI 命令樹宣告（`spaces`, `presets`, `match`, `ls`, `hash`），並註冊基礎內建預設集（如 `common-ignore`, `python-ignore`, `yscb-runtime-ignore`） |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 於頂層命令路由判斷中，當 `first_token` 同時存在於 `core_commands` 與已安裝非 `core` 外部模組名稱時（如 `sub_04` 前之 `file-space`），未帶 `core` 前綴時優先路由至外部模組，確保 `yscb.py core file-space` 與 `yscb.py fs` 直通 `core` 且舊 `yscb.py file-space` 零衝突 |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 新增 `file_space_*` 與 `fs_*` L0 CLI 處理函式（`spaces`, `presets`, `match`, `ls`, `hash`） |
| `ys_codebase/source/core/tests/test_space.py` | New | `core.space` 原子引擎與 L0 CLI 完整單元與邊界測試套件（涵蓋 `FR-01`~`FR-07`, `EC-01`~`EC-06`, `NFR-01`~`NFR-03`） |
| `docs/core/README.md` | Modify | 同步補充 `core.space` 原子引擎與 `file-space` / `fs` L0 CLI 導覽說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 規則來源追蹤與三座標預編譯結構 (`RuleItem` & `CompiledRuleSet`)**：
  - 為使 `match` 原語能精確回報「哪一條規則（來自空間自身或哪個 preset）導致檔案被排除或包含」，每條規則在展開時封裝為 `RuleItem(pattern, source, is_negated)`（例如 `source="preset:core/python-ignore"` 或 `source="space:project/docs"`）。
  - 一般 `ls` 高速走訪使用預編譯之集合與合併正規表示式達成 $O(1)$ 判定；一旦觸發目錄剪枝或 `match_path` 單點診斷，即可瞬間定位具體命中之 `RuleItem`。
- **[P02:DR-02] 短名聯集與多入口之規範邏輯路徑消歧 (`Canonical Display RelPath`)**：
  - 走訪產出之 `SpaceFileEntry` 以 `os.path.normcase(os.path.realpath(abs_path))`（當 `follow_symlinks=False` 時為 `os.path.normcase(os.path.abspath(abs_path))`）作為實體去重鍵；若同一檔案被多個限定空間（如 `agents-workflow/docs` 與 `project/docs`）命中，自動聚合其 `matched_spaces: Tuple[str, ...]`。
  - 邏輯相對路徑 `rel_path` 優先計算相對於 `project://` 之 POSIX 相對路徑；若該入口位於 `project://` 之外（`EC-02`），則退回以相對於所屬 `entry` 之路徑表示，徹底消除 `ValueError` 崩潰。
- **[P02:DR-03] 頂層命令與外部模組同名避讓機制 (`dispatcher.py`)**：
  - 在 `core/commands/dispatcher.py` 判斷 `if first_token in core_commands:` 時，若 `registry.resolve_module_name(first_token)` 解析出一個非 `"core"` 之已安裝外部模組（如 `"file-space"`），則頂層無 `core` 前綴呼叫自動優先交由該外部模組處理；唯有顯式呼叫 `yscb.py core file-space ...` 或使用無衝突別名 `yscb.py fs ...` 時路由至 `core`；待 `sub_04` 移除外部 `file-space` 模組後，`yscb.py file-space ...` 將無縫自動落入 `core_commands`，達成 0 過渡陣痛。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/space/exceptions.py
class SpaceError(Exception): ...
class SpaceNotFoundError(SpaceError): ...

# ys_codebase/source/core/core/space/schema.py
class HashPolicy(str, Enum):
    ADAPTIVE = "adaptive"
    FULL_HASH = "full_hash"
    STAT_ONLY = "stat_only"
    LAZY_STABILIZED = "lazy_stabilized"

@dataclass(frozen=True)
class RuleItem:
    raw_pattern: str
    source: str
    is_negated: bool = False

@dataclass(frozen=True)
class PresetConfig:
    qualified_name: str
    owner: str
    short_name: str
    description: str = ""
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()

@dataclass
class SpaceConfig:
    qualified_name: str
    owner: str
    short_name: str
    description: str = ""
    entries: Tuple[str, ...] = ()
    presets: Tuple[str, ...] = ()
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    hash_policy: HashPolicy = HashPolicy.ADAPTIVE
    large_file_threshold_mb: int = 10
    follow_symlinks: bool = False
    effective_include: Tuple[RuleItem, ...] = ()
    effective_exclude: Tuple[RuleItem, ...] = ()
    unresolved_presets: Tuple[str, ...] = ()

    def resolve_entries(self, project_root: Path) -> List[Tuple[str, Path, bool]]: ...
    def check_dir_excluded(self, dir_abs: Path, entry_abs: Path, project_root: Path) -> Optional[RuleItem]: ...
    def match_file(self, file_abs: Path, entry_abs: Path, project_root: Path) -> Tuple[bool, Optional[RuleItem], Optional[RuleItem]]: ...

# ys_codebase/source/core/core/space/registry.py
@dataclass(frozen=True)
class SpaceFileEntry:
    rel_path: str
    abs_path: Path
    entry_path: Path
    matched_spaces: Tuple[str, ...]
    size: int
    mtime_ns: int
    ctime_ns: int

@dataclass(frozen=True)
class SpaceMatchDetail:
    qualified_space: str
    matched: bool
    reason: str
    matched_entry: Optional[str] = None
    include_rule: Optional[str] = None
    include_source: Optional[str] = None
    exclude_rule: Optional[str] = None
    exclude_source: Optional[str] = None

@dataclass(frozen=True)
class MatchExplainResult:
    target_path: str
    abs_path: str
    matched: bool
    matched_spaces: Tuple[str, ...]
    details: Tuple[SpaceMatchDetail, ...]

class SpaceRegistry:
    def __init__(
        self,
        project_root: Optional[Path] = None,
        yscb_dir: Optional[Path] = None,
        *,
        raw_presets: Optional[Dict[str, Dict[str, Any]]] = None,
        raw_spaces: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None: ...
    @property
    def project_root(self) -> Path: ...
    def list_presets(self, owner: Optional[str] = None) -> List[PresetConfig]: ...
    def resolve_presets(self, query: str) -> List[PresetConfig]: ...
    def list_spaces(self, owner: Optional[str] = None) -> List[SpaceConfig]: ...
    def resolve_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]: ...
    def match_path(self, file_path: Union[str, Path], space_query: Optional[str] = None) -> MatchExplainResult: ...
    def iter_space_files(
        self,
        space_query: Optional[str] = None,
        *,
        pattern: Optional[str] = None,
    ) -> List[SpaceFileEntry]: ...

# ys_codebase/source/core/core/space/hasher.py
@dataclass(frozen=True)
class FileHashEntry:
    rel_path: str
    abs_path: str
    size: int
    mtime_ns: int
    content_hash: str
    matched_spaces: Tuple[str, ...]

@dataclass(frozen=True)
class SpaceHashResult:
    target: str
    target_type: str  # "file" | "space"
    policy: str
    file_count: int
    merkle_root: str
    files: Tuple[FileHashEntry, ...]

def compute_file_hash(
    file_path: Path,
    size: Optional[int] = None,
    mtime_ns: Optional[int] = None,
    policy: Union[HashPolicy, str] = HashPolicy.ADAPTIVE,
    large_file_threshold_mb: int = 10,
) -> str: ...

def hash_target(
    registry: SpaceRegistry,
    target: Optional[str] = None,
    *,
    policy: Optional[Union[HashPolicy, str]] = None,
) -> SpaceHashResult: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SpaceNotFoundError`：當 `resolve_spaces(query)` 或 `resolve_presets(query)` 找不到匹配之 `<owner>/<name>` 或 `<name>` 時拋出。
  - CLI 層捕獲 `SpaceError` / `FileNotFoundError`，於標準輸出或 `--json` 輸出結構化 `{"status": "error", "error": str(exc)}` 並回傳 `exit code 1`。
- **階段決策紀錄**：`[P03:DR-01]` 統一將 `core/scripts/cli.py` 中之 `file-space` 與 `fs` 子命令透過共用內部 handler 分派，確保 `yscb.py core file-space <subcmd>` 與 `yscb.py fs <subcmd>` 行為 100% 同構。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-07 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-03 指標約束（純標準庫、預編譯匹配、POSIX 路徑正規化）
- **靈魂拷問與防護解法**：
  1. **問：若專案 `.gitignore` 中包含 `!important.log` 負向規則，且 Space 引用了 `@gitignore` 但自身同時宣告了 `exclude: ["*.log"]`，誰優先？**
     - **答**：Space 顯式宣告之 `exclude` 優先於 `@gitignore` 內部之 `!` 豁免（`EC-06`）；`@gitignore` 被封裝為獨立的內部忽略評估器，僅判斷「該路徑是否被 `.gitignore` 視為忽略」，若被 `.gitignore` 忽略則視為命中 `@gitignore` 排除規則。
  2. **問：當同一個檔案同時落入一個 Space 的兩個不同 `entries`（例如 `yscb://source` 與 `yscb://source/core`）時，`entry_rel` 怎麼判定？**
     - **答**：對該 Space 的所有命中的 `entries` 逐一評估，採用最深（最具體）之包含 `entry` 計算 `entry_rel`，並於實體檔案去重時確保單一檔案僅出現一次。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 新增 `core.space` 原子引擎與 `file-space` (`fs`) L0 CLI 章節說明 |
| **專題手冊** | `docs/core/uri_protocols.md` | N/A | 本階段未新增 URI 協議，無須變更 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 架構決策已記錄於計畫文件與模組手冊 |
| **微觀註解** | `ys_codebase/source/core/core/space/*.py` | Modify | 完整編寫公開類別與函式之 Docstrings（遵守零工單編號註解鐵律） |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_01` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `core.space` 獨立放置於 `ys_codebase/source/core/core/space/` 子套件，維持 `core` 頂層命名空間整潔並符合 SRP。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `ys_codebase/source/core/contributes/_format.json` 與 `contributes/core.json`（新增 `PresetDef`, `SpaceDef`, `presets`, `spaces` 及 `file-space` / `fs` L0 CLI 宣告），並更新 `core/commands/dispatcher.py` 支援同名外部模組優先避讓
- [x] **TASK-02**：實作 `core/space/{exceptions.py,schema.py,registry.py,hasher.py,__init__.py}` 原子引擎與 `core/scripts/cli.py` 五大 L0 CLI 子命令（`spaces`, `presets`, `match`, `ls`, `hash`）
- [x] **TASK-03**：編寫 `ys_codebase/source/core/tests/test_space.py` 單元與邊界測試（覆蓋 `FR-01`~`FR-07`, `EC-01`~`EC-06`, `NFR-01`~`NFR-03`），通過 `dev check core`、`dev test core -q` 並安裝 `core@build`
- [x] **TASK-DOC**：同步更新 `docs/core/README.md` 與源碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
