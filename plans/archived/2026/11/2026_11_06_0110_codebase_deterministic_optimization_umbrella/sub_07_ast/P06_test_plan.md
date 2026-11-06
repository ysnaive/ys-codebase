# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_07_ast 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Passed  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `GrammarProvisioner` 鎖與警告、`ASTEngine` 執行緒安全、Lazy Graph Loading 與損毀圖譜自癒 | FR-01, FR-02, EC-01, NFR-02 | `TestProvisionerAndJIT`, `TestASTEngine` |
| **FT-02** | 單元測試 | 驗證重載符號 `parent_id` 同步、泛型逗號簽名、0 參數重載消歧與 `super().method()` 解析 | FR-03 | `TestOverloadAndTopology` |
| **FT-03** | 單元測試 | 驗證 Markdown 代碼塊隔離、CSS/HTML 行內註解、C++ `ClassName<T>::method`、`impact` 模式與 CLI/Hook/遷移腳本 | FR-04, EC-02, NFR-01 | `TestDialectsAndParsers`, `TestPartialAndOutline` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Ran 33 tests in 0.22s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-02** | `Passed` | `Ran 33 tests in 0.22s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-03** | `Passed` | `Ran 33 tests in 0.22s — OK (0 ResourceWarning)` | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 驗證 `ast` 全量單元測試（`33 / 33` 通過、`0 ResourceWarning`）、`Checker().check_module("ast")`（`0 FAIL, 0 WARN`）與五步盲測閉環融斷結果 | `[測試通過]` | 經 Blind Subagents D / E 與 Review Gate 驗證通過 |
