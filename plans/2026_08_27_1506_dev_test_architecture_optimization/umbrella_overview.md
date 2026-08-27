# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：dev 測試架構優化 (Dev Test Architecture Optimization)  
> 建立日期：2026-08-27  
> 主計畫目錄：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：進行中 (sub_01, sub_02 已結案, sub_03 討論中)  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面檢視、重構與優化 `dev` 模組的測試架構與沙盒生態，解決磁碟空間佔用、測試隔離、執行效率與開發者體驗等系列問題。
- **架構邊界**：涵蓋 `dev` 模組測試工具鏈（`tester.py`、`sandbox.py`、`runner.py` 等），不破壞既有對外相容契約。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_residual_sandbox_cleanup` | Full Track | `Completed` | 殘留沙盒清理機制：建立殘留 sandbox 之清理、檢視與修剪工具鏈，防止測試失敗或調試保留之沙盒持續增量占用硬碟空間。 |
| **sub_02** | `sub_02_test_architecture_refinement` | Full Track | `Completed` | 測試架構完善：落實預設共用沙盒機制、`Requirement.ISOLATED_SANDBOX` 獨立沙盒分流，以及 `YSCB_TEST_SANDBOX` 測試模式 JIT 靜默防護。 |
| **sub_03** | `sub_03_test_performance_optimization` | Full Track | `Discussing` | 測試效能深水區與沙盒型別安全防固：落實 `YSCBTestCase` 剛性型別守門（禁止原生 `unittest.TestCase` 根治沙盒外洩）與發布測試重複跑測優化。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (sub_01)**：完成殘留沙盒清理工具鏈與生命週期治理機制（滾動上限 3 個 + `test --all` 全量清空）。
- [x] **里程碑 2 (sub_02)**：完成沙盒共享分流與 URI JIT 測試靜默防護（跑測加速 >50%）。
- [ ] **里程碑 3 (sub_03)**：完成 `YSCBTestCase` 剛性型別守門與效能瓶頸優化（目標全量跑測降至 15s 內且零外洩）。

---

## 4. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 增量推進原則**：依開發者指示逐一拆分子計畫，先從影響硬碟空間與開發體驗最顯著的「殘留 sandbox 清理」開始推進。
- **[UMBRELLA:DR-02] sub_01 落地驗證**：已完成雙軌沙盒自動清理，全系統 134 測試回歸通過。
- **[UMBRELLA:DR-03] sub_02 落地驗證**：已完成預設共用沙盒、`ISOLATED_SANDBOX` 分流與 `YSCB_TEST_SANDBOX` JIT 防護，跑測加速 >50% (141/141 Passed)。
- **[UMBRELLA:DR-04] sub_03 啟動調研與型別安全定義**：完成 141 測試耗時量測與型別守門需求納入。
