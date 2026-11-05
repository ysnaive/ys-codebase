# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_gdrive_and_vscode_support  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SyncCoordinator.run_sync(mode="pull")` 遇本地單方修改之檔案時，不覆寫本地基準線 `branch_state_dict[rel_p]`，後續執行 `push`/`sync` 正常識別為 `PUSH_UPDATE` 並上傳。 | FR-01 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **FT-02** | 單元測試 | 驗證 `SyncCoordinator.run_sync()` 於 `sync_spaces` 為空清單時拋出 `GDriveConfigError`，且 `ys_codebase/config/gdrive-support/contribute.json` 宣告 `"sync_spaces": [{"space": "cloud"}]`。 | FR-02 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **FT-03** | 單元測試 | 驗證分支內 `README.md` 與 `.`/`_` 開頭子目錄（如 `.github/workflows/ci.yml`、`_internal/guide.md`）於 Level 1 與 Level 2 皆能完整掃描與增量更新。 | FR-03 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **FT-04** | 單元測試 | 驗證 CLI `_build_coordinator(sandbox_dir)` 將 `state_path`、`lock_path`、`log_path`、`readme_state_path` 隔離錨定至沙盒目錄，且沙盒 `checkout_branch` 不會觸發 `core_config.set` 污染全域設定。 | FR-04 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **FT-05** | 單元測試 | 驗證 `DELETE_REMOTE` 刪除遠端深層子目錄最後一個檔案後，由深至淺自動清理遠端空父目錄並保留分支根目錄與系統目錄。 | FR-05 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **FT-06** | 單元測試 | 驗證 `GoogleDriveApiTransport._cache_lock`、`warm_folder_cache`、`reset_scan_state`、`trash_file(file_id=...)` 與 `_precreate_remote_dirs` 按深度分層 BFS 平行建目錄。 | FR-06, NFR-01, NFR-02 | `test_atomic_api_and_config.py::TestGDriveAtomicApiAndConfig.test_ft_09_drive_api_transport_401_retry_folder_protection_and_mkdir_sorting` |
| **FT-07** | 單元測試 | 驗證 `GoogleDriveApiTransport` 對 HTTP `401` 重置 Token 重試、`download_file` `entry_hint` 與 `503` 退避重試、`list_files` 同名資料夾免移垃圾桶保護、`mkdir` 按 `modifiedTime` 降序選取最新資料夾及 Shortcut 平行解析。 | FR-07, NFR-01 | `test_atomic_api_and_config.py::TestGDriveAtomicApiAndConfig.test_ft_09_drive_api_transport_401_retry_folder_protection_and_mkdir_sorting` |
| **FT-08** | 單元測試 | 驗證 `vscode-support` 之 `on_remove` Fail-Closed（含 `"vsc"` 別名）、`_select_latest_mirror_zip` 四段式 SemVer 排序（`1.0.0.10.zip > 1.0.0.2.zip`）、URI Snippets 快取、`revert_vscode_settings` 空排除字典清理及 `get_status` 懸空連結與 JSONC 支援。 | FR-08, NFR-01, NFR-03 | `test_vscode_support.py::TestVSCodeSupport.test_ft_08_audit_remediation_hook_alias_semver_mirror_and_clean_status` |
| **ET-01** | 邊界測試 | 驗證單向 `pull`/`push` 遇對向未同步變更時保留原基準線不覆寫。 | EC-01 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **ET-02** | 邊界測試 | 驗證雙端同時刪除檔案時清除 `branch_state_dict[rel_p]` 與 `curr_branch_files[rel_p]`。 | EC-02 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_et_06_orthogonal_cloud_branch_discovery_both_deleted_prune_and_untracked_checkout_guard` |
| **ET-03** | 邊界測試 | 驗證紅線 1：當存在 `auto_discovered=True` 之分支時，拒絕跳過掃描並於 `.history/` GC 前實地掃描，防止誤刪歷史凍結實體檔。 | EC-03 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **ET-04** | 邊界測試 | 驗證雲端同一父目錄存在多個同名資料夾時，`list_files` 僅移走同名重複之一般檔案，絕不將同名資料夾移入垃圾桶。 | EC-04 | `test_atomic_api_and_config.py::TestGDriveAtomicApiAndConfig.test_ft_09_drive_api_transport_401_retry_folder_protection_and_mkdir_sorting` |
| **ET-05** | 邊界測試 | 驗證遠端目錄因檔案刪除騰空為空殼資料夾時，由深至淺自動清理並同步移除 `remote_repo_cache` 內對應項目。 | EC-05 | `test_branch_and_sync_engine.py::TestGDriveBranchAndSyncEngine.test_ft_14_audit_remediation_baseline_preservation_readme_dot_dirs_prune_and_sandbox_isolation` |
| **ET-06** | 邊界測試 | 驗證 `on_remove(None)` / `on_remove(ctx_with_none_args)` 回傳 `False`，以及 `get_status` 針對懸空 Symlink 回報 `stable_link_active: False` 並支援 JSONC `settings.json`。 | EC-06 | `test_vscode_support.py::TestVSCodeSupport.test_ft_08_audit_remediation_hook_alias_semver_mirror_and_clean_status` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

> 註：已完成全數修改檔案之 `python -m py_compile` 語法編譯驗證、`python yscb.py dev check gdrive-support` / `python yscb.py dev check vscode-support` 靜態合規檢查（100% PASSED），以及 P06 統一沙盒測試驗收（`gdrive-support` 33/33 Pass，`vscode-support` 12/12 Pass）並同步安裝 `@build`。

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0)，已同步 `gdrive-support@1.0.1.build` | 2026-11-05 |
| **FT-02** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-03** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-04** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-05** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-06** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-07** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **FT-08** | `Passed` | `dev test vscode-support -q --sync` 沙盒測試 100% 通過 (Pass: 12, Fail: 0, Skip: 0)，已同步 `vscode-support@1.0.0.build` | 2026-11-05 |
| **ET-01** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-02** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-03** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-04** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-05** | `Passed` | `dev test gdrive-support -q --sync` 沙盒測試 100% 通過 (Pass: 33, Fail: 0, Skip: 0) | 2026-11-05 |
| **ET-06** | `Passed` | `dev test vscode-support -q --sync` 沙盒測試 100% 通過 (Pass: 12, Fail: 0, Skip: 0) | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev test gdrive-support vscode-support` 確認全數自動化測試案例通過 | `[測試通過]` | 開發者確認推進統一沙盒測試驗收，`gdrive-support` (33/33) 與 `vscode-support` (12/12) 100% 通過並同步 `@build` |
