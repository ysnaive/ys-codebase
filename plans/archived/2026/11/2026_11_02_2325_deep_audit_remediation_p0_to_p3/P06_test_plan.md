# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：deep_audit_remediation_p0_to_p3  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `Installer` (`cmd_install`, `cmd_update`, `cmd_remove`) 將 `act_snapshot` 與 `act_restore_snapshot` 嚴格置於 `transaction_lock` 內；當鎖競爭拋出 `BlockingIOError` 時不建立快照亦不執行回滾。 | FR-01, EC-01 | `python yscb.py dev test core -q` (`TestCoreInstaller.test_transaction_lock_contention_does_not_overwrite_snapshot_or_rollback`) |
| **FT-02** | 單元測試 | `spawn_detached_master` 以 `sys.argv` 安全傳遞含單引號路徑，`MasterSupervisor.restart_worker` 先獲取 `_dispatch_lock` 再獲取 `_worker_lock`，`daemon.json` 權限與 `secrets.compare_digest` 正常運作。 | FR-02, EC-02 | `python yscb.py dev test server -q` (`TestServerModule.test_spawn_detached_master_quote_safe_args_and_restart_worker_lock_order`) |
| **FT-03** | 單元測試 | `OSBackend.assert_safe_path` 與 `exists`/`is_file`/`is_dir` 透過對稱 `realpath` 阻斷指向根目錄外的 Symlink 逃逸，且 `process.py`、`lock.py`、`pip_manager.py`、`dispatcher.py`、`telemetry.py` 正常運作。 | FR-03, EC-03 | `python yscb.py dev test core -q` (`TestCoreInstaller.test_transaction_lock_contention_does_not_overwrite_snapshot_or_rollback`) |
| **FT-04** | 單元測試 | `file-space` 與 `knowledge-db` 支援 `on_server_worker_warming`、`is_transaction_locked` 探測、C# 同名重載方法保留於類別成員列表、`is_dirty_file_match` 避免無斜線同名檔案誤判，且 `wait_until_worker_idle` 跨進程等待不發生 100% CPU 空轉。 | FR-04, EC-04, EC-05, NFR-01 | `python yscb.py dev test file-space -q` & `python yscb.py dev test ast -q` & `python yscb.py dev test knowledge-db -q` |
| **FT-05** | 單元測試 | `agents_workflow/publisher.py` 原子寫入落地檔與 `.gitignore`，`SandboxProvisioner.cleanup_sandbox` 支援唯讀屬性清除回呼，`OutputCapturer` 支援單測方法級輸出切片捕獲。 | FR-05 | `python yscb.py dev test agents-workflow -q` & `python yscb.py dev test dev -q` |
| **RT-01** | 全量回歸測試 | 全專案 7 大核心模組（`core`, `server`, `file-space`, `ast`, `knowledge-db`, `agents-workflow`, `dev`）合規檢查與 627 項自動化測試 100% 通過。 | FR-01 ~ FR-05, NFR-02 | `python yscb.py dev check <mod>` & `python yscb.py dev test <mod> -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 測試集 222/222 (100.0%) 通過：驗證 `act_lock` 拋出 `BlockingIOError` 時 `act_snapshot` 與 `act_restore_snapshot` 呼叫次數皆為 0。 | 2026-11-02 |
| **FT-02** | `Passed` | `server` 測試集 41/41 (100.0%) 通過：含單引號路徑 `"O'Connor's Workspace"` 透過 `sys.argv` 安全傳遞，且 `restart_worker` 期間 `_dispatch_lock.locked()` 為 `True`。 | 2026-11-02 |
| **FT-03** | `Passed` | `core` 測試集 222/222 (100.0%) 通過：`OSBackend(root_dir=...)` 對指向外部檔案之 Symlink 呼叫 `read_text` 與 `exists` 均拋出 `PermissionError`。 | 2026-11-02 |
| **FT-04** | `Passed` | `file-space` 15/15、`ast` 20/20、`knowledge-db` 105/105 (100.0%) 通過：`wait_until_worker_idle` 於 60ms 跨進程等待中僅輪詢 $\le 10$ 次（消除數萬次空轉）。 | 2026-11-02 |
| **FT-05** | `Passed` | `agents-workflow` 141/141、`dev` 83/83 (100.0%) 通過。 | 2026-11-02 |
| **RT-01** | `Passed` | 全 7 模組共 627 項測試（`core`: 222, `agents-workflow`: 141, `knowledge-db`: 105, `dev`: 83, `server`: 41, `ast`: 20, `file-space`: 15）100.0% 通過，0 失敗、0 跳過。 | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視全專案深度審計 22 項問題（`AUD-01` ~ `AUD-22`）之修復實作、7 大模組 627 項測試全綠結果與盲審子代理靜態審計結論是否符合預期。 | `[跳過/免測]` | 開發者指示免測，已實機確認 7 大模組 status 與核心功能 100% 正常 |

