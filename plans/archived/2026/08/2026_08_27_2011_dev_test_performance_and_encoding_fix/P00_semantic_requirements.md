# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 計畫類型：Performance, Refactor & Bug Fix  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：選項 A（精準分類） + 單元測試 Mock 去子進程化，並且若其想測試標準建置、發布流程，應使用 mock module 測試，而不是打包現有原始碼，會造成未來新增其他官方 module 時出現 side effect。
- **核心目標**：
  1. **Windows 控制台與子進程 Unicode/cp950 編碼修復**：全面於子進程 `subprocess.run`、標準流、`TestRunner` 與 `ASCIIReportFormatter` / `Tester` 輸出層注入 `utf-8` 及 `errors="replace"` 安全處理，根除 Windows 中文語系環境下 `cp950` 編碼中斷異常。
  2. **測試四層分類精準歸類 (Taxonomy Realignment)**：將純高階 E2E 調度測試標記為 `@require(Requirement.WORKFLOW)`，使日常回歸 (`LOGIC` + `ENV`) 保持極速（預期回歸時間由 12.5 秒壓至 ~3~4 秒）。
  3. **單元測試去子進程化 (Unit Test Mocking & Process Decoupling)**：針對參數解析、清理邏輯等單元測試，以 Mock 隔離子進程，避免單元測試內部遞迴啟動多行程與多重全量沙盒。
  4. **標準建置/發布測試改採 Mock Module 隔離 (Mock Module Build/Release Isolation)**：重構 `test_builder.py`、`test_release_pipeline.py` 等建置與發布測試，嚴格改採動態生成的 Mock Module 進行打包、修剪與發布驗證，徹底解除對真實官方模組（`core`, `dev`, `agents-workflow`）原始碼的耦合與 side effect。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更外部公開 CLI 命令介面與 public API 簽名。
  - 不降低測試覆蓋率與既有三道守門鎖。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Windows 終端與子進程編碼安全防禦策略**
  - 在 Windows 環境下執行子進程或終端輸出時，標準化使用 UTF-8 管道並設置 `errors="replace"`，防止特殊字符（如替換符、表格符號）造成編碼崩潰。
- **[P00:DR-02] 測試分類與單元去子進程化雙軌優化**
  - **軌道 ① (分類分流)**：將跨模組 E2E 流程（如 `test_dev_test_high_level_orchestration`）標記為 `WORKFLOW`，日常 `dev test --all` 預設跳過，僅在 `--workflow` / `--all-types` 時執行。
  - **軌道 ② (單元去子進程)**：重構驗證清理邏輯與內部狀態的單元測試（如 `test_run_test_all_success_cleans_sandboxes`），使用 mock 取代實機多進程跑測。
- **[P00:DR-03] 建置與發布測試全面隔離 (Zero-Side-Effect Mock Module)**
  - 測試 Builder、Release Pipeline、Revision Purge 等打包生命週期時，動態建立輕量 `mock_build_pkg` 進行全流程打包與清理驗證，禁止打包真實 official 模組原始碼。

---

## 3. 開放議題與確認紀錄

- [x] **議題 1**：本次修復範疇是否包含「Windows cp950 編碼修復」以及「重型測試耗時分類/重構」兩大項？➔ **已確認納入**。
- [x] **議題 2**：針對 `dev` 模組內部重型測試，採「分類至 WORKFLOW」+「單元測試 Mock 去子進程化」雙軌並行。➔ **已確認**。
- [x] **議題 3**：建置與發布流程測試全面改用動態 Mock Module，根除對真實官方模組的打包耦合與 side effect。➔ **已確認納入**。
