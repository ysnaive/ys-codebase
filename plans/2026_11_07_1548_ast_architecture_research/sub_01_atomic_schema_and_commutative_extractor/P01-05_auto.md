# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：AST 四大不可變內核原子結構、平權交換律提取器與 core.space 規則範圍綁定  
> 建立日期：2026-11-08  
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
| **FR-01** | 四大不可變原子結構與 `FileSymbolGraph` | 於 `ast_engine/schema.py` 定義 `@dataclass(frozen=True)` 之 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge` 與 `FileSymbolGraph`；`SymbolNode.id` 格式為 `"{canonical_path}::{fqn}"`（同名多載附加確定性 `({param_types})` 後綴），與 `space` 及行號解耦；提供 `to_dict()` / `from_dict()` 雙向序列化並維持 `UnifiedSymbol` / `MemberInfo` / `SymbolCallSite` 相容。 | P0 | [P00:DR-01], [P00:DR-04] |
| **FR-02** | `contributes/ast.json` 規則範圍綁定 (`spaces`) 與多查詢檔 | 擴充 `ys_codebase/source/ast/contributes/_format.json` 與 `LanguageConfig`，支援 `query_files: list[uri]?`、`spaces: list[str]?` 與 `processors: list[str]?`；未指定 `spaces` 時預設對工作區符合副檔名之檔案生效，指定非空 `spaces` 時透過 `core.space.get_default_registry().match_path(file_path, space)` 判定適用性。 | P0 | [P00:DR-02] |
| **FR-03** | 原生相容官方 `queries/tags.scm` 與擴充標籤捕獲 | `TreeSitterDriver` 原生支援 Tree-sitter 官方 `tags.scm` 標籤（`@definition.<kind>`、`@name`、`@doc`、`@reference.<kind>` 及 `#strip!` / `#select-adjacent!`）與擴充標籤（`@def.<kind>`、`@part.<slot>`、`@facet.<key>`、`@edge.<kind>`，並向下相容既有 `@symbol.*` / `@call.*` / `@import.stmt`）。 | P0 | [P00:DR-01], [P00:DR-04] |
| **FR-04** | `@name` 物理座標交換律合流與 `Span` 包含堆疊樹 | 多組 `.scm` 在同檔案捕獲相同 `@name` / `@part.name` 物理 `Span(start_byte, end_byte)` 時，執行五大欄位交換律聯集（`kinds` 聯集、`span` Bounding Box 聯集、`parts` 聯集、`facets` 聯集、`provenance` 字典序穩定聯集），滿足 $A \cup B = B \cup A$；並以 `Span` 包含關係堆疊（Containment Stack）組裝無限層級遞迴 `SymbolNode.children` 與局部 `outgoing_edges`。 | P0 | [P00:DR-04] |
| **FR-05** | 平權 `SymbolProcessor` 管線與 `BaseParser.extract_file_graph` | 建立 `SymbolProcessor` 介面（支援對 `SymbolNode` 與 `RelationEdge` 精煉並追加 `ProvenanceStep(action="refine")`），將 `DialectAdapter` 與非 Tree-sitter 解析器（`MarkdownParser`、`HtmlParser`、`CssParser`、`SpiceParser`、`PythonASTParser`）統一對齊 `BaseParser.extract_file_graph(file_path, content) -> FileSymbolGraph`。 | P0 | [P00:DR-01], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `from_dict` 傳入非 `dict`、缺失必填欄位或容器為 `None` | 拋出 `SchemaValidationError`；`None` 容器欄位自動正規化為空 `tuple`、`frozenset` 或空 `MappingProxyType`。 |
| **EC-02** | 多 `.scm` 以任意相反順序載入或含損毀 `.scm` / Processor | 有效 `.scm` 依 `@name` 座標聯集且 `provenance` 按 `(provider_id, action, rule_or_hook)` 排序，產出 100% 相同 `FileSymbolGraph`；損毀 `.scm` 或 Processor 記錄 `log_warn(..., stream="stderr")` 與 `load_errors` 並跳過，不影響其餘規則。 |
| **EC-03** | 同作用域同名多載方法（如 C# / C++ / TS Overloads） | 從 `parts["parameters"]` 或簽名提取正規化參數型別清單附加至 `SymbolNode.id`（`{canonical_path}::{fqn}({param_types})`），確保同檔多載 ID 唯一且不依賴行號。 |
| **EC-04** | 規則宣告 `spaces: ["core/contributes"]` 但目標檔案不屬於該空間 | `ParserRegistry` 透過 `core.space` 檢查不匹配後自動略過該規則，不污染無關檔案之 `FileSymbolGraph`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 不可變性與靜態守門 | 全數新增資料結構滿足 `@dataclass(frozen=True)` 與 Hashable 契約，通過 `python yscb.py dev check ast`（0 Warnings, 0 Failed）。 |
| **NFR-02** | 單次解析與向後相容 | `extract_file_graph` 單次解析 CST 同時產出 `root_nodes` 與 `outgoing_edges`；既有 `ast` 與 `knowledge-db` 測試 100% 相容。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `ys_codebase/source/ast/tests/test_ast_engine.py:L195` 對 `len(ast_engine.__all__)` 有精確數量斷言，擴充 `ast_engine/__init__.py` 匯出符號時須同步更新該測試斷言。
- **`[!NOTE]`** `dev check` 之 `C8`/`C9` 規則嚴禁頂層可變容器與非 `frozen=True` 之 `@dataclass`，內部字典欄位應統一正規化並搭配 `hash=False`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Source File (file_path, content_bytes)]
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. ParserRegistry & Space Scoping (core.space.match_path)               │
│ • 篩選匹配 extensions 且滿足 spaces 範圍約束（空則預設全範圍）之規則集    │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Multi-Query CST Capture (TreeSitterDriver / Custom Parser)           │
│ • 解析 1 次 CST，平行執行官方 tags.scm + 伴隨 .scm 捕獲定義、部位與關係邊 │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Commutative Merge & Containment Stack Hierarchy                      │
│ • 以 @name / @part.name 之 Span(start_byte, end_byte) 為錨點執行交換律聯集 │
│ • 透過 Containment Stack 組裝無限層級遞迴 SymbolNode.children 與邊起點   │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. SymbolProcessor Pipeline & FileSymbolGraph Materialization           │
│ • 執行平權 SymbolProcessor / DialectAdapter 精煉可見度、修飾符與關係邊    │
│ • 產出不可變 FileSymbolGraph (root_nodes, all_nodes_by_id, edges)       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/contributes/_format.json` | Modify | 擴充 `LanguageDef` 支援 `query_files: list[uri]?`、`spaces: list[str]?`、`processors: list[str]?` |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 新增 `@dataclass(frozen=True)` 之 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge`、`FileSymbolGraph` 與擴充 `LanguageConfig` |
| `ys_codebase/source/ast/ast_engine/parsers/base.py` | Modify | 新增 `SymbolProcessor` 協定基類與 `BaseParser.extract_file_graph` 方法（與既有 `parse()` 雙軌互通） |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 實作多 `.scm` 平權載入、官方 `tags.scm` + 擴充標籤捕獲、`@name` 物理座標交換律合流、無限層級包含堆疊與單次掃描 `extract_file_graph` |
| `ys_codebase/source/ast/ast_engine/parsers/registry.py` | Modify | 支援 `query_files`、`spaces`（透過 `core.space` 過濾）、`processors` 載入與 `extract_file_graph` 聚合分派 |
| `ys_codebase/source/ast/ast_engine/__init__.py` | Modify | 匯出 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge`、`FileSymbolGraph`、`SymbolProcessor` |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 擴充四大不可變原子結構、`FileSymbolGraph`、穩定 ID 與雜湊/序列化測試，對齊 `__all__` 數量斷言 |
| `ys_codebase/source/ast/tests/test_dialects_and_parsers.py` | Modify | 擴充官方 `tags.scm` 相容、多 `.scm` 交換律合流（$A \cup B = B \cup A$）、無限層級樹、`spaces` 範圍綁定與 `SymbolProcessor` 測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `FileSymbolGraph` 與既有 `UnifiedSymbol` 雙軌無損橋接**：`BaseParser` 新增 `extract_file_graph(file_path, content, *, space="unified") -> FileSymbolGraph`；既有 `parse()`、`extract_call_sites()` 可直接由 `FileSymbolGraph` 無損轉換或互相推導，確保 `sub_01` 期間零破壞既有呼叫端。
- **[P02:DR-02] `@name` 錨點交換律合流演算法**：同檔案內凡 `@name` / `@part.name` 擁有相同 `(start_byte, end_byte)` 之捕獲項自動歸併為同一符號：
  - `kinds`：$K_A \cup K_B$（若同時含 `"function"` 與容器內 `"method"`，在類別/結構/介面容器內正規化包含 `"method"`）
  - `span`：$(\min(\text{start\_byte}), \max(\text{end\_byte}))$ Bounding Box 聯集
  - `parts`：以槽位名稱合併，同槽位取 Bounding Box 聯集
  - `facets`：鍵值合併（集合/元組類屬性執行排序去重聯集）
  - `provenance`：去重後依 `(provider_id, action, rule_or_hook, detail or "")` 字典序排序。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
@dataclass(frozen=True)
class Span:
    start_byte: int
    end_byte: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def contains(self, other: "Span") -> bool: ...
    def union(self, other: "Span") -> "Span": ...
    def slice_bytes(self, source_bytes: bytes) -> bytes: ...
    def slice_text(self, source_bytes: bytes, encoding: str = "utf-8") -> str: ...
    def to_dict(self) -> Dict[str, int]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Span": ...


@dataclass(frozen=True)
class ProvenanceStep:
    provider_id: str
    action: str
    rule_or_hook: str
    detail: Optional[str] = None

    def sort_key(self) -> Tuple[str, str, str, str]: ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceStep": ...


@dataclass(frozen=True)
class SymbolNode:
    id: str
    name: str
    scope_path: Tuple[str, ...]
    kinds: FrozenSet[str]
    language: str
    span: Span
    parts: Mapping[str, Span] = field(default_factory=dict, hash=False)
    facets: Mapping[str, Any] = field(default_factory=dict, hash=False)
    children: Tuple["SymbolNode", ...] = field(default=(), hash=False)
    provenance: Tuple[ProvenanceStep, ...] = field(default=(), hash=False)

    @property
    def fqn(self) -> str: ...
    @staticmethod
    def compute_canonical_id(
        file_path: str,
        fqn: str,
        overload_suffix: str = "",
    ) -> str: ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolNode": ...


@dataclass(frozen=True)
class RelationEdge:
    source_id: str
    target_expr: str
    edge_kind: str
    span: Span
    resolution_status: str = "unresolved"
    resolved_target_ids: Tuple[str, ...] = ()
    provenance: Tuple[ProvenanceStep, ...] = field(default=(), hash=False)

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationEdge": ...


@dataclass(frozen=True)
class FileSymbolGraph:
    file_path: str
    content_hash: str
    language: str
    root_nodes: Tuple[SymbolNode, ...] = field(default=(), hash=False)
    all_nodes_by_id: Mapping[str, SymbolNode] = field(default_factory=dict, hash=False)
    outgoing_edges: Tuple[RelationEdge, ...] = field(default=(), hash=False)

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileSymbolGraph": ...


class SymbolProcessor:
    provider_id: str = "ast:default_processor"

    def refine_file_graph(
        self,
        graph: FileSymbolGraph,
        source_bytes: bytes,
    ) -> FileSymbolGraph: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `Span.from_dict`、`ProvenanceStep.from_dict`、`SymbolNode.from_dict`、`RelationEdge.from_dict`、`FileSymbolGraph.from_dict` 遇非 `dict` 或缺失必要欄位時統一拋出 `SchemaValidationError`。
  - 無效之 `.scm` 查詢檔或動態 `SymbolProcessor` 載入失敗時，捕獲異常並透過 `core.log.log_warn(..., stream="stderr")` 記錄於 `ParserRegistry.load_errors`，不中斷主流程。
- **階段決策紀錄**：`[P03:DR-01]` `SymbolNode.parts` 與 `facets`、`FileSymbolGraph.all_nodes_by_id` 於 `__post_init__` 統一封裝為 `MappingProxyType`，確保執行期唯讀不可變且符合 `dev check` `C9` 規範。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：多組 `.scm` 若同時定義同一函式（如官方 `tags.scm` 捕獲 `@definition.function` + `@name`，伴隨 `parts.scm` 捕獲 `@def.function` + `@part.name` + `@part.parameters` + `@part.return_type` + `@part.body`），如何保證不論載入順序為何皆合成單一 `SymbolNode`？*
  - *解*：提取器將 `@name` 與 `@part.name` 統一映射至 `parts["name"]`，並以 `(name_span.start_byte, name_span.end_byte)` 作為單檔符號實體唯一合併鍵；所有集合與來源步驟均透過排序聯集歸併，從數學上保證交換律與冪等性。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md` | Modify | 增補四大原子結構、`FileSymbolGraph`、`spaces` 範圍綁定與官方 `tags.scm` 平權合流說明 |
