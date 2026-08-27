# 實作任務清單 (Task Breakdown)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `dev.tester` 與 `dev.testing.runner` 導入 `safe_print` / `SafeStreamWriter`，強化 `subprocess.run` 之標準輸出解碼與終端打印編碼防禦。
- [x] **TASK-02**：在 `dev.testing.case.YSCBTestCase` 新增 `create_mock_source_module` 輔助方法，並為 `run_cli` 注入 `encoding="utf-8"`, `errors="replace"`。
- [x] **TASK-03**：重構 `tests/test_builder.py`，全面改用 Mock Module 驗證 `build_module`、`package_release`、`revision_purge` 與 `index.json` 更新。
- [x] **TASK-04**：重構 `tests/test_release_pipeline.py`，全面改用 Mock Module 驗證發布管道與 release-check 閘門。
- [x] **TASK-05**：重構 `tests/test_tester.py` 中之 `test_run_test_all_success_cleans_sandboxes`，使用 Mock 隔離多進程跑測並新增 `safe_print` 單元測試。
- [x] **TASK-06**：在 `tests/test_sandbox.py` 將 `test_dev_test_high_level_orchestration` 與 `test_single_module_worker_execution_and_report_json` 標記為 `Requirement.WORKFLOW`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (100% 依 P04 拓撲實作) | - |
