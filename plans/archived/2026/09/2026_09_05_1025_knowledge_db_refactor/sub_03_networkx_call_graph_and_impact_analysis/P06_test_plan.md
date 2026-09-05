# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Passed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | `CallGraphIndex` 建立邊、查詢 callers / callees 準確性 | FR-01 | `test_networkx_graph.py::test_add_and_query_edges` |
| **FT-02** | 單元測試 | 多階影響面分析 (`query_impact`) 深度與調用鏈路精確性 | FR-05 | `test_networkx_graph.py::test_query_impact_layers` |
| **FT-03** | 單元測試 | 循環調用圖譜 (Cycle Detection) 走訪不陷入死循環且 visited 剪枝正確 | EC-01 | `test_networkx_graph.py::test_cyclic_graph_resilience` |
| **FT-04** | 單元測試 | `SymbolSelector` 解析各種語法（`class foo`, `struct foo`, `foo.a()`, `const MAX`） | FR-04 | `test_selector.py::test_selector_parsing` |
| **FT-05** | 單元測試 | `SelectorMatcher` 比對符號集合並精確過濾 | FR-04 | `test_selector.py::test_selector_matching` |
| **FT-06** | 單元測試 | `TopologyLinker` 基於 FQN 與 Import 消歧，杜絕跨檔案同名幽靈關聯 | FR-03 | `test_networkx_graph.py::test_fqn_disambiguation_eliminates_ghosts` |
| **FT-07** | 單元測試 | `LanguageTopologyProtocol` 多語言提取協議與適配器介面合規性 | FR-02 | `test_networkx_graph.py::test_topology_protocol_interface` |
| **FT-08** | 單元測試 | 圖持久化 Gzip Pickle Protocol 5 序列化與反序列化一致性 | FR-06 | `test_networkx_graph.py::test_serialization_roundtrip` |
| **ET-01** | 邊界測試 | 語法無效時符號選擇器寬容回退處理 | EC-02 | `test_selector.py::test_invalid_syntax_graceful_fallback` |
| **ET-02** | 邊界測試 | 孤立節點與無出入度節點查詢空安全 | EC-04 | `test_networkx_graph.py::test_isolated_node_queries` |
| **RT-01** | 回歸測試 | 既有 `test_call_graph.py` 全量案例 100% 通過相容驗證 | FR-06 | `test_call_graph.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_add_and_query_edges`: NetworkX DiGraph 出入度邊與調用點查詢無誤 | 2026-09-05 14:50 |
| **FT-02** | `Passed` | `test_query_impact_layers`: 3 階影響面分析精確產出 Layer 1..3 與前驅鏈路 | 2026-09-05 14:50 |
| **FT-03** | `Passed` | `test_cyclic_graph_resilience`: 環路圖譜 (A➔B➔C➔A) visited 剪枝正確，零死循環 | 2026-09-05 14:50 |
| **FT-04** | `Passed` | `test_selector_parsing_*`: 純標識符、調用標記 `()`、class/struct/fn/const 語法解析 100% 正確 | 2026-09-05 14:50 |
| **FT-05** | `Passed` | `test_selector_matching_and_filtering`: 符號池精確過濾與範疇比對通過 | 2026-09-05 14:50 |
| **FT-06** | `Passed` | `test_fqn_disambiguation_eliminates_ghosts`: 裸調用無 import 判定為 None，顯式 import 綁定成功，杜絕幽靈關聯 | 2026-09-05 14:50 |
| **FT-07** | `Passed` | `test_topology_protocol_interface`: LanguageTopologyProtocol 與 Registry 適配驗證通過 | 2026-09-05 14:50 |
| **FT-08** | `Passed` | `test_serialization_roundtrip`: Gzip Protocol 5 二進位快取持久化與字典還原一致 | 2026-09-05 14:50 |
| **ET-01** | `Passed` | `test_invalid_syntax_graceful_fallback`: 異常語法寬容回退，零崩潰 | 2026-09-05 14:50 |
| **ET-02** | `Passed` | `test_isolated_node_queries`: 孤立節點與空圖查詢空安全防禦通過 | 2026-09-05 14:50 |
| **RT-01** | `Passed` | `test_call_graph.py` 全量 14 案例 100% 通過相容驗證；全模組 132/132 通過 | 2026-09-05 14:54 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 透過 CLI 執行 `python yscb.py knowledge-db callers "TopologyLinker.resolve_call_site()"` 與 `knowledge-db impact "class CallGraphIndex"`，驗證符號選擇器輸出精確度與可讀性 | `[跳過/免測]` | 開發者明確指示免測 |
