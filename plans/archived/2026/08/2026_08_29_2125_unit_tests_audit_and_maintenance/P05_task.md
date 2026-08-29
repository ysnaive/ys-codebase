# 實作任務清單 (Task Breakdown)

> 功能名稱：`unit_tests_audit_and_maintenance`  
> 建立日期：2026-08-29  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (`core`)**：重構 `source/core/tests/test_semver.py`，完整涵蓋 4 段式與 3 段式 SemVer 解析、比較、升級與約束求解，並安全刪除 `source/core/tests/test_semver_v4.py`。
- [x] **TASK-02 (`dev`)**：純化 `source/dev/tests/test_tester.py` 與 `test_sandbox.py`，精簡重複之沙盒生命週期斷言。
- [x] **TASK-03 (`agents-workflow`)**：移除孤立之 `source/agents-workflow/tests/test_basic.py`，確認 `test_compiler.py` 與 `test_targets.py` 測試覆蓋。
- [x] **TASK-04 (`knowledge-db`)**：重構 `source/knowledge-db/tests/test_parsers.py` 整合深度解析邊界案例並刪除 `test_parsers_deep.py`；重構 `source/knowledge-db/tests/test_tokenizer.py` 整合同義詞測試並刪除 `test_thesaurus.py`。
- [x] **TASK-05 (全生態系驗收)**：執行 `python yscb.py dev test --all` 確保全模組單元測試 100% Passed。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
