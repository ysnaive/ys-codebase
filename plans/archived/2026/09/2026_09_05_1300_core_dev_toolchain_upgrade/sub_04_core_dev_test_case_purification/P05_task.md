# 實作任務清單 (Task Breakdown)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：Dev 模組測試整併（將 sync 與 throttle 測試吸收至 `test_tester.py`，安全刪除舊兩檔）。
- [x] **TASK-02**：Dev 模組沙盒重型測試 WORKFLOW 標註（`test_sandbox.py` 中 5 項實體沙盒案例）。
- [x] **TASK-03**：Core 模組 CLI 與 Contributes 測試整合（建立 `test_cli_router.py`，整合 JIT 案例至 `test_contributes.py`，清理舊檔）。
- [x] **TASK-04**：Core 模組 Pip SDK 測試緊湊化與 Engine WORKFLOW 標註。
- [x] **TASK-05**：執行全量與預設測試雙軌驗證（`--quiet` 與 `--all-types` 100% 通過）。
- [x] **TASK-DOC**：更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
