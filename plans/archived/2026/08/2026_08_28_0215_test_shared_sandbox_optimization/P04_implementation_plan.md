# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：測試框架 Session 層級共用沙盒與效能優化 (Test Session-Level Shared Sandbox Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與架構設計中有對應實作策略與生命週期保證。
- [x] **邊界防護**：EC-01 ~ EC-03 具備 `try...finally` 釋放、`--keep-sandbox` 判斷與環境變數剛性復原機制。
- [x] **依賴純淨**：100% Python 標準庫，零第三方套件依賴，符合 NFR-01 ~ NFR-03 指標。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 4 (使用者手冊)** | `docs/dev/user_guide.md` | Modify | 更新 §4.3 測試沙盒架構說明，記錄 Session-Level 共用沙盒與 ISOLATED_SANDBOX 最佳實踐。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若某個未標記 `ISOLATED_SANDBOX` 的測試在共用沙盒中拋出未捕獲的嚴重 Exception 甚至進程異常終止，共用沙盒是否會殘留佔用磁碟空間？  
> 💡 **防護解法**：
> 1. `TestRunner.run_suite()` 採用 `try...finally` 確保無論測試成功或失敗，`cleanup_shared_sandbox()` 均會剛性觸發（除非指定 `--keep-sandbox`）。
> 2. `SandboxProvisioner.prune_sandboxes(max_keep=3)` 在每次新跑測時會自動滾動清理最舊的孤兒沙盒，雙重保險根除無限累積。

> ❓ **尖銳問題 2**：在多 Worker 並行 (`dev test --all`) 模式下，多個進程同時執行是否會競爭同一個 `_shared_sandbox_ctx`？  
> 💡 **防護解法**：
> 每個 Worker 是透過 `subprocess` 派發的獨立 Python 進程，各自擁有完全獨立的記憶體空間與進程內 `_shared_sandbox_ctx`。沙盒目錄名稱包含微秒時間戳與 `uuid`，各 Worker 零鎖競爭且零路徑碰撞。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/dev/dev/testing/case.py` 實作 `_shared_sandbox_ctx` 與 `cleanup_shared_sandbox()`，調整 `setUp`/`tearDown` 生命週期。
- [ ] **TASK-02**：在 `source/dev/dev/testing/runner.py` 之 `TestRunner.run_suite()` 整合 `finally: YSCBTestCase.cleanup_shared_sandbox()`。
- [ ] **TASK-03**：全面盤點寫入型測試，於 `source/core/tests/`、`source/dev/tests/`、`source/agents-workflow/tests/` 標註 `@require(Requirement.ISOLATED_SANDBOX)`。
- [ ] **TASK-04**：更新 `source/dev/tests/test_case.py` 單元測試驗證 Session 共用與獨立沙盒行為。
- [ ] **TASK-05**：執行全庫回歸跑測與效能指標量測。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿 P06 測試計畫**：確認 FT-01 ~ FT-06 與 RT-01 完整覆蓋所有功能與邊界，將 `P06_test_plan.md` 狀態定稿為 `Confirmed`。
