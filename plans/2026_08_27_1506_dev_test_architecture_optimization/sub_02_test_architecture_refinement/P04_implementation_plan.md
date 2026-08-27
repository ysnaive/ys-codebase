# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中有對應介面與型態定義。
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略與環境還原防線。
- [x] **依賴純淨**：100% 採用 Python 標準庫，零新增第三方依賴。
- [x] **測試前置**：P06 測試計畫包含 FT-01~05, ET-01~02, RT-01~02，已完全對齊 FR/EC。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `docs/dev/user_guide.md` | Modify | 增補 §4.3 測試沙盒模式指南（預設共用沙盒 vs `@require(Requirement.ISOLATED_SANDBOX)` 獨立沙盒宣告規範）。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若某個測試方法在共用沙盒模式下意外污染了目錄結構（例如寫入同名 mock 套件），是否會導致同類別後續測試產生不穩定？  
> 💡 **防護解法**：在開發者指南中明確建立規範：一般無狀態或自清理測試使用預設共用沙盒；若測試涉及破壞性寫入、模組建置或物理安裝，**必須明確標記 `@require(Requirement.ISOLATED_SANDBOX)`** 以獲得獨立沙盒。同時每個測試方法仍嚴格執行 `sys.path` 與 `os.environ` 的 100% 備份與還原。

> ❓ **尖銳問題 2**：在多層子行程中調用 `run_cli`（例如在 Windows PowerShell 下執行），`YSCB_TEST_SANDBOX` 是否能被可靠透傳至深層行程？  
> 💡 **防護解法**：`YSCBTestCase.run_cli` 透過 `subprocess.run(..., env=p_env)` 顯式將 `YSCB_TEST_SANDBOX="1"` 注入環境字典，跨平台確定性透傳至所有深層調用中。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Core URI JIT 防護)**：在 `source/core/core/uri.py` 中更新 `reconcile_undefined_uri`，增加 `YSCB_TEST_SANDBOX` 感應；並在 `source/core/tests/test_uri.py` 新增單元測試。
- [ ] **TASK-02 (Dev Requirement 列舉擴充)**：在 `source/dev/dev/testing/requirement.py` 新增 `Requirement.ISOLATED_SANDBOX` 列舉值。
- [ ] **TASK-03 (Dev TestCase 智慧沙盒分流)**：在 `source/dev/dev/testing/case.py` 實作 Class-level 共用沙盒與 Per-Method 專屬沙盒分流機制、`tearDownClass` 清理、`YSCB_TEST_SANDBOX` 自動注入與 `run_cli` 透傳。
- [ ] **TASK-04 (Dev Runner & Tester 環境感應)**：在 `source/dev/dev/testing/runner.py` 與 `source/dev/dev/tester.py` 中設置 `YSCB_TEST_SANDBOX`。
- [ ] **TASK-05 (Dev 整合單元測試撰寫)**：在 `source/dev/tests/` 撰寫完整驗證案例（共用沙盒、獨立沙盒、混合執行、環境透傳）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿**：P04 實作計畫與 P06 測試計畫同步定稿（`Confirmed`），依拓撲順序進入 Phase 5 實作。
