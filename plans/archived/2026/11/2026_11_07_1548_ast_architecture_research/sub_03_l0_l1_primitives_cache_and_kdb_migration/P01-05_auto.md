# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：AST 單次掃描 FileSymbolGraph 快取、L0/L1 六大操作原語、CLI 升級與 KDB 下游對接遷移  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 單次掃描 `FileSymbolGraph` 快取與雙視圖無損橋接 | 擴充 `ASTSnapshot` 保存 `file_graphs: Dict[str, FileSymbolGraph]`，並於 `CallGraphIndex` 支援附掛不可變 `workspace_graph: Optional[WorkspaceSymbolGraph]`。`SemanticBundler.extract_all_file_graphs` 與 `ASTEngine.build_index` 支援對每個檔案執行單次 `ParserRegistry.extract_file_graph` 提取 `FileSymbolGraph`（含 `content_hash`）並透過 `WorkspaceGraphLinker.link_workspace` 建構 `WorkspaceSymbolGraph`，同時確定性衍生聚合後之 `UnifiedSymbol` 字典與 `CallGraphIndex`，消除同檔三次重複解析。 | P0 | [P00:DR-01] |
| **FR-02** | $O(\|\text{Dirty}\|)$ 零污染增量熱修補管線 | `ASTEngine.hot_patch_index` 接收到 `ScanDiffDetail` 時，僅針對 `added \| modified` 髒檔案重新提取 `FileSymbolGraph`、從已快取之 `file_graphs` 字典移除 `deleted` 檔案，其餘無變更檔案 100% 沿用不可變 `FileSymbolGraph` 並重新執行 `WorkspaceGraphLinker.link_workspace` 與衍生快照，徹底拔除脆弱之 `_own_members` 髒狀態原地還原，確保增量修補與全量重建產出 100% 等價之圖譜與符號表。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | L0 無狀態單檔原語 (`parse_file`、`outline`、`slice_part`) | 於 `ASTEngine` 實作：① `parse_file(file_or_uri, *, content=None) -> FileSymbolGraph`（純記憶體無狀態單檔解析，絕不觸發全倉 `ensure_jit_synced()` 或讀寫磁碟快取）；② `outline(file_or_uri, ...)`（保持既有 `OutlineResult.to_dict()` 與三維正交過濾契約）；③ `slice_part(symbol_or_id, part="outer", *, file_bytes=None) -> str`（基於 `SymbolNode.parts[part]` 或 `node.span` 對原始 UTF-8 bytes 執行 $O(1)$ 無損位元組切片）。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-04** | L1 全倉語意圖譜原語 (`get_workspace_graph`、`resolve`、`select_nodes`、`traverse_edges`) | 於 `ASTEngine` 實作：① `get_workspace_graph(auto_sync=True) -> WorkspaceSymbolGraph`；② `resolve(selector_expr, *, spaces=None, kinds=None, ftypes=None) -> SymbolResolutionResult`（同時支援匹配 `SymbolNode` 與 `UnifiedSymbol`）；③ `select_nodes(*, spaces=None, kinds=None, visibility=None, facets=None, ftypes=None) -> Tuple[SymbolNode, ...]`；④ `traverse_edges(seed_ids, *, edge_kinds=None, direction="out", depth=1, status_filter=None) -> Dict[str, Any]`（通用有向圖 BFS 遍歷原語，支援任意 `edge_kinds`、雙向遍歷與 `resolution_status` 過濾）。 | P0 | [P00:DR-02], [P00:DR-05] |
| **FR-05** | CLI `slice` 與 `traverse` 子命令擴充及下游 `knowledge-db` 無縫對接 | 於 `ys_codebase/source/ast/contributes/core.json`、`scripts/cli.py` 與 `ASTResultFormatter` 擴充 `slice`（對應 `slice_part`）與 `traverse`（對應 `traverse_edges`）子命令，保留 `outline`、`callers`、`callees`、`impact`、`status`、`clean` 100% 相容；確保 `knowledge-db` 檢索與增量熱修補管線無縫協同並通過 `ast` 與 `knowledge-db` 全量測試。 | P0 | [P00:DR-01], [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `slice_part` 請求目標節點不存在的部位（如變數節點請求 `part="body"` 或無註解節點請求 `part="doc"`） | 若 `part` 屬於合法部位集合（`"outer"`, `"name"`, `"signature"`, `"parameters"`, `"return_type"`, `"doc"`, `"body"`）但 `node.parts` 未包含該鍵，安全回傳空字串 `""`；若 `part` 非合法部位名稱則拋出 `ASTError`。 |
| **EC-02** | `slice_part` 傳入字串選擇器或符號 ID 無法唯一解析，或目標源碼含多語系 UTF-8 字元 | 若傳入 `SymbolNode` 直接使用其 `span`/`parts`；若傳入 `str`（ID 或選擇器）先從 `WorkspaceSymbolGraph` 查找，找不到則拋出 `ASTError`；切片一律對 UTF-8 `bytes` 取 `[start_byte:end_byte]` 再 `.decode("utf-8", errors="replace")`，杜絕字元與位元組位移錯位。 |
| **EC-03** | `traverse_edges` 遇到循環圖譜（如遞迴呼叫或雙向 `merges_with`）或 `depth <= 0` | 內建 `visited_node_ids` 集合與 BFS 層級推進，防止環路無限迴圈；當 `depth <= 0` 或 `seed_ids` 為空時，安全回傳空 `layers: {}` 與 `edges: ()`。 |
| **EC-04** | 舊版磁碟快取（無 `file_graphs` 或無 `workspace_graph`）升級載入相容 | 當反序列化舊版 `unified.symbols.bin.gz` / `unified.graph.bin.gz` 發現缺少 `file_graphs` 或 `workspace_graph` 時，自動按需從現有檔案重建或補齊 `WorkspaceSymbolGraph`，不拋出未預期崩潰。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 不可變與執行期隔離 | `FileSymbolGraph` 與 `WorkspaceSymbolGraph` 維持 100% `@dataclass(frozen=True)`；遵守 `A1`~`F13` 規範（`python yscb.py dev check ast` 100% 通過）。 |
| **NFR-02** | 單檔與切片效能 | `parse_file(..., content=...)` 0 磁碟索引 I/O；`slice_part(..., file_bytes=...)` 時間複雜度嚴格為 $O(1)$ 位元組切片（0 Tree-sitter 重解析）。 |
| **NFR-03** | 向下相容零回歸 | `ys_codebase/source/ast/tests/` 與 `ys_codebase/source/knowledge-db/tests/` 既有測試及新增 `sub_03` 測試 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` [DN-AST-01] 禁止遮蔽標準庫 `ast`**：所有新公開原語與輔助函式統一透過 `ast_engine` 匯出。
- **`[!IMPORTANT]` [DN-AST-03] 兩階段寫鎖與原子替換**：持久化 `unified.symbols.bin.gz`、`unified.graph.bin.gz` 與 `unified.meta.json` 時維持 `InterProcessLock` 與 `atomic_save_gzip_pickle`。
- **`[!NOTE]` 單次寫檔行數上限 (`AGENTS.md` §4)**：每次 `write_file` 或 `edit_file` 嚴禁超過 150 行。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[core.space: consume_diff(consumer="ast") -> ScanDiffDetail(added, modified, deleted)]
  │
  ├──► [L0 Stateless Primitives (0-Index / 0-Disk Cache)]
  │      ├── ASTEngine.parse_file(file_or_uri, content=...) ──► ParserRegistry.extract_file_graph ──► FileSymbolGraph
  │      ├── ASTEngine.outline(file_or_uri, ...)            ──► FileSymbolGraph + (optional partial siblings) ──► OutlineResult
  │      └── ASTEngine.slice_part(symbol_or_id, part, ...)  ──► raw_bytes[span.start_byte:span.end_byte].decode("utf-8")
  │
  └──► [Single-Pass Cache & O(|Dirty|) Hot-Patch Pipeline]
         ├── SemanticBundler.extract_all_file_graphs / extract_dirty_file_graphs
         │     └── Single-pass per file ──► file_graphs_by_path: Dict[str, FileSymbolGraph] (frozen)
         ├── WorkspaceGraphLinker.link_workspace(file_graphs) ──► WorkspaceSymbolGraph (frozen)
         └── Deterministic Projection:
               ├── ASTSnapshot(symbols=..., file_graphs=file_graphs_by_path, ...) -> unified.symbols.bin.gz
               └── CallGraphIndex(graph=..., workspace_graph=ws_graph)            -> unified.graph.bin.gz
                     │
                     └──► [L1 Workspace Graph Primitives & KDB Consumers]
                            ├── get_workspace_graph() / resolve() / select_nodes() / traverse_edges()
                            ├── callers() / callees() / impact() (Domain Views)
                            └── knowledge-db IndexingPipeline (_sync_ast_snapshot / _collect_all_dirty_files)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 擴充 `ASTSnapshot` 新增 `file_graphs: Dict[str, FileSymbolGraph] = field(default_factory=dict)` 欄位與序列化/反序列化支援；提供 `SymbolNode` 與 `UnifiedSymbol` 無損轉換輔助方法 |
| `ys_codebase/source/ast/ast_engine/graph.py` | Modify | 擴充 `CallGraphIndex` 支援保存與序列化 `workspace_graph: Optional[WorkspaceSymbolGraph]`，並提供從 `WorkspaceSymbolGraph` 同步建構 `CallGraphIndex` 邊的方法 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 新增單次掃描 `extract_all_file_graphs`、`extract_dirty_file_graphs` 與從 `Dict[str, FileSymbolGraph]` 確定性投影 `SemanticBundle`（含 C# `partial` 聚合）之無狀態管線 |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 擴充 `DeterministicSymbolResolver` 支援 `kinds` 過濾與解析 `SymbolNode`，並實作 `select_workspace_nodes` 與通用有向圖 BFS `traverse_workspace_edges` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 升級 `build_index` 與 `hot_patch_index` 為單次掃描 `FileSymbolGraph` + `WorkspaceGraphLinker` 管線；實作 L0（`parse_file`, `outline`, `slice_part`）與 L1（`get_workspace_graph`, `resolve`, `select_nodes`, `traverse_edges`）原語 |
| `ys_codebase/source/ast/ast_engine/formatter.py` | Modify | 新增 `format_slice_output` 與 `format_traverse_output` 格式化方法 |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 新增 `slice` 與 `traverse` CLI 子命令宣告與選項定義 |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 新增 `slice` 與 `traverse` CLI 路由處理函式並註冊至 `dispatch_cli` |
| `ys_codebase/source/ast/ast_engine/__init__.py` | Modify | 匯出 `select_workspace_nodes`、`traverse_workspace_edges` 等新公開符號 |
| `ys_codebase/source/ast/tests/test_l0_l1_primitives_and_cache.py` | New | 驗證單次掃描快取、$O(\|\text{Dirty}\|)$ 零污染熱修補、L0（`parse_file`, `outline`, `slice_part`）、L1（`resolve`, `select_nodes`, `traverse_edges`）、CLI `slice`/`traverse` 與 KDB 對接之完整測試套件 |
| `docs/ast/README.md` | Modify | 同步更新 L0/L1 六大公開原語與 `slice` / `traverse` CLI 手冊 |
| `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `[DN-AST-07]` 記錄單次掃描 `FileSymbolGraph` 快取、L0/L1 原語與雙視圖無損橋接設計決策 |
| `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_03` 變更摘要 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 單次掃描 `FileSymbolGraph` 快取與雙視圖無損衍生**：
  - `SemanticBundler` 對每個檔案僅呼叫一次提取（結合 `ParserRegistry.extract_file_graph` 與單檔符號）產出不可變 `FileSymbolGraph`，存入 `ASTSnapshot.file_graphs`；在 `hot_patch_index` 中僅更新髒檔案對應之 `FileSymbolGraph` 並直接重算 `WorkspaceGraphLinker.link_workspace` 與 `aggregate_partial_symbols`，彻底消除同檔三次解析與 `_own_members` 原地變異還原。
- **[P02:DR-02] L0 `slice_part` 原生位元組無損切片**：
  - `ASTEngine.slice_part` 支援傳入 `SymbolNode`、`UnifiedSymbol`、符號 ID 或選擇器字串；當傳入選擇器字串或 ID 時，透過 `WorkspaceSymbolGraph` 定位 `SymbolNode`，再直接讀取目標檔案原始 `bytes`（或使用呼叫方傳入之 `file_bytes`）切取 `[span.start_byte:span.end_byte]`，時間複雜度嚴格為 $O(1)$。
- **[P02:DR-03] L1 `traverse_edges` 通用有向圖 BFS 引擎**：
  - `traverse_edges` 直接操作 `WorkspaceSymbolGraph` 之 `outgoing_edges_by_source` 與 `incoming_edges_by_target` 鄰接表，支援任意 `edge_kinds` 集合過濾、`"out"` / `"in"` / `"both"` 方向、指定 `depth` 層級展開與 `status_filter`（預設包含 `"resolved"`, `"overload_group"`, `"ambiguous"`），回傳結構化之 `seed_nodes`、`layers`（每層節點清單）、`edges`（走訪經過之 `RelationEdge` 清單）與 `ambiguous_edges`（供下游審計消歧）。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/ast/ast_engine/engine.py
VALID_SLICE_PARTS: FrozenSet[str] = frozenset({
    "outer", "name", "signature", "parameters", "return_type", "doc", "body",
})

class ASTEngine:
    def parse_file(
        self,
        file_or_uri: Union[str, Path],
        *,
        content: Optional[Union[str, bytes]] = None,
        space: Optional[str] = None,
    ) -> FileSymbolGraph: ...

    def slice_part(
        self,
        symbol_or_id: Union[SymbolNode, UnifiedSymbol, str],
        part: str = "outer",
        *,
        file_bytes: Optional[Union[bytes, str]] = None,
        space: Optional[Union[str, List[str]]] = None,
    ) -> str: ...

    def get_workspace_graph(self, auto_sync: bool = True) -> WorkspaceSymbolGraph: ...

    def resolve(
        self,
        selector_expr: str,
        *,
        spaces: Optional[Union[str, Sequence[str]]] = None,
        kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        ftypes: Optional[Union[str, Sequence[str]]] = None,
    ) -> SymbolResolutionResult: ...

    def select_nodes(
        self,
        *,
        spaces: Optional[Union[str, Sequence[str]]] = None,
        kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        visibility: Optional[Union[str, Sequence[str]]] = None,
        facets: Optional[Mapping[str, Any]] = None,
        ftypes: Optional[Union[str, Sequence[str]]] = None,
    ) -> Tuple[SymbolNode, ...]: ...

    def traverse_edges(
        self,
        seed_ids: Union[str, Sequence[str], Set[str], FrozenSet[str]],
        *,
        edge_kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        direction: str = "out",
        depth: int = 1,
        status_filter: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        spaces: Optional[Union[str, Sequence[str]]] = None,
    ) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `slice_part`：當 `part not in VALID_SLICE_PARTS` 時拋出 `ASTError(f"Unsupported slice part: {part!r}")`；當 `symbol_or_id` 為字串且無法在圖譜中找到對應符號時拋出 `ASTError`；當目標符號無該選填部位（如欄位無 `"body"` 或無 `"doc"`）時安全回傳 `""`。
  - `traverse_edges`：當 `direction not in ("out", "in", "both")` 時拋出 `ASTError(f"Invalid traversal direction: {direction!r}")`；當 `seed_ids` 傳入符號選擇器或 ID 時自動解析為起始節點 ID 集合。
- **階段決策紀錄**：`[P03:DR-01]` L0/L1 六大公開方法直接掛載於 `ASTEngine` 門面，並於 `scripts/cli.py` 暴露 `yscb.py ast slice <symbol> [--part=outer|signature|doc|body|...]` 與 `yscb.py ast traverse <symbol> [--kind=calls,inherits,...] [--direction=out|in|both] [--depth=1]`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  1. *問：當 `ASTEngine.hot_patch_index` 執行增量更新時，若一個 C# `partial class` 的其中一個分部檔被修改或刪除，不依賴 `_own_members` 如何保證聚合結果 100% 正確？*
     - **答**：因為每個檔案的未聚合原始符號結構均完整保存在不可變的 `FileSymbolGraph`（存入 `ASTSnapshot.file_graphs`）中！當任何分部檔變更或刪除時，僅需更新/刪除該檔的 `FileSymbolGraph`，再從所有存活檔案的 `FileSymbolGraph` 投影出乾淨的單檔符號並執行 `aggregate_partial_symbols` 與 `WorkspaceGraphLinker.link_workspace`，天然免疫任何歷史聚合狀態污染。
  2. *問：`knowledge-db` 的 `IndexingPipeline` 依賴 `ASTEngine.ensure_jit_synced()`、`hot_patch_index()` 與 `snapshot.symbols`，升級後是否會破壞 KDB 的單次解析符號共享？*
     - **答**：`ASTSnapshot.symbols` 依然保持完整（由單次提取之 `FileSymbolGraph` 無損衍生並完成 C# `partial` 聚合），且 `ASTSnapshot.ast_generation`、`file_to_symbol_ids`、`files_map` 契約 100% 不變，因此 `knowledge-db` 無需重複解析即可直接共享最新符號。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md` | Modify | 補充 L0 (`parse_file`, `outline`, `slice_part`) 與 L1 (`get_workspace_graph`, `resolve`, `select_nodes`, `traverse_edges`) SDK 與 CLI `slice`/`traverse` 用法 |
| **專題手冊** | `docs/ast/[topic].md` | N/A | 整合於模組手冊與設計筆記 |
| **設計決策** | `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `[DN-AST-07]` 記錄單次掃描 `FileSymbolGraph` 快取與 L0/L1 原語設計 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `engine.py`, `bundler.py`, `resolver.py`, `cli.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_03` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `P01`~`P04` 規格閉環，準備執行 Pre-Code Analyze Gate 並進入實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `ast_engine/schema.py`（`ASTSnapshot.file_graphs` 與 `SymbolNode` $\leftrightarrow$ `UnifiedSymbol` 輔助轉換）與 `ast_engine/graph.py`（`CallGraphIndex.workspace_graph` 保存與同步）
- [x] **TASK-02**：升級 `ast_engine/bundler.py` 支援單次掃描 `extract_all_file_graphs`、`extract_dirty_file_graphs` 與從 `FileSymbolGraph` 字典無狀態衍生 `SemanticBundle` 及 `call_sites`/`imports`
- [x] **TASK-03**：擴充 `ast_engine/resolver.py` 實作 `select_workspace_nodes`、`traverse_workspace_edges` 與支援 `kinds` 過濾之 `resolve`
- [x] **TASK-04**：升級 `ast_engine/engine.py`（`build_index` / `hot_patch_index` 單次掃描快取管線，以及 L0 `parse_file`、`slice_part` 與 L1 `get_workspace_graph`、`resolve`、`select_nodes`、`traverse_edges` 原語）
- [x] **TASK-05**：擴充 `contributes/core.json`、`ast_engine/formatter.py`、`scripts/cli.py` 與 `ast_engine/__init__.py` 支援 CLI `slice` 與 `traverse` 子命令
- [x] **TASK-06**：編寫 `ys_codebase/source/ast/tests/test_l0_l1_primitives_and_cache.py` 並通過 `dev check ast`、`dev test ast` 與 `dev test knowledge-db` 全量測試
- [x] **TASK-DOC**：同步更新 `docs/ast/README.md` 與 `docs/ast/DESIGN_NOTES.md`（`[DN-AST-07]`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
