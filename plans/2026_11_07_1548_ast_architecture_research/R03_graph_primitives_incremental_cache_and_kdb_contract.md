# 專題調研與分析報告：AST 全倉圖譜操作原語、增量快取與下游消費契約 (R03_graph_primitives_incremental_cache_and_kdb_contract.md)

> 調研主題：AST 第三大項：L0/L1 圖譜操作原語（Slice / Query / Traverse）、對齊 core.space 之單檔子圖增量快取與下游 KDB / Compiler 消費契約  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 在 `R01`（原子符號定義与平權注入）與 `R02`（四階段確定性跨檔連結器）定案後，檢視現有 `ast_engine/bundler.py` 與 `ast_engine/engine.py` 在「快取維護」與「對外 API 原語」層面仍存在三大結構性痛點：
    1. **單檔重複解析三次且跨檔狀態污染單檔快取**：現有 `bundler.py` 的 `_parse_file_full()` 對同一檔案分別呼叫 `parse_file()`、`extract_call_sites()`、`extract_imports()` 三次；且將 C# `partial class` 的跨檔合併直接覆寫於單檔 `UnifiedSymbol` 上，導致增量更新時必須依賴 `metadata["_own_members"]` 執行脆弱的狀態還原（`restore_unaggregated_partial_symbol`）。
    2. **L0（無狀態單檔操作）與 L1（全倉有狀態快取）糾纏且未對齊 `core.space`**：現有 `ASTEngine.outline()` 強制初始化磁碟索引目錄與舊版 `FileSpaceManager`；同時 AST 規則缺乏與 `core.space` 的空間綁定機制。
    3. **缺乏無損部位切片（Part Slicing）與通用關係圖遍歷原語**：現有 `SnippetExtractor` 僅能按行號前後固定抓取 2~5 行（上限 25 行），無法按符號子部位（如 `signature`、`doc`、`body`）無損提取源碼；且圖譜查詢僅有寫死 `calls` 邊的 `callers`/`callees`/`impact`，無法支撐 KDB 多視角文檔管線對繼承鏈、文檔引用邊與可見度過濾的需求。
- **調研目標與範疇**：
  - 本報告（`R03`）聚焦於 AST 架構拆解之**第三大項：圖譜操作原語、增量快取與下游消費契約**，旨在：
    1. 確立 `module:ast` 與 `core.space` 的正交協同機制（規則透過 `spaces` 直接引用 `core.space` 定義，預設不填即 `project://` 全掃描）。
    2. 定義基於不可變單檔局部圖（`FileSymbolGraph`）的一次性提取（Single-Pass）與增量熱修補（Incremental Hot-Patch）架構。
    3. 定義 L0 無狀態單檔原語與 L1 全倉圖譜通用查詢原語，對齊未來 KDB「萬物皆符號 SSOT」文檔管線與 Compiler/Checker 的消費需求。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 與 `core.space` 之正交協同：直接引用 `space` 定義（預設 `project://` 全掃描）

為徹底貫徹單一職責原則（SRP），`module:ast` 全面移除對舊 `module:file-space` 的依賴，直接建立於微內核 `core.space` 之上：

| 協同介面 | `core.space` 負責之職責（SSOT） | `module:ast` 消費方式 |
| :--- | :--- | :--- |
| **1. 貢獻規則適用範圍**<br>*(Rule Space Binding)* | 在 `contributes/core.json -> spaces` 統一管理所有空間定義（含 `entries`、`presets`、`include`、`exclude` 與三座標預編譯匹配器）。 | `contributes/ast.json` 中的規則僅需選填 **`spaces?: list[str]`**（如 `["core/contributes"]`），**絕不在 `ast.json` 另搞一套 `include`/`exclude`**：<br>• **有指定 `spaces`**：僅對命中該 `core.space` 之檔案生效（L0 呼叫 `core.space.match_path(path, space)` 判定；L1 列舉該空間檔案）。<br>• **未指定 `spaces`（預設）**：預設對整個 `project://` 工作區所有符合該語言副檔名之檔案生效。 |
| **2. 增量變更偵測**<br>*(Dirty Diff Cursor)* | 透過 `core.space` 指紋與游標機制追蹤工作區新增、修改、刪除之檔案集合。 | `ASTEngine` 以 `consumer_id="ast"` 消費變更集，僅針對 Dirty Files 重新產出單檔 `FileSymbolGraph` 並重連受影響的跨檔 `RelationEdge`。 |

### 2.2 單檔不可變子圖（`FileSymbolGraph`）與零污染增量快取架構

為根除「同檔解析三次」與「`_own_members` 跨檔狀態污染」，內核將單檔解析產物封裝為純粹、不可變的 **`FileSymbolGraph`**：

