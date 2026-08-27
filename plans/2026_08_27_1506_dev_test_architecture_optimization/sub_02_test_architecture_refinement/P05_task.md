# 實作任務清單 (Task Breakdown)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Core URI JIT 防護)**：在 `source/core/core/uri.py` 中更新 `reconcile_undefined_uri`，增加 `YSCB_TEST_SANDBOX` 感應；並在 `source/core/tests/test_uri.py` 新增單元測試。
- [x] **TASK-02 (Dev Requirement 列舉擴充)**：在 `source/dev/dev/testing/requirement.py` 新增 `Requirement.ISOLATED_SANDBOX` 列舉值。
- [x] **TASK-03 (Dev TestCase 智慧沙盒分流)**：在 `source/dev/dev/testing/case.py` 實作 Class-level 共用沙盒與 Per-Method 專屬沙盒分流機制、`tearDownClass` 清理、`YSCB_TEST_SANDBOX` 自動注入與 `run_cli` 透傳。
- [x] **TASK-04 (Dev Runner & Tester 環境感應)**：在 `source/dev/dev/testing/runner.py` 與 `source/dev/dev/tester.py` 中設置 `YSCB_TEST_SANDBOX`。
- [x] **TASK-05 (Dev 整合單元測試撰寫)**：在 `source/dev/tests/test_case.py` 撰寫完整驗證案例（共用沙盒、獨立沙盒、混合執行、環境透傳）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (100% 依 P04 規劃落地) | - |
