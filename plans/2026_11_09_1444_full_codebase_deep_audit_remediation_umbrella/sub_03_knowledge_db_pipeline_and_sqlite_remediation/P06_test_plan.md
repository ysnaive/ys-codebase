# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_knowledge_db_pipeline_and_sqlite_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證修改 C# `partial class` 副檔觸發 `hot_patch_unified_index` 後，未修改主檔內之其他非 partial 類別/結構 100% 保留 (`EC-01`)；驗證跨多世代 AST 更新不會跳號漏索引 | FR-01, EC-01 | `python3 yscb.py dev test --m knowledge-db` |
| **FT-02** | 單元測試 | 驗證常駐 Worker 空閒時前景 `search` 能感知新檔案變更並完成增量同步，以及 `build_unified_index(force=False)` 能同步待處理變更、補齊缺失向量並寫入 `_GLOBAL_INDEX_CACHE` | FR-02 | `python3 yscb.py dev test --m knowledge-db` |
| **FT-03** | 單元測試 | 驗證 Mode A 手術 `S2`：背景 Stage 2 禮讓前景時持久化部分向量並標記 `yielded_to_foreground`，前景 `_ensure_indices_loaded(force_reload=True)` 不覆寫記憶體內較新之髒向量 (`EC-04`)；驗證 `sync_incremental_changes` 統一三處增量迴圈與 `io_utils.py` `.tmp` 清理 | FR-05, EC-04 | `python3 yscb.py dev test --m knowledge-db` |
| **ET-01** | 邊界測試 | 驗證 `hook.ast.py` 支援 `list`/專案級組態、`purify_lines` 不吞噬含 `"src/*"` 之程式碼行 (`EC-02`)、雙詞查詢不誤吞首詞且指定空間向量檢索不餓死 (`EC-03`) | FR-03, EC-02, EC-03 | `python3 yscb.py dev test --m knowledge-db` |
| **RT-01** | 回歸與效能測試 | 驗證 `config.py` 互斥超時鍵、`schema.py` `NaN`/`Inf` 攔截、BM25 聚合完整排序、macOS `/private/var` 路徑對齊，以及 `status` 零模型載入與檢索延遲下降 (`NFR-01`, `NFR-02`) | FR-04, NFR-01, NFR-02 | `python3 yscb.py dev check && python3 yscb.py dev test --m knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_csharp_partial_class_two_phase_dirty_closure_and_multigen_jump` 驗證通過，`Player.cs` 內 `HelperStruct` 100% 保留且跨多世代 `Gen2AddedNode` / `Gen3AddedNode` 完整補齊 | 2026-11-09 |
| **FT-02** | `Passed` | `test_mutual_yield_paradox_defense_and_idle_worker_jit_sync` 驗證通過，空閒 Worker 下前景 `search` 即時同步 `IdleSyncedGamma`，`build_unified_index(force=False)` 自動補齊向量並更新 `_GLOBAL_INDEX_CACHE` | 2026-11-09 |
| **FT-03** | `Passed` | 驗證 `_ensure_indices_loaded(force_reload=True)` 不覆寫記憶體髒向量，且 `pipeline.py`、`service.py`、`scripts/hook.core.py` 全數透過 `sync_incremental_changes` 通過端到端測試 | 2026-11-09 |
| **ET-01** | `Passed` | `test_purify_lines_glob_star_selector_multiword_and_vector_prefilter` 驗證通過，`pattern = "src/*"` 後續程式碼完整保留、`"user profile"` 完整解析、向量遮罩預過濾精準命中 | 2026-11-09 |
| **RT-01** | `Passed` | `dev check` 9/9 模組 0 Warnings / 0 Failed；`dev test --m knowledge-db` 116/116 全數通過（耗時 4.16s）；BM25 聚合檢索延遲下降 30.1%、Hybrid 過濾檢索延遲下降 19.8% | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python3 yscb.py dev check` 與 `python3 yscb.py dev test --m knowledge-db`，確認 0 違規且全部 116 項單元與契約測試 100% 通過 | `[測試通過]` | 沙盒實機驗證 9/9 模組靜態檢查通過、116/116 測試全綠 |
