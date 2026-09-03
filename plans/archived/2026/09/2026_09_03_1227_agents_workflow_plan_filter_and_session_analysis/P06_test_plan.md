# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `PlanVerifier.verify_all_plans()` 自動忽略 `roadmap/`、`archived/` 與自訂資源資料夾，僅檢驗時間戳合法計畫。 | FR-01, EC-01 | `test_plans_toolchain.py` |
| **FT-02** | 單元測試 | `PlanScanner.scan_active_plans()` 僅返回時間戳開頭之計畫，排除其餘所有目錄。 | FR-01, EC-01 | `test_plans_toolchain.py` |
| **FT-03** | 單元測試 | `PlanSearcher.find_all_plans()` 在無過濾條件下僅收集時間戳開頭之計畫目錄。 | FR-01, EC-01 | `test_plans_toolchain.py` |
| **FT-04** | 單元測試 | `SessionAnalysis.md` 資產完整性：驗證檔案存在、四大步驟齊全、尾部包含 `__@{WORKFLOW_SESSIONANALYSIS}__`。 | FR-02, FR-03, FR-04 | `test_session_analysis_workflow.py` |
| **FT-05** | 單元測試 | `contributes/agents-workflow.json` 導出項目與 Token 錨點宣告驗證（包含 `WORKFLOW_SESSIONANALYSIS` 與 `SESSION_ANALYSIS_CHECK_ITEMS`）。 | FR-02, FR-03 | `test_session_analysis_workflow.py` |
| **FT-06** | 單元測試 | `core` 退出注入與 `knowledge-db` 對齊注入 `SESSION_ANALYSIS_CHECK_ITEMS` 宣告驗證。 | FR-06, FR-07 | `test_session_analysis_workflow.py` |
| **ET-01** | 邊界測試 | `plans/` 中存在語法錯誤或無標頭之非時間戳目錄時，全量檢核完全不拋出異常亦不標記 FAIL。 | EC-01, EC-02 | `test_plans_toolchain.py` |
| **ET-02** | 邊界測試 | Compiler Stage 1 編譯 `SessionAnalysis.md`，驗證佔位符解析與 Stage 1 快取產物無語意丟失。 | EC-04, NFR-02 | `test_session_analysis_workflow.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_plans_toolchain.py` 驗證 `verify_all_plans` 成功排除 roadmap、custom_resources 目錄，僅檢核合法計畫。 | 2026-09-03 12:34 |
| **FT-02** | `Passed` | `test_plans_toolchain.py` 驗證 `scan_active_plans` 僅回傳時間戳前綴計畫目錄。 | 2026-09-03 12:34 |
| **FT-03** | `Passed` | `test_plans_toolchain.py` 驗證 `find_all_plans` 排除非時間戳目錄。 | 2026-09-03 12:34 |
| **FT-04** | `Passed` | `test_session_analysis_workflow.py` 驗證資產完整性、四大維度章節與 Token。 | 2026-09-03 12:34 |
| **FT-05** | `Passed` | `test_session_analysis_workflow.py` 驗證 contributes 導出 SessionAnalysis.md 與新 Token。 | 2026-09-03 12:34 |
| **FT-06** | `Passed` | `test_session_analysis_workflow.py` 驗證 core 無注入、knowledge-db 對齊注入。 | 2026-09-03 12:34 |
| **ET-01** | `Passed` | `test_plans_toolchain.py` 驗證非時間戳目錄包含不合規 markdown 時安全略過。 | 2026-09-03 12:34 |
| **ET-02** | `Passed` | `test_session_analysis_workflow.py` 驗證 Stage 1 編譯成功，快取產物無遺失。 | 2026-09-03 12:34 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機執行 `python yscb.py agents-workflow plan check`，全庫檢驗確認 `roadmap` 不再被判定為不合規計畫，整體狀態為 `PASSED`。
- [x] **UX-02**：發布至 `.agents/` 後實機檢視 `.agents/workflows/SessionAnalysis.md`，確認包含 `/SessionAnalysis` Slash Command 標頭、內容語言精煉客觀且已正確展開 `knowledge-db` 自檢內容（且已移除頂部 URI 地圖）。
