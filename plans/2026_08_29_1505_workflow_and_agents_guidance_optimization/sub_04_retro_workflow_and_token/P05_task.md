# 實作任務清單 (Task Breakdown)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：新建 `source/agents-workflow/assets/workflows/Retro.md` 工作流資產（含頂部文檔溯源剛性紀律、核心自檢異常過濾、`__@{RETRO_CHECK_ITEMS}__` 與 `__@{WORKFLOW_RETRO}__` 錨點）。
- [x] **TASK-02**：於 `source/agents-workflow/contributes/agents-workflow.json` 註冊 `Retro.md` 導出與 `RETRO_CHECK_ITEMS` / `WORKFLOW_RETRO` Token。
- [x] **TASK-03**：更新 `source/agents-workflow/contributes.format.md` 與 `source/agents-workflow/assets/standards/DevelopmentStandards.md`。
- [x] **TASK-04**：於 `source/agents-workflow/tests/test_compiler.py` 新增單元測試 `test_sub_08_retro_workflow_export_and_token`。
- [x] **TASK-05**：實機執行 `python yscb.py dev test agents-workflow` 與自引用物化 `python yscb.py install agents-workflow@build --force`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | `Minor` | 依使用者明確指示，移除 `Retro.md` 頂部之 `__@{DYNAMIC_CONTEXT_MAP}__` 佔位符注入，保持工作流頂部簡潔 | 已更新 `Retro.md` 源碼並通過編譯測試 |
