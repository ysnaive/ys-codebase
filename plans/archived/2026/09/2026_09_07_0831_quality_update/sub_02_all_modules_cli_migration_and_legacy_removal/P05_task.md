# 實作任務清單 (Task Breakdown)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`dev` 模組遷移：更新 `source/dev/contributes/core.json` commands schema（含內部原子命令 `op-test` 與 `op-mksb`），重構 `source/dev/scripts/cli.py` 為精確命令函式並刪除 `process(args)`
- [x] **TASK-02**：`knowledge-db` 模組遷移：更新 `source/knowledge-db/contributes/core.json` commands schema（查詢類開啟 `server_compatible: true`），重構 `source/knowledge-db/scripts/cli.py` 為精確命令函式並刪除 `process(args)`
- [x] **TASK-03**：`agents-workflow` 模組遷移：更新 `source/agents-workflow/contributes/core.json` commands schema（含 `plan` 巢狀樹），重構 `source/agents-workflow/scripts/cli.py` 為精確函式並刪除 `process(args)`
- [x] **TASK-04**：Hard Sunset Gate 剛性守門：自 `source/core/core/commands/dispatcher.py` 徹底刪除雙軌向後相容退化代碼與 `has_legacy_process` 試探邏輯
- [x] **TASK-05**：更新測試套件（`test_core_commands.py` 升級 FT-08 為嚴格 EC-05 斷言）並執行全生態系 5 大模組回歸跑測（486 案例 100% 通過）
- [x] **TASK-DOC**：同步更新 `docs/Core/cli_commands_architecture.md` 與生態系模組文檔

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-03** | Minor | commands schema 依架構規範配置於 `contributes/core.json`（對齊 core 命令引擎載入機制），自 `agents-workflow.json` 清理重複宣告 | 已對齊 `source/agents-workflow/contributes/core.json` |
| **TASK-01** | Minor | `dev test` 沙盒執行內部依賴原子命令 `dev op-test` 與 `dev op-mksb`，補充宣告至 `contributes/core.json` | 已宣告並標記為 gated 內部操作 |
