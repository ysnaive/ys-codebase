# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `callers --json` 結構化鍵名對齊與穩定性修復 | 修正 `scripts/cli.py:callers` 在 `--json`（`simple`、`preview`/`snippet`、`detail` 三種 tier）下對 `res["callers"]` 的讀取邏輯（使用 `c.get("symbol") or c.get("caller_symbol")`），並於 `pipeline.py:act_callers` 同時提供 `"symbol"` 與向後相容別名 `"caller_symbol"`，徹底根除 `KeyError: 'caller_symbol'`。 | P0 | [P00:DR-01] |
| **FR-02** | `callers` / `callees` / `impact` 預設排除非程式碼文檔符號與 `--ftype` 篩選支援 | 1. `act_callers`、`act_callees`、`act_impact` 預設排除非程式碼文檔符號（`language == "markdown"` 或 `kind` 以 `doc_` 開頭之節點），且 `find_target_symbol` 預設優先定位程式碼符號。<br/>2. 於 `contributes/core.json`、`scripts/cli.py`、`engine.py` 與 `pipeline.py` 為 `callers`、`callees`、`impact` 補齊 `--ftype` 參數；當顯式指定 `--ftype=md`（或包含 `md`/`markdown`）時，允許納入並回報 Markdown 文檔引用。 | P0 | [P00:DR-01] |
| **FR-03** | 多語言 Tree-sitter `.scm` 查詢與 `TreeSitterDriver` 調用點/作用域完整萃取 | 1. **C# (`c_sharp.scm`)**：補齊 `record_declaration`、`local_function_statement`；擴充 `invocation_expression` 支援泛型方法呼叫 `(generic_name)`、成員泛型呼叫 `(member_access_expression name: (generic_name))`、條件存取呼叫 `(conditional_access_expression (member_binding_expression ...))`。<br/>2. **C (`c.scm`)**：補齊結構/指標成員調用 `(field_expression field: (field_identifier) @call.name)`。<br/>3. **C++ (`cpp.scm`)**：補齊模板函式調用 `(template_function)`、成員模板調用 `(field_expression field: (template_method))`、限定模板調用 `(qualified_identifier name: (template_function))`，以及類別外方法定義 `ClassName::Method` 之 `parent_scope` 綁定。<br/>4. **Python / JS / TS (`treesitter.py`)**：重構 `extract_call_sites` 的 `context_prefix` 提取邏輯，直接基於 AST `function` 節點拆解接收者與方法名（取代易受鏈式呼叫 `a().b()` 括號干擾的 `split("(", 1)[0]`），將 `this`、`base`、`super`、`cls` 正規化，並將 `constructor`、`property` 納入合法 `caller_member_name` 作用域，同時萃取類別繼承與介面清單 `metadata["base_types"]`。 | P0 | [P00:DR-03] |
| **FR-04** | `TopologyLinker` 命名空間多維索引、無前綴隱含 `this` 消歧與遞迴自呼叫保留 | 1. **多維符號索引 (`_reindex`)**：針對含命名空間前綴之多段式符號（如 `Namespace.Class.Method` 或 `Ns::Class::Method`），同步索引完整名稱、`Class.Method` 雙段名稱與 `Method` 短名，並以 `metadata["parent_scope"]` 精確提取所屬類別。<br/>2. **Tier 1 隱含 `this` 消歧**：當 `prefix == ""` 且調用者位於類別成員（`method` / `constructor` / `property`）內時，優先檢索同類別及 `base_types` 繼承鏈上的同名方法；支援完整命名空間限定前綴（如 `UIToolkit.UI.Layout.FlexLayoutEngine.CalculateLayout`）之 FQN 後綴與尾段類別匹配。<br/>3. **遞迴自呼叫保留**：於 `link_call_sites` 中，當 `caller_id == callee_id` 且符號屬於可調用程式碼單元（`function`、`method`、`constructor`）時，保留自呼叫邊。 | P0 | [P00:DR-02]<br/>[P00:DR-03] |
| **FR-05** | 介面方法與實作類別契約關聯聚合 (`find_related_symbol_ids`) | 在 `pipeline.py` 的 `act_callers` 與 `act_impact` 中，當定位到目標方法（如介面方法 `IPanel.UpdateLayout` 或基類/實作類方法 `Panel.UpdateLayout`）時，透過 `TopologyLinker` 的 `base_types` 契約映射，自動聚合實作該介面或繼承鏈上同名方法的上游調用邊與調用點，消除多型呼叫漏報。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 遞迴自呼叫（`A -> A`）或介面/實作雙向聚合時執行 `impact` 多階擴散分析 | `CallGraphIndex.query_impact` 將所有初始目標集合納入 `visited` 集合並以 BFS 剪枝，確保 `callers` / `callees` 可見遞迴自呼叫，但 `impact` 絕不陷入無限迴圈或將自身重複計入擴散層。 |
| **EC-02** | 跨檔案無關類別定義了常見同名方法（如 `Dispose`、`ToString`、`Update`），且呼叫端為無前綴裸調用 | Tier 1 僅允許綁定「呼叫者所屬類別自身或其顯式宣告之 `base_types`」內的同名方法；若所屬類別與基類皆無該方法，且非同檔頂層函式或顯式 import，則嚴格維持 `None`，杜絕跨類別幽靈邊。 |
| **EC-03** | 鏈式調用與複雜接收者表達式（如 `GetService<IPanel>().UpdateLayout()`、`m_Owner?.MarkMeasureDirty()`、`a.b().c()`） | AST 前綴提取器精準剝離最外層 `.callee` / `?.callee` / `->callee` / `::callee`，並將尾端帶有泛型或呼叫括號之前綴正規化為可識別之接收者識別符或型別提示，不因括號或 `?.` 語法丟失調用點。 |
| **EC-04** | 使用者對 `callers` / `callees` / `impact` 傳入不匹配的 `--ftype`（如 `--ftype=cs` 但專案僅有 `.py`） | 篩選後安全回傳空清單（`total_callers: 0` / `total_impacted_symbols: 0`），CLI 與 `--json` 正常輸出 0 筆結果，exit code 為 0。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與零依賴 | 維持 `CallGraphIndex` 500 節點 / 2000 邊查詢延遲 $< 10\text{ ms}$，且 100% 使用既有 Tree-sitter grammars 與 Python 標準庫，零新增外部依賴。 |
| **NFR-02** | 向後相容性 | 既有 `test_parsers.py`、`test_graph.py`、`test_cli.py` 與全生態系測試套件 100% 向後相容通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` [DN-02] Worker 進程級單例與 AST 單次走訪復用**：修改 `TreeSitterDriver.extract_call_sites` 時，必須維持支援傳入預解析之 `symbols` 參數，嚴禁強制觸發二次 `self.parse()`。
- **`[!CAUTION]` [DN-03] `--json` 純淨通道保護**：所有 CLI `--json` 輸出嚴禁混入非 JSON 雜訊。
- **`[!CAUTION]` [DN-06] 圖譜查詢輕量 JIT 解耦 (`require_vectors=False`)**：`act_callers`、`act_callees`、`act_impact` 必須維持 `require_vectors=False`，嚴禁觸發 ONNX 向量模型載入。

