# 需求規格說明書 (Requirements Specification)

> 功能名稱：多進程多模組並行跑測 (Multi-Process Multi-Module Parallel Test Runner)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.4  

---

## 1. 需求背景與目標 (Background & Goals)

- **現況痛點**：
  1. `dev test --all` 雖然已在單模組內實作 Class-level 共用沙盒與四層分類篩選，但多模組間（`agents-workflow`、`core`、`dev`）依然為單進程順序阻塞執行（耗時 3s + 10s + 10s = ~23 秒）。
  2. 隨著專案模組數量增加，順序執行回歸耗時將呈現線性增長。
- **改進目標**：
  1. 實作多進程多模組並行測試調度器，預設自動啟用並行執行，將全庫回歸總耗時縮短至單一最慢模組耗時（由 ~23 秒壓至 **~10 秒以內**）。
  2. 每個並行 Worker 派發獨立虛擬沙盒（`sandbox 1`、`sandbox 2`、`sandbox 3`），達成完全無狀態污染與零檔案競爭。
  3. 即時交錯輸出各 Worker 沙盒進度 Log，並在全部完成後由主進程聚合產出單一格式化診斷報告。

---

## 2. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱與說明 | 優先級 | 驗收標準 (Acceptance Criteria) |
| :--- | :--- | :---: | :--- |
| **FR-01** | **多進程多模組並行跑測調度**<br/>在執行多模組跑測（`--all` 或多模組清單）時，預設自動以多 Worker 同時並行派發跑測任務。 | P0 | 多模組同時開始跑測，總回歸耗時顯著小於各模組耗時總和（約等於最慢模組耗時）。 |
| **FR-02** | **獨立虛擬沙盒實例分配與隔離**<br/>每個並行 Worker 獲取專屬的獨立沙盒目錄，環境變數 `YSCB_SANDBOX_ID="sandbox <N>"` 與 `YSCB_SANDBOX_INDEX=<N>` 隔離。 | P0 | 各 Worker 獨立寫入自身 `host_env`，零跨進程檔案鎖與競態衝突。 |
| **FR-03** | **並行度控制與順序回退開關**<br/>預設並行度為 `min(os.cpu_count(), len(modules))`，支援 `-j <N> / --jobs=<N>` 自訂；支援 `--sequential / --no-parallel` 回退單進程。 | P0 | 傳入 `-j 2` 時嚴格限制最大 2 個 Worker 並行；傳入 `--sequential` 時以單進程依序執行。 |
| **FR-04** | **即時交錯進度 Log 流**<br/>各 Worker 建立沙盒、開始測試與結束測試時，即時向控制台輸出標準 Log。 | P0 | 終端依序呈現 `Create sandbox 1..N`、`<mod> begin test in sandbox <N>` 與 `<mod> test finish in ({time}s)`。 |
| **FR-05** | **多進程診斷報告聚合**<br/>各 Worker 完成後，主進程聚合所有模組的結果，按原始模組順序輸出單一格式化的 ASCII Diagnostic Report。 | P0 | 終端最終輸出單一完整診斷報告，包含各模組耗時、分類計數與總結狀態。 |
| **FR-06** | **精細化沙盒生命週期銷毀與失敗保留**<br/>測試成功之模組沙盒即時/最終自動銷毀；若特定模組失敗，僅保留該失敗模組所在的沙盒目錄。 | P0 | 成功時銷毀所有沙盒，失敗時僅保留失敗模組的沙盒並印出路徑。 |

---

## 3. 例外與邊界條件 (Edge Cases)

| 邊界編號 | 邊界情境描述 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單模組跑測（例 `dev test core` 或帶 `--target`） | 自動退化為單沙盒直跑模式，不建立多 Worker 線程池。 |
| **EC-02** | 特定 Worker 遭遇未預期崩潰或 Subprocess 異常 | 主進程捕獲例外，將該模組標記為失敗，不影響其餘 Worker 正常跑測與報告聚合。 |
| **EC-03** | CPU 核心數小於模組數（例 `-j 2` 跑 3 模組） | 線程池佇列依序派發，釋放之 Worker 立即接續執行下一個模組。 |

---

## 4. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 維度 | 約束條件與指標 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 全庫 3 模組並行回歸總耗時小於 12 秒（相比順序執行加速 >45%）。 |
| **NFR-02** | 執行安全性 | 零進程間競態、零檔案寫入衝突、跨平台（Windows / Linux / macOS）並行無損。 |
