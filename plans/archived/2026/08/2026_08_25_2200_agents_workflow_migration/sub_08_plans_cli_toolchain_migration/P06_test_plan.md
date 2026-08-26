# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Passed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `PlanArchiver.archive_plan` 通過 4 重檢查後安全搬移至 `workflow.archived://YYYY/MM/` 並自動清理 `handoff.md` | `FR-01` | `python yscb.py dev test agents-workflow -k test_scanner_and_archiver_flow` |
| **FT-02** | 單元測試 | 驗證 `PlanScanner.scan_plans` 識別 4 大 Track 與各 Phase 狀態並輸出 ASCII 矩陣清冊（確認不掃描歷史目錄） | `FR-02` | `python yscb.py dev test agents-workflow -k test_scanner_and_archiver_flow` |
| **FT-03** | 單元測試 | 驗證 `PlanSearcher.search` `--dr` 正則擷取去重與全文程式碼片段匹配 | `FR-03` | `python yscb.py dev test agents-workflow -k test_searcher_and_verifier_flow` |
| **FT-04** | 單元測試 | 驗證 `PlanVerifier.verify_plan` 偵測指引註解殘留與 Header 缺失 | `FR-04` | `python yscb.py dev test agents-workflow -k test_searcher_and_verifier_flow` |
| **ET-01** | 邊界測試 | 驗證嘗試歸檔不存在之計畫目錄時拋出 `PlanNotFoundError` | `EC-01` | `python yscb.py dev test agents-workflow` |
| **ET-02** | 邊界測試 | 驗證計畫名稱時間戳無效（非 `YYYY_MM_` 前綴）時拋出 `PlanFormatError` 阻斷歸檔 | `EC-02` | `python yscb.py dev test agents-workflow` |
| **ET-03** | 邊界測試 | 驗證未完成/未記載 CHANGELOG 計畫歸檔拋出 `PlanIncompleteError`，且傳入 `--force` 時放行 | `EC-03` | `python yscb.py dev test agents-workflow` |
| **ET-04** | 邊界測試 | 驗證歸檔目的地目錄已存在同名計畫時拋出 `PlanDestinationExistsError` 阻斷覆蓋 | `EC-04` | `python yscb.py dev test agents-workflow` |
| **ET-05** | 邊界測試 | 驗證 `plan status` 遇空目錄時優雅輸出提示訊息，不拋出未捕獲例外 | `EC-05` | `python yscb.py dev test agents-workflow` |
| **ET-06** | 邊界測試 | 驗證檢索與稽核遇 UTF-8 編碼異常或空檔案安全略過不崩潰 | `EC-06` | `python yscb.py dev test agents-workflow` |
| **RT-01** | 回歸測試 | 驗證全系統沙盒端到端測試 100% 全部通過（111/111 Passed） | 全模組 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 斷言結果 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_scanner_and_archiver_flow`: 4 重守門通過，成功將計畫搬移至 `archive_plans/2026/08/2026_08_20_1200_demo` 並物理刪除 `handoff.md` | 2026-08-26 21:44 |
| **FT-02** | `Passed` | `test_scanner_and_archiver_flow`: 成功掃描 active plans，正確識別 Full Track 與 Completed 狀態（確認排除歷史歸檔） | 2026-08-26 21:44 |
| **FT-03** | `Passed` | `test_searcher_and_verifier_flow`: DR 正則擷取去重成功，成功匹配 `[P01:DR-01] 內部決策` | 2026-08-26 21:44 |
| **FT-04** | `Passed` | `test_searcher_and_verifier_flow`: 成功稽核 Markdown Header 與指引過濾，回傳 `total_errors: 0` | 2026-08-26 21:44 |
| **ET-01** | `Passed` | 嘗試歸檔不存在之目錄時精確捕獲 `PlanNotFoundError` | 2026-08-26 21:44 |
| **ET-02** | `Passed` | 無 `YYYY_MM_` 前綴之名稱歸檔時精確捕獲 `PlanFormatError` | 2026-08-26 21:44 |
| **ET-03** | `Passed` | 未完成計畫無 `--force` 時攔截拋出 `PlanIncompleteError`，傳入 `--force` 時安全放行 | 2026-08-26 21:44 |
| **ET-04** | `Passed` | 目的地已存在同名歸檔目錄時拋出 `PlanDestinationExistsError` 阻斷覆蓋 | 2026-08-26 21:44 |
| **ET-05** | `Passed` | 空目錄下執行 `plan status` 優雅輸出 `[INFO] 目前無進行中的開發計畫。` | 2026-08-26 21:44 |
| **ET-06** | `Passed` | 遇非 UTF-8 二進制損毀檔案時安全略過，檢索與稽核進程不中斷 | 2026-08-26 21:44 |
| **RT-01** | `Passed` | 全模組沙盒端到端回歸測試 111/111 100% 全部通過 (20.474s) | 2026-08-26 21:44 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者於終端機實際驗證或指示免測通過（開發者指示：免測通過）。
