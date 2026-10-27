# 實作任務清單 (Task Breakdown)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修復 `server/master.py` (`start()` 單例鎖防穿透、先行寫入 `daemon.json`、`restart_server()` 防重入) 與 `server/watcher.py` (`.yscb.lock` 交易鎖感知)（詳見 P04 §4）
- [x] **TASK-02**：實作 `core/engine.py`、`core/installer.py`、`yscb.py` Staging 預組裝與 `_atomic_swap_dir` 原子替換及 `dispatcher.py` 生命週期指令免預喚醒（詳見 P04 §4）
- [x] **TASK-03**：補齊 `test_server.py` 與 `test_distribution_lifecycle.py` 單元回歸測試並同步更新 `docs/{core,server}/DESIGN_NOTES.md`（詳見 P04 §4）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

