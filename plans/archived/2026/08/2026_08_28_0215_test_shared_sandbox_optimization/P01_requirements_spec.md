# 需求規格說明書 (Requirements Specification)

> 功能名稱：測試框架 Session 層級共用沙盒與效能優化 (Test Session-Level Shared Sandbox Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Session-Level 全局共用沙盒生命週期 | `YSCBTestCase` 預設沙盒由 Class 級提升為 Session 級（模組跑測期間唯一），同一次 `runner.run_suite()` 中跨 Class 複用同一個共用沙盒，並於 Suite 結束時統一釋放。 | P0 | [P00:DR-01] |
| **FR-02** | 獨立沙盒動態建立與即時回收 | 顯式標記 `@require(Requirement.ISOLATED_SANDBOX)` 的測試方法在 `setUp()` 時取得全新獨立沙盒，並在 `tearDown()` 時即時銷毀，不影響共用沙盒。 | P0 | [P00:DR-01] |
| **FR-03** | 寫入與變異型測試標記全面覆蓋 | 盤點所有建立 mock package、寫入 `module://`、修改 `config://` 的測試案例，100% 標註 `@require(Requirement.ISOLATED_SANDBOX)`，杜絕狀態外溢。 | P0 | [P00:DR-02] |
| **FR-04** | 多 Worker / 多進程並行安全相容 | 確保在 `dev test --all` 多 Worker 並行架構下，各 Worker 進程內部的 Session-Level 沙盒生命週期各自獨立，零鎖競爭與零路徑碰撞。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Suite 執行中斷或未經 TestRunner 執行時的殘留保護 | `YSCBTestCase.cleanup_shared_sandbox()` 提供安全的靜態/類別清理方法，且 `tearDownClass` 具備防禦性兜底能力，確保不外洩未清理目錄。 |
| **EC-02** | 測試失敗且指定 `--keep-sandbox` 時的現場保留 | 若測試失敗或開啟 `YSCB_TEST_KEEP_SANDBOX=1`，跳過沙盒目錄清理並印出保留路徑供除錯。 |
| **EC-03** | 測試方法修改 `sys.path` 或 `os.environ` | 每個測試方法（無論是否使用共用沙盒）在 `setUp` 時備份、`tearDown` 時 100% 剛性還原 `sys.path` 與 `os.environ`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 全系統回歸跑測 (`dev test --all`) 耗時大幅下降，平均單一測試執行耗時降至 $\le 0.03\text{s}$。 |
| **NFR-02** | 穩定性與回歸 | 全代碼庫 118+ 個測試案例維持 100% Passed (100% Ready)，無順序相依 Flaky Tests。 |
| **NFR-03** | 相容性 | 保持 Windows cp950 / UTF-8 編碼安全與無第三方套件依賴 (100% Python 標準庫)。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 知識庫參考**：查閱 `docs/dev/user_guide.md` §4.3 (測試沙盒模式指南) 與 §4.5 (三道防呆守門鎖)。
- **`[!CAUTION]` 狀態殘留防禦**：未標註 `ISOLATED_SANDBOX` 的測試若有隱蔽的檔案寫入，將影響後續測試；必須透過全量回歸與單獨隨機跑測驗證狀態純淨。
