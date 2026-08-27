# 任務清單與實作追蹤表 (Task Tracking)

> 功能名稱：多進程多模組並行跑測 (Multi-Process Multi-Module Parallel Test Runner)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 模板版本：v1.3  

---

## 1. 任務清單與進度 (Task List)

| 任務編號 | 核心工作內容 | 狀態 | 預計產出 / 關聯檔案 |
| :--- | :--- | :---: | :--- |
| **TASK-01** | 擴充 `Tester._run_op_test` 支援 `--report-json=<path>` 參數，輸出結構化單模組測試結果。 | `Completed` | `source/dev/dev/tester.py` |
| **TASK-02** | 實作 `Tester._run_single_module_worker` 負責個別 Worker 獨立沙盒建立、日誌串流與生命週期清理。 | `Completed` | `source/dev/dev/tester.py` |
| **TASK-03** | 實作 `Tester._run_parallel_test` 支援 `ThreadPoolExecutor` 多 Worker 並行調度、參數解析 (`-j`, `--jobs`, `--sequential`) 與診斷報告聚合。 | `Completed` | `source/dev/dev/tester.py` |
| **TASK-04** | 更新 `source/dev/scripts/cli.py` 支援並行相關參數與 `--help` 說明。 | `Completed` | `source/dev/scripts/cli.py` |
| **TASK-05** | 在 `source/dev/tests/test_sandbox.py` 編寫單元測試覆蓋多 Worker 派發、獨立沙盒與報告聚合。 | `Completed` | `source/dev/tests/test_sandbox.py` |

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 偏差編號 | 任務編號 | 偏差層級 | 偏差原因與具體調整說明 | 處置方式與回報時間 |
| :--- | :---: | :---: | :--- | :---: |
| **DEV-01** | TASK-02 | Minor | 多 Worker 同時呼叫 `create_sandbox` 時微秒級時間戳可能重疊，導致沙盒目錄競爭衝突。 | 在 `SandboxProvisioner.create_sandbox` 引入 `uuid.uuid4().hex[:6]` 保障唯一性 (2026-08-27 17:46) |
