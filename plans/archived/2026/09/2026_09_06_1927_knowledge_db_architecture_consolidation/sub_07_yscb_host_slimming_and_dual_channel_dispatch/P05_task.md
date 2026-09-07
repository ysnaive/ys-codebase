# 實作任務清單 (Task Breakdown)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Completed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/core/core/installer.py` 實作 `generate_internal_gitignore`、`_restore_module_package` 與 `Installer.cmd_restore`，並在 reload / install / restore 中觸發 gitignore 自愈。
- [x] **TASK-02**：在 `source/core/core/contributes.py` 實作動態全域 Help 聚合器 `print_global_help()`，支援掃描各模組 `contributes/core.json` 與 `manifest.json`。
- [x] **TASK-03**：在 `source/core/scripts/cli.py` 掛載 `restore` 與 `help` 子指令。
- [x] **TASK-04**：重構 `yscb.py` 宿主入口，剝除下沉邏輯，實裝雙管道路由、Token 注入、模糊拼寫建議與 Exit Code 透傳，行數壓縮至 200~250 行。
- [x] **TASK-05**：編寫單元測試 `source/core/tests/test_installer_restore.py` 與 `source/core/tests/test_contributes_help.py`。
- [x] **TASK-06**：執行自動化測試驗證 FT-01 ~ FT-07 與回歸測試 RT-01。
- [x] **TASK-DOC**：更新 `docs/core/DESIGN_NOTES.md` (DN-21)、`plans/roadmap/yscb_host_slimming_and_dual_channel_dispatch.md` 與微觀代碼註解。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
