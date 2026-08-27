# 實作任務清單 (Task Breakdown)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/dev/dev/testing/sandbox.py` 中實作 `prune_sandboxes` 與 `cleanup_all_sandboxes`，並於 `create_sandbox` 整合修剪呼叫。
- [x] **TASK-02**：在 `source/dev/dev/tester.py` 中更新 `_run_test`，於 `--all` 成功時呼叫 `cleanup_all_sandboxes`。
- [x] **TASK-03**：在 `source/dev/tests/test_sandbox.py` 與 `source/dev/tests/test_tester.py` 中編寫完整單元測試。
- [x] **TASK-04**：執行全量回歸驗證 `python yscb.py dev test dev` 並回填 P06 日誌。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-03** | Minor | 單元測試 `test_prune_sandboxes_limit` 與 `test_cleanup_all_sandboxes` 需在建立 mock 資料夾前先清空快取以確保測試獨立性。 | 於測試前置調用 `cleanup_all_sandboxes()` 隔離。 |
