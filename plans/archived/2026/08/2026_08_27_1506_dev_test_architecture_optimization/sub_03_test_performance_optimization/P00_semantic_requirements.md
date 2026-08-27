# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 計畫類型：Architecture / Security / Testing / Performance  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 遞迴調用跑測問題必須徹底解決，不該出現測試內部又遞迴調用 `dev test` 的狀況。
  2. 建立細部的測試四層分類體系（邏輯測試、環境測試、工作流測試、壓力測試），預設跑測僅執行「邏輯測試」與「環境測試」，「工作流測試」與「壓力測試」預設略過。
  3. `dev test` CLI 支援對應的分類旗標（`--logical`, `--env`, `--workflow`, `--perf`）與精準目標選擇器（`--target=module:test_xxx`）。
  4. 支援多模組並行跑測（`dev test --all` 平行化調度）。
  5. 剛性禁止原生 `unittest.TestCase`，全面遷移至 `YSCBTestCase` 並落實非標準入口（宿主直跑）強制阻斷。

- **核心目標矩陣**：
  1. **[四層測試分類體系 (Test Taxonomy)]**：
     - **邏輯測試 (`Requirement.LOGIC`)**：純內部邏輯、無外部依賴、自我完備（預設執行）。
     - **環境測試 (`Requirement.ENV`)**：涉及跨模組連動、依賴注入 (DI)、VFS 虛擬檔案系統、外部 CLI 調用等（預設執行）。
     - **工作流測試 (`Requirement.WORKFLOW`)**：組合多個原子操作的高階端到端流水線（如 `release_git`），除錯時僅需驗證流程，**預設略過**。
     - **壓力測試 (`Requirement.PERF` / `STRESS`)**：效能基準、高負載、大型 ZIP/磁碟 I/O 等，**預設略過**。
     - **沙盒標籤正交化 (`Requirement.ISOLATED_SANDBOX`)**：獨立沙盒需求作為正交標籤，可自由與上述四類組合。
  2. **[CLI 參數與目標定位增強]**：
     - 分類過濾：`--logical`, `--env`, `--workflow`, `--perf`, `--all-types`。
     - 目標精確定位：`--target=<mod>:<case_or_method>`（例：`--target=dev:test_builder` 或 `--target=core:TestCoreURI.test_resolve`）。
  3. **[根除遞迴跑測與多模組並行]**：
     - 徹底消除 `release_git` 等測試中的遞迴子行程跑測。
     - `dev test --all` 支援多行程並行跑測（`agents-workflow`、`core`、`dev` 平行化）。
  4. **[三道防呆守門鎖 (Triple-Lock Guard)]**：
     - 靜態 AST 合規檢查（`dev check` 禁止原生 `unittest.TestCase`）。
     - 動態載入型別驗證（`TestDiscovery` 執行 `isinstance(test, YSCBTestCase)` 斷言）。
     - 非標準入口（宿主裸跑）強制阻斷（`YSCBTestCase.setUp` 檢測非沙盒環境直接報錯終止）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Phase 0-R 耗時調研前置**：以 `R01_test_execution_bottleneck_investigation.md` 作為測試耗時瓶頸之量測基準。
- **[P00:DR-02] 剛性型別守門與宿主裸跑阻斷**：以 `R02_sandbox_isolation_and_type_safety_investigation.md` 確立三道守門鎖與全庫 100% 遷移至 `YSCBTestCase`。
- **[P00:DR-03] 四層測試分類與預設過濾原則**：
  - 預設模式（`dev test` 與 `dev test --all`）：僅執行 `LOGIC` + `ENV`（快速回歸）。
  - 進階模式：`WORKFLOW` 與 `PERF` 需顯式加上 `--workflow`、`--perf` 或 `--all-types` 方觸發。
- **[P00:DR-04] 精準定位語法標準**：支援 `--target=<module>:[<file_or_class>][.<method>]` 語法，大幅提升單點調試體驗。

---

## 3. 開放議題與確認紀錄

- [x] 完成全系統耗時量測與 `R01` 報告產出。
- [x] 完成沙盒隔離漏洞與三道守門鎖 `R02` 報告產出。
- [x] 完整定義四層測試分類、CLI 旗標與精準目標定位需求。
- [ ] 待開發者最終確認本 P00，呈遞分流層級建議以推進至 Phase 1。