| **專題手冊** | `docs/ast/architecture.md` | N/A | 整合於 `README.md` 與 `DESIGN_NOTES.md` |
| **設計決策** | `docs/ast/DESIGN_NOTES.md` | Modify | 記錄 `@name` 物理座標交換律合流與 `core.space` 規則範圍綁定設計 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `schema.py`、`treesitter.py`、`registry.py`、`base.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_01` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 規格契約已鎖定，進入 Pre-Code Analyze Gate 與實作階段。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `ys_codebase/source/ast/contributes/_format.json` 與 `ast_engine/schema.py`（實作 `Span`, `ProvenanceStep`, `SymbolNode`, `RelationEdge`, `FileSymbolGraph` 及 `LanguageConfig` 擴充欄位）
- [x] **TASK-02**：於 `ast_engine/parsers/base.py`、`treesitter.py`、`registry.py` 及各語言 Parser 實作官方 `tags.scm` 相容提取、`@name` 物理座標交換律合流、無限層級包含堆疊、`spaces` 範圍過濾、`SymbolProcessor` 管線與 `extract_file_graph`，並於 `ast_engine/__init__.py` 匯出新符號
- [x] **TASK-03**：於 `tests/test_ast_engine.py` 與 `tests/test_dialects_and_parsers.py` 編寫正向與負向單元測試，通過靶向測試、`dev check ast` 與全量回歸測試
- [x] **TASK-DOC**：同步更新 `docs/ast/README.md`、`docs/ast/DESIGN_NOTES.md` 與微觀 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
