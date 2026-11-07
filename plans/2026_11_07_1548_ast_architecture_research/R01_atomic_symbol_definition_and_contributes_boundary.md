# 專題調研與分析報告：AST 原子符號定義與內核 vs. Contributes 注入邊界 (R01_atomic_symbol_definition_and_contributes_boundary.md)

> 調研主題：AST 第一大項：產出的原子符號定義、Tree-sitter 官方 tags.scm 標準相容與內核 vs. Contributes 注入設定邊界  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 繼 `file-space` 模組因早期僅從 `knowledge-db`（KDB）抽離部分設計而進行正交重構並下沉為 `core.space` 後，檢視 `ys_codebase/source/ast/` 發現其同樣存在嚴重的「KDB 檢索切片耦合症候群」：
    1. **資料結構三軌分裂與資訊截斷**：`ast_engine/schema.py` 將符號拆成互不相容的 `UnifiedSymbol`、`MemberInfo` 與 `OutlineNode` 三套結構；`UnifiedSymbol` 內含專供 KDB 全文檢索使用的 `search_payload`，且 `treesitter.py` 將 `signature` 硬截斷於 200 字元、`docstring` 硬截斷於 500 字元，並丟棄參數列表與裝飾器等語意細節。
    2. **單層壓平階層與空間綁定 ID**：`treesitter.py` 僅以單層 `parent_symbol` 字串記錄直屬父類別，超過兩層之巢狀結構全部扁平化；`symbol_id` 直接將 `space` 名稱硬編碼為前綴（`f"{space}:{file_path}::{fqn}"`），導致同一檔案在不同邏輯空間下產生分裂的符號 ID。
    3. **自造非標 `.scm` 語法規則且缺乏 `core.space` 適用範圍綁定**：現有 `assets/queries/*.scm` 採用自訂標籤從頭手寫各語言查詢規則，與上游 Tree-sitter 官方 `queries/tags.scm` 標準脫節；同時 `contributes/ast.json` 僅能按副檔名（如 `.json`、`.py`）全域套用，無法直接引用 `core.space` 空間定義來鎖定特定領域檔案子集（如僅針對 `core/contributes` 空間解析 `contributes/*.json`）。
- **調研目標與範疇**：
  - 本報告（`R01`）聚焦於 AST 架構拆解之**第一大項：產出的原子符號定義與提取邊界**，旨在：
    1. 對齊 Tree-sitter 的底層運作機制（CST 具體語法樹 $\to$ S-Expression `.scm` 模式匹配捕獲 $\to$ 宿主驅動器組裝抽象符號圖）。
    2. 劃定「**內核原始碼（Kernel Source Code）**」與「**`contributes` 宣告式注入設定 + 符號處理器（Symbol Processor）**」的正交職責邊界。
    3. 定義統一、無損、可追溯的內核原子結構（`Span`、`SymbolNode`、`RelationEdge`、`ProvenanceStep`），確立**多 `.scm` 全平權一等公民與交換律合流（Commutative Merge）機制**、**原生相容 Tree-sitter 官方 `queries/tags.scm` 標準**，以及**直接引用 `core.space` 定義作為規則適用範圍（預設不填為 `project://` 全掃描）**之正交契約。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 Tree-sitter 運作機制與 AST 引擎三階轉換流程

Tree-sitter 本身並非直接產出高階語意符號圖譜，而是執行從原始字節流到結構化模式匹配的底層引擎。完整的單檔符號提取分為三個嚴格分離的階段：

