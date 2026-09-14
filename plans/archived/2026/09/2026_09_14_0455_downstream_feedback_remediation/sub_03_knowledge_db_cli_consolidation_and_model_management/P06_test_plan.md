# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證舊指令 (`scan`, `bundle`) 已徹底移除，調用時返回未知指令且退出碼為 1 | FR-01, EC-05 | `test_cli.py:test_removed_commands` |
| **FT-02** | 單元測試 | 驗證 `status --scan` / `status --diff` 正常輸出空間指紋統計與變更 | FR-02 | `test_cli.py:test_status_with_scan` |
| **FT-03** | 單元測試 | 驗證 `index` 一鍵完成全管線索引建置，並驗證 `index --export <path>` 正常導出 Bundle | FR-03, EC-04 | `test_cli.py:test_index_pipeline_and_export` |
| **FT-04** | 單元測試 | 驗證 `model status` 與 `model download` 正常運作，權重資訊輸出精確 | FR-04 | `test_cli.py:test_model_subcommands` |
| **FT-05** | 單元測試 | 驗證本地無模型時 `search` 絕不連網發 HF 請求，平滑且靜默退回 BM25 | FR-05, EC-01 | `test_cli.py:test_search_smooth_fallback` |
| **FT-06** | 單元測試 | 驗證當 `enable_vector_search: true` 但無模型時，stderr 輸出 `[GUARD]` 提示 | FR-06 | `test_cli.py:test_guard_directive_output` |
| **ET-01** | 邊界測試 | 驗證離線模式下模型缺失探針秒級生效，檢索無逾時、無卡頓與無例外崩潰 | EC-02, NFR-01 | `test_cli.py:test_offline_zero_crash` |
| **RT-01** | 全量回歸 | 驗證 `knowledge-db` 全套單元測試 100% 通過 | NFR-02 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 斷言 `scan` 與 `bundle` 指令退出碼非 0，舊指令徹底移除生效 | 2026-09-14 05:28 |
| **FT-02** | `Passed` | `status --scan` 與 `status --diff` 正常渲染 Added/Modified/Deleted/Unchanged | 2026-09-14 05:28 |
| **FT-03** | `Passed` | `index --all` 全量建立與 `index --export` 正常導出至巢狀路徑 JSON | 2026-09-14 05:28 |
| **FT-04** | `Passed` | `model status` 輸出模型名、目錄、維度；支援 `--json` 格式；`model download` 正常連動 | 2026-09-14 05:28 |
| **FT-05** | `Passed` | 空快取目錄下探針正確判定未下載，不發起網路連線，last_error 結構化封裝 | 2026-09-14 05:28 |
| **FT-06** | `Passed` | `enable_vector_search: true` 且本地無模型時，stderr 精確輸出 `[GUARD]` 引導 | 2026-09-14 05:28 |
| **ET-01** | `Passed` | 本機無權重探針耗時 $< 0.5\text{s}$ (實測 $< 0.01\text{s}$)，零卡頓、零崩潰 | 2026-09-14 05:28 |
| **RT-01** | `Passed` | `python yscb.py dev test knowledge-db`: 157/157 Passed (100% Ready) | 2026-09-14 05:30 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py knowledge-db status --scan` 確認增量指紋輸出 | `[跳過/免測]` | 開發者指示免測 (單元測試已驗證通過) |
| **UX-02** | 實機執行 `python yscb.py knowledge-db model status` 檢視模型狀態 | `[跳過/免測]` | 開發者指示免測 (單元測試已驗證通過) |
| **UX-03** | 實機無模型檢索確認平滑降級至 BM25 且輸出 `[GUARD]` 引導 | `[跳過/免測]` | 開發者指示免測 (單元測試已驗證通過) |
