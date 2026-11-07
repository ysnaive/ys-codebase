# 專題調研與分析報告：AST 跨檔語意連結與全倉圖譜組裝機制 (R02_cross_file_linking_and_workspace_graph.md)

> 調研主題：AST 第二大項：單檔符號樹如何透過跨檔名稱解析與連結器（Scope-Import Linker & Deterministic Resolver）組裝為全倉語意圖譜  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 在第一大項（`R01`）完成後，單一檔案經過平權 `.scm`（官方 `tags.scm` + 伴隨 `parts_and_imports.scm`）與 `SymbolProcessor` 處理，會產出包含遞迴 `SymbolNode` 樹與未解析關係邊（`RelationEdge(target_expr=..., resolved_target_ids=())`）的**單檔局部符號圖（`FileSymbolGraph`）**。
  - 然而，檢視現有 `ast_engine/linker.py` 與 `ast_engine/resolver.py`，在將單檔局部圖組裝為跨檔案**全倉語意圖譜（`WorkspaceSymbolGraph`）**時存在四大架構缺陷：
    1. **僅連結 `calls` 而忽略繼承與匯入之拓撲先後依賴**：現有 `linker.py` 將類別繼承（`base_types`）與欄位型別（`field_types`）視為塞在 `metadata` 的純字串短名稱（`short_name`），未先透過 `imports` 邊消歧，一旦跨模組存在同名基底類別即發生錯連。
    2. **語言專屬關鍵字與跨檔規則硬寫死於內核**：`linker.py` 硬編碼 `if prefix in ("self", "cls", "base", "super"):`，`resolver.py` 硬編碼 C# `partial class` 與 `KIND_PREFIX_MAP`。
    3. **啟發式模糊打分（Heuristic Fuzzy Scoring）污染圖譜確定性**：`linker.py` 的 `_score_candidates()` 在找不到確切匯入目標時，以 `+15.0 / +10.0 / +8.0` 的子字串模糊匹配強行挑選最高分候選連邊，產生幽靈錯誤邊（False Positives）。
    4. **硬編碼排除文檔符號（`is_doc_symbol`）**：`resolver.py` 預設將 Markdown 符號排除於拓撲查詢之外，阻斷「文檔與程式碼共構同一張全倉符號圖譜」的能力。
- **調研目標與範疇**：
  - 本報告（`R02`）聚焦於 AST 架構拆解之**第二大項：跨檔語意連結與全倉圖譜組裝機制**，旨在：
    1. 對比業界跨檔名稱解析方案（GitHub `stack-graphs`、Sourcegraph `SCIP`、輕量級 Scope-Import Graph），確立零外部編譯器強依賴且支援高精度擴充的連結架構。
    2. 定義內核**四階段依序連結流水線（4-Pass Deterministic Linking Pipeline）**與**四階確定性作用域查找（4-Tier Scope Cascade）**。
    3. 劃定跨檔連結層的「**內核原始碼（Kernel）**」與「**`contributes` 平權注入設定（Module Path Resolver / Receiver Aliases / External Edge Refiner）**」邊界。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 業界跨檔名稱解析方案橫向評估與選型

| 評估維度 | 方案 A：GitHub `stack-graphs` (`.tsg`) | 方案 B：Sourcegraph `SCIP` / LSP 編譯器索引 | 方案 C：輕量 Scope-Import 圖論引擎 + 平權外部 Edge Refiner（採納方案） |
| :--- | :--- | :--- | :--- |
| **核心原理** | 為每個語言撰寫專屬 `.tsg` 圖形建構狀態機 DSL，將單檔轉為 Scope Stack 子圖後執行堆疊路徑搜尋。 | 直接調用各語言官方型別檢查器（Pyright、TSServer、Roslyn、`rust-analyzer`）輸出跨檔引用圖。 | 內核實作通用「詞法作用域 + 匯入綁定表 + 繼承 DAG」四階段連結器；同時開放平權介面供外部高精度分析器（如 Python `symtable` 或 `SCIP`）精煉關係邊。 |
| **零配置與輕量性** | 需引入 Rust `stack-graphs` 綁定，且單一語言 `.tsg` 規則動輒上千行。 | **極重**（需安裝各語言完整 SDK 與建置環境，無法毫秒級冷啟動）。 | **100% 輕量純 Python 內核**，僅需官方 `tags.scm` + 15 行 `imports.scm` 即可毫秒級運作。 |
| **多語言與文檔覆蓋度** | 官方僅維護 Python/TS/Java，C#/C++/Rust 與 Markdown 缺乏完整 `.tsg`。 | 僅限主流程式語言，不支援自訂領域符號或 Markdown 文檔連結。 | **全語言與文檔通用**：程式碼 `import`/`call` 與 Markdown `[text](path#symbol)` 皆走同一套圖譜連結模型。 |

