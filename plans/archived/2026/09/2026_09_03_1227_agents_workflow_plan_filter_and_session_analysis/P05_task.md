# 實作任務清單 (Task Breakdown)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`core` 模組清理 — 修改 `source/core/contributes/agents-workflow.json` 移除 `RETRO_CHECK_ITEMS`，刪除 `source/core/assets/retro_check.md`。
- [x] **TASK-02**：`knowledge-db` 模組對齊 — 更新 `source/knowledge-db/contributes/agents-workflow.json` 注入錨點為 `SESSION_ANALYSIS_CHECK_ITEMS`，新增 `source/knowledge-db/assets/session_analysis_check.md`，刪除舊 `retro_check.md`。
- [x] **TASK-03**：`agents-workflow` Plans 工具鏈正則收斂 — 修改 `verifier.py`, `scanner.py`, `searcher.py` 排除非時間戳目錄。
- [x] **TASK-04**：`agents-workflow` 工作流與 Token 宣告 — 新增 `SessionAnalysis.md`，刪除 `Retro.md`，更新 `contributes/agents-workflow.json`。
- [x] **TASK-05**：單元測試編寫與回歸 — 修改 `test_plans_toolchain.py` 增加非時間戳略過測試；新增 `test_session_analysis_workflow.py` 專屬套件。
- [x] **TASK-06**：本地編譯、打包、安裝與全生態系端到端回歸驗證。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
