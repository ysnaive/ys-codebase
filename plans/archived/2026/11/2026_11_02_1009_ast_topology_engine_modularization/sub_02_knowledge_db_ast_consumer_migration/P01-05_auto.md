# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`module:knowledge-db` 轉型為 Layer 3 純混合檢索消費者與三階單向 DAG 快照對接  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 物理移除重複 AST 解析與拓撲基建 | 物理刪除 `knowledge_db/parsers/`、`assets/queries/`、`knowledge_db/{bundler,linker,graph,topology_query}.py` 與 `contributes/knowledge-db.json`；`manifest.json` 宣告 `"ast": ">=1.0.0"` 依賴並移除 `tree-sitter*` 與 `networkx`（`pip_dependencies` 僅保留 `"fastembed": ">=0.3.0"`）。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-02** | `UnifiedSymbol` 型別同一性與 `ASTSnapshot` 單次解析共享 | `knowledge_db.schema` 直接重匯出 `ast_engine` 之 `UnifiedSymbol`、`MemberInfo`、`SymbolKind`、`LanguageType`、`SemanticBundle`；`IndexingPipeline.build_unified_index()` 直接消費 `ast_engine.ensure_jit_synced()` 產出之 `ASTSnapshot.symbols` 建立 `InvertedIndex` 與 `VectorIndex`，不重複執行語法解析。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 三階 Pull-Based JIT 游標水位線與增量熱修補 | `IndexingPipeline` 於 `unified.index.bin.gz` 記錄 `acked_ast_generation`；`_ensure_jit_index_ready()` 與 `hot_patch_unified_index()` 串聯 `file-space` 差量與 `ast_engine.ensure_jit_synced()`，從最新 `ASTSnapshot` 提取變更檔案符號修補 BM25 與向量索引（含 10-symbol 向量探針自癒）。 | P0 | [P00:DR-03] |
| **FR-04** | CLI、`contributes` 與常駐服務對接純化 | `contributes/core.json` 與 `scripts/cli.py` 僅保留 `status`、`index`、`search`、`clean`、`model` 子命令（移除 `callers/callees/impact`）；`contributes/_format.json` 僅保留 `space_weights`；`KnowledgeDBServiceWorker` 與 `scripts/hook.file-space.py` 支援對接 `ASTEngine` 快照。 | P0 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `partial class` 跨分部符號之 BM25 成員索引防膨脹 | `ASTSnapshot.symbols` 雖已完成跨檔邏輯聚合，但保留單檔物理 `_own_members`；`InvertedIndex._extract_symbol_members_text` 優先索引 `_own_members`，確保修改或檢索單一分部檔時不發生 $N^2$ 成員重複膨脹。 |
| **EC-02** | `ast_engine` 已被外部 `yscb ast` 指令先行推進世代（`space` 差量為空但 `acked_ast_generation` 落後，或反之） | `_ensure_jit_index_ready()` 同時檢查 `file-space` 對 `"knowledge-db"` 的差量與 `acked_ast_generation != snapshot.ast_generation`：若有檔案差量則執行 `hot_patch_unified_index`；若無檔案差量但 `acked_ast_generation` 落後則同步重建或對齊快照世代。 |
| **EC-03** | 無 ONNX 模型或離線環境下之混合檢索與向量熱修補降級 | 當 `EmbeddingService.is_available` 為 `False` 時，自動降級為純 BM25 檢索並透過 `check_and_heal_vectors` / `_patch_vector_index_with_probe` 維持零報錯運作。 |
| **EC-04** | `knowledge-db index --export <path>` 語意包匯出相容性 | `KnowledgeEngine.bundle()` 透過 `ast_engine.get_snapshot(auto_sync=True)` 組裝 `SemanticBundle` 並支援匯出 JSON，維持 `index --export` 介面無損。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構解耦與依賴純淨度 | `ys_codebase/source/knowledge-db/` 內 `tree-sitter`、`networkx` 與自建 Parser 殘留數為 `0`；`python yscb.py dev check knowledge-db` 100% `[PASS]`。 |
| **NFR-02** | 單次解析共享效能 | 同一變更週期內，先執行 `yscb ast` 再執行 `yscb knowledge-db search` 時，`ASTEngine` 直接命中磁碟/記憶體快照，Tree-sitter 重複解析次數為 `0`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Stdlib `ast` 命名空間防護**：`module:ast` 的 Python 匯入套件名稱固定為 `ast_engine`（不可在 `.modules/ast/` 根目錄放置 `__init__.py`），`knowledge_db/__init__.py` 注入路徑時須將 `.modules/ast` 與 `source/ast` 加入 `sys.path` 並以 `import ast_engine` 載入。
- **`[!NOTE]` 雙游標解耦**：`file-space` 中 `"ast"` 游標由 `ASTEngine` 獨立推進，`"knowledge-db"` 游標由 `KnowledgeEngine` 於完成 BM25/Vector 索引更新後推進，確保 `yscb ast` 先行執行不會吞掉 `knowledge-db` 所需的變更差量清單。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
Layer 1: module:file-space (FileSpaceManager /UnifiedFileScanner)
   │  ├── consumer_id="ast"          ──► Layer 2: module:ast (ASTEngine)
   │  │                                     └── unified.ast.bin.gz (ASTSnapshot: symbols + _own_members, ast_generation)
   │  └── consumer_id="knowledge-db" ──► Layer 3: module:knowledge-db (KnowledgeEngine / IndexingPipeline)
   │                                        ├── 呼叫 ast_engine.ensure_jit_synced() 取得 ASTSnapshot (0 重複解析)
   │                                        ├── unified.index.bin.gz (InvertedIndex BM25 + acked_ast_generation)
   │                                        └── unified.vectors.bin.gz (VectorIndex ONNX + 10-symbol probe)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/manifest.json` | Modify | `dependencies` 加入 `"ast": ">=1.0.0"`；`pip_dependencies` 移除 `tree-sitter*` 與 `networkx` |
| `ys_codebase/source/knowledge-db/contributes/_format.json` | Modify | 移除 `languages` 與 `_types.LanguageDef`，僅保留 `space_weights` |
| `ys_codebase/source/knowledge-db/contributes/_manifest.md` | Modify | 更新擴充點說明為僅 `space_weights`（語言擴充指引至 `module:ast`） |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 移除 `callers`、`callees`、`impact` CLI 宣告；保留 `status`、`index`、`search`、`clean`、`model` |
| `ys_codebase/source/knowledge-db/contributes/knowledge-db.json` | Delete | 語言查詢定義已遷移至 `ys_codebase/source/ast/contributes/ast.json` |
| `ys_codebase/source/knowledge-db/assets/queries/*` | Delete | Tree-sitter `.scm` 查詢資產已遷移至 `ys_codebase/source/ast/assets/queries/` |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/*` | Delete | 所有程式碼與文檔解析器已遷移至 `ys_codebase/source/ast/ast_engine/parsers/` |
| `ys_codebase/source/knowledge-db/knowledge_db/{bundler,linker,graph,topology_query}.py` | Delete | 語意打包、連結器與呼叫圖譜已遷移至 `ys_codebase/source/ast/ast_engine/` |
| `ys_codebase/source/knowledge-db/knowledge_db/__init__.py` | Modify | `_ensure_dependency_module_paths()` 納入 `ast`；移除 `ParserRegistry`、`SemanticBundler`、`CallGraph`、`TopologyLinker` 匯出 |
| `ys_codebase/source/knowledge-db/knowledge_db/schema.py` | Modify | 從 `ast_engine` 重匯出 `UnifiedSymbol`、`MemberInfo`、`SymbolKind`、`LanguageType`、`SemanticBundle` 等，保留 `SearchQuery` 與 `SearchResult` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 以 `self.ast_engine = ASTEngine(...)` 取代 `parser_registry`/`bundler`；移除 `callers/callees/impact`；實作三階 Pull-Based JIT 同步 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 消費 `ASTEngine` 快照建立/熱修補 `InvertedIndex` 與 `VectorIndex`，持久化 `acked_ast_generation`，移除 `CallGraph` 管線 |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 移除 `format_callers_output`、`format_callees_output`、`format_impact_output`，保留 `format_search_output` 與 `extract_symbol_snippet` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 更新 `KnowledgeDBServiceWorker` 狀態與熱重載邏輯以對接 `ast_engine` |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 移除 `cmd_callers`、`cmd_callees`、`cmd_impact`，更新 `cmd_status` 與 `cmd_index` 輸出 |
| `ys_codebase/source/knowledge-db/scripts/hook.file-space.py` | Modify | 檔案變更事件觸發時透過 `engine.ast_engine` 同步快照並熱修補 BM25/Vector 索引 |
| `ys_codebase/source/knowledge-db/tests/test_{parsers,bundler,graph}.py` | Delete | 單元測試已遷移至 `ys_codebase/source/ast/tests/` |
| `ys_codebase/source/knowledge-db/tests/test_{cli,engine,file_space,schema,hot_reload,self_healing,service_worker}.py` | Modify | 更新測試集以驗證三階 DAG 快照共享、JIT 連鎖熱自癒與純化後之 CLI 契約 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `ASTEngine` 儲存路徑隔離與共享自動偵測**：
  - 當 `KnowledgeEngine` 使用預設專案快取目錄（`.cache/knowledge-db`）時，其內部 `ASTEngine` 預設指向共享的 `.cache/ast`（使得 `yscb ast` 與 `yscb knowledge-db` 100% 讀寫同一份 `unified.ast.bin.gz` 快照）；當測試環境傳入自訂隔離 `storage_dir` 時，`ASTEngine` 使用 `storage_dir / "ast"` 以保證平行測試沙盒互不干擾。
- **[P02:DR-02] 雙游標協同之增量熱修補（Dual-Cursor Hot Patching）**：
  - `ASTEngine` 使用 `consumer_id="ast"` 維護 `unified.ast.bin.gz`，`KnowledgeEngine` 使用 `consumer_id="knowledge-db"` 取得自上次檢索以來的變更檔案清單 `diff_detail`，先呼叫 `self.ast_engine.ensure_jit_synced()` 讓 `ASTSnapshot` 完成解析與 `partial class` 重聚，再從 `snapshot.symbols` 提取髒檔案對應之最新 `UnifiedSymbol` 餵入 `InvertedIndex.patch_incremental()`，兼顧零重複解析與精準差量修補。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
class IndexingPipeline:
    def __init__(
        self,
        storage_dir: Path,
        ast_engine: ASTEngine,
        tokenizer: CodeTokenizer,
        embedding_service: EmbeddingService,
        space_manager: Optional[FileSpaceManager] = None,
        scanner: Optional[UnifiedFileScanner] = None,
    ) -> None: ...

    @property
    def acked_ast_generation(self) -> int: ...

    def build_unified_index(
        self,
        force: bool = False,
        enable_vec: bool = True,
        skip_vectors: bool = False,
    ) -> Dict[str, Any]: ...

    def hot_patch_unified_index(
        self,
        diff_detail: Dict[str, Any],
        enable_vec: bool = True,
        skip_vectors: bool = False,
    ) -> Dict[str, Any]: ...


class KnowledgeEngine:
    ast_engine: ASTEngine
    pipeline: IndexingPipeline

    def status(self) -> Dict[str, Any]: ...
    def bundle(self, space: Optional[str] = None, export_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]: ...
    def build_index(self, space: Optional[str] = None, force: bool = False, enable_vec: bool = True, skip_vectors: bool = False) -> Dict[str, Any]: ...
    def search(self, query_text: str, space: Optional[str] = None, top_k: int = 10, ftype: Optional[str] = None, enable_semantic: Optional[bool] = None, include_snippet: bool = False, max_snippet_lines: int = 0) -> Dict[str, Any]: ...
    def clean(self) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 若 `ASTEngine` 快照尚未建立，`build_unified_index` 與 `_ensure_jit_index_ready` 自動觸發 `ast_engine.ensure_jit_synced()` 建立快照，絕不拋出未初始化例外。
  - 若髒檔案在 `diff_detail` 中屬於 `deleted` 或不產生任何符號，`hot_patch_unified_index` 正常清除舊符號與舊向量且不報錯。
- **階段決策紀錄**：`[P03:DR-01]` `KnowledgeEngine.status()` 回傳結構新增 `ast_generation` 與 `acked_ast_generation` 欄位，移除已廢棄之 `has_graph_index` 與 `indices["graph"]`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：若使用者修改了一個 C# `partial class` 的其中一個分部檔 `Window.Dragging.cs`，`knowledge-db` 熱修補時如何確保同群組姊妹檔 `Window.cs` 的邏輯聚合屬性同步更新，且不發生 `_own_members` 膨脹？*
  - *答*：`ASTEngine.hot_patch_index()` 在收到 `Window.Dragging.cs` 變更時，會自動重新聚合整個 `Window` 分部群組並更新 `ASTSnapshot.symbols`（同時各自保留物理 `_own_members`）；`IndexingPipeline.hot_patch_unified_index()` 從更新後的 `snapshot.symbols` 提取受影響檔案（含同 `partial` 群組姊妹檔或變更檔）之符號並以 `_own_members` 建立倒排索引，100% 保持一致與防膨脹。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/knowledge-db/README.md` | Modify | 更新模組職責為純混合檢索消費者，指向 `module:ast` 處理語法與拓撲 |
| **專題手冊** | `docs/knowledge-db/ARCHITECTURE.md` | N/A | 將於 `sub_03_agents_workflow_ast_routing` 統一完成 `docs/` 三層文檔同步 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 將於 `sub_03_agents_workflow_ast_routing` 統一完成 `docs/` 三層文檔同步 |
| **微觀註解** | `ys_codebase/source/knowledge-db/knowledge_db/*.py` | Modify | 同步更新 `KnowledgeEngine`、`IndexingPipeline` 與 `schema.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_02` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_02` 專注於 `ys_codebase/source/knowledge-db/` 源碼、組態、README 與測試集重構；跨模組技能與 `docs/` 文檔於 `sub_03` 統一收斂。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `manifest.json`、`contributes/{_format.json,_manifest.md,core.json}` 並物理刪除 `contributes/knowledge-db.json`、`assets/queries/`、`knowledge_db/parsers/`、`knowledge_db/{bundler,linker,graph,topology_query}.py`
- [x] **TASK-02**：重構 `knowledge_db/{__init__,schema,formatter,engine,pipeline,service}.py` 與 `scripts/{cli,hook.file-space}.py`，對接 `ast_engine.ASTEngine` 單次解析快照與三階 Pull-Based JIT 熱修補
- [x] **TASK-03**：刪除已遷移之 `tests/test_{parsers,bundler,graph}.py`，更新 `tests/test_{cli,engine,file_space,schema,hot_reload,self_healing,service_worker}.py` 並通過 `dev check knowledge-db` 與 `dev test knowledge-db`
- [x] **TASK-DOC**：更新 `ys_codebase/source/knowledge-db/README.md` 與核心類別 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

