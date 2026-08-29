# 實作任務清單 (Task Breakdown)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `source/agents-workflow/agents_workflow/compiler.py`，升級 `resolve_stage2_uri` 實作 Standalone 佔位符完全替代與反引號剝除。
- [x] **TASK-02**：批次校正 `source/agents-workflow/assets/` 下的工作流與標準資產（`ContextInit.md` 等），切換 Agent 讀檔動線為 `__${...}__` 並修正非標準協議前綴（`plans://`, `archive://`）。
- [x] **TASK-03**：在 `source/agents-workflow/tests/test_compiler.py` 新增單元測試用例，覆蓋 Stage 2 二分法解析。
- [x] **TASK-04**：執行全生態系構建與測試（`dev test --all` 全數 209/209 Passed）。
- [x] **TASK-05**：執行 Dogfooding 同步部署至消費空間（`install` + `--ide-antigravity`），並驗證物化產物。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
