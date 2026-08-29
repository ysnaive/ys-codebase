# 實作任務清單 (Task Breakdown)

> 功能名稱：`sub_02_agents_workflow_injection_optimization` (agents workflow 注入內容優化)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：編輯 `ys_codebase/source/knowledge-db/assets/KnowledgeAgentsStandards.md`，注入檢索決策樹（簽章/複合詞/語意分流）、定向閱讀哲學與 Docstring 符號防護規範。
- [x] **TASK-02**：編輯 `ys_codebase/source/knowledge-db/assets/phase00_guild.md`，更新 Phase 0 定向檢索與 `-s` 參數指引。
- [x] **TASK-03**：編輯 `ys_codebase/source/knowledge-db/assets/research_guild.md`，更新 Research 調研預檢與複合詞檢索建議。
- [x] **TASK-04**：編輯 `ys_codebase/source/knowledge-db/assets/phase07_guild.md`，移除強制手動 index 敘述，替換為 JIT 熱自愈說明。
- [x] **TASK-05**：執行 Stage 2 打包構建 `python yscb.py dev build knowledge-db`。
- [x] **TASK-06**：執行 Stage 3 回歸測試 `python yscb.py dev test --all`，確保 100% Passed (198/198, 8.825s)。
- [x] **TASK-07**：執行 Stage 4 Dogfooding 同步，重新生成 `agents-workflow` 並核驗 `AGENTS.md` 與 `.agents/` 軟合併無損。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
