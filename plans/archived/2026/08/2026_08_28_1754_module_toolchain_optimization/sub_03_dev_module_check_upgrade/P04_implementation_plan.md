# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 實作任務拓撲與依賴拆解 (Task Breakdown)

| 任務編號 | 任務名稱 | 核心實作內容 | 依賴前置 | 預計產出檔案 |
| :--- | :--- | :--- | :---: | :--- |
| **TASK-01** | **核心檢查器升級** | 於 `source/dev/dev/checker.py` 實作 `CheckIssue`, `CheckReport` 與 5 步流水線檢核 | 無 | `dev/checker.py` |
| **TASK-02** | **發布守門阻斷整合** | 升級 `source/dev/dev/releaser.py` 在 `dev release` 整合 `check_module` 剛性守門阻斷 | TASK-01 | `dev/releaser.py` |
| **TASK-03** | **CLI 格式化與診斷輸出** | 升級 `source/dev/scripts/cli.py` 支援三級嚴重度彩色終端排版與 `--json` | TASK-01 | `dev/scripts/cli.py` |
| **TASK-04** | **單元測試與沙盒回歸** | 建立 `source/dev/tests/test_checker.py` 覆蓋 5 步檢核維度，執行全生態系回歸驗證 | ALL | `dev/tests/test_checker.py` |

---

## 2. 交叉驗證檢查表 (Cross Validation)

- [x] **P01 需求覆蓋**：FR-01~07 全數映射至 TASK-01~04 與 P06 測試案例。
- [x] **P02 架構吻合**：5 步檢核流水線、反模式靶向過濾、Release 阻斷與 Build 容錯完全落實。
- [x] **P03 介面吻合**：公開 API 簽名與資料結構 100% 保持一致。
- [x] **P06 測試前置**：FT-01~07、ET-01~02 與 RT-01 案例全數對齊。

---

## 3. 架構靈魂拷問 (Architecture Soul-Searching)

### 拷問 1：如果 `dev check` 出現 `[FAIL]`，為什麼 `dev build` 可以放行但 `dev release` 必須阻斷？
- **防護機制**：
  `dev build` 是本機開發者進行熱重載、單元跑測與除錯調試的日常手段；若因規範瑕疵在開發途中就阻斷 build，會讓開發者無法在沙盒中驗證修復程式碼。而 `dev release` 則是產生供外部環境或下游消費端安裝的正式版本，必須 100% 遵守架構與合規規範。因此「開放 Build 除錯、剛性守門 Release 發布」是兼顧開發敏捷度與產物質量的最佳架構平衡。

### 拷問 2：如何避免反模式檢測（Direct Config / Direct Contributes Probing）產生誤報？
- **防護機制**：
  採用「精確系統保留字串常數靶向檢測」，模組使用 `open("my_file.txt")` 或 `json.load()` 操作自身檔案完全放行；僅在非 `core` 模組的業務源碼中檢測到 `"config.project.json"` 或 `"contributes.merged.json"` 等保留特徵時觸發，且測試檔案（`tests/`）獲得完全豁免，達成 0 誤報。
