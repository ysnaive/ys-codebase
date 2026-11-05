# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：2026_11_05_0321_kdb_cli_and_engine_optimization  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 模型：Gemini  
> 依據 P00：[R01_kdb_cli_and_engine_optimization.md](./R01_kdb_cli_and_engine_optimization.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | CLI 文字輸出預設拔除冗餘 `(file:///...)` 絕對路徑連結 (`OPT-01`) | 1. 將 `knowledge_db/formatter.py` (`ResultFormatter`) 與 `ast_engine/formatter.py` (`ASTResultFormatter`) 之 `file_uri` 預設值改為 `False`；當 `file_uri=False` 時，強制令 `effective_basename = False`，確保永遠輸出完整專案相對路徑與行號（如 `ys_codebase/core/uri.py:L10-25`），嚴禁退化為純檔名。<br>2. 於 `knowledge-db/contributes/core.json` 與 `ast/contributes/core.json` 新增獨立選項群組 `"uri"` 之 `--file-uri` 旗標（不與 `--json` 互斥）；當顯式傳入 `--file-uri` 或 `--md` 匯出模式時自動啟用 `file_uri=True`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | CLI 預設 `auto` 單結果折疊與多子項去重 (`OPT-02`) | 1. 於 `knowledge-db/scripts/cli.py` 區分顯式傳入 `--simple`（維持 `detail_mode="simple"` 與 `"清單模式"` 標頭）與未帶層級旗標之預設模式（設為 `tier="auto"`, `detail_mode="auto"`, `snippet=False`）。<br>2. 於 `knowledge_db/formatter.py` 的 `detail_mode == "auto"` 分支：當單檔僅命中 1 個符號 (`len(res.items) == 1`) 時折疊為單行並附帶行號與分數；當單檔命中多個符號 (`len(res.items) > 1`) 時，父標題 `#01` 僅印出檔案相對路徑（不重複掛載首項行號），子項目 `#01.1` ~ `#01.3` 僅印出符號名稱、分數與 `(Lines X~Y)`（不再重複印出檔名）。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | JSON 輸出依 `tier` 分級瘦身 (`OPT-03`) | 於 `knowledge_db/formatter.py` (`format_search_json`)：在 `tier in ("simple", "auto", "snippet")` 且未傳入 `--file-uri` 時，預設省略冗餘之 `"file_uri"` 欄位及空字串選填欄位；在 `tier == "detail"`（`--json --detail`）或顯式傳入 `--file-uri` 時，100% 保留完整固定 Schema 鍵名（含 `"file_uri"`）。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | 註冊 `kdb` 短別名並對齊軌跡審計器 (`OPT-04`) | 1. 於 `knowledge-db/contributes/core.json` 的 `commands.cmd` 頂層新增 `"kdb"` 短別名（指向與 `"knowledge-db"` 相同之子指令結構）。<br>2. 同步更新 `agents_workflow/plans/_trace_parser.py` (`_extract_yscb_invocations` 與 `_analyze_turn_commands`)，支援辨識 `python yscb.py kdb ...` 並將模組名稱歸一化映射為 `"knowledge-db"`，防止觸發 `UNINDEXED_BLIND_READ` 誤報。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-05** | `ASTEngine` 圖譜延遲載入與 `unified.meta.json` 熱查詢短路 (`OPT-05`) | 1. 將 `ast_engine/engine.py` 的 `_ensure_loaded_from_disk()` 拆分為 `_ensure_symbols_loaded()` 與 `_ensure_graph_loaded()`（僅於 `callers`/`callees`/`impact` 時才解壓 `unified.graph.bin.gz`）。<br>2. 於 `ast_engine/engine.py` 寫入 `unified.symbols.bin.gz` 時同步寫入輕量 `unified.meta.json`（含 `generation`, `space_generations`, `symbols_count`, `symbols_mtime_ns`, `symbols_size`）；`knowledge_db/pipeline.py` 熱查詢與 `get_status` 優先讀取並校驗 `unified.meta.json`，命中時免除解壓 2.3MB `unified.symbols.bin.gz`。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-06** | 文字模式 `limit="auto"` 動態相對分數斷崖截斷 (`OPT-06`) | 於 `knowledge_db/pipeline.py` 與 `engine.py` 的 `search()` 新增 `adaptive_limit: bool = False` 參數（預設 `False` 不截斷以保障 SDK 與 `--json` 穩定性）；僅當 CLI 處於文字模式且未顯式指定 `--limit`（即 `(not is_json) and limit_val == "auto"`）時傳入 `adaptive_limit=True`，於 `rank >= 3` 且分數低於 `top_score * 0.38`（或相鄰跌幅 `> 45%`）時自動截斷低分長尾雜訊。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-07** | `InvertedIndex` 內部 `0..n` 整數 `doc_idx` 字串駐留與稀疏欄位詞頻 (`OPT-07`) | 1. 於 `knowledge_db/retrieval.py` 的 `InvertedIndex` 內部建立單調遞增 + Free-List 回收佇列 (`_free_doc_indices`) 之 `_doc_id_table: List[Optional[str]]` 與 `_space_table: List[str]`，將數萬個 `Posting` 物件內部的 `doc_id`/`space` 字串替換為整數 `doc_idx` 與 `space_idx`。<br>2. `Posting` 維持 `__slots__` 並透過 `@property` 動態解析 `.doc_id`、`.space`、`.spaces` 與 `to_dict()`；將 `field_freqs` 封裝為僅儲存非零欄位的 `SparseFieldFreqs(dict)`（`__missing__` 回傳 `0`）。 | P1 | [P00:DR-02], [P00:DR-03] |
| **FR-08** | `get_status()` 消除雙重 `os.walk` 磁碟掃描 (`OPT-08`) | 於 `knowledge_db/engine.py` (`get_status`) 的 `if snap_path.exists():` 分支內，直接透過已載入之 `snap_state.entries.values()` 計算存活檔案數 `sum(1 for fp in snap_state.entries.values() if not getattr(fp, "is_deleted", False))`，僅於快照不存在 (`file_count is None`) 時才 fallback 呼叫 `iter_space_files(sp_name)`。 | P1 | [P00:DR-01], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 使用者同時傳入 `--json` 與 `--file-uri` | 因 `--file-uri` 獨立於 `"uri"` 選項群組（非 `"format"` 群組），不會觸發 `MutualExclusionError`，且 JSON 輸出會強制包含 `"file_uri"` 欄位。 |
| **EC-02** | 外部單獨執行 `ast build` 更新了 `unified.symbols.bin.gz`，但 `unified.meta.json` 缺失或指紋不符 | `ASTEngine.get_Persisted_Meta()` 比對 `symbols_mtime_ns` 與 `symbols_size` 失敗時，自動退回 `_ensure_symbols_loaded()` 完整載入並自癒重寫 `unified.meta.json`。 |
| **EC-03** | 多執行緒測試（如 `test_service_worker.py`）直接賦值 `idx.symbols[s.id] = s` 並呼叫 `idx.to_dict()` | `InvertedIndex._register_doc_id` 具備冪等自動註冊能力，且 `Posting` 的 `@property` 與 `to_dict()` 100% 相容字串 `doc_id` 存取；`patch_incremental` 採用 Free-List 回收而不平移陣列索引。 |
| **EC-04** | `file-space` 快照內含已刪除檔案之 Tombstone (`fp.is_deleted == True`) | `get_status()` 統計存活檔案數時嚴格過濾 `not getattr(fp, "is_deleted", False)`，確保與 `iter_space_files` 數量一致。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | Context 精簡度 | 預設 CLI 搜尋文字輸出字元數下降 `>= 60%`（單次搜尋由 `~1,840 chars` 降至 `~620 chars`）；預設 `--json` 輸出體積下降 `>= 25%`。 |
| **NFR-02** | 效能與相容性 | 熱查詢免除 `unified.symbols.bin.gz` 與 `unified.graph.bin.gz` 冗餘解壓；`ast`、`knowledge-db`、`agents-workflow` 全數單元測試與 `dev check` 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 遵守 `2026_11_04_1739_sys_path_and_five_semantic_spaces` 新立之靜態守門：非 `core` 模組嚴禁出現任何 `sys.path` 變動語句（`_find_sys_path_mutations`），且持久索引路徑位於 `storage.local://`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[CLI Layer: yscb kdb / knowledge-db]
  |-- contributes/core.json ("kdb" alias + "--file-uri" in "uri" group)
  |-- scripts/cli.py (tier="auto" default vs explicit "--simple"; adaptive_limit=(not is_json and limit=="auto"))
  v
[Formatting Layer: knowledge_db/formatter.py & ast_engine/formatter.py]
  |-- format_file_link(file_uri=False -> effective_basename=False -> relative path only)
  |-- detail_mode="auto": fold 1-item hits; deduplicate child paths for multi-item hits
  |-- format_search_json: strip "file_uri" & empty strings in simple/auto/snippet tiers
  v
[Engine & Retrieval Layer: ast_engine/engine.py, knowledge_db/{engine,pipeline,retrieval}.py]
  |-- ASTEngine: unified.meta.json (mtime_ns + size bound) + lazy _ensure_graph_loaded()
  |-- KnowledgeDBEngine.get_status(): count active entries from SnapshotState without 2nd os.walk
  |-- InvertedIndex: _doc_id_table (0..n + _free_doc_indices) + SparseFieldFreqs(dict)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 新增 `"uri"` 群組之 `--file-uri` 選項定義 |
| `ys_codebase/source/ast/ast_engine/formatter.py` | Modify | `file_uri` 預設改為 `False`，且 `file_uri=False` 時強制顯示相對路徑 (`effective_basename=False`) |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 拆分 `_ensure_symbols_loaded()` 與 `_ensure_graph_loaded()`，並實作 `unified.meta.json` 讀寫與指紋校驗 |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 解析並傳遞 `--file-uri` 旗標至 `ASTResultFormatter` |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 新增頂層 `"kdb"` 指令別名與 `"uri"` 群組之 `--file-uri` 選項 |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 實作 `OPT-01`（預設 `file_uri=False`）、`OPT-02`（`auto` 單項折疊與多子項去重）、`OPT-03`（JSON 依 `tier` 分級瘦身） |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `search()` 支援 `adaptive_limit: bool = False`；`get_status()` 直接由 `snap_state.entries` 計算存活檔案數 (`OPT-08`) |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 串接 `ASTEngine` 之輕量 `unified.meta.json` 與 `_ensure_symbols_loaded()` (`OPT-05`)，並實作 `adaptive_limit` 相對斷崖截斷 (`OPT-06`) |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 實作 `SparseFieldFreqs(dict)` 與 `InvertedIndex` 內部 `0..n` `doc_idx` 單調 Free-List 字串駐留表 (`OPT-07`) |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 區分未帶參預設 `tier="auto"` 與顯式 `--simple`，傳遞 `file_uri` 與 `adaptive_limit` |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 更新 `file_uri=False` 預設斷言並新增 `file_uri=True`、`OPT-05`~`OPT-08` 單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | 更新 CLI 預設相對路徑、預設 `auto` 模式、`--file-uri`、`kdb` 別名與 JSON 分級瘦身測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 新增 `InvertedIndex` `doc_idx` 駐留、Free-List 增量回收與 `SparseFieldFreqs` 驗證 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_trace_parser.py` | Modify | 支援辨識 `yscb.py kdb` 短別名並歸一化為 `"knowledge-db"` (`OPT-04`) |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 新增 `OPT-01` `file_uri=False/True` 與 `OPT-05` `unified.meta.json` 及圖譜惰性載入單元測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `python yscb.py kdb search` 免誤報 `UNINDEXED_BLIND_READ` 與模組名稱歸一化單元測試 |
| `docs/knowledge-db/README.md` | Modify | 同步更新 `kdb` 短別名、`--file-uri` 與預設 `auto` 精簡輸出說明 |
| `docs/knowledge-db/retrieval.md` | Modify | 同步更新 `InvertedIndex` `doc_idx` 駐留、動態斷崖截斷與 `unified.meta.json` 機制說明 |
| `CHANGELOG.md` | Modify | 記錄 `2026_11_05_0321_kdb_cli_and_engine_optimization` 優化變更摘要 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 採納盲審校準處方：CLI 輸出層維持無狀態相對路徑（`file_uri=False` 時強制 `effective_basename=False`），將 `0..n` 整數唯一碼下沉為 `InvertedIndex` 內部之 `doc_idx` 字串駐留表（搭配 `_free_doc_indices` 避免刪除時陣列索引平移）。
- **[P02:DR-02]** `ASTEngine` 拆分為 `_ensure_symbols_loaded()` 與 `_ensure_graph_loaded()`，使 `knowledge-db` 永遠不會載入其用不到的 `unified.graph.bin.gz`，並以綁定 `symbols_mtime_ns` 與 `symbols_size` 的 `unified.meta.json` 加速熱查詢世代校驗。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/knowledge-db/knowledge_db/formatter.py
class ResultFormatter:
    def __init__(self, project_root: str, file_uri: bool = False) -> None: ...
    def format_file_link(
        self,
        rel_path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        use_basename: bool = True,
    ) -> str: ...
    def format_search_json(
        self,
        response: SearchResponse,
        tier: str = "simple",
        include_file_uri: bool = False,
    ) -> str: ...

# ys_codebase/source/ast/ast_engine/engine.py
class ASTEngine:
    def _ensure_symbols_loaded(self) -> None: ...
    def _ensure_graph_loaded(self) -> None: ...
    def get_persisted_meta(self) -> Dict[str, Any]: ...

# ys_codebase/source/knowledge-db/knowledge_db/retrieval.py
class SparseFieldFreqs(dict):
    def __missing__(self, key: str) -> int: ...

class Posting:
    __slots__ = ("doc_idx", "_index_ref", "term_freq", "field_freqs", "_fallback_doc_id", "_fallback_space", "_fallback_spaces")
    @property
    def doc_id(self) -> str: ...
    @property
    def space(self) -> str: ...
    @property
    def spaces(self) -> Tuple[str, ...]: ...
    def to_dict(self) -> Dict[str, Any]: ...

# ys_codebase/source/knowledge-db/knowledge_db/engine.py & pipeline.py
class KnowledgeDBEngine:
    def search(
        self,
        query: str,
        space: Optional[str] = None,
        ftype: Optional[str] = None,
        limit: int = 20,
        min_score: float = 0.5,
        snippet: bool = False,
        detail: bool = False,
        adaptive_limit: bool = False,
    ) -> SearchResponse: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `ASTEngine.get_persisted_meta()` 讀取 `unified.meta.json` 若遭遇 `OSError`、`JSONDecodeError` 或 `symbols_mtime_ns`/`symbols_size` 不符，自動無感回退至 `_ensure_symbols_loaded()` 並重寫 `unified.meta.json`，絕不向呼叫端拋出未預期例外。
  - `Posting` 若在未綁定 `InvertedIndex` 之獨立單元測試中被直接實例化（傳入 `doc_id="..."`），自動透過 `_fallback_doc_id` / `_fallback_space` 屬性無損相容。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有既有公開方法之位置參數與預設行為向後相容（`adaptive_limit` 預設 `False`、`Posting` 建構子相容 `doc_id` 關鍵字參數）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-08 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束，零新增第三方依賴，且遵守非 `core` 模組零 `sys.path` 變動紅線
- **靈魂拷問與防護解法**：
  - *問：若舊版磁碟快取 `lexical.index.bin.gz` 反序列化載入時仍為舊版字典結構，新版 `InvertedIndex.from_dict` 是否會崩潰？*
  - *答*：`InvertedIndex.to_dict()` 與 `from_dict()` 維持雙向相容（序列化時支援输出 `doc_id_table` 緊湊格式並相容舊版 `doc_id` 字串欄位，反序列化時自動將舊版 `Posting` 轉換註冊入 `_doc_id_table` 與 `SparseFieldFreqs`）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 更新 `kdb` 短別名、`--file-uri` 旗標與預設 `auto` 精簡輸出說明 |
| **專題手冊** | `docs/knowledge-db/retrieval.md` | Modify | 補充 `InvertedIndex` `doc_idx` 駐留、動態分數斷崖截斷與 `unified.meta.json` 快照標頭說明 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 既有設計備忘已涵蓋，免更防膨脹 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `ResultFormatter`, `ASTEngine`, `InvertedIndex`, `Posting` 之 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `knowledge-db`、`ast`、`agents-workflow` 本次優化摘要 |

- **決策定稿**：**[P04:DR-01]** 規格審查通過，進入 Phase 05 實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `ast` 模組之 `OPT-01`（`--file-uri` 旗標與 `ASTResultFormatter` 預設相對路徑）與 `OPT-05`（`ASTEngine` 拆分 `_ensure_symbols_loaded` / `_ensure_graph_loaded` 與 `unified.meta.json` 指紋快取）
- [x] **TASK-02**：實作 `knowledge-db` 模組之 CLI 與 Formatter 優化（`OPT-01` `--file-uri`、`OPT-02` 預設 `auto` 折疊與去重、`OPT-03` JSON 分級瘦身、`OPT-04` `kdb` 短別名）及 `agents-workflow` `_trace_parser.py` `kdb` 識別對齊
- [x] **TASK-03**：實作 `knowledge-db` 模組之引擎與檢索優化（`OPT-05` `pipeline.py` 讀取 `unified.meta.json`、`OPT-06` `adaptive_limit` 動態斷崖截斷、`OPT-07` `InvertedIndex` `0..n` `doc_idx` 駐留與 `SparseFieldFreqs`、`OPT-08` `get_status` 快照存活檔案計數）
- [x] **TASK-04**：更新並擴充 `ast`、`knowledge-db`、`agents-workflow` 單元測試，於沙盒環境執行 `dev check` 與 `dev test` 驗證 100% 通過
- [x] **TASK-DOC**：同步更新 `docs/knowledge-db/{README,retrieval}.md`、`CHANGELOG.md` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