### 2.2 內核原始碼（Kernel）vs. `contributes` 注入設定之正交職責切分

| 連結維度 | 內核原始碼（Kernel — 通用圖論與確定性查找引擎） | `contributes` 注入設定（平權一等公民規則與外部增強器） |
| :--- | :--- | :--- |
| **1. 跨檔同體宣告折疊**<br>*(Cross-File Symbol Folding)* | 支援具有相同跨檔合併鍵（或宣告/實作配對關係）之 `SymbolNode` 建立 `declares` / `merges_with` 雙向對等關聯。 | 注入語言專屬的跨檔同體識別規則（如 C# `partial class`、C/C++ `.h` 標頭宣告與 `.cpp` 實作、TypeScript `.d.ts` 與 `.ts`）。 |
| **2. 模組匯入路徑換算**<br>*(Module Path Resolution)* | 維護全倉檔案與導出符號索引表（Export Index），將 `edge_kind="imports"` 解析並建構每份檔案的**局部匯入綁定表（`FileImportTable`：局部別名 $\to$ 目標檔案或目標 `SymbolNode.id`）**。 | 注入該語言的**模組路徑解析器（`ModulePathResolver`）**（例如 Python 將 `from ..utils import a` 換算為相對路徑與 `__init__.py`；TS 換算 `./utils` 與 `index.ts`；Markdown 解析相對檔案連結與 `#anchor`）。 |
| **3. 確定性四階作用域查找**<br>*(4-Tier Scope Cascade)* | 廢除模糊打分猜測，嚴格依序查找：① **詞法封閉作用域（Lexical Enclosing Scope）** $\to$ ② **所屬型別與繼承鏈 DAG（Class & Base DAG）** $\to$ ③ **檔案匯入綁定表（File Import Table）** $\to$ ④ **同模組/全倉唯一 FQN 精確匹配**。 | 注入該語言的**接收者語意別名（`receiver_aliases`）**：宣告哪些前綴代表當前外層容器型別（如 `"self"`、`"this"`、`"cls"`），哪些前綴代表跳過自身查父類別鏈（如 `"super"`、`"base"`）。 |
| **4. 關係邊消歧狀態與外部精煉**<br>*(Resolution Status & Edge Refiners)* | 為每條 `RelationEdge` 明確賦予四種確定性狀態之一：`resolved`、`overload_group`、`ambiguous`、`external`，並保存完整 `resolved_target_ids: Tuple[str, ...]`。 | 允許透過 `contributes` 平權注入**外部高精度邊精煉器（`EdgeRefiner`）**（如 Python 內建 `symtable`/型別推導或外部 `SCIP` 索引），將 `ambiguous` 精確收斂為 `resolved` 並追加 `ProvenanceStep`。 |

### 2.3 內核四階段依序連結流水線（4-Pass Deterministic Linking Pipeline）

為解決現有 `linker.py`「未連匯入就連繼承、未連繼承就連呼叫」的順序倒置問題，內核 `WorkspaceGraphLinker` 對全倉單檔局部圖執行嚴格的四階段（4-Pass）拓撲組裝：

