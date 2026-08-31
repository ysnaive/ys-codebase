# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：PASSED  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SymbolCallSite` 與 `CallGraphNode` Schema 資料模型不可變性與序列化正確性 | FR-01 | `test_schema_call_site_models` |
| **FT-02** | 單元測試 | 驗證 `PythonParser` 與 `CallSiteVisitor` 作用域棧 (`ScopeStack`) 與調用點提取 (含 `self`、函式、類別方法與 import) | FR-02 | `test_python_parser_call_sites_and_imports` |
| **FT-03** | 單元測試 | 驗證 `TopologyLinker` 四階消歧鏈接演算法 (Tier 1~4 精準跨檔案關聯) | FR-03 | `test_topology_linker_four_tier_cascade` |
| **FT-04** | 單元測試 | 驗證 `CallGraphIndex` 整數池化、雙向圖建立與 `callers`/`callees` 查詢 | FR-04 | `test_call_graph_index_bidirectional` |
| **FT-05** | 單元測試 | 驗證 `CallGraphIndex.query_impact` 多階擴散分析與循環調用防護 (`visited_set`) | FR-04, EC-02 | `test_call_graph_impact_and_cycle_protection` |
| **FT-06** | 整合測試 | 驗證 `CallGraphIndex` 二進位 Gzip 快取持久化 (save/load Protocol 5) 與 `patch_incremental` 差量熱修補 | FR-05, EC-03 | `test_call_graph_binary_cache_and_incremental_patch` |
| **FT-07** | 整合測試 | 驗證 `KnowledgeEngine` 與 CLI 指令 (`callers`, `callees`, `impact`) 輸出符合 RFC 8089 規範格式 | FR-06, NFR-04 | `test_cli_call_graph_commands_and_rfc8089` |
| **FT-08** | 單元測試 | 驗證 `CppParser` 提取 `#include`, `using` 映射與類別/函式方法調用點 | FR-02 | `test_ft_08_cpp_parser_call_sites_and_imports` |
| **FT-09** | 單元測試 | 驗證 `CSharpParser` 提取 `using` 映射與類別方法調用點 | FR-02 | `test_ft_09_csharp_parser_call_sites_and_imports` |
| **FT-10** | 單元測試 | 驗證 `JsTsParser` 提取 `import`/`require` 映射與類別/函式方法調用點 | FR-02 | `test_ft_10_js_ts_parser_call_sites_and_imports` |
| **FT-11** | 單元測試 | 驗證 `MarkdownParser` 提取文檔超連結與符號引用點 | FR-02 | `test_ft_11_markdown_parser_call_sites_and_imports` |
| **ET-01** | 邊界測試 | 驗證動態多型、未知屬性鏈與字串調用安全降級，系統永不中斷 | EC-01, EC-04 | `test_edge_case_dynamic_calls_and_error_handling` |
| **ET-02** | 邊界測試 | 驗證跨語意空間同名符號 Tier 3 空間隔離優先綁定 | EC-05 | `test_edge_case_space_isolation_for_same_symbol` |
| **PT-01** | 效能測試 | 驗證圖索引載入耗時 $< 10\text{ ms}$、單次查詢 $< 5\text{ ms}$、全專案持久化體積 $< 150\text{ KB}$ | NFR-02, NFR-03 | `test_call_graph_performance_and_memory` |
| **RT-01** | 全量回歸 | 驗證 `knowledge-db` 模組既有全量單元測試 100% 通過無回歸 | NFR-01 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASSED` | `SymbolCallSite` & `CallGraphNode` 不可變性與 `to_dict`/`from_dict` 序列化還原 100% 正確 | 2026-08-31 10:45:20 |
| **FT-02** | `PASSED` | `PythonParser` 完整萃取 `CallSiteVisitor` 作用域 (`MyEngine._init_cache`)、調用點與 import 別名映射 | 2026-08-31 10:45:20 |
| **FT-03** | `PASSED` | `TopologyLinker` 四階消歧 (Tier 1 `self` ➔ Tier 2 `import` ➔ Tier 3 `space` ➔ Tier 4 `context`) 跨檔案精準綁定 | 2026-08-31 10:45:20 |
| **FT-04** | `PASSED` | `CallGraphIndex` 雙向鄰接表與 `get_callers`/`get_callees`/`get_call_sites` 查詢正確無誤 | 2026-08-31 10:45:20 |
| **FT-05** | `PASSED` | `query_impact` BFS 擴散分析於 A➔B➔C➔A 循環圖譜中受 `visited_set` 防護，正確產出分層清單且無死循環 | 2026-08-31 10:45:20 |
| **FT-06** | `PASSED` | `CallGraphIndex` Protocol 5 + Gzip 快取持久化還原正確；`patch_incremental` 成功拔除舊邊並注入新邊 | 2026-08-31 10:45:20 |
| **FT-07** | `PASSED` | `KnowledgeEngine` 端到端整合測試，輸出完整包含 RFC 8089 `file:///` Markdown 直達連結與切片 | 2026-08-31 10:45:20 |
| **FT-08** | `PASSED` | `CppParser` 成功提取 `#include`, `using namespace`, `using Alias` 與 `this->Init()` 調用點 | 2026-08-31 10:49:30 |
| **FT-09** | `PASSED` | `CSharpParser` 成功提取 `using Namespace`, `using Alias` 與 `Controller.Process` 內部調用點 | 2026-08-31 10:49:30 |
| **FT-10** | `PASSED` | `JsTsParser` 成功提取 named/default `import`, `require` 與 `AppService.start` 類別方法調用點 | 2026-08-31 10:49:30 |
| **FT-11** | `PASSED` | `MarkdownParser` 成功提取文檔內部超連結與 `Class.method` 符號引用點 | 2026-08-31 10:49:30 |
| **ET-01** | `PASSED` | 語法錯誤與動態屬性調用安全降級為 `None`，系統穩定不中斷 | 2026-08-31 10:45:20 |
| **ET-02** | `PASSED` | 跨語意空間同名符號優先綁定同空間符號 (`sym_space_a` / `sym_space_b`)，隔離防護有效 | 2026-08-31 10:45:20 |
| **PT-01** | `PASSED` | 500 節點 2000 邊 Gzip 體積 28.4 KB (< 150 KB)，載入延遲 1.8 ms (< 50 ms)，查詢延遲 0.12 ms (< 10 ms) | 2026-08-31 10:45:20 |
| **RT-01** | `PASSED` | `dev test knowledge-db` 全量 125 個測試案例 100% 通過 (總耗時 1.08s) | 2026-08-31 10:49:30 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在 CLI 中執行 `python yscb.py knowledge-db callers "InvertedIndex.load_binary" -s`，確認終端輸出為 RFC 8089 可點擊 Markdown 連結，且 IDE 中點擊能直達來源程式碼行號。(開發者指示免測通過)
- [x] **UX-02**：在 CLI 中執行 `python yscb.py knowledge-db impact "InvertedIndex.patch_incremental" --depth=2`，確認輸出層次分明的影響面擴散樹狀結構。(開發者指示免測通過)
