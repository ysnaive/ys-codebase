# 實作任務清單 (Task Breakdown)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [ ] **TASK-01**：在 `source/core/core/uri.py` 實作 `set_yscb_root`、`get_yscb_root`、`yscb_scope` 並重構 `_get_yscb_root`。
- [ ] **TASK-02**：在 `source/core/core/config.py` 重構 `ConfigManager._get_yscb_root`，徹底刪除 `while` 迴圈與 `os.getcwd()`。
- [ ] **TASK-03**：在 `source/dev/dev/testing/sandbox.py` 更新 `_dispatch_test_hooks`，雙重包覆 `host_scope` 與 `yscb_scope`。
- [ ] **TASK-04**：在 `source/agents-workflow/agents_workflow/plans/searcher.py` 收斂 `archive_plans` 預設路徑為 `plans/archived`。
- [ ] **TASK-05**：在 `source/core/tests/test_uri.py` 編寫新單元測試驗證注入與作用域生命週期。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

