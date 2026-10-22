# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`callers --json` 結構對齊與零崩潰 (`FR-01`)**：統一 `IndexingPipeline.act_callers` 回傳項目之 `symbol` 與 `caller_symbol` 鍵名，並在 `scripts/cli.py:callers` 三級 `--json` 輸出模式（`simple` / `preview` / `detail`）採用安全讀取，根除有實際調用者時拋出 `KeyError: 'caller_symbol'` 之問題。
  2. **非程式碼文檔引用預設隔離與 `--ftype` 正交篩選 (`FR-02`)**：於 `find_target_symbol`、`act_callers`、`act_callees` 與 `act_impact` 預設排除 Markdown 文檔節點（`language == "markdown"` 或 `kind.startswith("doc_")`），避免規格書文字提及汙染調用圖譜與重構影響面；同步於 `contributes/core.json`、`scripts/cli.py` 與 `engine.py` 補齊 `callers`、`callees`、`impact` 之 `--ftype` 過濾選項。
  3. **多語言 Tree-sitter 語法查詢與 `TreeSitterDriver` 全面強化 (`FR-03`)**：
     - 擴充 `c_sharp.scm`（`record_declaration`、`local_function_statement`、`generic_name` 泛型調用、`conditional_access_expression` `?.` 條件存取調用）、`cpp.scm`（C++17 `nested_namespace_specifier`、`template_function`、`template_method`）與 `c.scm`（結構指標 `ptr->fn()` / `obj.fn()` `field_expression` 調用）。
     - 於 `TreeSitterDriver` 實作 `_extract_base_types` 提取 C# / C++ / TS / Python 類別繼承與介面清單至 `metadata["base_types"]`，修正 C++ 類別外方法實作 (`Class::Method`) 之 `parent_scope`，並改用 AST byte 區間精確提取鏈式調用、泛型與 `?.` 接收者前綴，同時支援 `constructor` 與 `property` 存取器內調用歸屬與 `base`/`super` 基底呼叫識別。
  4. **四階消歧引擎 `TopologyLinker` 與介面/實作契約展開 (`FR-04`, `FR-05`)**：
     - 於 `TopologyLinker._reindex` 為巢狀於命名空間下之類別成員建立 `Class.Method` 雙段式索引，解決多段命名空間導致 `split(".")[0]` 誤取命名空間名稱之問題。
     - Tier 1 支援類別內部隱式 `this` 裸調用及跨檔案 `base_types` 繼承鏈方法解析；Tier 3/4 支援完整命名空間限定前綴尾段匹配與同類別/同檔案候選加權。
     - 保留可調用單元（`function` / `method` / `constructor`）之遞迴自調用邊（`caller_id == callee_id`），並於 `IndexingPipeline` 實作 `_expand_contract_symbol_ids`，自動將介面/基底方法與實作類別同名方法雙向關聯聚合，徹底解決 `callers` 大量漏報與 `impact` 嚴重低估問題。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/assets/queries/c_sharp.scm` | Modify | 補齊 `record`、區域函式、泛型調用與 `?.` 條件存取調用查詢規則 |
| `ys_codebase/source/knowledge-db/assets/queries/cpp.scm` | Modify | 補齊 C++17 巢狀命名空間與模板函式/方法調用查詢規則 |
| `ys_codebase/source/knowledge-db/assets/queries/c.scm` | Modify | 補齊 C 結構指標與成員函式指標 `field_expression` 調用查詢規則 |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py` | Modify | 新增 `_extract_base_types`、修正 C++ 類別外方法作用域、升級 byte 區間前綴提取與 `property`/`constructor` 調用者定位 |
| `ys_codebase/source/knowledge-db/knowledge_db/linker.py` | Modify | 新增 `Class.Method` 雙段索引、隱式 `this` 與 `base_types` 繼承鏈消歧、`base`/`super` 祖先查找與可調用單元遞迴邊保留 |
| `ys_codebase/source/knowledge-db/knowledge_db/selector.py` | Modify | 支援 `::` 範疇分隔符與 `metadata["parent_scope"]` / `short_name` 結構化選擇器匹配 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 實作預設排除文檔符號、`ftypes` 正交過濾、`_expand_contract_symbol_ids` 介面/實作契約展開與 `caller_symbol` 鍵名相容 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 擴充 `act_callers`、`act_callees`、`act_impact` 與 `_find_target_symbol` 之 `ftypes` 參數傳遞 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 修復 `callers --json` 讀取 `symbol`/`caller_symbol`，並為 `callers`/`callees`/`impact` 接線 `--ftype` 參數 |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 為 `callers`、`callees`、`impact` 註冊 `--ftype` 選項宣告 |
| `ys_codebase/source/knowledge-db/tests/test_graph.py` | Modify | 新增 `test_ft_12_csharp_and_multilang_advanced_call_topology` 完整驗證 C# 與多語言進階調用拓撲 |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | 新增 `callers` / `callees` / `impact` 之 `--ftype` 與非空 `callers --json` 三模式回歸測試 |
| `docs/knowledge-db/call_graph_and_reference_index.md` | Modify | 同步更新四階消歧演算法、隱式 `this`、繼承契約聚合與 `--ftype` 過濾說明 |
| `docs/knowledge-db/README.md` | Modify | 同步更新 CLI 拓撲查詢 `--ftype` 範例說明 |
| `docs/knowledge-db/parsers.md` | Modify | 同步更新 C# 與 C/C++ 解析器提取維度說明 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev test knowledge-db -q` 全套 158 項測試 100% 通過（`Pass: 158(100.0%), Fail: 0, Skip: 0`）；`python yscb.py dev check knowledge-db --json` 靜態檢查 `PASS`。
- **實機 UX / 人工驗證**：已部署 `knowledge-db@build` 並以 C# UIToolkit 實境案例與本專案知識庫完成 `UX-01` 實機驗證，確認 `--json` 零崩潰、文檔預設隔離、`--ftype=md` 篩選與 5 大 C# 調用場景全數精準命中。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | CHANGELOG.md | 已完成 | 增補 `2026_10_22_0843_downstream_feedback_and_optimizations` (`sub_01`) 變更紀錄 |
| **中觀 (Meso)** | `docs/knowledge-db/README.md` | 已完成 | 更新模組手冊 CLI 拓撲查詢與 `--ftype` 範例 |
| **中觀 (Meso)** | `docs/knowledge-db/call_graph_and_reference_index.md`、`docs/knowledge-db/parsers.md` | 已完成 | 更新四階 FQN 消歧、隱式 `this`、介面契約展開與多語言解析維度 |
| **中觀 (Meso)** | `docs/knowledge-db/DESIGN_NOTES.md` | 免更 | 本次修復已完整收錄於專題手冊，無反直覺妥協需額外寫入 DN |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 完整維護 `treesitter.py`、`linker.py`、`pipeline.py`、`engine.py` 之 Docstrings |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack，且臨時測試檔案已全數清除。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(knowledge-db): resolve callers --json crash, C#/multi-lang call site misses, and doc noise in call graph
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_10_22_0843_downstream_feedback_and_optimizations` 驗證 100% Passed。
- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成。

