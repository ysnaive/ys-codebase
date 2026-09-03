# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：agents_workflow_plan_filter_and_session_analysis  
> 建立日期：2026-09-03  
> 狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 本主計畫涵蓋 `agents-workflow` 計畫篩選機制、工作流規格進化與開發者回歸測試工具鏈之全面打磨。
  - 統籌落實計畫正則過濾（排除 `roadmap/` 等非計畫目錄）、`/SessionAnalysis` 工作流重構，以及衍生子計畫之 `dev test` 節流模式優化，最大化降低日常開發中之 Token I/O 消耗。
- **架構邊界**：
  - `agents-workflow` 模組：計畫目錄識別工具鏈、`SessionAnalysis` 工作流與 Token 錨點體系。
  - `dev` 模組：`tester.py` 測試調度器、`ASCIIReportFormatter` 報告格式化與 CLI 參數解析。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_dev_test_throttle_output` | Full Track | `Completed` | `dev test` 輸出格式優化與節流模式（深度靜默前置日誌、`Pass: {n}({percent:.1f}%), Fail: {n}, Skip: {n}` 單行輸出與失敗詳情壓縮） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **基底任務**：完成計畫目錄時間戳正則收斂、`SessionAnalysis` 工作流重構與 305 項全生態系測試通過。
- [x] **里程碑 1 (sub_01)**：完成 `dev test` `--quiet` / `-q` 節流模式與深度靜默實作，大幅壓縮 Token I/O。
