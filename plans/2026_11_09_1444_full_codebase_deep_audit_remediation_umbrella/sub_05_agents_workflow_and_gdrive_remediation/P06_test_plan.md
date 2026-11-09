# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_agents_workflow_and_gdrive_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `collect_space_local_files_with_stat`、`is_local_abs_allowed` 與 `is_sensitive_credential_path` 攔截指向空間外部或敏感憑證之 Symlink (`EC-01`)，且 `load_lightweight_repo_sync_settings` 與 `list_files(deduplicate=False)` CQS 唯讀列舉運作正常 | FR-01, EC-01 | `python3 -W error::ResourceWarning yscb.py dev test --m gdrive-support` |
| **FT-02** | 單元測試 | 驗證 `compiler.py` 不將行內標籤誤判為整行刪除、同 Token 獨立行與行內皆展開、Fenced Code Block 內 `//` 整數除法與註解不被破壞 (`EC-02`)、Stage 1 產生預計算 `sha256`，且 `publisher.py` 雙軌 Manifest 與 `agent_rules` 100% 合規 | FR-02, EC-02 | `python3 -W error::ResourceWarning yscb.py dev test --m agents-workflow` |
| **ET-01** | 邊界測試 | 驗證雲端新增/更新檔案後 `pull` 正確寫回遠端 `.yscb_gdrive.json` (`EC-03`) 並更新 `remote_repo_cache` 與 `fingerprint_cache`、`GDriveSyncServiceWorker` 於 `checkout_branch` 後動態重新整理 `active_branch`，以及 `GoogleDriveApiTransport` 連線池回收與 `close()` 0 `ResourceWarning` (`NFR-01`) | FR-03, EC-03, NFR-01 | `python3 -W error::ResourceWarning yscb.py dev test --m gdrive-support` |
| **RT-01** | 回歸測試 | 驗證 `PlanVerifier` 交易式自癒於失敗時回滾、攔截空白標頭並精準對齊 Fenced Code Block 後之 1:1 物理行號、支援 `changelog.md` 轉義直線 `\|`、`PlanArchiver` 阻斷含未完成子計畫之 Umbrella 歸檔，且 `dev check` 0 違規 (`NFR-02`) | FR-04, NFR-02 | `python3 yscb.py dev check && python3 -W error::ResourceWarning yscb.py dev test --m agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestGDriveAtomicApiAndConfig.test_ft_10_symlink_escape_rejection_cqs_ls_and_connection_pool_reuse` 等 36 項測試全數通過（`0 Failed, 0 ResourceWarning`） | 2026-11-09 |
| **FT-02** | `Passed` | `TestArtifactCompiler.test_fenced_code_slash_preservation_and_dual_token_occurrences` 等 147 項測試全數通過（`0 Failed, 0 ResourceWarning`） | 2026-11-09 |
| **ET-01** | `Passed` | `TestGDriveBranchAndSyncEngine.test_ft_16_pull_cache_coherency_stage1_meta_persist_and_service_dynamic_branch_refresh` 驗證通過（`2.416s`） | 2026-11-09 |
| **RT-01** | `Passed` | `TestPlansModelRecord.test_transactional_healing_escaped_pipes_and_umbrella_completion_consistency` 與 `python3 yscb.py dev check`（9/9 Passed, 0 Warnings, 0 Failed）全數通過 | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python3 yscb.py dev check`、`python3 -W error::ResourceWarning yscb.py dev test --m agents-workflow` 與 `python3 -W error::ResourceWarning yscb.py dev test --m gdrive-support`，確認 9 大模組 0 違規且兩模組共 183 項測試 100% 通過 | `[測試通過]` | VM 隔離沙盒實機驗收通過（147/147 + 36/36 Passed，0 Warnings） |
