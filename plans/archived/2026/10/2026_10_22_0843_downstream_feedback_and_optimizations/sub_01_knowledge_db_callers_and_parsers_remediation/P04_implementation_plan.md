# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中有對應介面
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-02 指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 同步更新 `callers` / `callees` / `impact` 支援 `--ftype` 說明 |
| **專題手冊** | `docs/knowledge-db/call_graph_and_reference_index.md` | Modify | 更新 Tier 1 隱含 `this`、介面/實作契約展開、遞迴自呼叫與預設排除文檔機制 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 補充多語言調用拓撲消歧與防幽靈邊邊界說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本子計畫修復與優化摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：開放「無前綴隱含 `this`」方法查找後，若類別 A 的方法內呼叫了一個全域輔助函式 `Helper()`，而無關類別 B 恰好有一個方法也叫 `B.Helper()`，是否會誤連到 `B.Helper()`？  
> [*] **防護解法**：在 `TopologyLinker.resolve_call_site` 的 Tier 1 中，無前綴呼叫**僅限於在呼叫者所屬類別 (`caller_class`) 自身及其顯式繼承之 `base_types` 集合內**尋找 `Class.Callee`；若自身與基類均無此方法，則僅檢查同檔案頂層函式或顯式 `imports`，絕不跨類別盲連到無關類別 B（完美防禦 `EC-02`）。

> [?] **尖銳問題 2**：允許保留遞迴自呼叫邊（`caller_id == callee_id`）後，會不會讓容器符號（例如類別 `class Foo` 內部某處沒匹配到方法而 fallback 到 `Foo`）因為內部呼叫 `new Foo()` 變成類別自呼叫？此外 `query_impact` 會不會把目標自身算進 Layer 1 影響面？  
> [*] **防護解法**：
> 1. `link_call_sites` 僅在 `caller_id == callee_id` 且該符號之 `kind in ("function", "method", "constructor")` 時才保留自呼叫邊，類別/檔案/文檔標題一概不允許自連。
> 2. `CallGraphIndex.query_impact` 初始化時已將 `visited = {target_symbol_id}`（以及契約展開之等效目標 ID）放入已訪問集合，因此自呼叫邊在 `if caller not in visited:` 時會被安全剪枝，不會將自身計入 `layers[1]`，而在 `act_callers` / `act_callees` 中則可正常顯示遞迴調用點（完美防禦 `EC-01`）。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：擴充多語言 Tree-sitter 查詢檔（`c_sharp.scm`, `c.scm`, `cpp.scm`, `typescript.scm`, `javascript.scm`）與 `TreeSitterDriver`（`base_types` 萃取、C++ 類別外方法 `parent_scope`、鏈式/泛型/條件存取 `context_prefix` 提取與 `constructor`/`property` 作用域定位）。
2. **TASK-02**：升級 `TopologyLinker`（多段式名稱之 `Class.Method` 雙段索引、Tier 1 無前綴隱式 `this` 與 `base_types` 繼承鏈查找、完整命名空間限定前綴尾段匹配、可調用符號遞迴自呼叫保留）。
3. **TASK-03**：升級 `IndexingPipeline`、`KnowledgeEngine`、`scripts/cli.py` 與 `contributes/core.json`（修復 `callers --json` 之 `caller_symbol` 鍵名、實作介面/實作方法契約展開聚合、預設排除文檔節點並支援 `--ftype` 篩選）。
4. **TASK-04**：編寫並執行單元與邊界測試（`test_graph.py`、`test_cli.py` 與全模組回歸測試）。
5. **TASK-DOC**：同步更新 `docs/knowledge-db/` 專題手冊、模組手冊與微觀代碼 Docstrings。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認採用 AST 結構化前綴提取取代字串 `split("(", 1)[0]`，並以 `caller_class` + `base_types` 嚴格限定無前綴隱式 `this` 消歧範圍，同時定稿 `P04_implementation_plan.md` 與 `P06_test_plan.md`。

