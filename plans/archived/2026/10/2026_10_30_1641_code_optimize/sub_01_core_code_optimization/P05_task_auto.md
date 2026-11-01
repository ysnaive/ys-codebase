# 實作任務清單 (Task Breakdown)

> 功能名稱：Core 模組五維度靜態診斷與無損重構  
> 建立日期：2026-10-31  
> 所屬主計畫：`2026_10_30_1641_code_optimize` (`sub_01`)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 `core/uri.py` 15 個 VFS 薄轉發與 `_get_yscb_root` 別名刪除，統一 5 處尋根委派至 `uri.resolve_yscb_root()`
- [x] **TASK-02**：完成 `core/engine.py` 與 `core/installer.py` 死代碼與 7 個靜態重綁定移除、`transaction_lock` 與 `.gitignore` VFS 合一
- [x] **TASK-03**：完成 `core/config.py`（移除 `tempfile` 死分支）、`events.py`、`locale.py`、`validator.py`、`contributes.py`、`pip_manager.py`、`ide_projector.py` 重構
- [x] **TASK-04**：完成 `registry.py`（移除 `all_modules` 與 `case_pros/cons`）、`contributes_cmd.py`、`dispatcher.py` 與 `scripts/cli.py` 重構
- [x] **TASK-05**：同步更新 `ys_codebase/source/core/tests/` 下 14 個測試檔案，對齊正統頂層函式入口與 VFS 介面

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
