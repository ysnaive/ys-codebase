# 實作任務清單 (Task Breakdown)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：In Progress  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core.platform.process.can_spawn_background_daemon` 探針與記憶體快取邏輯。
- [x] **TASK-02**：實作 `server.config.ServerConfig` 之 `auto_spawn` 欄位解析與預設值。
- [x] **TASK-03**：升級 `core.commands.dispatcher._maybe_auto_spawn_server` 整合 `auto_spawn` 檢核、探針判定與防洗頻 `stderr` 提示。
- [x] **TASK-04**：編寫 `test_platform_process.py`, `test_dispatcher.py`, `test_config.py` 單元測試並執行 `dev test` 全套驗證。
- [x] **TASK-DOC**：同步更新 `docs/server/` 相關手冊與 `DESIGN_NOTES.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
