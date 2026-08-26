# 變更摘要 (Walkthrough)

> 功能名稱：開發者測試框架與全自動契約回歸工作流 (Dev Testing Framework & Regression Workflow)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述

本子計畫成功建立了 YS-Codebase 核心測試框架 SDK **`dev.testing`** 與命令列測試引擎 **`dev test`**。深入借鑑 `uitk.net` 企業級測試架構精華並完成 Pythonic 特化：
1. **全自動標準規格契約守門 (Universal Auto-Contract)**：測試引擎自動對 `source/` 下所有模組動態合成並執行 3 大核心契約檢驗（Manifest Schema、進入點與簽名、純淨建置試跑），達成零樣板代碼、剛性不可跳過之品質守門；
2. **測試基礎類別 (`YSCBTestCase`)**：提供原生沙盒隔離、`sys.path`/`os.environ` 狀態 100% 歸零、失敗保留現場 (Preserve on Failure) 與專屬斷言庫；
3. **環境能力動態探測 (`@require`)**：動態探測環境能力，離線或未滿足時自動 `SkipTest` 優雅跳過，杜絕 CI 假性紅燈；
4. **全量回歸品質守門 (`dev test --all`)**：支援 4+1 測試分級，格式化輸出跨平台零亂碼之結構化 ASCII 報告與標準 Exit Code (0/1)。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :---: | :--- |
| [`ys_codebase/source/dev/dev/testing/requirement.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/requirement.py) | Add | 實作 `Requirement` (位元旗標) 與 `@require` 條件探測裝飾器 |
| [`ys_codebase/source/dev/dev/testing/case.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/case.py) | Add | 實作 `YSCBTestCase`（自動沙盒、狀態歸零、失敗保留、專屬斷言庫與 `run_cli`） |
| [`ys_codebase/source/dev/dev/testing/contract.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/contract.py) | Add | 實作 `BaseModuleContractTestCase` 與全自動契約工廠 `make_contract_suite` |
| [`ys_codebase/source/dev/dev/testing/runner.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py) | Add | 實作 `TestDiscovery`（兩階段組裝）、`TestRunner` 與 `ASCIIReportFormatter` |
| [`ys_codebase/source/dev/dev/testing/__init__.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/__init__.py) | Add | 匯出 `Requirement`, `require`, `YSCBTestCase`, `make_contract_suite`, `TestRunner` |
| [`ys_codebase/source/dev/dev/tester.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/tester.py) | Add | 實作 `Tester` 業務層分發與參數解析 (`--all`, `-k`, `--type`, `--contract-only`, `--verbose`) |
| [`ys_codebase/source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/builder.py) | Modify | 於 Layer 1 全域內建納入 `tests` 與 `tests/*` 排除規則 |
| [`ys_codebase/source/dev/scripts/cli.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/scripts/cli.py) | Modify | 擴充 `dev test` 命令路由進入點 |

---

## 3. 測試與品質驗證結果

- **自動化測試**：P06 測試矩陣 11 項測試案例（`FT-01` ~ `FT-07`, `ET-01` ~ `ET-03`, `PT-01`）**100% 通過（11/11 Passed）**。
- **UX / 手動驗證**：開發者於專案根目錄實機執行 `python yscb.py dev test --all` 驗證通過。
- **偏差記錄**：
  1. 契約測試全面升級為全自動動態合成模式 (`make_contract_suite`)，套件開發者零樣板代碼即可享有合規檢驗；
  2. `tests/` 正式納入 `Builder.GLOBAL_IGNORES` 全域內建排除清單；
  3. 報告格式化器採用通用 ASCII 連接符 (`|--`, `\--`) 確保跨平台終端零亂碼。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的 `docs/` 文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :--- | :--- | :--- |
| `docs/Dev/testing_framework.md` | ⏳ 排程於 sub_07 | 測試體系架構、4+1 測試運行階層、全自動契約守門與 `dev test` CLI | P03 §1, §2, §3 |
| `docs/Dev/writing_tests.md` | ⏳ 排程於 sub_07 | 套件開發者測試指南、`YSCBTestCase` 斷言庫與 `@require` 跳過範例 | P03 §2.1, §2.2 |
| `docs/Dev/DESIGN_NOTES.md` | ⏳ 排程於 sub_07 | 登記 `DN-03` 失敗沙盒保留機制與全自動契約動態合成坑點防護 | P02 DR-01, DR-02 |
| `docs/README.md` | ⏳ 排程於 sub_07 | 全域知識地圖同步更新模組狀態與索引 | 全域知識庫同步 |

---

## 5. 推薦 Commit 訊息

```text
feat(dev): implement testing framework SDK and automated contract regression workflow

- Implement dev.testing SDK with YSCBTestCase (automatic sandboxing & preserve-on-failure)
- Implement @require decorator with dynamic capability checking and SkipTest handling
- Implement universal automatic contract testing (make_contract_suite) with zero boilerplate
- Implement TestDiscovery, TestRunner, and ASCIIReportFormatter supporting 4+1 execution levels
- Add tests/ to Builder.GLOBAL_IGNORES for automatic exclusion from release builds
- Add dev test CLI command supporting single module, --all, -k pattern, and --contract-only
```
