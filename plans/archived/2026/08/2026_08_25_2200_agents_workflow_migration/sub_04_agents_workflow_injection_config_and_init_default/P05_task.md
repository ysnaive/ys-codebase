# Phase 5: 實作任務清單 (Task Breakdown) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據計畫：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：`Completed` (Phase 5 實作全部完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Manifest 協議貢獻與 Config 模板建立)**：
  - 在 `source/agents-workflow/manifest.json` 中註冊 4 大 `workflow.*` 協議。
  - 新增 `source/agents-workflow/config.project.json` 模板（`paths` 全為 `"!undefined"`，含 `ide: []` 等保留欄位）。
- [x] **TASK-02 (初始化引導引擎實作 `WorkflowInitializer`)**：
  - 建立 `source/agents-workflow/agents_workflow/initializer.py`。
  - 實作推薦路徑封裝、實體存在性探測、互動式 `[-y / -n]` 提示、缺失目錄建立與組態原子增量寫入。
- [x] **TASK-03 (CLI 指令擴充與變種參數解析)**：
  - 修改 `source/agents-workflow/scripts/cli.py`，支援 `--init-default`、`-y`/`--yes` 與 `--path-{plans|archived|ext|docs}` 參數。
- [x] **TASK-04 (單元測試、Dogfooding 部署與全模組回歸驗證)**：
  - 建立 `source/agents-workflow/tests/test_initializer.py` 覆蓋 FT-01~06、ET-01~03。
  - 實機執行 `python yscb.py dev test --all`（104/104 測試 100% Passed）。
  - 執行 `dev build` 與 `install agents-workflow --force` 完成部署。

---

## 2. 實作進度追蹤 (Progress Tracking)

| 任務代碼 | 負責模組/檔案 | 執行狀態 | 驗證關聯 |
| :--- | :--- | :---: | :---: |
| **TASK-01** | `manifest.json` & `config.project.json` | `Completed` | FT-01, FT-02 |
| **TASK-02** | `agents_workflow/initializer.py` | `Completed` | FT-03, FT-04, ET-01, ET-02 |
| **TASK-03** | `scripts/cli.py` | `Completed` | FT-05, ET-03 |
| **TASK-04** | `tests/test_initializer.py` | `Completed` | FT-01~06, ET-01~03, RT-01 |
