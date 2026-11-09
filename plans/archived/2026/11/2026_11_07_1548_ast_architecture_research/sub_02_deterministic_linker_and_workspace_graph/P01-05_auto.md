# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：AST 四階段確定性跨檔連結流水線 (4-Pass Linker)、四階作用域查找與全倉圖譜組裝  
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
| **FR-01** | `FileImportTable` 與 `WorkspaceSymbolGraph` 不可變結構 | 於 `ast_engine/schema.py` 定義 `@dataclass(frozen=True)` 之 `FileImportBinding`、`FileImportTable` 與 `WorkspaceSymbolGraph`（內部字典與集合全數正規化為 `tuple`、`frozenset` 與 `MappingProxyType`），提供全倉 `file_graphs`、`nodes_by_id`、`resolved_edges`、`outgoing_edges_by_source`、`incoming_edges_by_target`、`file_import_tables`、`folded_symbol_groups`、`type_bases_by_id`、`type_derived_by_id` 與 `field_types_by_class_id`，並支援雙向無損 `to_dict()` / `from_dict()`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | `contributes` 跨檔連結設定與平權擴充介面 | 擴充 `ys_codebase/source/ast/contributes/_format.json`、`LanguageConfig`、`ParserRegistry` 與 `ast_engine/parsers/base.py`，支援 `receiver_aliases`（`self_aliases` / `super_aliases`）、`symbol_folding`、`module_resolver: str?`（`ModulePathResolver` 抽象契約與內建各語言實作）與 `edge_refiners: list[str]?`（`EdgeRefiner` 抽象契約）。 | P0 | [P00:DR-01], [P00:DR-04] |
| **FR-03** | Pass 1 & Pass 2：全域索引、跨檔同體折疊與 `FileImportTable` 匯入邊解析 | 實作 `WorkspaceGraphLinker` 之 Pass 1（建立全倉 `SymbolNode` 索引，並對 C# `partial` 型別與 C/C++ `.h`/`.cpp` out-of-line 配對生成對稱 `merges_with` / `declares` 邊與 `folded_symbol_groups`，絕不竄改單檔 `FileSymbolGraph`）與 Pass 2（透過 `ModulePathResolver` 解析 `edge_kind="imports"`，支援相對路徑、別名、萬用匯入 `*` 與 `__all__`/`export` 重導出，產出 `FileImportTable` 並標記 `resolved` 或 `external`）。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-04** | Pass 3：型別繼承與實作 DAG 建構 | 實作 `WorkspaceGraphLinker` 之 Pass 3，利用 Pass 2 `FileImportTable` 與詞法作用域解析 `edge_kind in ("inherits", "implements")` 邊，將基底型別精確綁定至目標 `SymbolNode.id`（根除跨模組同名 `short_name` 誤連），建立無環型別繼承 DAG（`type_bases_by_id` / `type_derived_by_id`）與欄位型別映射（`field_types_by_class_id`），並讓 `expand_contract_symbol_ids` 原生支援 `WorkspaceSymbolGraph`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-05** | Pass 4：四階確定性作用域查找、零幽靈邊消歧與平權 `EdgeRefiner` | 實作 `WorkspaceGraphLinker` 之 Pass 4，嚴格依序透過 ① **詞法封閉作用域（Lexical Enclosing Scope）** $\to$ ② **所屬型別與 Pass 3 繼承鏈 DAG（含 `receiver_aliases` 與欄位型別派發）** $\to$ ③ **Pass 2 檔案匯入綁定表（`FileImportTable`）** $\to$ ④ **同模組/全倉唯一 FQN 精確匹配** 解析 `calls`、`references`、`documents` 邊；執行選填 `EdgeRefiner`，賦予 `resolved` / `overload_group` / `ambiguous` / `external` / `unresolved` 狀態並追加字典序 `ProvenanceStep`，100% 廢除啟發式子字串模糊打分。 | P0 | [P00:DR-02], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 循環型別繼承或循環萬用匯入 (`class A(B): ... class B(A): ...` / `from a import *`) | Pass 2 萬用匯入展開與 Pass 3 型別繼承 BFS/DFS 均維護 `visited` 集合，偵測到環路時立即斷路，保證 $O(V+E)$ 終止且不引發 `RecursionError`。 |
| **EC-02** | 鴨子型別或跨模組同名方法導致無唯一目標 (`obj.run()`) | 不執行任何子字串模糊打分猜測；若匹配多個不同父型別之同名方法，將 `resolution_status` 設為 `"ambiguous"`，並將所有候選 `SymbolNode.id` 按字典序穩定存入 `resolved_target_ids`。 |
| **EC-03** | 同一父型別下的同名多載方法 (`overload_group`) | 若呼叫端具有明確參數數量（`arg_count`）且恰好唯一匹配單一重載，收斂為 `"resolved"`；若無參數數量資訊或多個重載同參數數量，設為 `"overload_group"` 並保留該型別下所有匹配重載之 `SymbolNode.id`。 |
| **EC-04** | 外部標準庫或第三方套件呼叫 (`os.path.join`、`tree_sitter.Parser`) | 當接收者前綴命中 `FileImportTable` 中標記為 `is_external=True` 之外部匯入別名時，將該 `RelationEdge` 之 `resolution_status` 設為 `"external"`、`resolved_target_ids=()`，區隔於本倉缺失之 `"unresolved"`。 |
| **EC-05** | 自訂 `ModulePathResolver` 或 `EdgeRefiner` 載入失敗或執行期拋錯 | 捕獲異常並透過 `core.log.log_warn(..., stream="stderr")` 記錄告警與 `ParserRegistry.load_errors`，自動回退至內核預設解析器或跳過故障 Refiner，不中斷整體圖譜連結。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 執行期隔離與不可變契約 (`A1`~`F13`) | 100% 通過 `python yscb.py dev check ast` 靜態守門（0 `print`/`logging`、0 `global`、0 頂層可變單例、所有資料結構 `@dataclass(frozen=True)`）。 |
| **NFR-02** | 確定性與可重現性 (Determinism) | 對任意順序輸入之 `FileSymbolGraph` 集合，`WorkspaceGraphLinker.link_workspace` 產出之 `WorkspaceSymbolGraph`（含 `resolved_target_ids` 與 `provenance`）100% 順序無關且可重現。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `docs/ast/DESIGN_NOTES.md` 與 `R02_cross_file_linking_and_workspace_graph.md`：跨檔同體折疊（如 C# `partial class`）必須僅於 `WorkspaceSymbolGraph` 層級建立邏輯關聯，嚴禁回寫污染單檔 `FileSymbolGraph`，確保未來 `sub_03` 單檔快取熱修補零狀態還原開銷。
- **`[!CAUTION]`** `AGENTS.md` §4：單次寫檔或替換嚴禁超過 150 行，大檔案實作必須採分段 `write_file (Append=True)` 或小區塊 `edit_file`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Iterable[FileSymbolGraph] + LanguageConfig (receiver_aliases / symbol_folding / ModulePathResolver / EdgeRefiner)]
        │
        ▼  WorkspaceGraphLinker.link_workspace(file_graphs)
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 1：Global Indexing & Cross-File Symbol Folding                     │
│ • 建立全倉 nodes_by_id、by_file、by_fqn、by_short_name 索引             │
│ • 依 symbol_folding 規則建立對稱 merges_with / declares 邊與折疊群組      │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 2：Import Edge Resolution & FileImportTable Construction           │
│ • 透過 ModulePathResolver 解析 edge_kind == "imports"                   │
│ • 展開萬用匯入 (*) 與 __all__ / export 重導出，產出 FileImportTable      │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 3：Inheritance & Type Graph DAG Construction                       │
│ • 結合詞法作用域與 FileImportTable 解析 "inherits" / "implements" 邊     │
│ • 建立無環 type_bases_by_id / type_derived_by_id 與欄位型別映射          │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 4：4-Tier Scope Cascade & Peer EdgeRefiner Pipeline                │
│ • ① 詞法封閉樹 -> ② 型別與繼承 DAG -> ③ FileImportTable -> ④ 唯一 FQN   │
│ • 執行 EdgeRefiner 管線，寫入 resolved / overload_group / ambiguous /   │
│   external / unresolved 與 ProvenanceStep，產出不可變 WorkspaceSymbolGraph │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/contributes/_format.json` | Modify | 為 `LanguageDef` 新增 `receiver_aliases`、`symbol_folding`、`module_resolver` 與 `edge_refiners` 欄位規格。 |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 新增 `@dataclass(frozen=True)` 之 `FileImportBinding`、`FileImportTable`、`WorkspaceSymbolGraph`，並擴充 `LanguageConfig`。 |
| `ys_codebase/source/ast/ast_engine/parsers/base.py` | Modify | 新增平權擴充抽象基底類別 `ModulePathResolver` 與 `EdgeRefiner`。 |
| `ys_codebase/source/ast/ast_engine/parsers/registry.py` | Modify | 擴充 `DEFAULT_LANGUAGES` 預設 `receiver_aliases`/`symbol_folding`，支援載入與查詢語言專屬 `ModulePathResolver` 與 `EdgeRefiner`。 |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 升級 `_extract_relation_edges`：區分 `inherits` 與 `implements`、保留匯入別名表達式（`alias=target`）與呼叫端參數數量後綴資訊，並提取欄位型別至 `facets["field_types"]`。 |
| `ys_codebase/source/ast/ast_engine/parsers/markdown.py` | Modify | 實作原生 `extract_file_graph` 產出階層式文檔 `SymbolNode` 與 `edge_kind="documents"` / `"imports"` 之 `RelationEdge`。 |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | 實作內建各語言 `ModulePathResolver`、`WorkspaceGraphLinker`（Pass 1~4 與四階作用域查找），並升級 `expand_contract_symbol_ids` 原生支援 `WorkspaceSymbolGraph`。 |
| `ys_codebase/source/ast/tests/test_deterministic_linker.py` | New | 針對 `FR-01` ~ `FR-05` 與 `EC-01` ~ `EC-05` 編寫完整單元與邊界測試。 |
| `docs/ast/README.md` | Modify | 同步更新 `WorkspaceSymbolGraph`、4-Pass 確定性連結器與 `contributes` 擴充欄位說明。 |
| `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `DN-AST-06` 記錄四階段依序連結流水線、四階確定性作用域查找與零幽靈邊狀態機設計決策。 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 單檔匯入邊別名承載格式**：`TreeSitterDriver._extract_relation_edges` 與 `MarkdownParser.extract_file_graph` 在建立 `edge_kind="imports"` 之 `RelationEdge` 時，若存在明確局部別名（例如 `from pkg.mod import Foo as Bar` 或 `import pkg.mod as pm`），將 `target_expr` 編碼為 `"Bar=pkg.mod.Foo"`（無別名時為 `"pkg.mod.Foo"`，萬用匯入為 `"*=pkg.mod.*"`），使 Pass 2 `ModulePathResolver` 能 100% 精確建構 `FileImportTable.bindings[local_alias]`。
- **[P02:DR-02] 內建多語言 `ModulePathResolver` 與平權覆寫**：內核提供開箱即用的預設模組路徑解析器（支援 Python 相對點號與 `__init__.py`、TS/JS 相對路徑與 `index.ts`/`index.js`、C/C++ `#include` 標頭配對、C# `using` 命名空間映射、Markdown 相對檔案連結與 `#anchor`），同時允許任何模組透過 `contributes.ast.languages[*].module_resolver` 注入自訂 `ModulePathResolver` 子類別覆寫。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/ast/ast_engine/schema.py
@dataclass(frozen=True)
class FileImportBinding:
    local_alias: str
    target_expr: str
    resolved_file_path: Optional[str] = None
    resolved_symbol_ids: Tuple[str, ...] = ()
    is_wildcard: bool = False
    is_external: bool = False
    is_reexport: bool = False

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileImportBinding": ...


