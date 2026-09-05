# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `adapt_build_pip_dependencies` 掃描 build zip 與 manifest 正確提取相依性規格 | FR-01 | `test_adapt_build_pip_dependencies` |
| **FT-02** | 單元測試 | 驗證 `create_sandbox` 成功建立微環境跨平台投影至沙盒 `engine/.venv` | FR-02 | `test_sandbox_venv_projection` |
| **FT-03** | 整合測試 | 驗證沙盒環境原生感知並能導入微環境安裝之第三方套件 | FR-02 | `test_sandbox_import_from_projected_venv` |
| **ET-01** | 邊界測試 | 驗證微環境投影在不支援 Junction/Symlink 時自動平滑降級為 `.pth` 指標 | FR-03 | `test_sandbox_venv_pth_fallback` |
| **ET-02** | 邊界測試 | 驗證 `cleanup_sandbox` 銷毀沙盒時安全斷開連結，宿主微環境零損毀 | FR-04 | `test_cleanup_sandbox_protects_host_venv` |
| **FT-04** | 單元測試 | 驗證 `Checker` 對合法與非法 `pip_dependencies` 宣告之合規檢核行為 | FR-05 | `test_checker_pip_dependencies_validation` |
| **RT-01** | 回歸測試 | 驗證 dev 模組自動化測試全套 100% 通過 | NFR-02 | `python yscb.py dev test dev --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證 `adapt_build_pip_dependencies` 正確提取規格並順序去重 | 2026-09-05 13:21 |
| **FT-02** | `Passed` | 驗證 Windows Junction 成功投影微環境至沙盒 `engine/.venv` | 2026-09-05 13:21 |
| **FT-03** | `Passed` | 驗證沙盒能感知並讀取投影微環境內之模組檔案 | 2026-09-05 13:21 |
| **ET-01** | `Passed` | 驗證當連結引發 OSError 時自動降級為 `.pth` 檔案指標 | 2026-09-05 13:21 |
| **ET-02** | `Passed` | 驗證 `cleanup_sandbox` 安全斷開重析點，宿主微環境檔案完好 | 2026-09-05 13:21 |
| **FT-04** | `Passed` | 驗證 Checker 正確檢驗 dict 結構與鍵值型態 | 2026-09-05 13:21 |
| **RT-01** | `Passed` | `dev test dev --quiet` 72/72 全數 100% 通過 | 2026-09-05 13:25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 本次變更為 dev 工具鏈沙盒與靜態檢查機制，無終端 UI/UX 互動 | `[跳過/免測]` | 純工具鏈架構升級免測 |