```python
@dataclass(frozen=True)
class FileSymbolGraph:
    """單一檔案經過平權 .scm 與 SymbolProcessor 一次性提取出的不可變局部符號圖。"""
    file_path: str                              # 規範化專案相對路徑或語意 URI (如 "ys_codebase/source/ast/ast_engine/engine.py")
    content_hash: str                           # 檔案內容指紋 (對齊 core.space hasher)
    language: str                               # 主語言識別碼
    root_nodes: Tuple[SymbolNode, ...]          # 該檔案之頂層遞迴符號樹 (內含 children)
    all_nodes_by_id: Dict[str, SymbolNode]      # 該檔案所有層級 SymbolNode 之平坦索引表
    outgoing_edges: Tuple[RelationEdge, ...]    # 該檔案發起之所有 RelationEdge (imports, inherits, calls, references, documents)
```

- **為什麼以 `FileSymbolGraph` 作為快取原子能徹底簡化增量更新？**
  1. **Single-Pass 一次性產出**：Tree-sitter 解析一次 CST 後，平權執行所有適用的 `.scm` 與 `SymbolProcessor`，同時產出 `root_nodes` 與 `outgoing_edges`（含 `imports`、`inherits`、`calls`），磁碟 I/O 與 CST 解析次數從 3 次降至 **1 次**。
  2. **單檔物理狀態永遠純淨**：跨檔同體聚合（如 C# `partial class` 或 `.h`/`.cpp` 配對）僅在 L1 全倉圖譜的邏輯視角（`WorkspaceSymbolGraph`）透過 `RelationEdge(edge_kind="merges_with")` 建立關聯，**絕不回頭竄改單檔 `FileSymbolGraph` 內的 `SymbolNode`**。
  3. **$O(|\text{Dirty}|)$ 乾淨熱修補**：當檔案 `F` 修改或刪除時，快取直接替換或移除 `file_graphs[F]`，並僅針對檔案 `F` 的 `outgoing_edges` 及原本指向檔案 `F` 舊符號的外部入邊（Incoming Edges）重新執行 `WorkspaceGraphLinker` 消歧，無須任何 `_own_members` 還原邏輯。

### 2.3 L0（無狀態單檔層）vs. L1（全倉圖譜層）正交 API 原語設計

對齊 `core.space` 的 L0 / L1 分層規範，將 `module:ast` 的能力收斂為兩層共 6 個正交原語：

| 分層 | 原語名稱與簽名 | 核心功能與特性 | 對下游（KDB 文檔管線 / Compiler / IDE）之價值 |
| :--- | :--- | :--- | :--- |
| **L0 無狀態單檔層**<br>*(Zero-Index / Stateless)* | **1. `parse_file(file_or_uri, *, content=None) -> FileSymbolGraph`** | 不讀寫任何全倉索引檔，直接對單一檔案執行平權 `.scm` + `SymbolProcessor`（自動透過 `core.space.match_path` 套用符合 `spaces` 之規則），返回 `FileSymbolGraph`。 | 供 Compiler/Checker 或單檔工具毫秒級取得完整語法符號樹與局部關係邊。 |
| **L0 無狀態單檔層**<br>*(Zero-Index / Stateless)* | **2. `outline(file_or_uri, *, kinds=None, visibility=None) -> Tuple[SymbolNode, ...]`** | 直接投影 `FileSymbolGraph.root_nodes` 階層樹，支援按 `kinds` 集合與 `facets["visibility"]` 過濾（廢除獨立的 `OutlineNode` 類別）。 | 消除 `UnifiedSymbol` 與 `OutlineNode` 雙軌轉換成本，單檔大綱與全倉符號 100% 同構。 |
| **L0 無狀態單檔層**<br>*(Zero-Index / Stateless)* | **3. `slice_part(symbol_or_id, part="outer", *, file_bytes=None) -> bytes \| str`** | 根據 `SymbolNode.parts[part]`（如 `"name"`、`"signature"`、`"parameters"`、`"return_type"`、`"doc"`、`"body"`）或 `node.span`（`"outer"`）的 `Span(start_byte, end_byte)`，直接對原始檔執行 **$O(1)$ 無損字節切片**。 | **KDB 文檔生成核心原語**：直接從源碼無損抽出 100% 完整的函式簽名、完整 Docstring 或範例函式體，徹底廢除固定行數截斷的 `SnippetExtractor`！ |
| **L1 全倉圖譜層**<br>*(Workspace Graph)* | **4. `resolve(selector_expr, *, spaces=None, kinds=None) -> SymbolResolutionResult`** | 支援結構化選擇器（`[kind] [scope.]name[(param_types)]`），跨全倉（含程式碼、文檔與 `contributes` 符號）確定性消歧，回傳 `matched` / `overload_group` / `ambiguous` / `not_found`。 | 統一全倉符號尋址入口，移除硬編碼的 `is_doc_symbol` 排除限制，讓文檔符號與配置符號享有同等解析能力。 |
| **L1 全倉圖譜層**<br>*(Workspace Graph)* | **5. `select_nodes(*, spaces=None, kinds=None, visibility=None, facets=None) -> Tuple[SymbolNode, ...]`** | 在全倉 `WorkspaceSymbolGraph` 上按所屬空間（`core.space`）、多重 `kinds` 交集、可見度（`public`/`protected`/`private`）與自訂 `facets` 批次篩選符號節點。 | 供 KDB 按視角批次提取目標符號集合（例如一次抽出某模組所有 `visibility="public"` 的 SDK 符號，或所有 `kinds` 含 `"cli_command"` 的指令符號）。 |
| **L1 全倉圖譜層**<br>*(Workspace Graph)* | **6. `traverse_edges(seed_ids, *, edge_kinds=None, direction="out"\|"in"\|"both", depth=1, status_filter=None) -> SubGraph`** | 通用有向圖 BFS 遍歷原語：支援指定任意 `edge_kinds`（`calls`、`inherits`、`implements`、`imports`、`references`、`documents`、`contributes_to`）與跳數 `depth`（既有 `callers`、`callees`、`impact` 直接退化為 `edge_kinds={"calls"}` 的便捷別名）。 | 同時支撐呼叫鏈分析、類別繼承樹展開、跨模組 `contributes` 拓撲追蹤，以及 KDB 的文檔引用圖遍歷！ |

