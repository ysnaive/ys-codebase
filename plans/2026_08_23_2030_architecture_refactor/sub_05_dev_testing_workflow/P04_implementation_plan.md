# 最終實作計畫書 (Implementation Plan)

> 功能名稱：開發者測試框架與全自動契約回歸工作流 (Dev Testing Framework & Regression Workflow)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P01 / P02 / P03：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md) / [P03_api_spec.md](./P03_api_spec.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.4

---

## 1. 實作任務拆解 (Implementation Tasks)

| 任務編號 | 檔案路徑 | 變更類型 | 實作內容與驗收要點 | 依賴 |
| :--- | :--- | :---: | :--- | :--- |
| **TASK-01** | [`source/dev/dev/testing/require.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/require.py) | NEW | 實作 `Requirement` (Flag enum: `NONE`, `SANDBOX`, `HOST_CLI`, `NETWORK`) 與 `@require` 條件裝飾器，未滿足時自動 `unittest.SkipTest`。 | - |
| **TASK-02** | [`source/dev/dev/testing/case.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/case.py) | NEW | 實作 `YSCBTestCase`：`setUp`/`tearDown` 環境備份恢復、沙盒生命週期（通過清理、失敗保留）、專屬斷言庫 (`assertSuccess`, `assertInOutput`, `assertFileExists`, `assertJsonEquals`) 與 `run_cli`。 | TASK-01 |
| **TASK-03** | [`source/dev/dev/testing/contract.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/contract.py) | NEW | 實作 `BaseModuleContractTestCase` 與全自動契約工廠 `make_contract_suite(module_name)`，覆蓋 4 大標準契約檢驗。 | TASK-02 |
| **TASK-04** | [`source/dev/dev/testing/runner.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py) | NEW | 實作 `TestDiscovery`（兩階段動態組裝：Auto-Contract ➔ Custom Tests）、`TestRunner` 與 `ASCIIReportFormatter`。 | TASK-03 |
| **TASK-05** | [`source/dev/dev/testing/__init__.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/__init__.py) | NEW | 套件頂層匯出 `YSCBTestCase`, `require`, `Requirement`, `ModuleContractTestCase`, `make_contract_suite`, `TestRunner`。 | TASK-04 |
| **TASK-06** | [`source/dev/dev/tester.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/tester.py) | NEW | 實作 `Tester` 業務層類別，負責解析 CLI 參數並調用 `runner` 執行。 | TASK-05 |
| **TASK-07** | [`source/dev/scripts/cli.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/scripts/cli.py) | MODIFY | 擴充 `dev test` 命令路由，派發至 `Tester().run(argv)`。 | TASK-06 |
| **TASK-08** | [`sandbox/run_sub05_tests.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/sandbox/run_sub05_tests.py) | NEW | 於 `./sandbox/` 建立實機測試腳本，執行 P06 矩陣 11 項測試案例 (FT-01~07, ET-01~03, PT-01) 100% 驗證。 | TASK-07 |
| **TASK-09** | [`ys_codebase/build/dev/1.0.0/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/build/dev/1.0.0) | BUILD | 執行 `python yscb.py dev build dev` 純淨建置並物化部署至 `modules/dev/`。 | TASK-08 |

---

## 2. 預排知識庫文檔衝擊清單 (Documentation Delivery Schedule)

> 依據主計畫架構藍圖，知識庫文檔將於 `sub_07_core_docs_update` 集中進行綠地重建，本計畫預排之衝擊錨點如下：

| 預排文檔路徑 | 異動類型 | 預排章節與核心內容 | 對應 API / 驗收錨點 |
| :--- | :---: | :--- | :--- |
| `docs/Dev/testing_framework.md` | 新建 | 測試體系概述、4+1 測試運行階層、全自動契約守門與 `dev test` CLI 用法 | P03 §1, §2, §3 |
| `docs/Dev/writing_tests.md` | 新建 | 套件開發者測試撰寫指南、`YSCBTestCase` 斷言庫與 `@require` 條件跳過範例 | P03 §2.1, §2.2 |
| `docs/Dev/DESIGN_NOTES.md` | 更新 | 登記 `DN-03` 失敗沙盒保留機制與全自動契約動態合成坑點防護 | P02 DR-01, DR-02 |

---

## 3. 實施階段與驗證順序 (Execution Flow)

1. **Phase 5 (實作與編譯)**：依序實作 `TASK-01` ~ `TASK-07`，完成 `dev.testing` 套件與 `dev test` CLI 派發。
2. **Phase 6 (驗證與守門)**：執行 `TASK-08`，於 `./sandbox/` 運行 11 項全量自動化測試矩陣（維持 `source/*/tests/` 零污染）；隨後進行開發者手動 UX 驗證。
3. **Phase 7 (交付結案)**：執行 `TASK-09` 純淨建置 `dev@1.0.0`，物化更新至 `modules/dev`，產出 `P07_walkthrough.md` 結案。
