# 需求規格說明書 (Requirements Specification)

> 功能名稱：dev test CLI 輸出結構與資訊優化 (Dev Test CLI Output & UX Optimization)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.4  

---

## 1. 需求背景與目標 (Background & Goals)

- **現況痛點**：
  1. 測試執行期間，各模組單元測試內部調用 `cli.main()`、Hook 或 Mock 產生的未捕獲 stdout/stderr 會直接穿透至終端，造成大量控制台雜訊。
  2. 診斷報告未呈現四層分類（`LOGIC`, `ENV`, `WORKFLOW`, `PERF`）細分統計與模組獨立耗時。
  3. 測試失敗時缺乏結構化錯誤分析與一鍵快速重測引導。
  4. 巢狀 `_run_test` 呼叫導致終端印出兩份診斷報告。
  5. 跑測過程缺乏生命週期即時進度提示（如沙盒建立、模組測試進展等）。
- **改進目標**：
  1. 實作執行過程 stdout/stderr 緩衝捕獲，預設靜默降噪。
  2. 升級 `ASCIIReportFormatter`，豐富化過濾元數據、模組耗時與分類細分計數。
  3. 提供結構化失敗診斷與 `--target` 單點快速重測指令。
  4. 根除雙報表問題，並提供清晰的跑測生命週期進度 Log。

---

## 2. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱與說明 | 優先級 | 驗收標準 (Acceptance Criteria) |
| :--- | :--- | :---: | :--- |
| **FR-01** | **執行過程中間輸出緩衝捕獲與靜默降噪**<br/>在跑測期間將 stdout/stderr 重導向至記憶體緩衝區，常態保持終端極致乾淨。 | P0 | 跑測過程中無未捕獲之中間日誌穿透；僅在測試失敗或指定 `--verbose` 時印出捕獲日誌。 |
| **FR-02** | **診斷報告頂部過濾與執行元數據**<br/>在報告開頭呈現過濾模式、目標範圍與構建狀態。 | P1 | 報告頂部清晰展示 `Filter: [...] | Target: ... | Build: ...`。 |
| **FR-03** | **各模組獨立耗時與四層分類細分統計**<br/>在模組列顯示獨立執行耗時，在 Custom 節點展示四層分類通過數量。 | P0 | 模組標題呈現耗時（例 `(0.65s)`），Custom 節點呈現 `[Logic: X, Env: Y]`。 |
| **FR-04** | **結構化失敗診斷與單點快速重測引導**<br/>失敗時結構化呈現錯誤位置、斷言摘要、沙盒路徑與單點重測指令。 | P0 | 失敗區塊精確提供 `Re-run: python yscb.py dev test --target=...`。 |
| **FR-05** | **`--verbose / -v` 旗標支援**<br/>支援 verbose 參數，啟用時展開每個測試方法之即時執行狀態與輸出。 | P1 | 傳入 `-v` 或 `--verbose` 時，關閉靜默捕獲並呈現詳細執行資訊。 |
| **FR-06** | **跑測生命週期即時進度 Log**<br/>在建置、沙盒生成、各模組跑測與沙盒清理階段輸出標準提示。 | P0 | 終端依序呈現 `[dev:test] Provisioning...`, `[dev:test] Testing module '...'...` 等進度。 |
| **FR-07** | **子行程輸出捕獲與雙報表根除**<br/>`_run_test` 捕獲子行程輸出，在巢狀情境下抑制輸出，確保終端僅輸出 1 份最終報表。 | P0 | 執行 `dev test --all` 終端嚴格僅顯示 1 份完整診斷報告。 |

---

## 3. 例外與邊界條件 (Edge Cases)

| 邊界編號 | 邊界情境描述 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 模組無 Custom 測試案例（僅有 Contract 測試） | Custom 節點優雅顯示 `(No custom tests)`，不顯示空分類標籤。 |
| **EC-02** | 測試捕獲之輸出過長（>100 行） | 失敗展示時智能截斷，僅呈現關鍵前 20 行與後 50 行，避免終端洗版。 |
| **EC-03** | 測試進程崩潰或未捕獲之 Fatal Exception | 捕獲器確保於 `finally` 區塊無損還原 `sys.stdout` 與 `sys.stderr`。 |

---

## 4. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 維度 | 約束條件與指標 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 | 緩衝捕獲與報表格式化對整體跑測時間增加小於 1%。 |
| **NFR-02** | 跨平台視覺相容性 | ASCII 排版與符號在 Windows PowerShell、cmd、Linux、macOS 終端均保持對齊無亂碼。 |
