# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `from core import PipManager, PipInstallError` 導出成功且指向正確型態 | FR-01 | `test_pip_manager_sdk_export` |
| **FT-02** | 單元測試 | 驗證 `parse_pip_dependencies` 正確解析字典格式相依規格 | FR-02 | `test_parse_pip_dependencies_dict` |
| **FT-03** | 單元測試 | 驗證 `parse_pip_dependencies` 正確解析清單格式並進行順序去重 | FR-02 | `test_parse_pip_dependencies_list_and_dedup` |
| **ET-01** | 邊界測試 | 驗證 `parse_pip_dependencies` 面對 None、空字典或非法型態安全返回 `[]` | EC-01 | `test_parse_pip_dependencies_edge_cases` |
| **ET-02** | 邊界測試 | 驗證 `parse_pip_dependencies` 面對包含空白字串或不規範空格之防禦行為 | EC-02 | `test_parse_pip_dependencies_whitespace_defense` |
| **FT-04** | 單元測試 | 驗證 `PipManager` 自定義根目錄之路徑探測方法運作正常 | FR-04 | `test_pip_manager_custom_root_paths` |
| **RT-01** | 回歸測試 | 驗證全模組自動化測試無破壞性回歸 | NFR-02 | `python yscb.py dev test core --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 成功自 core 頂層匯入 PipManager, PipInstallError | 2026-09-05 13:07 |
| **FT-02** | `Passed` | 字典相依規格包含空約束/版本約束皆正確解析 | 2026-09-05 13:07 |
| **FT-03** | `Passed` | 清單相依規格正確過濾且維持原始順序去重 | 2026-09-05 13:07 |
| **ET-01** | `Passed` | None、非字典非清單或無效字串均安全回傳空清單 | 2026-09-05 13:07 |
| **ET-02** | `Passed` | 首尾空白字串自動清理且空白鍵值正確過濾 | 2026-09-05 13:07 |
| **FT-04** | `Passed` | 自定義根目錄之直譯器、site-packages 路徑解析正確 | 2026-09-05 13:07 |
| **RT-01** | `Passed` | `dev test core --quiet` 123/123 (100%) 全部通過 | 2026-09-05 13:07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 本次變更為底層 SDK 介面導出與函式重構，無終端 UI/UX 互動 | `[跳過/免測]` | 純代碼 SDK 變更免測 |
