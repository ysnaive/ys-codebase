# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`sub_02_dev_module_readme`  
> 建立日期：2026-08-29  
> 所屬主計畫：`user_guidance_and_module_readme_enhancement`  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  站在**純用戶與模組 Release 消費者視角**（在專案環境中執行 `python yscb.py install dev` 獲得開發者工具箱的開發者），於模組源碼目錄撰寫 100% 自包含 (Self-Contained) 的 `dev` 模組導引手冊 [`source/dev/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/README.md)。
  涵蓋：
  1. **模組角色與職責定位**：官方模組開發工具箱、標準腳手架、合規檢查、打包、沙盒測試守門與安全發布流水線。
  2. **模組開發雙軌流水線概念 (Dual-Track Pipeline)**：
     - **軌道 A (日常開發與本地自引用調試)**：`create` ➔ 編輯 `source/` ➔ `check` / `build` ➔ `test` ➔ `install <mod>@build --force`。
     - **軌道 B (版本晉升與正式發布交付)**：`bump-[rev|patch|minor|major]` ➔ `test` ➔ `release` ➔ `install <mod> --force`。
  3. **純用戶全量 CLI 指令集與語法範例**：
     - 腳手架建立：`dev create <name> [--desc="..."]`
     - 合規靜態檢查：`dev check [name | --all]`
     - 開發打包構建：`dev build [name | --all]`
     - 語意版本遞增：`dev bump-[major|minor|patch|revision] <name>`
     - 隔離沙盒測試：`dev test [name | --all] [--no-build] [-j <N>] [--sequential]`
     - 3-Gate 純淨發布：`dev release [name | --all] [--force]`
     - 安全本地 Git 發布：`dev release-git <name> "<msg>"`
     - 原地與沙盒底層工具：`dev op-test`, `dev op-mksb`
  4. **自包含單元測試編寫指南 (Testing Guide Quickstart)**：
     - 繼承 `dev.testing.YSCBTestCase` 或 `unittest.TestCase`
     - 測試發現慣例 (`tests/test_*.py`) 與斷言方法
  5. **常見開發者操作 Cookbook**：
     - 建立全新擴充模組
     - 日常本地調試熱安裝 (`@build`)
     - 正式發布與環境更新
- **影響範圍**：
  - 新增：[`source/dev/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/README.md)（隨模組發布打包分發給所有下游用戶）
- **Fast Track 4 維度確認**：
  - [x] 修改行數預估 $\le 100$ 行 (文檔型任務)
  - [x] Public API 契約 0 變更
  - [x] 架構自包含、零外部 `docs/` 依賴
  - [x] 既有測試/CLI 可 100% 驗證指令正確性

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：撰寫並交付 100% 自包含的 [`source/dev/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/README.md)。
- **測試案例**：
  - `FT-01`：驗證文檔內所有示範之 `python yscb.py dev` CLI 指令均能在真實環境中無誤解析與執行。
  - `FT-02`：以 `dev test dev` 驗證模組測試 100% 通過且無回歸。
  - `FT-03`：驗證 `source/dev/README.md` 完全自包含，無指向外部 `docs/` 的斷鏈。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於 `source/dev/README.md` 產出完整自包含說明文檔，包含五大引擎架構圖、雙軌閉環流水線、全量 CLI 指令速查矩陣、`YSCBTestCase` 單元測試撰寫範例及兩大開發情境 Cookbook。
- **實機測試日誌**：
  - `dev test dev`：50/50 測試全數通過（3 契約測試 + 47 自訂單元測試，耗時 6.57s）。
  - `dev check dev`：合規靜態檢查 100% Passed。
  - CLI 指令驗證（`dev create`, `dev check`, `dev build`, `dev test`, `dev release` 等）：語法與 help 輸出 100% 正常。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_2035_user_guidance_and_module_readme_enhancement/sub_02_dev_module_readme` 驗證 100% Passed。
- **結案狀態**：`Completed`