### 2.4 如何直接賦能 KDB「萬物皆符號 SSOT」三大文檔輸出管線？

當 `module:ast` 具備上述 `R01 + R02 + R03` 架構後，未來 KDB 建立「單一符號 SSOT 多視角文檔管線」時，完全不需要自己解析源碼或維護重複敘述，只需直接組合呼叫 AST 的原語：

1. **視角一：對外技術文檔 / SDK Reference（Public API View）**
   - 呼叫 `select_nodes(spaces=["source"], visibility={"public"})` 取得所有公開 API 符號。
   - 搭配 `slice_part(node, "signature")` 與 `slice_part(node, "doc")` 即時從原始碼無損提取最新型別簽名與 Docstring，並用 `traverse_edges(node.id, edge_kinds={"inherits", "implements"}, direction="out")` 自動生成繼承關係圖。
2. **視角二：對內技術超集文檔（Internal Architecture & Audit View）**
   - 呼叫 `select_nodes(spaces=["source", "core/contributes"], visibility={"public", "protected", "private"})` 納入內部私有實作與 `contributes` 擴充點符號。
   - 結合 `traverse_edges(..., edge_kinds={"calls", "contributes_to"}, direction="both")` 與 `node.provenance`，自動輸出包含上下游呼叫拓撲、跨模組注入來源與實作細節的完整內部手冊。
3. **視角三：教學文檔與文檔健康度守門（Tutorial & Doc-Drift Gate）**
   - 教學文檔（Markdown）透過符號引用語法（產生 `RelationEdge(edge_kind="documents", target_expr="...")`）直接嵌入或指向程式碼中的 `SymbolNode.id`（甚至直接 `slice_part(target_id, "body")` 內嵌真實測試範例代碼，確保教學範例永遠不會與源碼脫節）。
   - 當某個底層函式改名或刪除時，KDB 只需查詢 `traverse_edges(..., edge_kinds={"documents"}, status_filter={"unresolved", "ambiguous"})`，即可在 CI / Checker 階段 100% 攔截所有失效的文檔引用！

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. `module:ast` 的規則範圍綁定應**直接透過 `spaces?: list[str]` 引用 `core.space` 定義（預設不填即 `project://` 全掃描）**，不在 `ast` 內重複定義 `include`/`exclude`，實現與 `core.space` 的 100% 正交咬合。
  2. 以單次掃描產出的不可變 **`FileSymbolGraph`** 作為 L1 快取基本單位，結合 **L0 三大無狀態原語（`parse_file`、`outline`、`slice_part`）**與 **L1 三大圖譜查詢原語（`resolve`、`select_nodes`、`traverse_edges`）**，即可彻底消除現有 `bundler.py`/`engine.py` 的重複解析與狀態污染，並為未來 KDB 的「萬物皆符號 SSOT」多視角文檔管線提供堅實底座。
- **後續建議（選填）**：
  - 至此，AST 模組正交化重構的三大核心議題（`R01` 原子符號定義與平權注入、`R02` 跨檔語意連結與全倉圖譜、`R03` 圖譜操作原語與 `core.space` 增量協同）已全數完成深度調研與定案。可選擇直接於本計畫轉入实作規格規劃，或先將結論收納至 Roadmap 並回頭展開 KDB 文檔管線設計。
