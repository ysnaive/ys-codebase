# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：dev 測試架構優化 (Dev Test Architecture Optimization)  
> 建立日期：2026-08-27  
> 主計畫目錄：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Executing`  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面檢視、重構與優化 `dev` 模組的測試架構、沙盒生態與終端 UX，解決磁碟空間佔用、測試隔離、執行效率、型別安全防固、輸出結構與開發者體驗等系列問題。
- **架構邊界**：涵蓋 `dev` 模組測試工具鏈（`tester.py`、`sandbox.py`、`runner.py`、`case.py`、`checker.py` 等）以及全庫測試標準化遷移與 CLI 輸出視覺優化。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_residual_sandbox_cleanup` | Full Track | `Completed` | 殘留沙盒清理機制：建立殘留 sandbox 之清理、檢視與修剪工具鏈，防止測試失敗或調試保留之沙盒持續增量占用硬碟空間。 |
| **sub_02** | `sub_02_test_architecture_refinement` | Full Track | `Completed` | 測試架構完善：落實預設共用沙盒機制、`Requirement.ISOLATED_SANDBOX` 獨立沙盒分流，以及 `YSCB_TEST_SANDBOX` 測試模式 JIT 靜默防護（跑測加速 >50%）。 |
| **sub_03** | `sub_03_test_performance_optimization` | Full Track | `Completed` | 測試分類體系重構、效能深水區與沙盒型別安全防固：四層測試分類 (LOGIC/ENV/WORKFLOW/PERF)、--target 精準定位 (0.75s)、根除遞迴跑測、三道守門鎖與全庫 16 測試檔 100% YSCBTestCase 遷移。 |
| **sub_04** | `sub_04_test_cli_output_and_ux_optimization` | Full Track | `Completed` | dev test CLI 輸出結構與資訊優化：日誌緩衝捕獲 (`OutputCapturer`)、即時生命週期 Log、雙報表徹底根除、診斷報告元數據與失敗單點重測引導。 |
| **sub_05** | `sub_05_parallel_module_test_runner` | Full Track | `Completed` | 多進程多模組並行跑測：多 Worker 並行派發、獨立沙盒實例隔離 (`sandbox 1..N`)、即時交錯進度 Log、全庫四層測試分類細化標註與多模組診斷報告聚合。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (sub_01)**：完成殘留沙盒清理工具鏈與生命週期治理機制（滾動上限 3 個 + `test --all` 全量清空）。
- [x] **里程碑 2 (sub_02)**：完成沙盒共享分流與 URI JIT 測試靜默防護（跑測加速 >50%）。
- [x] **里程碑 3 (sub_03)**：完成四層測試分類體系、精準目標定位、三道防呆守門鎖與全庫測試標準化遷移（144/144 回歸通過且零外洩）。
- [x] **里程碑 4 (sub_04)**：完成 dev test CLI 終端輸出結構降噪、即時生命週期 Log、雙報表根除與單點重測引導 (147/147 Passed)。
- [x] **里程碑 5 (sub_05)**：完成多進程多模組並行跑測框架、線程安全沙盒、即時日誌串流與全庫四層測試分類細化標註 (120/120 Passed，加速 >42%)。

---

## 4. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 增量推進原則**：依開發者指示逐一拆分子計畫，先從影響硬碟空間與開發體驗最顯著的「殘留 sandbox 清理」開始推進。
- **[UMBRELLA:DR-02] sub_01 落地驗證**：已完成雙軌沙盒自動清理，全系統 134 測試回歸通過。
- **[UMBRELLA:DR-03] sub_02 落地驗證**：已完成預設共用沙盒、`ISOLATED_SANDBOX` 分流與 `YSCB_TEST_SANDBOX` JIT 防護，跑測加速 >50% (141/141 Passed)。
- **[UMBRELLA:DR-04] sub_03 落地驗證**：產出 R01/R02 專題調研報告，落地四層分類、--target 精準定位、三道守門鎖與全庫遷移，達成 144/144 Passed (100% Ready)。
- **[UMBRELLA:DR-05] sub_04 啟動**：啟動 CLI 終端輸出結構與資訊密度優化。
- **[UMBRELLA:DR-06] sub_04 落地驗證**：完成日誌緩衝捕獲、即時生命週期 Log、雙報表徹底根除與一鍵單點重測引導，全庫 147 測試 100% Passed。
- **[UMBRELLA:DR-07] sub_05 啟動**：啟動多進程多模組並行跑測架構設計與實作。
- **[UMBRELLA:DR-08] sub_05 落地驗證**：完成多 Worker 獨立沙盒並行調度、即時日誌串流、線程安全沙盒與全庫測試細化分類，全庫回歸由 ~24s 縮短至 13.7s (120/120 Passed)。
