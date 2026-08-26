# 任務清單與實作追蹤 (Phase 5: Task Tracking)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 任務執行進度清單 (Task Checklist)

- [x] **TASK-01**：實作 `source/core/core/symbols.py`（符號定位協議解析、雙軌載入器與例外體系）並在 `source/core/core/__init__.py` 導出。
- [x] **TASK-02**：建立 `source/core/tests/test_symbols.py`，驗證 FR-01~02 與 EC-01~02。
- [x] **TASK-03**：擴充 `source/core/core/compiler.py` 與 `source/agents-workflow/agents_workflow/compiler.py` 支援 `type: "computed"` 與上下文注入。
- [x] **TASK-04**：實作 `source/agents-workflow/agents_workflow/providers.py` 之 `get_dynamic_context_map(ctx)`。
- [x] **TASK-05**：更新 `source/agents-workflow/manifest.json` 配置 `DYNAMIC_CONTEXT_MAP` Computed Token 宣告。
- [x] **TASK-06**：更新 `source/agents-workflow/tests/test_compiler.py` 進行端對端解算與動態地圖產出驗證。

---

## 2. 實作偏差紀錄 (Deviation Logs)

| 任務編號 | 偏差等級 (Minor/Moderate/Major) | 偏差原因與具體內容 | 處置方式與對齊決策 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