```text
[單檔局部圖集合 FileSymbolGraph*]
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 1：全域符號索引與跨檔同體關聯 (Global Indexing & Symbol Folding)     │
│ • 註冊所有檔案之 SymbolNode 至全倉索引表                                  │
│ • 處理跨檔同體宣告（如 C# partial class、C/C++ .h/.cpp 配對）             │
└─────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 2：匯入邊解析與檔案可見作用域表建構 (Import Edge Resolution)         │
│ • 解析所有 edge_kind == "imports" 之 RelationEdge                        │
│ • 處理萬用匯入 (from X import *) 與重導出 (__all__ / export * from)       │
│ • 為每個檔案產出確定性的 FileImportTable (alias -> target_id / file)     │
└─────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 3：型別繼承與實作 DAG 建構 (Inheritance & Type Graph Construction)  │
│ • 利用 Pass 2 的 FileImportTable 解析所有 "inherits" 與 "implements" 邊   │
│ • 將父類別與介面精確綁定至目標 SymbolNode.id（徹底告別 short_name 誤連） │
│ • 建立無環型別階層圖 (Type Hierarchy DAG) 與欄位型別映射                  │
└─────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Pass 4：呼叫、型別引用與文檔引用消歧 (Call & Reference Disambiguation)    │
│ • 依序透過：① 詞法封閉樹 -> ② Pass 3 繼承 DAG -> ③ Pass 2 匯入表          │
│   -> ④ 全倉唯一 FQN，解析所有 "calls"、"references"、"documents" 邊       │
│ • 執行選填之平權 EdgeRefiner，寫入最終 resolution_status 與 provenance    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.4 `RelationEdge` 確定性消歧狀態規格（零幽靈邊保證）

連結完成後，每條 `RelationEdge` 的結構與狀態具備 100% 數學確定性，絕不透過模糊子字串打分偽造單一連線：

```python
@dataclass(frozen=True)
class RelationEdge:
    """通用有向關係邊（含跨檔消歧結果與來源追蹤）。"""
    source_id: str                                # 發起端穩定 SymbolNode.id
    target_expr: str                              # 原始目標表達式 (如 "self.registry.get", "../engine.py#ASTEngine")
    edge_kind: str                                # "imports" | "inherits" | "implements" | "calls" | "references" | "documents"
    span: Span                                    # 該引用發生的精確物理座標
    resolution_status: str = "unresolved"         # "resolved" | "overload_group" | "ambiguous" | "external" | "unresolved"
    resolved_target_ids: Tuple[str, ...] = ()     # 唯一命中時為 (id,)，重載或歧義時保留所有候選 SymbolNode.id 元組
    provenance: Tuple[ProvenanceStep, ...] = ()   # 記錄提取規則 (.scm) 與參與消歧之 Linker Pass / EdgeRefiner
```

- **四種完成態定義**：
  1. **`resolved`**：100% 唯一確定命中單一目標符號（`len(resolved_target_ids) == 1`）。
  2. **`overload_group`**：命中同一型別作用域下的同名多載方法群組（支援依呼叫端參數數量或型別進一步收斂）。
  3. **`ambiguous`**：在缺乏動態執行期型別資訊下（如鴨子型別參數 `obj.run()`），同時匹配多個不同型別的同名方法；此時保留所有候選 ID 於 `resolved_target_ids`，供下游影響範圍分析（Impact Analysis）保守涵蓋或交由診斷工具提示，**嚴禁盲目猜測其一**。
  4. **`external`**：經匯入表確認指向外部標準庫或第三方套件（如 `os.path.join`、`tree_sitter.Parser`），非本倉缺失錯誤。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. 跨檔語意連結必須遵循**「Pass 1 全域索引与跨檔同體 $\to$ Pass 2 匯入綁定表 $\to$ Pass 3 型別繼承 DAG $\to$ Pass 4 呼叫與文檔引用消歧」**的四階段拓撲依序流水線，徹底解決現有 `linker.py` 以 `short_name` 字串硬湊繼承關係的缺陷。
  2. 廢除一切啟發式模糊打分（Heuristic Fuzzy Scoring），全面改採**四階確定性作用域查找**與明確的 **`resolution_status`（`resolved` / `overload_group` / `ambiguous` / `external`）**，並支援透過 `contributes` 平權注入語言模組路徑解析器與外部高精度 `EdgeRefiner`。
- **後續建議（選填）**：
  - 第二大項（`R02`）已完整定案（`Concluded`）；下一步推進至第三大項（`R03`）：**全倉 AST 圖譜之操作原語（Query / Slice / Splice）、增量快取持久化與提供給下游（KDB 文檔管線、Compiler/Checker）之正交消費契約**。