| 階段 | 執行組件 | 輸入 $\to$ 輸出 | 核心職責與邊界 |
| :--- | :--- | :--- | :--- |
| **Step 1：語法解析**<br>*(Lexing & Parsing)* | Tree-sitter Grammar (`Parser.parse`) | `source_bytes` $\to$ **CST（具體語法樹）** | 依據各語言 C 編譯文法將字節流轉為無損包含所有標點、括號、註解與精確 Byte/Row-Col 座標的 `Tree` / `Node` 樹，並支援 $O(\log N)$ 增量重解析。 |
| **Step 2：多規則模式捕獲**<br>*(Multi-Query Capturing)* | 符合該檔案副檔名與 `spaces` 範圍之所有 `.scm` (`Query.matches`) | **CST** + 多組 `.scm` 規則 $\to$ **帶標籤之 `Node` 捕獲集合** | 各模組注入的 `.scm`（包含上游官方 `tags.scm`、部位擴充 `.scm` 與限定特定 `space` 之領域 `.scm`）平權在 CST 上匹配語法結構並貼上標準語意捕獲標籤。 |
| **Step 3：交換律合流與精煉**<br>*(Commutative Merge & Refinement)* | 內核通用組裝器 + 注入之 `SymbolProcessor` | **捕獲集合** $\to$ **遞迴 `SymbolNode` 樹 + `RelationEdge` 列表** | 內核以 `@name` / `@part.name` 物理座標為錨點將多組 `.scm` 捕獲無序合流為同構 `SymbolNode`，按 `Span` 包含關係組裝父子樹，並執行平權 `SymbolProcessor` 正規化。 |

### 2.2 內核原始碼（Kernel）vs. `contributes` 注入設定之正交職責切分

為確保 `module:ast` 具備與 `core.space` 同等級的正交性，將「跨語言恆定的數學與圖論結構」收斂於內核原始碼，並將「語言與領域規則」100% 抽離為平權的 `contributes` 自注入設定：

| 維度 | 內核原始碼（Kernel — 恆定不變的結構與演算法） | `contributes` 注入設定（Declarative + Hook — 平權一等公民規則） | 現況病症對照（`schema.py` / `treesitter.py`） |
| :--- | :--- | :--- | :--- |
| **1. 符號資料結構與多重種類**<br>*(Atomic Schema & Multi-Kinds)* | 定義**單一遞迴同構的 `SymbolNode`** 與精確物理座標 **`Span`**；符號種類定義為**無主從之分的集合 `kinds: FrozenSet[str]`**，廢除三軌分裂與 `search_payload`。 | 任何模組皆可透過 `.scm` 的 `@definition.<kind>` / `@def.<kind>` 或 Processor 為符號注入平權種類標籤（如 `function` 與 `cli_command` 並列為一等公民）。 | 現況強行規定單一 `kind: str` 且將欄位寫死在 `UnifiedSymbol`，子成員被降級為缺欄位的 `MemberInfo`。 |
| **2. 規則適用空間綁定**<br>*(Space Scoping via `core.space`)* | 內核透過 `core.space.match_path()` 判定目標檔案是否屬於規則指定的 `spaces`；**若規則未指定 `spaces`，預設即對 `project://` 全範圍（凡副檔名匹配者）生效**。 | 於 `contributes/ast.json` 註冊規則時直接選填引用 `spaces: list[str]`（如 `["core/contributes"]`），**不在 `ast.json` 重複發明 `include`/`exclude`**，檔案集合定義 100% 交由 `core.space` SSOT 維護。 | 現況僅能按副檔名全域綁定，無法針對特定 `space`（如 `contributes/*.json` 或 `plans/*.md`）掛載專屬 AST 提取器。 |
| **3. 部位切片座標**<br>*(Part Spans)* | 在 `SymbolNode` 內建通用字典 **`parts: Dict[str, Span]`**，提供 $O(1)$ 根據部位名稱從原始檔無損切片（Slice）或原位替換（Splice）的原子方法。 | 透過 `.scm` 的 `@name` / `@doc`（官方 `tags.scm`）與 `@part.<slot>`（擴充槽位如 `parameters`、`return_type`、`body`）映射至 `parts`。 | 現況在 `treesitter.py` 硬編碼只抓 4 個固定標籤（且截斷至 200/500 字），不保留各子部位的 `Span` 座標。 |
| **4. 屬性與修飾符**<br>*(Facets & Metadata)* | 定義通用屬性容器 **`facets: Dict[str, Any]`** 與屬性集合合併規則。 | 透過 `.scm` 的 `@facet.<key>` 捕獲語法標記，並由選填的 `SymbolProcessor` 注入**語意推導規則**（如可見度判定、註解剝離、領域配置提取）。 | 現況散落在 `dialects/` 各語言類別中，缺乏統一的屬性擴充契約與宣告式映射。 |
| **5. 階層樹與作用域**<br>*(Containment & Scope)* | 實作**基於 `Span` 包含關係的通用父子堆疊演算法（Containment Stack）**、結構化路徑 `scope_path: Tuple[str, ...]` 與穩定語意 URI 計算器。 | 注入各語言的**作用域分隔符（`scope_separator`：`.`、`::` 或 `/`）**與**同名重載消歧規則（Overload Disambiguation）**。 | 現況只支援單層 `parent_symbol` 壓平列表，且 `symbol_id` 混入 `space` 前綴導致跨空間斷鏈。 |
| **6. 關係邊提取與來源追蹤**<br>*(Relation Edges & Provenance)* | 定義通用有向邊 **`RelationEdge`** 與不可變履歷 **`provenance: Tuple[ProvenanceStep, ...]`**，平權記錄所有參與提取與處理器介入的來源軌跡。 | 透過官方 `tags.scm` 的 `@reference.<kind>` 與擴充 `@edge.<kind>` 宣告關係邊，並自動以註冊之 `provider_id` 留痕。 | 現況僅支援硬編碼的 `SymbolCallSite`（只抓函式呼叫），且無任何規則來源追蹤。 |

