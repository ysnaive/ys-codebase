# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：`unit_tests_audit_and_maintenance`  
> 建立日期：2026-08-29  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與架構設計中有具體對應測試重構目標。
- [x] **邊界防護**：EC-01 (零邊界防線遺失) 與 EC-02 (測試發現規範) 已具備嚴密防護解法。
- [x] **依賴純淨**：符合 NFR-01 (執行總耗時 $\le 15$ 秒) 與 NFR-02 (全模組 100% Passed) 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

本次任務 100% 聚焦於單元測試套件之排查、合併與瘦身，未變更任何 Public API 契約與核心架構規格，`docs/` 知識庫無實質變更衝擊。

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：  
> 若刪除 `test_semver_v4.py`、`test_parsers_deep.py`、`test_thesaurus.py`、`test_basic.py`，會不會導致測試發現引擎報錯或覆蓋率降低？  
> 💡 **防護解法**：  
> 在執行實體檔案刪除前，**先將所有獨特的測試斷言與邊界邏輯完整移植至對應之主測試檔中**，並實機透過 `dev test <module>` 驗證所有測試案例 100% 通過後方可移除舊檔，確保防護網零破綻。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (`core`)**：重構 `source/core/tests/test_semver.py`，完整涵蓋 4 段式與 3 段式 SemVer 解析、比較、升級與約束求解，並安全刪除 `source/core/tests/test_semver_v4.py`。
- [ ] **TASK-02 (`dev`)**：純化 `source/dev/tests/test_tester.py` 與 `test_sandbox.py`，精簡重複之沙盒生命週期斷言。
- [ ] **TASK-03 (`agents-workflow`)**：移除孤立之 `source/agents-workflow/tests/test_basic.py`，確認 `test_compiler.py` 與 `test_targets.py` 測試覆蓋。
- [ ] **TASK-04 (`knowledge-db`)**：重構 `source/knowledge-db/tests/test_parsers.py` 整合深度解析邊界案例並刪除 `test_parsers_deep.py`；重構 `source/knowledge-db/tests/test_tokenizer.py` 整合同義詞測試並刪除 `test_thesaurus.py`。
- [ ] **TASK-05 (全生態系驗收)**：執行 `python yscb.py dev test --all` 確保全模組單元測試 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全模組單元測試純化與發布定稿**：
  確認以 5 大 Task 拓撲依序實作，維持 100% 綠燈守門，作為正式主發布版本前之代碼庫最終收斂。
