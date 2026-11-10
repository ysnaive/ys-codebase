# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_04_server_dev_and_vscode_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `WarmWorker` 在閒置期間接收背景 `log`/`service_status`/`touch_activity` IPC 封包時不阻塞 Pipe 且後續前景任務 100% 正常執行 (`EC-01`)；驗證 `ServiceManager.get_status()` 包含 `metrics`，且 `is_any_worker_service_busy()` 阻擋忙碌時之 RSS 回收、`restart_worker(touch_activity=False)` 不重置 `_last_active_time` | FR-01, EC-01, NFR-01 | `python3 yscb.py dev test --m server` |
| **FT-02** | 單元測試 | 驗證 `server stop` 優雅等待與日誌歸檔鎖保護，以及 `SpaceWatcher` 面對殘留未持鎖 `.yscb.lock` 檔案時不凍結 (`EC-02`)、在 macOS `/private/var` 下精準匹配路徑，並於移除監控目錄時呼叫 `unschedule` | FR-02, EC-02 | `python3 yscb.py dev test --m server` |
| **ET-01** | 邊界測試 | 驗證 `sandbox.py` 平行建立 10 個沙盒時不誤刪活躍沙盒、攔截含 `../` 之 Zip Slip 歸檔成員 (`EC-03`)、`releaser.py` 在 pre-flight 失敗時原子保護 `manifest.json`，以及 `projector.py` 在預設 `include_all=False` 下完整保留 `core.space` 排除規則、`hook.core.py` 同狀態去重與 `schema_compiler.py` `$ref` 元資料保留 | FR-03, FR-04, EC-03 | `python3 yscb.py dev test --m dev && python3 yscb.py dev test --m vscode-support` |
| **RT-01** | 回歸測試 | 驗證 `checker.py` `_MUTABLE_TYPE_NAMES` 包含 `"DefaultDict"` 且 AST/JSON 快取顯著加速重複檢查，以及全倉 `dev check` 與三模組 `dev test` 100% 通過 (`NFR-01`, `NFR-02`) | FR-03, FR-04, NFR-01, NFR-02 | `python3 yscb.py dev check && python3 yscb.py dev test --m server && python3 yscb.py dev test --m dev && python3 yscb.py dev test --m vscode-support` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_idle_worker_demuxer_drains_bg_logs_metrics_and_busy_rss_guard` 驗證通過，`ServiceManager.get_status()` 完整回傳 `metrics`，閒置期背景封包即時排空，忙碌期間 RSS 回收安全跳過且 `restart_worker(touch_activity=False)` 保留 `_last_active_time` | 2026-11-09 |
| **FT-02** | `Passed` | `test_stale_unlocked_lockfile_macos_private_prefix_and_unschedule` 驗證通過，空殼 `.yscb.lock` 不凍結 `is_transaction_locked()`、`/private/var` 前綴精準切片、移除目錄成功觸發 `unschedule` | 2026-11-09 |
| **ET-01** | `Passed` | `test_safe_extract_zip_blocks_zip_slip_and_parallel_allocation_keeps_active`、`test_release_module_preflight_failure_rolls_back_manifest` 與 `test_workspace_exclude_patterns_hook_dedup_and_mirror_zip_schema_bundle` 全數通過 | 2026-11-09 |
| **RT-01** | `Passed` | `dev check` 9/9 模組 0 Warnings / 0 Failed；`server` (66/66)、`dev` (112/112)、`vscode-support` (23/23) 共 201 項測試 100% 通過；`Checker.check_all()` Warm 延遲下降 86.31% | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python3 yscb.py dev check` 與 `python3 yscb.py dev test --m server`、`--m dev`、`--m vscode-support`，確認 0 違規且全部 201 項單元與契約測試 100% 通過 | `[測試通過]` | 沙盒實機驗證 9/9 模組靜態檢查通過、201/201 測試全綠 |
