# 實作任務清單 (Task Breakdown)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (基礎協議與 Contributes 定義)**：
  - 更新 `source/agents-workflow/contributes/core.json` 註冊 `workflow.roadmap` 協議與 `roadmap` CLI 指令元數據。
  - 更新 `source/agents-workflow/contributes/agents-workflow.json` 註冊新 export、token 與模板更名。
- [x] **TASK-02 (核心 SDK 與 CLI 工具實作)**：
  - 實作 `source/agents-workflow/agents_workflow/roadmap.py` (`RoadmapItem`, `RoadmapManager`)。
  - 實作 `source/agents-workflow/scripts/cli.py` (`cmd_roadmap` 子指令分發)。
- [x] **TASK-03 (模板資產重構與新增)**：
  - 建立 `source/agents-workflow/assets/templates/P00_discuss.md`。
  - 建立 `source/agents-workflow/assets/templates/roadmap.md`。
  - 更新 `source/agents-workflow/assets/templates/umbrella_overview.md`。
- [x] **TASK-04 (工作流導引與標準手冊演進)**：
  - 建立 `source/agents-workflow/assets/workflows/Roadmap.md`。
  - 更新 `source/agents-workflow/assets/workflows/NewPlan.md`。
  - 更新 `source/agents-workflow/assets/standards/DevelopmentStandards.md`。
  - 更新 `source/agents-workflow/assets/standards/AgentsStandards.md`。
- [x] **TASK-05 (測試套件更新與全量迴歸驗證)**：
  - 於 `source/agents-workflow/tests/test_roadmap.py` 新增 Roadmap CLI 與模板測試。
  - 實機執行全量迴歸測試 (209/209 100% Passed)。
  - 完成 Dogfooding Sync 與 host 環境部署 (`agents-workflow@1.0.2.5`)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