### 2.3 內核四大原子資料結構規格（Kernel Atomic Schema）

內核不感知具體程式語言細節，僅操作以下四個不可變（Frozen Dataclass）原子結構：

```python
@dataclass(frozen=True)
class Span:
    """精確物理區間原子：同時支撐 O(1) Byte 切片與人類可讀行列定位。"""
    start_byte: int
    end_byte: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass(frozen=True)
class ProvenanceStep:
    """符號解析來源履歷步驟：平權記錄參與該符號生成或精煉的規則來源。"""
    provider_id: str              # 注入來源 ID，如 "ast:python/tags.scm", "ast:python/parts.scm", "core:yscb_cli.scm"
    action: str                   # 動作類型: "extract" (.scm 捕獲) | "refine" (Processor 精煉)
    rule_or_hook: str             # 觸發的具體規則或 Hook 名稱，如 "@definition.function", "@def.cli_command"
    detail: Optional[str] = None  # 選填診斷說明


@dataclass(frozen=True)
class SymbolNode:
    """單一遞迴同構符號節點：統一表示檔案、類別、方法、參數、章節與領域符號。"""
    id: str                                       # 穩定語意 URI: "{canonical_path}::{fqn}" (與 space 名稱及行號脫鉤)
    name: str                                     # 局部名稱 (如 "handle_list")
    scope_path: Tuple[str, ...]                   # 結構化階層路徑 (如 ("CLIHandler", "handle_list"))，搭配 scope_separator 渲染 FQN
    kinds: FrozenSet[str]                         # 平權多重符號種類集合 (如 frozenset({"function", "cli_command"}))，無主從之分
    language: str                                 # 語言或方言 ID (如 "python", "markdown", "json")
    span: Span                                    # 整個符號定義的完整外框區間 (所有匹配規則之 Bounding Box 聯集)
    parts: Dict[str, Span]                        # 子部位區間字典 (如 {"name": Span, "doc": Span, "parameters": Span, "return_type": Span, "body": Span})
    facets: Dict[str, Any]                        # 結構化語意屬性 (如 visibility, modifiers, parameters, return_type)
    children: Tuple["SymbolNode", ...] = ()       # 遞迴子符號樹 (取代原本分裂的 members 與 OutlineNode)
    provenance: Tuple[ProvenanceStep, ...] = ()   # 完整記錄參與此符號生成的來源集合 (按 provider_id 確定性排序)


@dataclass(frozen=True)
class RelationEdge:
    """通用有向關係邊：統一表示匯入、繼承、實作、呼叫與文檔引用關係。"""
    source_id: str                                # 發起端 SymbolNode.id
    target_expr: str                              # 目標原始表達式 (未跨檔連結前之符號名或路徑表達式)
    edge_kind: str                                # 關係種類: "imports" | "inherits" | "implements" | "calls" | "references" | "documents"
    span: Span                                    # 該引用發生的精確原始碼位置
    resolution_status: str = "unresolved"         # "resolved" | "overload_group" | "ambiguous" | "external" | "unresolved"
    resolved_target_ids: Tuple[str, ...] = ()     # 經 Linker 跨檔消歧後的目標穩定 SymbolNode.id 元組
    provenance: Tuple[ProvenanceStep, ...] = ()   # 關係邊提取與消歧來源履歷
```

