# 實作任務追蹤清單 (Implementation Task List)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：In Progress  
> 模板版本：v1.3  

---

## 任務清單與執行進度

- [x] **TASK-01 (資產目錄結構遷移)**：
  - [x] 建立 `source/core/configurable/config.project.json` 並移除 `source/core/config.project.json`。
  - [x] 建立 `source/knowledge-db/configurable/config.project.json` 並移除 `source/knowledge-db/config.project.json`。
  - [x] 建立 `source/agents-workflow/configurable/config.project.json` 並移除 `source/agents-workflow/config.project.json`。
- [x] **TASK-02 (`core.config` SDK 實作)**：
  - [x] 建立 `source/core/core/config.py`，實作 `get`, `get_all`, `set`, `delete`, `reload`, `list_modules` 與 mtime 快取自愈。
- [x] **TASK-03 (部署引擎適配與淨化)**：
  - [x] 升級 `source/core/core/engine.py` 之 `act_deploy_configs_from_modules()` 掃描 `configurable/` 並物理刪除 runtime 模板。
- [x] **TASK-04 (`contribute.json` 專案特化升級)**：
  - [x] 升級 `source/core/core/contributes.py` 階層 ② 改讀 `config://<target>/contribute.json`，檢測到 `contribute.local.json` 時輸出警告並忽略。
- [x] **TASK-05 (消費端 SDK 100% 收斂)**：
  - [x] 重構 `source/core/core/uri.py` 收斂至 `core.config.get()`。
  - [x] 重構 `source/knowledge-db/knowledge_db/space.py` 收斂至 `core.config.get()`。
  - [x] 重構 `source/agents-workflow/agents_workflow/targets.py`、`publisher.py`、`initializer.py` 收斂至 `core.config` SDK。
- [x] **TASK-06 (CLI 工具鏈與 Contributes 註冊)**：
  - [x] 實作 `source/core/scripts/cli.py` 之 `config list / get / set` 指令。
  - [x] 於 `source/core/contributes/core.json` 註冊 `commands.config` 與防呆手冊。
- [x] **TASK-07 (單元測試與全系統沙盒回歸)**：
  - [x] 建立 `source/core/tests/test_config.py`。
  - [x] 更新 `source/core/tests/test_contributes.py`、`test_engine.py`。
  - [x] 執行 `python yscb.py dev test --all` 達成 100% Passed。

