# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：dev test CLI 輸出結構與資訊優化 (Dev Test CLI Output & UX Optimization)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 計畫類型：CLI / UX / Diagnostic Reporting  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：`dev test cli 輸出結構與資訊優化`、`方案 A，並解加入 Test 架構的進度 log (建立沙盒:... , 開始運行 <mod> Test... etc.)`
- **核心目標矩陣**：
  1. **[執行過程中間雜訊降噪 (Process Noise Suppression)]**：
     - 在跑測過程中預設對進程與子行程之 stdout/stderr 進行緩衝捕獲（Capture & Buffer）。
     - 常態保持終端極致乾淨，僅在測試真正失敗或帶有 `--verbose / -v` 時展開印出捕獲之日誌與堆疊。
  2. **[雙報表消除與子進程捕獲隔離 (Dual Report Elimination & Nested Isolation)]**：
     - 在 `Tester._run_test()` 捕獲子行程輸出，並在巢狀測試情境 (`YSCB_TEST_SANDBOX=1` / `YSCB_NESTED_TEST=1`) 下靜默輸出，徹底終結兩份表格問題。
  3. **[跑測生命週期進度提示 (Real-time Lifecycle Progress Logs)]**：
     - 提供清晰即時的進度回饋：
       - `[dev:test] Pre-building modules for test execution...`
       - `[dev:test] Provisioning virtual test sandbox...`
       - `[dev:test] Testing module '<mod>'...`
       - `[dev:test] Cleaning up virtual test sandbox...`
  4. **[診斷報告結構與分類指標 (Diagnostic Report Taxonomy & Metrics)]**：
     - 在報告開頭呈現**跑測過濾狀態**（例：`Filter: [LOGIC, ENV] | Target: All | Build: Hermetic Build`）。
     - 在各模組列呈現**獨立執行耗時**（例：`[*] Module: core (0.65s) [PASS]`）。
     - 在 Custom 測試樹狀節點展示**四層分類細分統計**（例：`\-- [Custom] (67/67) [Logic: 52, Env: 15]`）。
  5. **[失敗診斷與單點重測引導 (Failure UX & Quick Re-run)]**：
     - 失敗時結構化呈現出錯位置、行號、斷言訊息與現場保留之沙盒路徑。
     - 自動生成並印出該失敗測試之一鍵單點重測指令（例：`Re-run: python yscb.py dev test --target=...`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 中間雜訊捕獲與靜默降噪**：跑測期間預設重導向/緩衝測試執行中產生的標準輸出與標準錯誤，消除 Hook、Mock 與原子命令產生的控制台雜訊。
- **[P00:DR-02] 診斷報告豐富化**：在 `ASCIIReportFormatter` 中整合四層分類維度計數、模組耗時與過濾模式元數據。
- **[P00:DR-03] 失敗診斷與單點重測引導**：失敗時輸出清晰的診斷區塊並附帶 `--target` 快速重測指令。
- **[P00:DR-04] 雙報表根除與生命週期即時進度 Log**：採納方案 A，子行程標準輸出安全捕獲並進行巢狀隔離，加入沙盒建立、模組跑測與清理之即時進度反饋。

---

## 3. 開放議題與確認紀錄

- [x] 完成四大輸出結構與 UX 優化方向收斂（降噪捕獲、報告維度、重測引導、生命週期進度與雙報表根除）。
