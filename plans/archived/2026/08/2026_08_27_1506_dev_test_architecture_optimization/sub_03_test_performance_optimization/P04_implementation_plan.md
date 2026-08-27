# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 實作前定稿檢核清單 (Review Checklist)

- [x] **追溯性檢核**：需求 `FR-01 ~ FR-06` 均有對應架構設計（P02）、API 簽名（P03）與測試項目（P06）。
- [x] **零臆測檢核**：四層測試分類、預設過濾原則、`--target` 語法與三道守門鎖皆經開發者明確指示定稿。
- [x] **範疇保護檢核**：變更範圍嚴格收斂於 `dev` 測試工具鏈與全庫測試檔案標準化遷移，不破壞外部 Public 執行契約。
- [x] **測試前置檢核**：`P06_test_plan.md` 已隨 P02 同步初始化完成，將於本階段正式定稿 (Confirmed)。

---

## 2. 靈魂拷問深度評估 (Soul-Searching Q&A)

1. **問：四層分類後，日常開發執行 `dev test <module>` 會不會漏測？**  
   **答**：不會。日常核心驗證依賴 `LOGIC`（單元邏輯）與 `ENV`（跨模組/依賴注入），兩者皆納入預設跑測清單；而 `WORKFLOW`（高階 E2E 如 release-git）與 `PERF`（壓力測試）在需要時只要帶上 `--workflow` 或 `--all-types` 即可一鍵完整跑測。
2. **問：非標準入口阻斷會不會影響開發者本機調試？**  
   **答**：不會。標準調試途徑為 `python yscb.py dev test <mod> -k <pattern>` 或 `--target=<mod>:<test>`。阻斷機制能有效避免開發者誤用 `python -m unittest` 意外破壞真實專案的 `release/` 與 `config/`。

---

## 3. 實作任務拆解 (Task Breakdown)

- **TASK-01 (Requirement 列舉重構與標籤正交化)**：
  - 在 `source/dev/dev/testing/requirement.py` 實作 `Requirement(Flag)`（`LOGIC`, `ENV`, `WORKFLOW`, `PERF`, `ISOLATED_SANDBOX`）。
- **TASK-02 (三道防呆守門鎖體系落地)**：
  - 在 `source/dev/dev/testing/case.py` 實作 `SecurityError` 與宿主裸跑阻斷。
  - 在 `source/dev/dev/testing/runner.py` 實作 `TestDiscovery` `isinstance(test, YSCBTestCase)` 動態守門。
  - 在 `source/dev/dev/checker.py` 實作 `Checker` AST 靜態合規守門。
- **TASK-03 (過濾與目標定位引擎重構)**：
  - 在 `source/dev/dev/testing/runner.py` 實作 `filter_suite` 多類別與 `--target` 目標過濾。
  - 在 `source/dev/dev/tester.py` 解析 CLI 旗標（`--target`, `--logical`, `--env`, `--workflow`, `--perf`, `--all-types`）。
- **TASK-04 (根除遞迴跑測與單元測試優化)**：
  - 重構 `source/dev/tests/test_release_pipeline.py`，消除 `test_release_git` 內部重複跑測。
- **TASK-05 (全專案 16 個測試檔案 100% 遷移至 `YSCBTestCase`)**：
  - 將 `agents-workflow`（5 檔）、`dev/test_release_pipeline.py`、`core`（6 檔）全面遷移至 `YSCBTestCase` 並標記 `@require`。
- **TASK-06 (Dev 整合單元測試與守門驗證)**：
  - 於 `source/dev/tests/test_case.py`、`test_checker.py` 與 `test_sandbox.py` 撰寫完整驗收測試。
