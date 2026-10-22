# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_get_source_file_sha1` 對包含 `\r\n` 與 `\n` 之檔案計算出完全相同的 SHA-1 雜湊值 | FR-01 | `pytest ys_codebase/source/agents-workflow/tests/test_publisher_cross_platform.py -k test_sha1_crlf_normalization` |
| **FT-02** | 單元測試 | 驗證 `ReleasePublisher` 使用 `cache://` 儲存 project 軌 manifest，並在執行時自動遷移並物理刪除舊版 `storage://` manifest 檔案與空目錄 | FR-02, EC-02 | `pytest ys_codebase/source/agents-workflow/tests/test_publisher_cross_platform.py -k test_manifest_cache_isolation_and_migration` |
| **FT-03** | 單元測試 | 驗證 `PipManager.get_cross_platform_site_packages_dirs` 回傳包含 POSIX (`lib/pythonX.Y/site-packages`) 與 Windows (`Lib/site-packages`) 之雙平台路徑 | FR-03 | `pytest ys_codebase/source/core/tests/test_ide_projector_cross_platform.py -k test_get_cross_platform_site_packages_dirs` |
| **FT-04** | 單元測試 | 驗證 `IdeProjector.sync_vscode_settings` 注入雙平台 `extraPaths`，陣列順序恆定且能正確回滾 | FR-03 | `pytest ys_codebase/source/core/tests/test_ide_projector_cross_platform.py -k test_sync_vscode_settings_dual_extra_paths` |
| **FT-05** | 單元測試 | 驗證 `IdeProjector.sync_vscode_settings` 停止寫入 `python.defaultInterpreterPath`，且自動清理既有 `_yscb_managed` 託管之舊值 | FR-04 | `pytest ys_codebase/source/core/tests/test_ide_projector_cross_platform.py -k test_sync_vscode_settings_removes_managed_interpreter` |
| **FT-06** | 單元測試 | 驗證使用者自訂之 `python.defaultInterpreterPath` 不會被 `sync_vscode_settings` 或 `revert_vscode_settings` 誤刪 | EC-03 | `pytest ys_codebase/source/core/tests/test_ide_projector_cross_platform.py -k test_sync_vscode_settings_preserves_user_custom_interpreter` |
| **FT-07** | 單元測試 | 驗證當 `.vscode/settings.json` 內容無異動時，`sync_vscode_settings` 跳過寫盤（Zero-Touch），不更新 `mtime` | EC-04 | `pytest ys_codebase/source/core/tests/test_ide_projector_cross_platform.py -k test_sync_vscode_settings_zero_touch` |
| **ET-01** | 單元測試 | 驗證 `_get_source_file_sha1` 遇到目錄中二進位檔案時退回 raw bytes 雜湊，不崩潰拋出 `UnicodeDecodeError` | EC-01 | `pytest ys_codebase/source/agents-workflow/tests/test_publisher_cross_platform.py -k test_binary_file_sha1_fallback` |
| **ET-02** | 單元測試 | 驗證完整發布（含短路路徑）後 Git 追蹤區 `storage://agents-workflow/release_manifest.json` 不存在，清單僅存於 `cache://` | FR-02 | `python yscb.py dev test --target=agents-workflow:TestPublisherCrossPlatform.test_release_never_writes_tracked_storage` |
| **RT-01** | 回歸測試 | 驗證 `core` 與 `agents-workflow` 模組全量既有測試通過，無功能退化 | NFR-02 | `python yscb.py dev test core -q` 與 `python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證 CRLF 與 LF 文字目錄及單檔案 SHA-1 完全一致 (40 位元雜湊等價) | 2026-10-22 09:53 |
| **FT-02** | `Passed` | 驗證 project manifest 寫入 `cache://` 且舊版 `storage://` 自動遷移並清理舊檔 | 2026-10-22 09:53 |
| **FT-03** | `Passed` | 驗證回傳 POSIX 與 Windows 雙候選路徑集合，順序恆定 | 2026-10-22 09:52 |
| **FT-04** | `Passed` | 驗證雙平台 `extraPaths` 同時注入且順序固定，無 `defaultInterpreterPath` | 2026-10-22 09:52 |
| **FT-05** | `Passed` | 驗證清理既有 YSCB 託管之直譯器路徑，`_yscb_managed` 亦同步清理 | 2026-10-22 09:52 |
| **FT-06** | `Passed` | 驗證使用者自訂直譯器路徑 100% 完整保留未被異動 | 2026-10-22 09:52 |
| **FT-07** | `Passed` | 驗證內容相同時 `mtime_ns` 未變動，成功觸發 Zero-Touch 略過寫盤 | 2026-10-22 09:52 |
| **ET-01** | `Passed` | 驗證二進位非 UTF-8 檔案安全降級至 raw bytes，無 UnicodeDecodeError | 2026-10-22 09:53 |
| **ET-02** | `Passed` | 完整發布與短路發布後舊 `storage://` 清單皆不存在，僅 `cache://` 清單存在 | 2026-10-22 10:10 |
| **FT-05b/06b** | `Passed` | 反向複查補測：他平台寫入之 YSCB 直譯器被清理；使用者專案 `.venv` 直譯器於 sync/revert 皆保留 | 2026-10-22 10:03 |
| **RT-01** | `Passed` | `agents-workflow` 108/108（含補齊前計畫遺失資產之 `FT-07`）、`core` 202/202；`test_ft_05` 過時斷言已依開發者指示修正 | 2026-10-22 10:23 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 跨平台執行或模擬執行 `python yscb.py` 指令後，檢驗 `git status` 工作區無意外 dirty 檔案（`.vscode/settings.json` 與 `release_manifest.json` 無未預期變更） | `[跳過/免測]` | 2026-10-22 開發者指示：目前無跨平台實機環境，先標記免測 |