@dataclass(frozen=True)
class FileImportTable:
    file_path: str
    bindings: Mapping[str, FileImportBinding] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    exported_symbols: FrozenSet[str] = field(default_factory=frozenset)

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileImportTable": ...


@dataclass(frozen=True)
class WorkspaceSymbolGraph:
    file_graphs: Mapping[str, FileSymbolGraph] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    nodes_by_id: Mapping[str, SymbolNode] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    resolved_edges: Tuple[RelationEdge, ...] = field(default=(), hash=False)
    outgoing_edges_by_source: Mapping[str, Tuple[RelationEdge, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    incoming_edges_by_target: Mapping[str, Tuple[RelationEdge, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    file_import_tables: Mapping[str, FileImportTable] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    folded_symbol_groups: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    type_bases_by_id: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    type_derived_by_id: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    field_types_by_class_id: Mapping[str, Mapping[str, str]] = field(default_factory=lambda: MappingProxyType({}), hash=False)

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceSymbolGraph": ...


# ys_codebase/source/ast/ast_engine/parsers/base.py
class ModulePathResolver:
    provider_id: str = "ast:default_module_resolver"

    def resolve_import(
        self,
        importing_file: str,
        target_expr: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]: ...


class EdgeRefiner:
    provider_id: str = "ast:default_edge_refiner"

    def refine_workspace_edges(
        self,
        edges: Tuple[RelationEdge, ...],
        nodes_by_id: Mapping[str, SymbolNode],
        file_import_tables: Mapping[str, FileImportTable],
    ) -> Tuple[RelationEdge, ...]: ...


# ys_codebase/source/ast/ast_engine/linker.py
class WorkspaceGraphLinker:
    def __init__(
        self,
        file_graphs: Iterable[FileSymbolGraph],
        language_configs: Optional[Mapping[str, LanguageConfig]] = None,
        module_resolvers: Optional[Mapping[str, ModulePathResolver]] = None,
        edge_refiners: Optional[Mapping[str, Tuple[EdgeRefiner, ...]]] = None,
    ) -> None: ...

    def link_workspace(self) -> WorkspaceSymbolGraph: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `FileImportBinding.from_dict`、`FileImportTable.from_dict` 與 `WorkspaceSymbolGraph.from_dict` 於必填欄位缺失或型別不符時拋出 `SchemaValidationError`。
  - `WorkspaceGraphLinker.link_workspace` 保證對空輸入、循環匯入、循環繼承與損毀之外掛 `ModulePathResolver`/`EdgeRefiner` 零未捕獲例外，故障外掛降級記錄 `log_warn(..., stream="stderr")`。
- **階段決策紀錄**：`[P03:DR-01]` `RelationEdge.resolution_status` 合法值集合擴充為 `{"unresolved", "resolved", "overload_group", "ambiguous", "external"}`，於 `RelationEdge.__post_init__` 強制驗證。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：當兩個不同模組定義了同名基底類別 `BaseRunner`，子類別 `SubRunner(BaseRunner)` 如何避免像舊版 `TopologyLinker` 一樣用 `short_name` 誤連到錯誤模組？*
  - *答*：Pass 3 解析 `inherits` 邊時，嚴格先查同檔案詞法作用域（Tier 1）與 Pass 2 已解析之 `FileImportTable`（Tier 3：`bindings["BaseRunner"].resolved_symbol_ids`），直接取得唯一目標 `SymbolNode.id` 寫入 `type_bases_by_id[sub_id]`；若未匯入且全倉存在多個同名 `BaseRunner`，該 `inherits` 邊標記為 `ambiguous`，絕不盲目合併兩者的繼承樹。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md` | Modify | 新增 `WorkspaceSymbolGraph`、`WorkspaceGraphLinker` 四階段連結流水線與 `contributes` 擴充設定說明 |
| **專題手冊** | `docs/ast/[topic].md` | N/A | 由 `README.md` 與 `DESIGN_NOTES.md` 完整涵蓋 |
| **設計決策** | `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `DN-AST-06` 記錄四階段確定性跨檔連結流水線、四階作用域查找與零幽靈邊消歧設計 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `schema.py`、`base.py`、`registry.py`、`treesitter.py`、`markdown.py`、`linker.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_02` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認規格鎖定並進入 Pre-Code Analyze Gate 與 Phase 5 實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `contributes/_format.json`、`ast_engine/schema.py`（`FileImportBinding`、`FileImportTable`、`WorkspaceSymbolGraph`、`LanguageConfig`）與 `ast_engine/parsers/base.py`（`ModulePathResolver`、`EdgeRefiner`）
- [x] **TASK-02**：升級 `ParserRegistry`、`TreeSitterDriver` 與 `MarkdownParser`（支援匯入別名、繼承/實作邊區分、欄位型別提取、Markdown `extract_file_graph` 與外掛載入）
- [x] **TASK-03**：於 `ast_engine/linker.py` 實作內建多語言 `ModulePathResolver`、`WorkspaceGraphLinker` 四階段確定性連結流水線（Pass 1~4）與 `expand_contract_symbol_ids` 對接
- [x] **TASK-04**：新建 `ys_codebase/source/ast/tests/test_deterministic_linker.py` 驗證 `FR-01` ~ `FR-05` 與 `EC-01` ~ `EC-05`，並執行全量測試與 `dev check ast`
- [x] **TASK-DOC**：同步更新 `docs/ast/README.md`、`docs/ast/DESIGN_NOTES.md` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
