# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (編碼安全)、FR-02 (WORKFLOW 分類)、FR-03 (單元 Mock 去子進程)、FR-04 (Mock 模組建置) 在 API 規格書與架構中皆有具體介面與檔案對應。
- [x] **邊界防護**：EC-01 (特殊字元替代)、EC-02 (沙盒產物隔離)、EC-03 (--workflow 與 --all-types 正常調度) 均有相應防禦措施。
- [x] **依賴純淨**：符合 NFR-01 (< 5.0 秒) 與 NFR-02 (100% Passed 零副作用)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 4** | `docs/dev/user_guide.md` | Update | 更新測試指南章節，登載 Windows 控制台編碼相容性與 Mock 模組標準建置測試實踐規範。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若單元測試改用 Mock 模組，如何保證真實官方模組（`core`, `dev`, `agents-workflow`）的打包與發布邏輯依然正確可用？  
> 💡 **防護解法**：`dev` 模組內建的 `DevAutoContractTestCase`（通用契約測試）與 `dev check` 會自動在每個模組跑測時對目標模組執行 `test_contract_clean_build`（確保當前模組能正常乾淨打包），而專案級的端到端發布流水線已由 `WORKFLOW` 級別測試覆蓋；`test_builder.py` 則是測試 Builder 內部的「多版本滑動修剪算法」、「index.json 合併」等純機制，改用 Mock 模組既徹底覆蓋了 Builder 內部所有路徑，又完全消除了對真實代碼的副作用。

> ❓ **尖銳問題 2**：在 Windows PowerShell / CMD 下，如果輸出流被重定向到檔案或管線（非終端 TTY），`safe_print` 是否能正常工作？  
> 💡 **防護解法**：`safe_print` 直接讀取目標 stream 物件的 `encoding` 屬性，若捕獲 `UnicodeEncodeError` 則以該 stream 宣告之編碼並使用 `errors="replace"` 進行替換編碼後寫入，無論是真實 TTY、檔案物件或 PIPE 均能穩定運作，永不拋出未捕獲例外。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `dev.tester` 與 `dev.testing.runner` 導入 `safe_print`，強化 `subprocess.run` 之標準輸出解碼與終端打印編碼防禦。
- [ ] **TASK-02**：在 `dev.testing.case.YSCBTestCase` 新增 `create_mock_source_module` 輔助方法。
- [ ] **TASK-03**：重構 `tests/test_builder.py`，全面改用 Mock Module 驗證 `build_module`、`package_release`、`revision_purge` 與 `index.json` 更新。
- [ ] **TASK-04**：重構 `tests/test_release_pipeline.py`，全面改用 Mock Module 驗證發布管道與 release-check 閘門。
- [ ] **TASK-05**：重構 `tests/test_tester.py` 中之 `test_run_test_all_success_cleans_sandboxes`，使用 Mock 隔離多進程跑測。
- [ ] **TASK-06**：在 `tests/test_sandbox.py` 將 `test_dev_test_high_level_orchestration` 與 `test_single_module_worker_execution_and_report_json` 標記為 `Requirement.WORKFLOW`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 Windows 控制台與子進程標準流全鏈路 UTF-8 + `errors="replace"` 安全防護。
- **[P04:DR-02]** 確立重型多進程測試歸入 `Requirement.WORKFLOW`，單元清理邏輯透過 Mock 隔離。
- **[P04:DR-03]** 確立 Builder / Release 測試全面採用動態 Mock Module 隔離體系。
