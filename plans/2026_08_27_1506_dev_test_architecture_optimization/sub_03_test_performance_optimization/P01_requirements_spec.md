# 需求規格說明書 (Requirements Specification)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 系統功能需求 (Functional Requirements)

| 需求編號 | 功能名稱 | 詳細需求描述 | 優先級 | 對應 P00 決策 |
| :--- | :--- | :--- | :---: | :---: |
| **FR-01** | 四層測試分類與正交標籤 | 在 `dev.testing.requirement` 重構列舉：定義 `LOGIC` (純邏輯)、`ENV` (環境/跨模組)、`WORKFLOW` (工作流/E2E)、`PERF` (效能/壓力)，並保留 `ISOLATED_SANDBOX` 作為正交隔離標籤。 | P0 | [P00:DR-03] |
| **FR-02** | 預設過濾原則與 CLI 分類旗標 | `dev test` 與 `dev test --all` 預設僅執行 `LOGIC` + `ENV` 測試；支援顯式旗標 `--logical`、`--env`、`--workflow`、`--perf` 與 `--all-types`。 | P0 | [P00:DR-03] |
| **FR-03** | 精準目標選擇器 `--target` | 支援 `--target=<module>:[<file_or_class>][.<method>]` 語法，允許精確定位單一模組、測試類別或測試方法執行。 | P0 | [P00:DR-04] |
| **FR-04** | 三道防呆守門鎖 (Triple-Lock) | ① `dev check` 靜態 AST 檢查禁止原生 `unittest.TestCase`；② `TestDiscovery` 動態 `isinstance(test, YSCBTestCase)` 守門；③ `YSCBTestCase.setUp()` 檢測宿主裸跑直接拋出 `SecurityError` 強制阻斷。 | P0 | [P00:DR-02] |
| **FR-05** | 全庫測試 100% 標準化遷移 | 將全庫 16 個測試檔案中剩餘 12 個使用原生 `unittest` 之測試檔案全面改寫為繼承 `YSCBTestCase`，並標記精確的 `@require` 分類。 | P0 | [P00:DR-02] |
| **FR-06** | 根除遞迴跑測與多模組並行 | ① 重構 `test_release_pipeline.py`，消除 `release_git` 內部重複跑測 `core` 的問題；② `dev test --all` 支援多行程並行跑測（`ProcessPoolExecutor`）。 | P0 | [P00:DR-01] |

---

## 2. 邊界條件與例外處理 (Edge Cases & Constraints)

| 編號 | 邊界 / 例外情境 | 系統行為規範與防呆機制 |
| :--- | :--- | :--- |
| **EC-01** | 未標記任何 `@require` 之測試方法 | 預設自動歸類為 `LOGIC` 測試，納入預設跑測清單，確保向後相容。 |
| **EC-02** | 指定 `--target` 執行特定 `WORKFLOW` 或 `PERF` 測試 | 當使用者顯式指定 `--target` 時，跳過預設略過規則，直接執行該目標測試。 |
| **EC-03** | 非標準入口（IDE / 裸 Python）直跑測試 | `YSCBTestCase.setUp()` 立即拋出 `SecurityError` 阻斷，並印出友善引導指示使用 `python yscb.py dev test`。 |
| **EC-04** | 多模組並行跑測沙盒衝突 | 每個並行行程建立唯一 UUID 之虛擬沙盒，目錄與日誌完全隔離，全部結束後統一清空。 |

---

## 3. 非功能性需求 (Non-Functional Requirements)

- **NFR-01 (極速回歸效能)**：全模組回歸跑測（`LOGIC` + `ENV` 預設回歸）總耗時壓進 **8 秒以內**。
- **NFR-02 (絕對零外洩)**：任何測試執行在任何情境下 100% 困在沙盒中，零污染宿主 `config/` 與 `release/`。
- **NFR-03 (向後相容)**：既有 `dev test <module>` 與 `-k <pattern>` 語法維持相容。
