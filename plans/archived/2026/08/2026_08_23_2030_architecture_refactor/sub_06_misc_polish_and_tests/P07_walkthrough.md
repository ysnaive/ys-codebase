# 變更摘要 (Walkthrough)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述

本子計畫（`sub_06`）完成了微內核核心機制的缺口補齊 (Gap 1~5)，包含遠端 Provider 清冊批次下載、動態 SemVer 版本探測升級、跨進程排他檔案鎖（含 10s 逾時自癒）、Contributes 5 大來源多層合併與宿主單檔 `self-update`。同時建立並落地 `source/core/tests/` 與 `source/dev/tests/` 官方持久化標準測試套件（8 大 Suites, 22 Custom Tests），並確立 `temp://sandbox_<uuid>` 純淨沙盒生命週期，達成全量回歸測試 28/28 Passed (0.370s) 且主機環境零污染。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :---: | :--- |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 實作遠端清冊批次下載 (`act_download`) 與跨進程排他鎖 (`act_lock` / `act_unlock`) |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 實作動態版本查詢與 SemVer 升級 (`cmd_update`)，固化 Provider 解析階層與鎖保護 |
| [`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/contributes.py) | Modify | 實作 5 大來源深度字典合併與注入機制 |
| [`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/contributes.format.md) | Add | 交付 Core 貢獻擴充格式規範說明書 |
| [`source/core/config.project.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/config.project.json) | Add | 交付專案層級標準組態範本 |
| [`source/dev/dev/testing/case.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/case.py) | Modify | 實作 `temp://sandbox_<uuid>` 隔離沙盒生命週期與失敗保留策略 |
| [`source/dev/dev/testing/runner.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py) | Modify | 修復 `TestDiscovery` 跨模組 `tests` 命名空間快取殘留衝突問題 |
| [`source/dev/dev/scaffold.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/scaffold.py) | Modify | 支援 `desc` 參數別名與模組建立範本格式化 |
| [`source/core/tests/test_uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_uri.py) | Add | Core 官方標準測試：VFS 原子 I/O 與語意 URI 解析 (4 Cases) |
| [`source/core/tests/test_engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_engine.py) | Add | Core 官方標準測試：快照還原、跨進程鎖與下載異常 (3 Cases) |
| [`source/core/tests/test_installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_installer.py) | Add | Core 官方標準測試：套件管理指令、保護防護與健康診斷 (3 Cases) |
| [`source/core/tests/test_contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_contributes.py) | Add | Core 官方標準測試：5 大來源合併與字典遞迴合併 (2 Cases) |
| [`source/dev/tests/test_scaffold.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/test_scaffold.py) | Add | Dev 官方標準測試：模組腳手架建立與防呆 (2 Cases) |
| [`source/dev/tests/test_checker.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/test_checker.py) | Add | Dev 官方標準測試：AST 語法校驗與 Schema 檢查 (3 Cases) |
| [`source/dev/tests/test_builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/test_builder.py) | Add | Dev 官方標準測試：純淨打包與 Layer 1 tests 排除斷言 (2 Cases) |
| [`source/dev/tests/test_tester.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/test_tester.py) | Add | Dev 官方標準測試：契約合成、兩階段探索與 CLI 派發 (3 Cases) |

---

## 3. 測試與品質驗證結果

- **自動化測試**：全量測試 100% 通過（共 28 項測試：6 項 Auto-Contract 契約測試 + 22 項持久化自訂測試，實測耗時 0.370s）
- **UX / 手動驗證**：開發者已於終端實機執行 `python yscb.py dev test --all --verbose` 確認通過 (Status: PASSED 100% Ready)
- **偏差記錄**：
  1. 解決了跨模組 `tests` 模組在 `sys.modules` 中殘留導致的命名空間衝突；
  2. 解決了測試快照還原時曾一度調用 `clean_stage` 清空主機 `modules/` 的問題，修正為標準 `temp://sandbox_<uuid>` 隔離模式，杜絕測試污染。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的規範/規格文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/contributes.format.md) | ✅ 已交付 | 定義 `path_placeholders`、`uri_schemes`、`events` 宣告格式與 Schema | P03 §2.1 / P06 FT-04 |
| [`source/core/config.project.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/config.project.json) | ✅ 已交付 | 專案層級標準組態範本，定義路徑別名與模組偏好設定 | P03 §2.2 / P06 FT-05 |
| [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/) | ✅ 已交付 | 交付 4 大持久化標準測試檔案，涵蓋 URI、Engine、Installer、Contributes | P03 §3.1 / P06 FT-06 |
| [`source/dev/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/) | ✅ 已交付 | 交付 4 大持久化標準測試檔案，涵蓋 Scaffold、Checker、Builder、Tester | P03 §3.2 / P06 FT-07 |

---

## 5. 推薦 Commit 訊息

```text
feat(core,dev): polish core mechanisms and establish standard persistent test suites

- implement remote batch download, dynamic SemVer update, and inter-process locking in core
- deliver contributes.format.md and config.project.json templates
- establish official persistent test suites in source/core/tests/ and source/dev/tests/
- enforce temp://sandbox_<uuid> isolation in YSCBTestCase to prevent host pollution
- achieve 28/28 automated regression tests passed (0.370s)
```
