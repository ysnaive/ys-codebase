# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `source/core/core/events.py`，提供 `broadcast()` 與 `get_contributed_events()`，並於 `core/__init__.py` 匯出。
- [x] **TASK-02**：重構 `source/core/core/engine.py` 與 `installer.py`，移除 `Engine.act_broadcast_event` 舊門面，全面改調用 `core.events.broadcast`。
- [x] **TASK-03**：更新 `source/core/contribute.json` 與 `contributes.format.md`，宣告 `events` 清單中繼資料。
- [x] **TASK-04**：重構 `source/dev/dev/testing/sandbox.py`，移除自建之 `_dispatch_test_hooks`，改呼叫 `core.events.broadcast(..., emit_module="dev")`。
- [x] **TASK-05**：升級 `yscb.py`：建立前置管線 `_ensure_jit_lifecycle_pre`、後置管線 `_ensure_jit_lifecycle_post`，新增 `python yscb.py event list` CLI 指令與 `cmd_event()`。
- [x] **TASK-06**：升級 `agents-workflow`：於 `source/agents-workflow/scripts/hook.core.py` 實作 `on_pre_cli_dispatch(ctx)`，於 `cli.py` 移除 Ad-hoc 的 `ensure_jit_release()` 攔截。
- [x] **TASK-07**：新增 `source/core/tests/test_events_pipeline.py`，編寫單元測試覆蓋 FT-01~08 與 ET-01~05。
- [x] **TASK-DOC**：同步更新代碼 Docstrings 與相關格式手冊。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
