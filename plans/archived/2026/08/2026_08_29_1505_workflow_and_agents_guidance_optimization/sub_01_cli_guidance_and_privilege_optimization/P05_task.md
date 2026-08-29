# 實作任務清單 (Task Breakdown)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Core Schema & Providers 實作)**：修訂 `source/core/contributes.format.md` 與 `source/core/core/providers.py`，完成三級權限手冊渲染與 `get_phase_cli_guild`。
- [x] **TASK-02 (Core 單元測試完善)**：修訂 `source/core/tests/test_cli_guild.py`，覆蓋 FT-01、FT-02、ET-01、ET-02。
- [x] **TASK-03 (全模組 Contributes 宣告更新)**：更新 `core`, `dev`, `knowledge-db`, `agents-workflow` 之 `contributes/core.json`，全面補齊 `tier` 與 `phases`。
- [x] **TASK-04 (Knowledge-DB 日常搜尋鐵律與 `--ftype` 決策樹強化)**：修訂 `source/knowledge-db/assets/KnowledgeAgentsStandards.md`。
- [x] **TASK-05 (ContextInit 職責分離與 AgentsStandards 剛性純化)**：修訂 `source/agents-workflow/assets/workflows/ContextInit.md` 與 `source/agents-workflow/assets/standards/AgentsStandards.md`。
- [x] **TASK-06 (全系統驗證與回歸測試)**：執行 `python yscb.py dev test <module>` 與 `dev check`，全生態系 4 大模組 208/208 測試 100% 通過。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (100% 依據 P04 拓撲實作完成) | - |
