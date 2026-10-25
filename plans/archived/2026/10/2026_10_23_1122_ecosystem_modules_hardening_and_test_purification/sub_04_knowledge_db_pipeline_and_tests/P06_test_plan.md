# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 整合測試 | 驗證全新進程冷啟動呼叫 `pipeline.search()` 能成功載入 `unified.vectors.bin.gz` 並走 Hybrid RRF 檢索 | FR-01 | `test_hot_reload.py::test_cold_start_vector_index_loading` |
| **FT-02** | 整合測試 | 驗證修改被調用檔案後觸發熱修補，外部未修改檔案之 `Callers` 入度邊（含類別方法與裸調用）100% 保真 | FR-02 | `test_graph.py::test_hot_patch_incoming_callers_retention` |
| **FT-03** | 單元測試 | 驗證 `hook.server.py` 僅執行 `pre_warm()` 不私自啟動第二個 Watcher，`service.py` 零 `source/` 注入 | FR-03 | `test_service_worker.py::test_hook_server_pure_prewarm` |
| **FT-04** | 單元測試 | 驗證 `--ftype=c,cpp,py` 逗號多副檔名拆解與過濾生效，`act_callers` 傳遞 `ftypes`，`find_target_symbol` 快取重用 | FR-04 | `test_retrieval.py::test_multi_ftype_filtering` |
| **FT-05** | 靜態檢核 | 驗證 `thesaurus / aliases / related` 欄位徹底自代碼與 contributes 清除，且 `protocol.py` 已刪除 | FR-05 | `test_schema.py::test_thesaurus_purity_and_dead_code_removal` |
| **FT-06** | 整合測試 | 驗證 `contributes/core.json` 選項補齊，`cli.py -d` 模式必然包含代碼切片，`search -d --json` 輸出完整欄位 | FR-06 | `test_cli.py::test_cli_detail_mode_and_json_fields` |
| **FT-07** | 單元測試 | 驗證 `KnowledgeDBConfig.load()` 以 `core.config` 為最高優先級，`KnowledgeEngine` 提供 `callers/callees/impact` SDK 別名 | FR-07 | `test_engine.py::test_sdk_aliases_and_config_priority` |
| **FT-08** | 結構檢核 | 驗證 `knowledge-db/tests/` 收斂為 12 檔（2 碎片檔刪除），雙胞胎重複測試與墓碑測試徹底消除 | FR-08 | `test_cli.py::test_test_suite_structure_convergence` |
| **FT-09** | 整合測試 | 驗證虛假測試重寫後具備真實斷言、單例隔離無殘留，且高風險路徑覆蓋完整 | FR-09 | `test_cli.py::test_cli_assertions_and_isolation` |
| **ET-01** | 邊界測試 | 磁碟無向量索引時，`want_vectors=True` 嘗試後 `can_use_vector=False` 平滑降級為純 BM25 檢索 | EC-01 | `test_retrieval.py::test_vector_fallback_when_unavailable` |
| **ET-02** | 邊界測試 | 外部未修改檔案以無前綴裸函式調用目標檔案，熱修補第一階 Identity Remap 成功對齊新 SHA-1 ID | EC-02 | `test_graph.py::test_bare_function_incoming_edge_remap` |
| **ET-03** | 邊界測試 | 調用之目標符號在熱修補中被徹底刪除時，雙階重連失敗後自然斷開，不留幽靈邊 | EC-03 | `test_graph.py::test_deleted_symbol_edge_cleanup` |
| **ET-04** | 邊界測試 | 傳入 `--ftype="c, cpp , py"` 包含空格之複合字串，成功解析並精確過濾 | EC-04 | `test_retrieval.py::test_whitespace_in_ftypes` |
| **ET-05** | 邊界測試 | 在未安裝 `server` 的環境下執行 `service.py`，優雅退回內建基類不崩潰 | EC-05 | `test_service_worker.py::test_service_fallback_without_server` |
| **RT-01** | 全量回歸 | 執行 `python yscb.py dev check knowledge-db` 與 `python yscb.py dev test knowledge-db -q` 100% 通過且環境零殘留 | NFR-01, NFR-02 | `dev check knowledge-db` && `dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-09** | `Passed` | 150/150 custom/contract tests passed (0 fail, 0 skip). 冷啟動向量載入、熱修補入度保真、多副檔名過濾、死代碼清理與 SDK 別名皆通過 | 2026-10-24 13:06 |
| **ET-01 ~ ET-05** | `Passed` | 向量平滑降級、裸函式重連、刪除符號邊清理、空白副檔名與無 server 依賴回退全數通過 | 2026-10-24 13:06 |
| **RT-01** | `Passed` | `dev check knowledge-db` 0 warn 0 fail；`dev test -q` 全生態系回歸 193/193 100% 通過 | 2026-10-24 13:06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db search "PIDController" -d`，驗證輸出包含完整程式碼切片與行號，且無已廢棄同義詞提示。 | `Passed` | 輸出包含高密度代碼切片與精確行號，且無同義詞提示。開發者確認通過。 |
| **UX-02** | 執行 `python yscb.py knowledge-db callers "verify" --ftype=py`，驗證多語言消歧與入度調用者輸出正確。 | `Passed` | 準確識別 `PlanVerifier.verify` 為 Facade 入口無靜態上游調用者（內部實際調用 `verify_plan`），拓撲消歧 100% 正確。開發者確認通過。 |
| **UX-03** | 執行 `python yscb.py knowledge-db status`，驗證顯示已註冊空間與快取現況，且無 `X 組同義詞` 殘留。 | `Passed` | 狀態顯示 3 空間、全域倒排索引、向量特徵索引與向量模型權重均就緒，無同義詞字串殘留。開發者確認通過。 |
