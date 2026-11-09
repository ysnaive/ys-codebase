# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：統一 Cell 生命週期快取原語、Epoch 世代常駐對稱與 Stage 耗時剖析器  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `CellScope`、`bind_cell_context`、`get_or_compute_cell_state`、`invalidate_cell_state`、冷派發無 Cell 降級、例外不污染快取與 `copy_context()` 背景執行緒防洩漏 (`is_closed`) | FR-01, EC-01, EC-03, [P01:DR-02] | `python yscb.py dev test core -k "cell" -q` |
| **FT-02** | 單元測試 | 驗證 `get_or_compute_epoch_state` 與 `invalidate_epoch_state` 跨 Cell 世代快取對稱、鎖外執行 `epoch_fn`/`builder_fn` 與 `reset_all_caches()` 清空 | FR-02, EC-03, [P01:DR-03] | `python yscb.py dev test core -k "epoch" -q` |
| **FT-03** | 單元測試 | 驗證 `cell_span` 階段耗時累加、`<0.5ms` 噪音過濾與 `DebouncedIOStreamer.send_task_finish(..., stages=...)` 向後相容傳遞 | FR-03, EC-02, [P01:DR-04] | `python yscb.py dev test core -k "cell_span" -q` |
| **FT-04** | 全倉回歸與自部署測試 | 驗證全專案 8 大活躍模組 (`core`, `server`, `dev`, `ast`, `knowledge-db`, `agents-workflow`, `vscode-support`, `gdrive-support`) 經非局部狀態 `Cell/Epoch` 收口與 `Mode A` 無損清理後 100% 通過合規檢查與單元測試並完成 `@build` 本機安裝 | FR-04, EC-04, NFR-01, NFR-02 | `python yscb.py dev check --all` & `python yscb.py dev test <mod> -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_cell_scope_lifecycle_and_background_thread_copy_context_guard` 通過；驗證退出 `bind_cell_context` 後 `cell.is_closed == True` 且背景執行緒 `copy_context()` 呼叫 `get_current_cell()` 回傳 `None`。 | 2026-11-08 19:20 |
| **FT-02** | `Passed` | `test_epoch_state_caching_invalidation_and_lock_free_builder` 通過；驗證 `epoch_fn` 世代不變時跨 Cell 命中快取、世代推進時重算，且 `reset_all_caches()` 徹底清空 `epoch_states`。 | 2026-11-08 19:20 |
| **FT-03** | `Passed` | `test_cell_span_profiling_and_noise_filtering` 通過；驗證 `cell_span` 正確累計毫秒數、過濾 `<0.5ms` 微小噪音並支援例外穿透記錄。 | 2026-11-08 19:20 |
| **FT-04** | `Passed` | `dev check --all`：`9 Total, 9 Passed, 0 Warnings, 0 Failed`。8 大活躍模組全量測試與 `@build` 自部署：`core` (286/286)、`server` (65/65)、`dev` (110/110)、`ast` (40/40)、`knowledge-db` (113/113)、`agents-workflow` (145/145)、`vscode-support` (22/22)、`gdrive-support` (34/34)，合計 **815 / 815 (100.0%)** 通過。 | 2026-11-08 19:20 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 本機自部署 `@build` 後重啟常駐 Server Daemon，連續調用全專案 8 大模組 18 組常用 CLI 指令，確認全部 `rc=0` 且 `ys_codebase/.cache/server/log` 自動顯影 `[pre_hooks=..., cmd_exec=...]` 階段耗時明細（`pre_hooks` 穩定於 `~7.5ms`，`ast.jit_sync` 穩定於 `~3.2ms`） | `[測試通過]` | 依開發者預排長任務指示，完成多路 `/blind-subagent` 全專案清理、本機 `@build` 自部署與 18 組常用 CLI 實機調用及耗時紀錄驗證通過 |
