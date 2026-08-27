# 實作任務清單 (Task Breakdown)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Requirement 列舉重構與標籤正交化)**：在 `source/dev/dev/testing/requirement.py` 實作 `Requirement(Flag)`（`LOGIC`, `ENV`, `WORKFLOW`, `PERF`, `ISOLATED_SANDBOX`）。
- [x] **TASK-02 (三道防呆守門鎖體系落地)**：
  - 在 `source/dev/dev/testing/case.py` 實作 `SecurityError` 與宿主裸跑阻斷。
  - 在 `source/dev/dev/testing/runner.py` 實作 `TestDiscovery` `isinstance(test, YSCBTestCase)` 動態守門。
  - 在 `source/dev/dev/checker.py` 實作 `Checker` AST 靜態合規守門。
- [x] **TASK-03 (過濾與目標定位引擎重構)**：
  - 在 `source/dev/dev/testing/runner.py` 實作 `filter_suite` 多類別與 `--target` 目標過濾。
  - 在 `source/dev/dev/tester.py` 解析 CLI 旗標（`--target`, `--logical`, `--env`, `--workflow`, `--perf`, `--all-types`）。
- [x] **TASK-04 (根除遞迴跑測與單元測試優化)**：
  - 重構 `source/dev/tests/test_release_pipeline.py`，消除 `test_release_git` 內部重複跑測。
- [x] **TASK-05 (全專案 16 個測試檔案 100% 遷移至 `YSCBTestCase`)**：
  - 將 `agents-workflow`（5 檔）、`dev/test_release_pipeline.py`、`core`（6 檔）全面遷移至 `YSCBTestCase` 並標記 `@require`。
- [x] **TASK-06 (Dev 整合單元測試與守門驗證)**：
  - 於 `source/dev/tests/test_case.py`、`test_checker.py` 與 `test_sandbox.py` 撰寫完整驗收測試。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無任何負面偏差，所有功能完全依 P01/P02/P03 設計落實 | 正常交付 |
