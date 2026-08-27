# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：多進程多模組並行跑測 (Multi-Process Multi-Module Parallel Test Runner)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Completed`  
> 計畫類型：Performance / Concurrency / Test Architecture  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：`新子計畫，多進程/多 Worker 多模組並行跑測`
- **核心目標矩陣**：
  1. **[多進程並行執行 (Multi-Process Concurrency by Default)]**：
     - 在執行全庫跑測（`dev test --all`）或多模組跑測時，系統預設自動啟用多進程（Worker Processes）同時並行跑測不同模組，將總回歸時間縮短至單一最慢模組耗時（預計從 22.8s 降至 ~10s）。
     - 支援 `--sequential / --no-parallel` 回退至單進程順序執行以供特定情境除錯。
  2. **[獨立沙盒實例隔離 (Per-Worker Isolated Sandbox)]**：
     - 每個並行 Worker 獲取獨立的虛擬沙盒環境（`sandbox 1`、`sandbox 2`、`sandbox 3` ...），徹底避免跨進程檔案寫入與環境變數競爭衝突。
  3. **[並行度 Worker 數量控制 (Concurrency Limit & `-j` Flag)]**：
     - 預設最大 Worker 數為 `min(os.cpu_count(), len(modules))`。
     - 支援 `-j <N>`（或 `--jobs=<N>`）參數自訂最大 Worker 並行度。
  4. **[即時交錯進度 Log (Real-time Interleaved Output)]**：
     - 終端即時、交錯呈現各 Worker 沙盒的建立、模組開始與結束進度：
       - `[dev:test] Create sandbox 1 at: "..."`
       - `[dev:test] Create sandbox 2 at: "..."`
       - `[dev:test] agents-workflow begin test in sandbox 1`
       - `[dev:test] core begin test in sandbox 2`
       - `[dev:test] agents-workflow test finish in (2.85s)`
       - `[dev:test] core test finish in (9.20s)`
  5. **[多進程診斷報告聚合 (Aggregated Diagnostic Report)]**：
     - 各並行 Worker 完成後，主進程聚合所有模組的 `ModuleTestMetrics`、耗時與錯誤診斷，最終輸出單一格式化的 ASCII Diagnostic Report。
  6. **[差異化沙盒生命週期銷毀與失敗保留 (Granular Failure Preservation)]**：
     - 若其中特定模組測試失敗，僅保留該失敗模組所在的沙盒（例 `sandbox 2 preserved at: ...`），其餘通過之模組沙盒（`sandbox 1`, `sandbox 3`）正常銷毀清理。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 預設自動並行**：多模組跑測預設啟用多進程並行執行，提供 `--sequential / --no-parallel` 回退開關。
- **[P00:DR-02] Worker 並行度上限**：預設為 `min(os.cpu_count(), len(modules))`，支援 `-j <N>` 自訂並行度。
- **[P00:DR-03] 即時交錯 Log 流**：各 Worker 沙盒與跑測進度即時印出，保持極致透明度。
- **[P00:DR-04] 精細化失敗沙盒保留**：失敗時僅保留該失敗模組對應之沙盒實例，其餘正常清理。

---

## 3. 開放議題與確認紀錄

- [x] **Q1 (並行模式觸發策略)**：選項 A（預設自動並行，支援 `--sequential`）。
- [x] **Q2 (並行度 Worker 數量上限)**：預設 `min(os.cpu_count(), len(modules))`，支援 `-j <N>`。
- [x] **Q3 (即時進度呈現)**：即時交錯印出各沙盒進度。
- [x] **Q4 (沙盒生命週期與失敗保留)**：僅保留失敗模組的沙盒，通過模組自動銷毀。
