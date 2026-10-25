# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：背景服務託管引擎修復 — `server/service.py` 補齊 `import os`，接入 `core.contributes.get`，支援 `code.class://`、`.modules/<provider>` 注入與 `auto_start` 控制 (`S-01`, `S-02`)
- [x] **TASK-02**：Worker IPC 硬隔離與兩階段優雅停機 — `server/worker.py` 實作 `_ipc_stdout` 句柄與 `sys.stdout -> sys.stderr` 重導向；`server/master.py` 實作兩階段停機握手、`start_time` 持久化，並移除所有 `source/` 注入與冗餘 `ServiceManager` (`S-03`, `S-04`, `S-05`)
- [x] **TASK-03**：Contributes 宣告、Reload 熱刷新與 CLI 清理 — `contributes/core.json` 補齊 `events`；`master.py:restart_worker` 刷新 `ServerConfig`；`scripts/cli.py` 刪除 `_handle_start` 死代碼並加固負數 TTL (`S-06`, `S-07`)
- [x] **TASK-04**：測試集純化收斂 4 檔 $\rightarrow$ 3 檔與高風險路徑補盲 — 物理刪除 `tests/test_basic.py`；重寫自寫自驗測試並補齊 4 大高風險路徑 (`ST-01` ~ `ST-04`)
- [x] **TASK-DOC**：三層文檔與手冊同步 — 更新 `docs/server/README.md`、`docs/server/DESIGN_NOTES.md`、`ys_codebase/source/server/README.md` 與 `CHANGELOG.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 依 P04 規劃之拓撲順序進行實作 |

