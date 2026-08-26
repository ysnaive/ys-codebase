# Phase 5: 實作任務清單 (Task Breakdown) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據計畫：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：`Completed` (Phase 5 實作全部完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (編譯器正則引擎與 5-Step 狀態機升級)**：修改 `source/agents-workflow/agents_workflow/compiler.py`，全面實作 `__@{token}__` 匹配、三模式注入與殘留抹除，確保 `__#{uri}__` 原樣保留。
- [x] **TASK-02 (全系統標準模板庫 1:1 語法遷移)**：更新 `source/agents-workflow/assets/templates/` 下所有 P01~P07 標準模板，將標頭錨點替換為 `__@{PHASEXX_STANDARD_HEADER}__`。
- [x] **TASK-03 (規範手冊與工作流導引文檔 1:1 遷移)**：更新 `assets/standards/DevelopmentStandards.md`（`__@{PROJECT_SPECIFIC_STANDARDS}__`）與 `assets/workflows/ContextInit.md`（`__@{DYNAMIC_CONTEXT_MAP}__`）。
- [x] **TASK-04 (單元測試更新與全模組回歸驗證)**：更新 `tests/test_compiler.py` 覆蓋 FT-01~06、ET-01~04，並實機執行 `python yscb.py dev test --all`（99/99 測試 100% Passed）。

---

## 2. 實作進度追蹤 (Progress Tracking)

| 任務代碼 | 負責模組/檔案 | 執行狀態 | 驗證關聯 |
| :--- | :--- | :---: | :---: |
| **TASK-01** | `source/agents-workflow/agents_workflow/compiler.py` | `Completed` | FT-01, FT-02, FT-03, ET-01, ET-02 |
| **TASK-02** | `source/agents-workflow/assets/templates/P01~P07.md` | `Completed` | FT-06 |
| **TASK-03** | `source/agents-workflow/assets/standards/` & `workflows/` | `Completed` | FT-06, UX-01 |
| **TASK-04** | `source/agents-workflow/tests/test_compiler.py` | `Completed` | FT-01~06, ET-01~04, RT-01 |
