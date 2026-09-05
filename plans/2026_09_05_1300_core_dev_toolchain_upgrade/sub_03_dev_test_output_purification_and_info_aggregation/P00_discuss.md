# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 接下來增量開啟 sub 03，dev test 信息純化，雖然現在有 -quiet 模式，但從 sub01 02 的開發過程，我發現還是產出許多無效資訊，分析歷史對話，規劃信息聚合策略 (不僅適用於 --quiet，同樣適用於一般模式)
- **核心目標**：
  1. **歷史痛點歸因**：深入分析 sub_01 與 sub_02 跑測歷程中的無效與噪訊資訊來源（包含沙盒內編譯器未解協議警告、子進程 stderr 穿透洩漏、瑣碎生命週期日誌交錯）。
  2. **信息聚合架構設計**：制定統一的信息聚合與淨化架構，不僅適用於 `--quiet` 節流模式，亦為一般模式（Normal Mode）提供結構化、分級收斂的輸出表現。
  3. **沙盒終端輸出完整屏蔽**：落實沙盒黑盒子原則，對沙盒內部終端輸出進行高保真捕獲與屏蔽，而非粗暴短路內部業務邏輯。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `dev test` 的測試探索演算法與 4-Tier 測試分類（Logic / Env / Workflow / Perf）。
  - 不短路沙盒內部真實業務邏輯或 JIT 自愈發布鉤子，維護沙盒高保真度。
  - 不阻斷真實測試失敗時的堆疊追蹤（Traceback）與 Quick Re-run 提示。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 恪守高保真沙盒原則，以「沙盒終端輸出完整屏蔽」取代業務短路 (Full Sandbox Terminal Output Shielding over Logic Short-Circuit)**：
  - *問題*：原先討論是否在沙盒內將 JIT 自動發布鉤子短路以消除警告，但此舉會人為破壞沙盒環境的高保真真實性（沙盒原意為 1:1 模擬真實執行期）。沙盒內產生的微內核日誌、未解 URI 警告或初始化訊息，本質上屬於沙盒內部黑盒子的運行雜訊。
  - *決策*：**嚴禁短路沙盒內的任何業務或鉤子邏輯**。回歸沙盒輸出屏蔽的設計初衷——由宿主調度器在調用沙盒子進程（`subprocess.run`）時，落實對沙盒內部 terminal 輸出（`res.stdout` 與 `res.stderr`）的完整捕獲、屏蔽與收斂。

- **[P00:DR-02] 統一 IPC 報告架構與單模組/循序子進程 stderr 洩漏修復 (Unified JSON IPC & Stderr Containment)**：
  - *問題*：`_run_parallel_test` 已具備 `if not quiet_mode: safe_print(res.stderr)` 防護，但 `_run_test` 卻直接無條件傾倒 `res.stderr`，破壞 `--quiet` 輸出契約；且 `_run_test` 依賴沙盒內部格式化報告向 stdout 列印，造成資料串流與雜散日誌混雜。
  - *決策*：
    1. 將單模組測試 (`_run_test`) 與平行測試 (`_run_parallel_test`) 的資料流統一：全面改採 `--report-json` 與 `--quiet-report`，由沙盒輸出純結構化資料，宿主調度器在外部集中控制渲染。
    2. 徹底修復 `_run_test` 無條件 `safe_print(res.stderr)` 的洩漏漏洞：在 `--quiet` 全數通過時嚴格保證 0 輸出；一般模式下未顯式指定 `--verbose` 時，將沙盒內部 stderr 進行計數折疊收斂，杜絕隨意傾倒。

- **[P00:DR-03] 雙模式信息聚合策略 (Dual-Mode Aggregation Strategy)**：
  - *決策*：
    1. **`--quiet` 模式**：
       - 通過：維持單行 `Pass: X(100.0%), Fail: 0, Skip: 0`，達到 100% 純淨與零 Token 浪費。
       - 失敗：單行統計 + 結構化 `FAILED / ERROR TEST CASES LIST`（含失敗訊息、行號、捕獲輸出與 Quick Re-run），其餘無關警告收斂。
    2. **一般模式 (Normal Mode)**：
       - 生命週期日誌結構化：將 `Pre-building...`、`Create sandbox...`、`Cleaned up sandbox...` 收斂為結構化前置摘要或單行進度指示。
       - 警告聚合分級：子進程中產生之一般警告（如 Python Warning、資源提示、未解 URI 等）進行計數收斂（如 `[!] Warnings: 28 notices (suppressed, run with --verbose to view)`），避免混雜打散測試診斷報告。
       - 測試通過提示收斂：消除亂碼提示字元，將安裝指示整併於 Report Summary 底部。

- **[P00:DR-04] 宿主沙盒穿透根因防護與剛性守門 (Anti-Sandbox-Leakage Guardrails)**：
  - *問題*：在 sub_02 開發排查期間曾執行 `python yscb.py dev op-test dev`，導致宿主 `source/`、`release/`、`config/` 及根目錄散落大量 `mock_*` 測試產物。經深度歸因發現兩大致命漏洞：
    1. `runner.py::TestRunner.run_suite` 內部竟主動設定 `os.environ["YSCB_TEST_SANDBOX"] = "1"`，導致若在宿主執行 `op-test` 時，`case.py` 的 Gate 3 安全守門直接被測試執行器自身偽造並繞過。
    2. `case.py::YSCBTestCase.setUp` 在向上尋找沙盒目錄失敗時，危險地回退為 `os.getcwd()`（宿主目錄），將 `sandbox_dir` 指向專案根目錄；且直接測試 `Builder`/`Releaser` 之用例直接操作真實 VFS。
  - *決策*：
    1. **移除偽造**：徹底移除 `TestRunner.run_suite` 內部設定 `YSCB_TEST_SANDBOX="1"` 之邏輯，該變數僅允許由真正建立沙盒之外層注入。
    2. **剛性路徑校驗**：`case.py::YSCBTestCase.setUp` 與 `SandboxContext` 必須嚴格檢驗沙盒路徑，若未解析出合法沙盒目錄，一律拋出 `SecurityError` 中斷，**絕對禁止回退到當前目錄 (`os.getcwd()`)**。
    3. **`dev op-test` 宿主守門**：若檢測到直接在宿主環境調用 `op-test`，直接阻斷並引導使用 `dev test`。
    4. **宿主殘留清理**：立即全面清理宿主環境因本次穿透遺留之 `mock_*` 產物。

---

## 3. 開放議題與確認紀錄

- [x] 是否同意以沙盒終端輸出完整屏蔽取代業務短路，維護沙盒高保真性？ -> 同意（維持沙盒真實性，由外層調度器收斂屏蔽）。
- [x] 是否同意統一單模組與平行測試之 IPC 報告架構（--report-json）？ -> 同意（徹底解耦沙盒 stdout 與報告輸出）。
- [x] 是否同意 `--quiet` 模式在全通情況下嚴格封閉 stderr 輸出？ -> 同意（對齊極致節流公理）。
- [x] 是否同意於 sub_03 落地 [P00:DR-04] 防呆機制徹底防堵沙盒穿透，並立即清除宿主殘留 mock 檔案？ -> 同意（剛性守門防污染）。
