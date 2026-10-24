# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：微內核純化去耦合 (`C-01`, `T-03`) — 修改 `core/providers.py`、`core/uri.py`、`core/contributes.py`，移除 11 個遺留導引函式與死代碼
- [x] **TASK-02**：CLI 與派發加固 (`C-02`~`C-06`) — 修改 `contributes_cmd.py`、`dispatcher.py`、`installer.py`、`contributes/core.json` 與 `core/scripts/cli.py`
- [x] **TASK-03**：測試集去重與碎片收斂 (`T-02`, `T-03`) — 刪除 `test_contributes_help.py`，收斂 8 碎片檔至對應 20 個子系統測試檔
- [x] **TASK-04**：虛假改寫、解耦與漏測補盲 (`T-01`, `T-04`, `T-05`, `T-06`) — 改寫 5 虛假測驗、清除跨模組 patch、沙盒加固與補盲
- [x] **TASK-DOC**：三層文檔同步與合規檢核 — 更新 `docs/core/README.md`、`docs/core/DESIGN_NOTES.md`，執行 `dev check core`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依 P04 計畫完成實作與測試純化 |
