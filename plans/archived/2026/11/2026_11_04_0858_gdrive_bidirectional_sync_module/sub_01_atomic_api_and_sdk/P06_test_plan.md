# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`module:gdrive-support` 模組骨架、組態映射與原子雲端操作 API/SDK (`sub_01_atomic_api_and_sdk`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證預設組態載入（`auto_sync: false`、`active_branch: "main"`）與 PEP 562 延遲匯出 | FR-01, NFR-01, NFR-02 | `TestGDriveAtomicApiAndConfig.test_ft_01_default_config_and_lazy_sdk_exports` |
| **FT-02** | 單元測試 | 驗證單根 `file-space` 相對路徑正規化（`abs_path.relative_to(project_root)`）與最長前綴雙向 `mapping` 轉換 | FR-02 | `TestGDriveAtomicApiAndConfig.test_ft_02_space_normalization_and_longest_prefix_mapping` |
| **FT-03** | 整合測試 | 驗證 `LocalSandboxTransport` 原檔案類型二進位上傳、原地 `in_place_file_id` 更新、Shortcut 目標解析下載與 `.trash/` 移除 | FR-03, NFR-02 | `TestGDriveAtomicApiAndConfig.test_ft_03_sandbox_transport_atomic_operations_and_shortcuts` |
| **FT-04** | 整合測試 | 驗證 CLI 原子指令（`mkdir`、`put`、`shortcut`、`ls --recursive`、`get`、`rm`）於本地沙盒完整閉環 | FR-04 | `TestGDriveAtomicApiAndConfig.test_ft_04_cli_atomic_commands_roundtrip` |
| **ET-01** | 邊界測試 | 驗證 `mapping.local` 超出 `file-space` `include` 根目錄邊界時拋出 `GDriveConfigError` | EC-01 | `TestGDriveAtomicApiAndConfig.test_et_01_mapping_outside_space_include_raises_config_error` |
| **ET-02** | 邊界測試 | 驗證雲端原生 Google Workspace 文件標記為 `SKIPPED_UNSUPPORTED_MIME` 且呼叫 `download_file` 拋出 `GDriveUnsupportedMimeError` | EC-02 | `TestGDriveAtomicApiAndConfig.test_et_02_unsupported_google_workspace_mime_skipped_and_blocked` |
| **ET-03** | 邊界測試 | 驗證懸空 Shortcut 標記 `dangling_shortcut=True` 並阻斷對資料夾建立 Shortcut | EC-03 | `TestGDriveAtomicApiAndConfig.test_et_03_dangling_shortcut_and_folder_shortcut_rejection` |
| **ET-04** | 邊界測試 | 驗證 `../` 路徑穿越攔截（`GDrivePathError`）與同目錄重複同名檔案自動選最新並將舊檔移入 `.trash/` | EC-04 | `TestGDriveAtomicApiAndConfig.test_et_04_path_traversal_and_duplicate_same_name_deduplication` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-04** | `Passed` | `python yscb.py dev check gdrive-support` (PASSED) & `python yscb.py dev test gdrive-support -q` (`Pass: 11(100.0%), Fail: 0, Skip: 0`) | 2026-11-04 09:59 |
| **ET-01 ~ ET-04** | `Passed` | 100% 基於 `LocalSandboxTransport` 與本地設定測試通過，零外部 Google Drive API test cases | 2026-11-04 09:59 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `sub_01_atomic_api_and_sdk` 之模組骨架、`config.py`、`transport.py` 與原子 CLI/SDK 沙盒測試成果 | `[跳過/免測]` | 開發者指示免測（將於 `sub_03` 統一執行非沙盒實機驗證） |

