# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：處理下游專案 `uitk.net`（.NET 8 / C#）回饋報告（`plans/roadmap/2026_10_19_feedback_from_uitk.net.md`）所列之 `knowledge-db` 4 大問題，並全面檢查與一併修復其他語言解析器（Python、C、C++、JavaScript、TypeScript 等）的同類調用圖譜提取與鏈接缺陷。
- **核心目標**：
  1. **修復 `callers --json` 崩潰**：解決 `scripts/cli.py:callers` 讀取 `c["caller_symbol"]` 與 `pipeline.py:act_callers` 回傳鍵名 `"symbol"` 不一致導致之 `KeyError: 'caller_symbol'`。
  2. **修復 C# 與多語言調用點大量漏報**：
     - 解決 C# 傳統大括號 `namespace` 與 C++ `namespace` 包裹類別時，導致方法 `sym.name` 變成 3 段式 (`Namespace.Class.Method`)，進而破壞 `TopologyLinker` 的 `Class.Method` 索引、`split(".")[0]` 類別前綴比對與 `caller_member_name` 定位之問題。
     - 支援類別內隱含 `this` 之無前綴方法呼叫（如 C# `MarkMeasureDirty()`、C++ / TS 同類別方法互呼），在 `TopologyLinker` Tier 1 優先檢索呼叫者所屬類別及繼承鏈之成員方法。
     - 補齊各語言 Tree-sitter `.scm` 查詢檔遺漏之調用語法與定義範圍（C# 泛型呼叫 `generic_name`、條件存取 `conditional_access_expression`、`constructor` / `property` / `local_function_statement` 作用域；C 結構指標成員呼叫 `field_expression`；C++ 模板函式/方法呼叫 `template_function` / `template_method`；Python/JS/TS 鏈式呼叫前綴解析等）。
     - 支援完整命名空間限定呼叫（如 `UIToolkit.UI.Layout.FlexLayoutEngine.CalculateLayout(...)`）之尾段類別與 FQN 後綴匹配。
  3. **保留真實函數/方法遞迴自呼叫**：解除 `TopologyLinker.link_call_sites` 對 `caller_id != callee_id` 的一刀切過濾，針對真實可調用程式碼符號（`function`、`method`、`constructor`）保留遞迴自呼叫邊（`CallGraphIndex.query_impact` 透過 `visited` 集合天然防禦無限迴圈）。
  4. **介面方法與實作類別契約關聯聚合**：解析類別/結構時提取基底型別與介面清單（`base_types`），在 `TopologyLinker` 消歧與 `act_callers` / `act_impact` 查詢介面方法（如 `IPanel.UpdateLayout`）或實作方法時，自動關聯並聚合契約鏈上對應同名方法的調用者。
  5. **預設排除非程式碼文檔符號並補齊 `--ftype` 過濾**：`callers`、`callees`、`impact` 預設排除 Markdown 文檔節點（`language == "markdown"` 或 `doc_*` 類型），並為三項指令補齊 `--ftype` 篩選參數（當顯式指定 `--ftype=md` 時才包含文檔引用）。
- **邊界排除 (Explicitly Excluded)**：
  - 不引入外部重量級語言編譯器或完整 LSP Server（維持 100% Tree-sitter + 原生 Python 輕量靜態拓撲分析架構）。
  - 不更動向量嵌入模型（FastEmbed）與 BM25 演算法權重。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `callers` / `callees` / `impact` 文檔過濾與 `--ftype` 契約對齊**：
  - 預設在 `act_callers`、`act_callees`、`act_impact` 中過濾掉非程式碼之文檔符號（`language == "markdown"` 或 `kind` 以 `doc_` 開頭者），避免計入計畫檔與文檔標題提及。
  - 於 `contributes/core.json`、`scripts/cli.py`、`engine.py` 與 `pipeline.py` 為 `callers`、`callees`、`impact` 統一擴充 `--ftype` 選項；若使用者顯式指定 `--ftype=md`（或包含 `md`/`markdown`），則允許回報 Markdown 文檔引用。
- **[P00:DR-02] 遞迴自呼叫邊保留策略**：
  - 於 `TopologyLinker.link_call_sites` 中，當 `caller_id == callee_id` 時，若該符號為程式碼可調用單元（`kind in ("function", "method", "constructor")`）且非文檔/容器 fallback 節點，則允許建立自呼叫邊，使遞迴呼叫（如 `FlexLayoutEngine.CalculateLayout`）能正確顯示於 `callers` 與 `callees`。
- **[P00:DR-03] 命名空間正規化、隱式 `this` 消歧與介面/實作方法雙向關聯**：
  - **命名空間與類別層級分離**：於 `TreeSitterDriver.parse` 中，將 `namespace` 節點記錄於 `scope_path` 與 `fqn`，但讓類別與方法的 `sym.name` 保持標準 `ClassName` 與 `ClassName.MethodName`（2 段式），確保無論是傳統大括號 `namespace` 或 file-scoped `namespace`，其 `sym.name` 與 `parent_scope` 均 100% 一致；同時在 `TopologyLinker` 中支援以短名、`Class.Method` 與完整 `FQN` 後綴多維匹配。
  - **無前綴隱含 `this` 消歧**：當 `prefix == ""` 且調用點位於類別方法/屬性/建構子內部時，Tier 1 自動檢查所屬類別（及其基底類別/介面）是否定義同名方法，若有則優先綁定，不再因無 `this.` 前綴而漏報。
  - **介面與實作類別聚合**：於 `TreeSitterDriver` 萃取類別/結構之繼承與實作介面名稱存入 `metadata["base_types"]`；在 `act_callers` 與 `act_impact` 定位目標方法時，自動查找同專案內實作該介面（或繼承該基底類別）的對應同名方法並合併其上游調用邊。

---

## 3. 開放議題與確認紀錄

- [x] 確認問題 3 預設排除非程式碼文檔符號，並為 `callers` / `callees` / `impact` 補齊 `--ftype` 選項。
- [x] 確認保留程式碼函式/方法之遞迴自呼叫邊。
- [x] 確認實作基底型別/介面提取與介面方法/實作方法呼叫端聚合。

