# 實作任務清單 (Task Breakdown)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (sub_05)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：In Progress  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `source/core/core/commands/help.py`，全面移除 Emoji，改用 `[SAFE]`, `[CONDITIONAL]`, `[GATED]` 等 ASCII 標籤；檢視並淨化全生態系 CLI 輸出。
- [x] **TASK-02**：於 `yscb.py` 進入點與 `source/core/core/commands/dispatcher.py` 實施 Windows `sys.stdout/stderr` UTF-8 重組與容錯保護。
- [x] **TASK-03**：清理舊版 `contributes.format.md`（core, server, knowledge-db）與 `source/knowledge-db/configurable/contribute.json`。
- [x] **TASK-04**：為 `agents-workflow` (44 處) 與 `core` (17 處) 補齊 `self.mark_passed()`，微調 `test_pt_01_uri_resolve_perf` 門檻以抵抗高並發沙盒波動。
- [x] **TASK-05**：執行 `dev check --all` (0 Warning) 與 `dev test --all` (511 測試 100% Passed)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
