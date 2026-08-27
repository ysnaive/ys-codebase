# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 計畫類型：Refactor / Feature / Testing  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 細化測試分類，於 `requirement` 中定義 "獨立沙盒" flag，現不具備此 flag 的話，將使用同一個沙盒運行測試。
  2. URI 未定義路徑 JIT 注入互動，跑 test 時即使測試目的就是要其失敗，但途中觸發該 JIT 機制導致工作流被打斷，體驗不佳。
  3. 將測試環境識別之環境變數名稱統一定義為 **`YSCB_TEST_SANDBOX`**。
  4. 釐清與確認：任何模組調用 URI 解譯在一般日常運行時維持預設 JIT 互動（保持工具體驗），僅在自動化測試執行時因 `YSCB_TEST_SANDBOX` 標誌靜默跳過 JIT 提示並拋出 `UndefinedURIError`。
- **核心目標**：
  1. **細化測試沙盒分類 (Requirement.ISOLATED_SANDBOX)**：
     - 在 `dev.testing.requirement` 定義 `ISOLATED_SANDBOX` flag。
     - **預設共用沙盒機制**：未標記 `ISOLATED_SANDBOX` 之測試方法，預設於同一 `TestCase` 類別內**共用同一個沙盒實例**（減少高頻 I/O 與目錄複製開銷，大幅提升跑測效能）。
     - **獨立沙盒機制**：標記 `@require(Requirement.ISOLATED_SANDBOX)` 之測試方法，維持 Per-Method 獨立專屬乾淨沙盒，於 `setUp` 建立、`tearDown` 清理。
  2. **測試環境 JIT 互動靜默阻斷 (`YSCB_TEST_SANDBOX`)**：
     - **日常 CLI 運行（維持現狀）**：`uri.resolve` 維持預設 `interactive=True`，遇到 `!undefined` 時正常觸發 JIT 終端互動，無縫引導使用者設定路徑並自動寫回設定檔。
     - **自動化測試環境（靜默跳過）**：當處於測試環境（`YSCBTestCase`、`dev test` 或 `dev op-test`）時，測試框架自動注入 `YSCB_TEST_SANDBOX=1`。`core.uri.reconcile_undefined_uri` 檢測到 `YSCB_TEST_SANDBOX=1` 時靜默跳過 `input()` 提示，直接拋出結構化 `UndefinedURIError`，確保測試流程 100% 流暢。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更一般日常 CLI 下 `uri.resolve` 的 JIT 互動行為與預設值。
  - 不變更既有 `dev test` 的外部 CLI 調用介面。
  - 確保所有既有模組測試案例 100% 相容與綠燈。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Requirement 標記定義**：新增 `Requirement.ISOLATED_SANDBOX = auto()`，與既有 `LOGIC`, `HOST_CLI`, `NETWORK` 保持 Flag 組合相容。
- **[P00:DR-02] 沙盒共享生命週期**：
  - 於 `YSCBTestCase` 實作智慧沙盒管理：若當前測試方法無 `ISOLATED_SANDBOX`，則複用 Class-level / Suite-level 沙盒；若具備 `ISOLATED_SANDBOX`，則建立獨立沙盒並於測試後釋放。
- **[P00:DR-03] 測試環境環境變數命名與 URI 測試防護**：
  - 統一定義環境變數名稱為 **`YSCB_TEST_SANDBOX=1`**。
  - `core.uri.reconcile_undefined_uri` 增加 `os.environ.get("YSCB_TEST_SANDBOX") == "1"` 檢測。當檢測到此標誌時，視為非互動測試環境，靜默阻斷 JIT 鍵盤提示並直接拋出 `UndefinedURIError`。
  - `YSCBTestCase.setUp` 與 `TestRunner` / `Tester` 於測試啟動時設置 `YSCB_TEST_SANDBOX=1`（並在 `run_cli` 子行程中透傳）。

---

## 3. 開放議題與確認紀錄

- [x] Phase 0-R 現行架構全景調研完成（[R01_current_test_architecture_investigation.md](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_1506_dev_test_architecture_optimization/sub_02_test_architecture_refinement/R01_current_test_architecture_investigation.md)）。
- [x] 確定環境變數名稱為 `YSCB_TEST_SANDBOX`。
- [ ] 請開發者確認本階段內容無誤，指示是否可推進至 Phase 1。
