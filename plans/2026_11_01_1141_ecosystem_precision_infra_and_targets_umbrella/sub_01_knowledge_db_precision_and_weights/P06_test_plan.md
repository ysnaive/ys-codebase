# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 檢索精準度、拓撲消歧、Watcher 時序、空間權重與 C#/C++ 解析強化  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SpaceDef` (`SpaceConfig`) `weight` 預設值 `1.0`、自訂正浮點權重 (`1.2`, `0.85`) 載入，以及 `weight <= 0` 或非數值時拋出 `InvalidSpaceConfigError` | FR-01, EC-01 | `python yscb.py dev test --target=knowledge-db:TestSpaceManager.test_ft_12_space_weight_schema_and_validation` |
| **FT-02** | 單元測試 | 驗證 `BM25Engine` 與 `HybridSearchEngine` 針對不同 Space 權重 (`docs: 1.2` vs `plans: 0.85`) 執行分數乘算與排序加權 | FR-01 | `python yscb.py dev test --target=knowledge-db:TestHybridSearchEngine.test_space_weights_in_bm25_and_hybrid_search` |
| **FT-03** | 單元測試 | 驗證 `TopologyLinker` 消除 `this._helper.Save()` 對 `caller_class` 的錯誤自綁定、阻斷無關 `prefix` 的跨檔案 `len(candidates) == 1` 幽靈邊，以及阻斷 `len(prefix_tail) < 3` 短變數 (`e`, `s`, `i`, `ev`) 的子字串誤配 | FR-02, EC-02 | `python yscb.py dev test --target=knowledge-db:TestCallGraphAndReferenceIndex.test_ft_13_topology_linker_disambiguation_precision` |
| **FT-04** | 單元測試 | 驗證 `service.py` 於 `Observer.start()` 成功後才寫入 `.watcher_active`、啟動異常時清理殘留 `.watcher_active`，以及 `pipeline._is_watcher_active()` 偵測到 `.watcher_dirty` 時返回 `False` 觸發前台增量同步 | FR-03, EC-03 | `python yscb.py dev test --target=knowledge-db:TestServiceWorker.test_watcher_dirty_flag_stat_bypass`、`test_watcher_start_failure_does_not_leave_active_flag` |
| **FT-05** | 單元測試 | 驗證 `TreeSitterDriver` 從 C#、C++ (`access_specifier`)、TypeScript (`accessibility_modifier`) AST 節點提取真實 `visibility` (`public`/`private`/`protected`/`internal`) | FR-04 | `python yscb.py dev test --target=knowledge-db:TestParsers.test_ft_07_ast_visibility_modifiers_extraction` |
| **FT-06** | 整合測試 | 驗證 C# 跨檔案 `partial class` 符號與成員聚合 (`aggregate_partial_symbols`)，以及跨分片方法呼叫與欄位型別消歧連線 | FR-04, EC-04 | `python yscb.py dev test --target=knowledge-db:TestCallGraphAndReferenceIndex.test_ft_14_csharp_partial_class_cross_file_aggregation_and_linking` |
| **FT-07** | 單元測試 | 驗證未安裝 `agents-workflow` 時 (`is_agents_workflow_installed() == False`)，`scripts/cli.py` 省略 AI Agent 工具提示且 `embedding.py` 不輸出 `[GUARD]` 訊息 | FR-05 | `python yscb.py dev test --target=knowledge-db:TestCLI.test_cli_options_extraction_and_orthogonal_filter` |
| **FT-08** | 回歸與合規測試 | 驗證 `contributes check`、`dev check knowledge-db` 與 `knowledge-db` 全量 157 項測試案例 100% 通過 | NFR-01 | `python yscb.py contributes check`、`python yscb.py dev check knowledge-db`、`python yscb.py dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestSpaceManager.test_ft_12_space_weight_schema_and_validation` 驗證通過 | 2026-11-01 |
| **FT-02** | `Passed` | `TestHybridSearchEngine.test_space_weights_in_bm25_and_hybrid_search` 驗證通過 | 2026-11-01 |
| **FT-03** | `Passed` | `TestCallGraphAndReferenceIndex.test_ft_13_topology_linker_disambiguation_precision` 驗證通過 | 2026-11-01 |
| **FT-04** | `Passed` | `TestServiceWorker.test_watcher_dirty_flag_stat_bypass` 與 `test_watcher_start_failure_does_not_leave_active_flag` 驗證通過 | 2026-11-01 |
| **FT-05** | `Passed` | `TestParsers.test_ft_07_ast_visibility_modifiers_extraction` 驗證通過 | 2026-11-01 |
| **FT-06** | `Passed` | `TestCallGraphAndReferenceIndex.test_ft_14_csharp_partial_class_cross_file_aggregation_and_linking` 驗證通過 | 2026-11-01 |
| **FT-07** | `Passed` | `TestCLI.test_cli_options_extraction_and_orthogonal_filter` 驗證通過 | 2026-11-01 |
| **FT-08** | `Passed` | `contributes check` (15 files PASS)、`dev check knowledge-db` (PASSED)、`dev test knowledge-db -q` (Pass: 157/157, 100.0%)、已安裝 `knowledge-db@1.1.2.build` | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db status` 與 `python yscb.py knowledge-db search "架構" --ftype=md`，確認 `docs` 空間預設具備 `weight: 1.2` 高於 `plans` (`0.85`)，且檢索、拓撲消歧與 Watcher 狀態運作正常 | `[測試通過]` | 開發者實機試調用確認通過 (2026-11-01) |
