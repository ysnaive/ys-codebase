# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Google Drive Changes API 增量快照與前景 CLI 優先搶占讓鎖機制 (GDrive Changes API Incremental Snapshot & CLI Lock Preemption)  
> 建立日期：2026-11-05  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `LocalSandboxTransport` 之 `get_start_page_token()` 與 `list_changes(page_token)` 精確追蹤實體檔案增刪改、Shortcut 目標變更與虛擬項目，並對過期/未知 `page_token` 拋出 `GDriveTransportError` | FR-01 | `python yscb.py dev test gdrive-support -q` (`test_ft_10_sandbox_changes_api_physical_and_shortcut_virtual_items`) |
| **FT-02** | 整合測試 | `SyncCoordinator` 三級遠端倉庫快取 (`remote_repo_cache`)：Level 0 零雲端變更時 `list_files` 呼叫次數為 `0` (`cache_hit_level == 0`)；Level 1 已知檔案修改、已知目錄新增檔案與 Shortcut `target_file_id` 更新時於記憶體增量 Patch (`list_files == 0`, `cache_hit_level == 1`)；Level 2 新增雲端目錄時自動回退全量掃描 (`cache_hit_level == 2`) | FR-02, EC-01, EC-02, NFR-01 | `python yscb.py dev test gdrive-support -q` (`test_ft_11_changes_api_three_level_cache_short_circuit_and_shortcut_target_patch`) |
| **FT-03** | 整合與邊界測試 | 前景 CLI 透過 `cli_yield.signal` 搶占背景 Worker 鎖（背景 `yielded == True` 且前景成功執行並自動清除訊號檔）、死進程/逾時孤兒訊號檔自動清除，以及 Stage 3 中途讓鎖時單檔原子 CoW + 上傳與 `.yscb_gdrive.json` (`meta_dirty`) 安全落盤 | FR-03, EC-03, NFR-02 | `python yscb.py dev test gdrive-support -q` (`test_ft_12_cli_yield_signal_preemption_orphan_self_healing_and_atomic_cow_mid_sync`) |
| **FT-04** | 回歸與合規測試 | `gdrive-support` 全量單元與整合測試集（30 項測試案例）與 `dev check` 模組結構合規檢查 100% 通過 | FR-01, FR-02, FR-03 | `python yscb.py dev check gdrive-support && python yscb.py dev test gdrive-support -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_10_sandbox_changes_api_physical_and_shortcut_virtual_items` 驗證實體檔、Shortcut 目標與虛擬項目差異游標及過期 token 例外通過 | 2026-11-05 |
| **FT-02** | `Passed` | `test_ft_11_changes_api_three_level_cache_short_circuit_and_shortcut_target_patch` 驗證 Level 0/1 皆為 `0` 次 `list_files` 呼叫、Shortcut 目標連動更新與 Level 2 結構變動回退通過 | 2026-11-05 |
| **FT-03** | `Passed` | `test_ft_12_cli_yield_signal_preemption_orphan_self_healing_and_atomic_cow_mid_sync` 驗證前景 CLI 搶占背景鎖、孤兒訊號自癒與單檔原子 CoW 中途讓鎖無狀態撕裂通過 | 2026-11-05 |
| **FT-04** | `Passed` | `dev check gdrive-support` `[PASS]`，`dev test gdrive-support -q --sync` `Pass: 30(100.0%), Fail: 0, Skip: 0` | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 連續執行兩次 `python yscb.py gdrive sync`（或於背景 Server Worker 運行時執行 `python yscb.py gdrive push`），確認第二次同步因 `changes` API Level 0 快取命中於 1 秒內完成，且前景 CLI 不再發生搶不到 `sync.lock` 的報錯 | `[測試通過]` | 實機執行 `gdrive push --force` (`pushed=129, conflicts=0`) 與後續 `gdrive sync` (`cache_hit_level=0`, `changes` API 對帳耗時 `0.30s ~ 0.35s`, `rc=0`) 驗收通過 |

