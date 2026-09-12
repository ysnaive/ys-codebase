# 實作任務清單 (Task Breakdown)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Passed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core.commands` 核心引擎子模組
  - [x] `bags.py`: `CmdOption`, `CmdBags`
  - [x] `registry.py`: `CommandsRegistry` Schema 解析器 (支援同構遞迴 `cmd` 樹與 `resolve_command_path`)
  - [x] `resolver.py`: `OptionResolver` 正交互斥與規範化
  - [x] `help.py`: `HelpRenderer` 格式化終端輸出 (支援 `AVAILABLE SUBCOMMANDS:` 渲染)
  - [x] `dispatcher.py`: `CommandDispatcher` 遞迴樹走訪、純分支自動 Help 與可呼叫複合分支派發
  - [x] `__init__.py`: 匯出核心 API
- [x] **TASK-02**：實作微內核延遲載入與薄宿主重構
  - [x] `core/__init__.py`: PEP 562 `__getattr__` 實作
  - [x] `yscb.py`: 宿主極致薄化與單一委託
- [x] **TASK-03**：先驅模組遷移與 Contributes Schema 升級
  - [x] `source/core/contributes/core.json`: `uri`、`config`、`event` 升級為同構巢狀 `cmd`
  - [x] `source/server/contributes/core.json`: 遷移為新 Schema
  - [x] `source/core/scripts/cli.py`: 改寫為獨立命令函式，實作 `config_*`、`uri_*`、`event_*` 平鋪函式
  - [x] `source/server/scripts/cli.py`: 改寫為獨立命令函式，移除 `process(args)`
  - [x] `source/server/server/worker.py`: 支援 `core.commands` 遞迴派發與相容
- [x] **TASK-04**：單元測試、邊界測試與回歸測試實作
  - [x] `source/core/tests/test_core_commands.py`: 涵蓋 FT-01~11, ET-01~08, PT-01, RT-01
- [x] **TASK-05**：同步更新 `docs/` 模組手冊、專題手冊與設計決策

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
