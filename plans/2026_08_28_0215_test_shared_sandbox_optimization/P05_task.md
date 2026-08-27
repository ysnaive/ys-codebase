# 實作任務清單 (Task Breakdown)

> 功能名稱：測試框架 Session 層級共用沙盒與效能優化 (Test Session-Level Shared Sandbox Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/dev/dev/testing/case.py` 實作 `_shared_sandbox_ctx` 與 `cleanup_shared_sandbox()`，調整 `setUp`/`tearDown` 生命週期。
- [x] **TASK-02**：在 `source/dev/dev/testing/runner.py` 之 `TestRunner.run_suite()` 整合 `finally: YSCBTestCase.cleanup_shared_sandbox()`。
- [x] **TASK-03**：全面盤點寫入型測試，於 `source/core/tests/`、`source/dev/tests/`、`source/agents-workflow/tests/` 標註 `@require(Requirement.ISOLATED_SANDBOX)`。
- [x] **TASK-04**：更新 `source/dev/tests/test_case.py` 單元測試驗證 Session 共用與獨立沙盒行為。
- [x] **TASK-05**：執行全庫回歸跑測與效能指標量測。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依 P04 與拓撲順序實作完成 |
