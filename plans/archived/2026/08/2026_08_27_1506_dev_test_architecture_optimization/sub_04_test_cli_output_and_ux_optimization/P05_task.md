# 任務清單與實作追蹤表 (Task Tracking)

> 功能名稱：dev test CLI 輸出結構與資訊優化 (Dev Test CLI Output & UX Optimization)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 模板版本：v1.3  

---

## 1. 任務清單與進度 (Task List)

| 任務編號 | 核心工作內容 | 狀態 | 預計產出 / 關聯檔案 |
| :--- | :--- | :---: | :--- |
| **TASK-01** | 實作 `OutputCapturer` 上下文管理器，支援跑測期間 stdout/stderr 緩衝捕獲與安全還原。 | `Completed` | `source/dev/dev/testing/runner.py` |
| **TASK-02** | 定義 `ModuleTestMetrics` 與收集四層分類計數 (`logic_passed`, `env_passed`, `workflow_passed`, `perf_passed`) 與獨立耗時。 | `Completed` | `source/dev/dev/testing/runner.py` |
| **TASK-03** | 升級 `ASCIIReportFormatter` 支援頂部過濾元數據、模組樹狀圖耗時與分類細分、結構化失敗診斷與 `--target` 快速重測引導。 | `Completed` | `source/dev/dev/testing/runner.py` |
| **TASK-04** | 在 `Tester._run_test()` 傳遞 `--verbose` 參數與過濾元數據，整合新版格式化器。 | `Completed` | `source/dev/dev/tester.py` |
| **TASK-05** | 在 `test_sandbox.py` 編寫單元測試覆蓋 `OutputCapturer`、元數據格式化與分類統計。 | `Completed` | `source/dev/tests/test_sandbox.py` |
| **TASK-06** | 在 `Tester._run_test()` 與 `run_test()` 實作生命週期進度提示，並在 `subprocess.run` 啟用 `capture_output=True`。 | `Completed` | `source/dev/dev/tester.py` |
| **TASK-07** | 在 `test_tester.py` 中設置巢狀標記以靜默內部子跑測，徹底終結雙報表問題。 | `Completed` | `source/dev/tests/test_tester.py` |

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 偏差編號 | 任務編號 | 偏差層級 | 偏差原因與具體調整說明 | 處置方式與回報時間 |
| :--- | :---: | :---: | :--- | :---: |
| DEV-01 | TASK-06/07 | Minor | 依開發者指示納入生命週期進度 Log 並根除子行程雙報表 | 2026-08-27 17:25 |
