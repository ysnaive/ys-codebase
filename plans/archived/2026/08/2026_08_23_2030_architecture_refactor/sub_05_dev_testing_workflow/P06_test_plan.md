# 測試計畫書 (Test Plan)

> 功能名稱：開發者測試框架與全自動契約回歸工作流 (Dev Testing Framework & Regression Workflow)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## ⚠️ 特別驗證原則宣告

> [!IMPORTANT]
> **本次測試內容為「測試框架本體 (dev.testing & dev test)」**：
> 依據架構紀律與開發者指示，本子計畫之所有驗證作業**一律於 `./sandbox/` 臨時隔離環境進行實機手動/自動化腳本驗證**，**嚴禁在 `source/*/tests/` 添加任何持久化測試檔案**，避免測試引擎未就緒前產生自引用循環相依。待測試引擎本體驗收完畢後，再行提供標準測試示範。

---

## 1. 測試案例矩陣 (Test Cases Matrix)

| 測試編號 | 測試項目 | 驗證目標 | 執行方式 | 預期結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `YSCBTestCase` 狀態歸零與沙盒 | 驗證 `setUp`/`tearDown` 環境備份/恢復與沙盒建立 | `python sandbox/run_sub05_tests.py` | 通過自動刪除沙盒，環境變數與 `sys.path` 100% 恢復 | ✅ Passed |
| **FT-02** | 失敗沙盒保留機制 | 驗證測試斷言失敗時沙盒完整保留與路徑輸出 | `python sandbox/run_sub05_tests.py` | 終端輸出 `[Test Failed] Sandbox preserved at: ...` 且目錄存在 | ✅ Passed |
| **FT-03** | `@require` 條件探測裝飾器 | 驗證 `Requirement` 位元旗標動態探測與 `SkipTest` | `python sandbox/run_sub05_tests.py` | 滿足執行，未滿足自動標記為 `[SKIPPED]`，不計入 Failure | ✅ Passed |
| **FT-04** | 專屬斷言庫功能 | 驗證 `assertSuccess`, `assertInOutput`, `assertFileExists`, `assertJsonEquals` | `python sandbox/run_sub05_tests.py` | 斷言正確命中與錯誤清晰回報 | ✅ Passed |
| **FT-05** | 全自動模組標準契約守門 | 驗證 `TestRunner` 自動對 `core` 與 `dev` 執行 4 大契約檢驗 | `python sandbox/run_sub05_tests.py` | 自動掃描並通過 Schema、進入點、純淨建置、0-依賴檢驗 (6/6 Passed) | ✅ Passed |
| **FT-06** | `dev test` 命令列派發與過濾 | 驗證單模組、`--all`、`-k pattern`、`--type`、`--verbose` | `python yscb.py dev test --all` | 正確解析參數並派發測試 | ✅ Passed |
| **FT-07** | ASCII 報告格式化與 Exit Code | 驗證終端結構化輸出與回歸守門阻斷 | `python yscb.py dev test --all` | 輸出對齊之 ASCII 表格，全部通過返回 0 | ✅ Passed |
| **ET-01** | 無 `tests/` 模組合規執行 | 模組無自訂測試時的處理 | `python yscb.py dev test core` | 自動完成契約測試，輸出 `(No custom tests)`，Exit Code 0 | ✅ Passed |
| **ET-02** | 語法錯誤或未捕獲例外 | 測試腳本自身語法錯誤或崩潰 | `python sandbox/run_sub05_tests.py` | 捕獲 Traceback，保留沙盒，Exit Code 1 | ✅ Passed |
| **ET-03** | `-k pattern` 無匹配測試 | 過濾關鍵字不存在時的處理 | `python yscb.py dev test dev -k non_existent` | 提示無匹配測試，Exit Code 0 | ✅ Passed |
| **PT-01** | 純邏輯與契約測試效能 | 驗證測試執行效率與啟動開銷 | 計時斷言 | 契約測試執行 < 30ms (閾值 200ms) | ✅ Passed |

---

## 2. 驗收檢核關卡 (Checkpoints)

- [x] **CLI 自動化/腳本驗證**：11 項測試案例全數 Passed (11/11 Passed)。
- [x] **零污染檢驗**：驗證 `source/` 與 `build/` 100% 無殘留測試臨時檔案。
- [x] **開發者 UX / 手動測試確認**：開發者明確回覆「沒問題/通過」，允許進入 Phase 7。
