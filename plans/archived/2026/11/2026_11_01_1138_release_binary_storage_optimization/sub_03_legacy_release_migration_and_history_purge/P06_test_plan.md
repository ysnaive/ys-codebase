# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：存量發布遷移、新版本發布與 Git 歷史徹底淨化 (sub_03)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **ET-01** | 邊界測試 | 當目標目錄因 `virtiofs` / 宿主機句柄鎖定導致 `os.replace` 拋出 `PermissionError(EACCES)` 時，三階段鑑別器通過寫入探針並完成檔案級原子同步與廢棄檔案清理 | EC-01 | `python yscb.py dev test core -q` |
| **ET-02** | 邊界測試 | 當目標目錄發生真實 I/O 或權限錯誤（如 `ENOSPC`）時，三階段鑑別器絕不吞錯，原樣拋出 `OSError` 且目標目錄保持原狀 | EC-02 | `python yscb.py dev test core -q` |
| **ET-03** | 邊界測試 | 在完全刪除本地 `ys_codebase/release/*/*.zip`、清空 `.mirror/` 與 `.build/` 的狀態下，`python yscb.py restore --force` 透過本地同版本 `source/<mod>` 100% 自給自足還原全部 5 大模組 | EC-03 | `python yscb.py restore --force` |
| **FT-04** | 整合測試 | 5 份 `ys_codebase/release/<mod>/index.json` 完整包含全部歷史與新發布版本之 `status`、`dependencies`、`type`、`urgency`、`summary` 且通過 `dev check` | FR-01 | `python yscb.py dev check` |
| **FT-05** | 單元測試 | `core@1.2.1.0` 與 `dev@1.1.3.0` 完成正式打包發布與安裝，`core` (214/214) 與 `dev` (82/82) 測試套件 100% 通過 | FR-02 | `python yscb.py dev test core -q && python yscb.py dev test dev -q` |
| **FT-06** | 整合測試 | 外部備份（36 個 Active `.zip` + 5 份 `index.json` + 2,015 個專案檔）通過 SHA256 與 Zip CRC 校驗，且 `git filter-repo` 歷史淨化與 `releases` 孤兒分支建立成功 | FR-03 | SHA256 校驗腳本 & `git status` / `git branch -a` |
| **RT-07** | 回歸測試 | 歷史淨化後 `.git/objects/pack` 體積顯著縮減，且 `main` 分支歷史中 `.zip` 數量為 `0` | NFR-01 | `du -sh .git/objects/pack` |
| **RT-08** | 回歸測試 | 備份與 `releases` 分支內全部 36 個 Active `.zip` 通過 `zipfile.testzip()` 檢查 | NFR-02 | `python3` CRC 檢查腳本 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **ET-01** | `Passed` | `TestCoreEngine.test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback` 驗證 `EACCES` 寫入探針與檔案級同步 | 2026-11-01 |
| **ET-02** | `Passed` | `TestCoreEngine.test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback` 驗證 `ENOSPC` 原樣拋出不吞錯 | 2026-11-01 |
| **ET-03** | `Passed` | 刪除全部 `.zip`、`.mirror/`、`.build/` 後執行 `restore --force`，5/5 模組 `HEALTHY (100% Ready)` | 2026-11-01 |
| **FT-04** | `Passed` | `python yscb.py dev check` 5 Total, 5 Passed, 0 Warnings, 0 Failed | 2026-11-01 |
| **FT-05** | `Passed` | `core` 214/214 (100.0%) 與 `dev` 82/82 (100.0%) 全數通過 | 2026-11-01 |
| **FT-06** | `Passed` | 36 個 `.zip`、5 份 `index.json` 與 2,015 個工作區檔案 SHA256 100% 匹配 | 2026-11-01 |
| **RT-07** | `Passed` | `git filter-repo` 與 `git gc --prune=now --aggressive` 徹底清除歷史二進位 `.zip` | 2026-11-01 |
| **RT-08** | `Passed` | 36 個 Active `.zip` 100% 通過 `zipfile.testzip()` CRC 校驗 | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 開發者逐步確認 Step 1（38 個歷史版本元數據表）、Step 2（`core@1.2.1.0` / `dev@1.1.3.0` 升版與三階段目錄鎖定鑑別）、Step 3（全專案備份 SHA256 校驗與無 `.zip` 自給自足還原） | `[已確認]` | 開發者於互動模式逐步確認通過 |
