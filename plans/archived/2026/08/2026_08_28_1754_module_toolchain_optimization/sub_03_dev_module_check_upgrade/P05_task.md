# 實作任務追蹤清單 (Implementation Task List)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：In Progress  
> 模板版本：v1.3  

---

## 任務清單與執行進度

- [x] **TASK-01 (核心檢查器重構升級)**：
  - [x] 在 `source/dev/dev/checker.py` 定義 `CheckSeverity`, `CheckIssue`, `CheckReport` 資料結構。
  - [x] 實作 5 步流水線：`_check_manifest` (FR-01), `_check_core_injection` (FR-02), `_check_file_structure` (FR-05, FR-06), `_check_source_files` (FR-03, FR-07, EC-01), `_check_test_classes` (FR-05)。
- [x] **TASK-02 (發布守門阻斷整合)**：
  - [x] 在 `source/dev/dev/releaser.py` 整合 `check_module()`，當 `has_fails == True` 時剛性阻斷發布打包。
- [x] **TASK-03 (CLI 格式化與彩色診斷輸出)**：
  - [x] 升級 `source/dev/scripts/cli.py` 之 `cmd_check` 輸出結構化三級嚴重度報告與 `--json` 格式化。
- [x] **TASK-04 (單元測試與沙盒回歸)**：
  - [x] 建立/更新 `source/dev/tests/test_checker.py` 覆蓋 5 步檢核維度。
  - [x] 執行全生態系 `python yscb.py dev test --all` 達成 100% Passed (178/178)。