### 2.4 多 `.scm` 全平權一等公民、交換律合流、官方 `tags.scm` 相容與 `core.space` 綁定機制

1. **直接引用 `core.space` 定義限定規則範圍（預設不給即 `project://` 全掃描）**：
   - 遵循單一職責原則（SRP），檔案過濾規則（`entries`、`presets`、`include`、`exclude`）100% 由 `core.space`（`contributes/core.json -> spaces`）統一維護，`contributes/ast.json` **絕不重複定義 `include`/`exclude`**。
   - 在 `contributes/ast.json` 註冊語法查詢或處理器規則時，僅需提供選填欄位 `spaces?: list[str]`（支援 `<owner>/<space>` 限定名或 `<space>` 短名，如 `spaces: ["core/contributes"]`）：
     - **指定 `spaces` 時**：僅對命中該 `core.space` 定義的檔案執行該 AST 解析規則（單檔 L0 操作時直接呼叫 `core.space.match_path(file_path, space_query)` 判定；全倉 L1 掃描時直接列舉對應空間）。
     - **未指定 `spaces` 時（預設）**：預設適用於整個 `project://` 工作區內所有符合該語言 `extensions` 的檔案。
2. **原生相容 Tree-sitter 官方 [`queries/tags.scm`](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html) 標準並支援多檔拆解組合**：
   - 內核直接將官方 `tags.scm` 的標準捕獲標籤視為原生一等語法（`@definition.<kind>`、`@name`、`@doc`、`@reference.<kind>`，並支援 `#select-adjacent!` 與 `#strip!` 指令）。
   - 任何主流語言可直接原封不動引入官方倉庫維護的 `queries/tags.scm` 作為基底，再平權掛載輕量伴隨 `.scm` 補抓 `@part.parameters`、`@part.return_type`、`@part.body` 與 `@edge.imports`。
3. **以 `@name` / `@part.name` 物理座標為錨點的交換律無序合流（Commutative Merge）**：
   - 當多個不同的 `.scm` 在同一檔案捕獲到**相同 `@name` 物理 `Span(start_byte, end_byte)`** 時，內核判定為同一符號實體，並執行滿足交換律（$A \cup B = B \cup A$）的五大欄位聯集（`kinds` 集合聯集、`span` Bounding Box 聯集、`parts` 字典聯集、`facets` 聯集、`provenance` 集合聯集），徹底免疫 `core.contributes` 底層合併順序差異。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. `module:ast` 的第一階段重構基石確立為**「單一遞迴同構的 `SymbolNode`（含平權多重種類 `kinds: FrozenSet[str]` 與多部位無損座標 `parts: Dict[str, Span]`）+ 通用有向邊 `RelationEdge` + 來源追蹤 `provenance`」**。
  2. 所有透過 `contributes` 注入的 `.scm` 規則與 `SymbolProcessor` 皆為**無主從之分的一等公民**，支援透過 `spaces` 欄位直接引用 `core.space` 空間定義（預設不給即 `project://` 全掃描），並透過**原生相容官方 `queries/tags.scm`** 與 **`@name` 物理座標交換律合流**消除手寫維護成本與順序依賴。
- **後續建議（選填）**：
  - 第一大項（`R01`）已完整定案（`Concluded`），並與 `R02`（跨檔語意連結）、`R03`（圖譜操作原語與 `core.space` 增量快取協同）構成完整的 AST 重構三部曲。
