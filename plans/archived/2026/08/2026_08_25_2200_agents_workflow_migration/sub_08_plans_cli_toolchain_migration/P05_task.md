# 實作任務清單 (Task Breakdown)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Completed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (基礎型別與套件進入點)**：建立 `source/agents-workflow/agents_workflow/plans/__init__.py`，定義自定義例外與套件導出。
- [x] **TASK-02 (狀態矩陣掃描引擎)**：實作 `agents_workflow/plans/scanner.py` (`PlanScanner`)，解析 4 大 Track 與 Phase 狀態並渲染 ASCII 矩陣。
- [x] **TASK-03 (計畫安全歸檔引擎)**：實作 `agents_workflow/plans/archiver.py` (`PlanArchiver`)，實施 4 重安全檢查、清理 `handoff.md` 與時間戳目錄搬移。
- [x] **TASK-04 (歷史檢索與規範稽核引擎)**：實作 `agents_workflow/plans/searcher.py` (`PlanSearcher`) 與 `verifier.py` (`PlanVerifier`)。
- [x] **TASK-05 (CLI 路由派發與別名整合)**：重構 `source/agents-workflow/scripts/cli.py`，新增 `cmd_plan` 與 `plan-archive`, `plan-status`, `plan-search`, `plan-verify` 別名支援。
- [x] **TASK-06 (專用測試套件與驗證)**：編寫 `test/test_agents_workflow_plans_toolchain.py` 與 `source/agents-workflow/tests/test_plans_toolchain.py`，覆蓋 FT-01~04 與 ET-01~06 (11 個測試)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 尚無偏差 | - |
