# 實作任務清單 (Task Breakdown)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：加固 `case.py` 與 `runner.py`：移除 `TestRunner.run_suite` 偽造標識，加固 `YSCBTestCase.setUp` 沙盒路徑校驗（失敗拋 SecurityError，嚴禁回退 cwd）。
- [x] **TASK-02**：加固 `Tester._run_op_test` 宿主直接調用守門，確保指定 `--report-json` 與 `--quiet-report` 時不洩漏 stdout。
- [x] **TASK-03**：重構 `Tester._run_test` 統一改採 JSON IPC，實作雙模式終端輸出屏蔽與信息聚合（徹底封堵 stderr 洩漏）。
- [x] **TASK-04**：升級 `ASCIIReportFormatter` 支援子進程警告計數折疊與乾淨底部安裝提示。
- [x] **TASK-05**：撰寫 `source/dev/tests/test_output_purification.py` 單元與整合測試套件（覆蓋 FT-01~04, ET-01~02）。
- [x] **TASK-06**：執行全套 dev 模組自動化測試與計畫合規檢核。
- [x] **TASK-DOC**：更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md` `[DN-DEV-07]`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
