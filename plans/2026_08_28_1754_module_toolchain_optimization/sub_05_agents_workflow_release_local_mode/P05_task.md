# 實作任務清單 (Task Breakdown)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Core Config 來源層級探測 API 實作)**：
  - [x] 在 `source/core/core/config.py` 中實作 `ConfigManager.get_raw()` 與 `ConfigManager.inspect()`。
  - [x] 匯出頂層 Facade 函式 `get_raw` 與 `inspect`。
  - [x] 在 `source/core/tests/test_config.py` 新增單元測試 (FT-01, FT-02)。
- [x] **TASK-02 (ReleaseTargetManager 升級與來源標註)**：
  - [x] 在 `source/agents-workflow/agents_workflow/targets.py` 升級 `add_target()` 與 `remove_target()` 預設 `is_project=False`（寫入 `config.local.json`），支援 `is_project=True`（寫入 `config.project.json`）。
  - [x] 升級 `list_targets()` 透過 `core.config.get_raw()` 比對 Local 與 Project 組態，標註 `[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]`、`[ENABLED (BOTH)]`、`[DISABLED]`。
- [x] **TASK-03 (ReleasePublisher 聯集發布與 .gitignore 軟合併)**：
  - [x] 在 `source/agents-workflow/agents_workflow/publisher.py` 實作 `sync_gitignore()` 區塊軟合併邏輯。
  - [x] 在 `release_all()` 發布交易中呼叫 `sync_gitignore()`。
- [x] **TASK-04 (CLI release-target 指令與排版升級)**：
  - [x] 在 `source/agents-workflow/scripts/cli.py` 升級 `cmd_release_target`，解析 `--proj` / `--project` 旗標並進行多層彩色排版輸出。
- [x] **TASK-05 (單元測試與全生態系沙盒回歸)**：
  - [x] 在 `source/agents-workflow/tests/test_targets.py` 新增/更新測試套件 (FT-03~08, ET-01~02)。
  - [x] 執行 `python yscb.py dev test --all` 確保 4 大模組 100% Passed。


---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 尚無偏差 | - |
