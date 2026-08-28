# 實作任務清單 (Task Breakdown)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：清空 `source/knowledge-db/configurable/contribute.json` 預設空間 (FR-01)
- [x] **TASK-02**：建立本專案 `config/knowledge-db/contribute.json` 宣告 `source` 空間 (FR-03)
- [x] **TASK-03**：更新 `source/agents-workflow/assets/standards/AgentsStandards.md` 補齊錨點，並於 `agents-workflow.json` 宣告 Token (FR-04)
- [x] **TASK-04**：建立 `source/agents-workflow/contributes/knowledge-db.json` 宣告 `docs` 空間 (FR-02)
- [x] **TASK-05**：於 `source/knowledge-db/assets/` 建立 4 個平鋪標準資產 (`KnowledgeAgentsStandards.md`, `phase00_guild.md`, `research_guild.md`, `phase07_guild.md`) (FR-05)
- [x] **TASK-06**：建立 `source/knowledge-db/contributes/agents-workflow.json` 宣告 `insert` 注入映射 (FR-06)
- [x] **TASK-07**：更新單元測試並執行全生態系沙盒回歸跑測 (FT-01 ~ FT-06, ET-01, RT-01)


---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (嚴格遵循 P01~P04 規劃執行) | - |
