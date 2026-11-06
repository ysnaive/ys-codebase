# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_08_core 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Passed  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `events`、`uri` 重入與 VFS 連動失效、`config` 深拷貝、`symbols` 異常清理與 `dispatcher` 對稱事件 | FR-01, EC-01 | `TestEventsPipeline`, `TestURI`, `TestConfig`, `TestSymbols`, `TestContributesCmd`, `TestCoreCommands` |
| **FT-02** | 單元測試 | 驗證 `contributes`、`validator` `dict[K, V]`、`engine` 自癒回退、`installer` 回滾鎖、`locale` 深拷貝與 `PipManager` 可重入鎖 | FR-02, EC-03 | `TestContributes`, `TestValidator`, `TestEngine`, `TestInstaller`, `TestLocale`, `TestVenvCore`, `TestDistributionLifecycle`, `TestRemoteZipBootstrap` |
| **FT-03** | 單元測試 | 驗證 `platform` 進程/檔案鎖、`semver` 非字串防禦与 LRU 快取、CLI 路由、`1.2.7.x.py` 遷移與 `VFS` 全路徑 | FR-03, FR-04, EC-02, NFR-01, NFR-02 | `TestPlatform`, `TestSemver`, `TestCLIRouter`, `TestUpdateChecker`, `TestMigrationLadder`, `TestVFS`, `TestGitignore`, `TestGuard` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Ran 257 tests in 28.22s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-02** | `Passed` | `Ran 257 tests in 28.22s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-03** | `Passed` | `Ran 257 tests in 28.22s — OK (0 ResourceWarning)` | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 驗證 `core` 全量單元測試（`257 / 257` 通過、`0 ResourceWarning`）、`Checker().check_module("core")`（`0 FAIL, 0 WARN`）與五步盲測閉環融斷結果 | `[測試通過]` | 經 Blind Subagents D / E 與 Review Gate 驗證通過 |
