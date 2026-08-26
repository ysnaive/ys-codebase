# 成果展示與結案報告 (Walkthrough)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

本子計畫徹底解決了 YS-Codebase 歷史演進中模組資料空間語意不清、`*.root://` 與常規協議二義性、`temp` 與 `cache` 職責重複、以及 `agents-workflow` 發布清冊寫入 `storage/core/agents-workflow` 雙重嵌套等架構缺陷。

- **核心功能落地**：
  1. **方案 B 全量 Root 化與 `@/` 自省解算引擎**：
     - 徹底廢除全系統所有 `*.root://` 協議與 `temp://`，協議庫精簡 50%，確立 8 大標準 Canonical 協議（`storage`, `cache`, `config`, `module`, `module.source`, `module.build`, `module.release`, `module.mirror`）。
     - 跨模組顯式尋址：`storage://dev/file.json` ➔ `yscb://storage/dev/file.json`（絕無雙重嵌套）。
     - 當前模組自省語法：`storage://@/file.json`（無上下文時拋出結構化 `UndefinedModuleContextError`）。
     - 內建舊協議 `DeprecationWarning` 向下相容轉向與 `..` 沙盒逃逸防護。
  2. **模組資料三位一體確立與生命週期治理 (`--purge`)**：
     - `storage://` (持久化/Git 追蹤)、`config://` (專案設定/Git 追蹤)、`cache://` (暫存快取/Git 忽略)。
     - 卸載時自動清空 `cache://{module}/` 並安全保留業務與設定資料；提供 `remove --purge` 支援一鍵物理銷毀。
  3. **開發工具鏈與測試沙盒環境遷移 (`dev`)**：
     - 測試沙盒全面遷移至 `cache://dev/sandbox/{sandbox_id}` (`.cache/dev/sandbox/`)，測試結束自動乾淨銷毀。
  4. **發布清冊錯誤路徑修復與歷史清理 (`agents-workflow`)**：
     - 修復 `release_manifest.json` 至 `storage://@/release_manifest.json` (`storage/agents-workflow/release_manifest.json`)。
     - 物理刪除歷史遺留之 `storage/core/agents-workflow/` 與 `.temp/`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 實作方案 B 全量 Root 化解算器、`@/` 自省展開、`UndefinedModuleContextError`、舊協議相容與路徑穿越阻斷 |
| [`source/core/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/manifest.json) | Modify | 自宣告 8 大標準協議（移除所有 `*.root` 與 `temp`） |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 互斥鎖遷移至 `cache://.yscb.lock`、落實 `_clean_module_cache` 與 `act_delete(--purge)` |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | `cmd_remove` 傳遞 `purge` 旗標與模組生命週期治理 |
| [`source/core/scripts/cli.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/scripts/cli.py) | Modify | CLI 支援 `remove <mod> [--purge]` |
| [`source/core/core/symbols.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/symbols.py) | Modify | 符號定位協議全面採用 `module://` 與 `module.source://` |
| [`source/dev/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/manifest.json) | Modify | 移除 `module.source.root`, `module.build.root`, `module.release.root` |
| [`source/dev/dev/testing/sandbox.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py) | Modify | 測試沙盒路徑遷移至 `cache://dev/sandbox/{sandbox_id}` |
| [`source/dev/dev/testing/case.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/case.py) | Modify | TestCase Fixture 沙盒 URI 遷移至 `cache://dev/sandbox/{sandbox_id}` |
| [`source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/builder.py) 等 | Modify | `dev` 開發工具鏈全面升級方案 B 協議 |
| [`source/agents-workflow/agents_workflow/publisher.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/publisher.py) | Modify | 發布清冊寫入 `storage://@/release_manifest.json` 與歷史目錄遷移 |
| [`source/agents-workflow/agents_workflow/compiler.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/compiler.py) | Modify | 中繼快照統一寫入 `cache://@/resolved_contents` |
| [`.gitignore`](file:///h:/UseFolder/CodeRepo/ys_codebase/.gitignore) | Modify | 確保 `/.cache/` 忽略，`storage/` 與 `config/` 納入 Git 追蹤 |
| [`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md) | Modify | 更新方案 B 全量 Root 化與 `@/` 語法標準手冊 |
| [`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md) | Modify | 追加資料三位一體與生命週期治理 (`--purge`) 章節 |
| [`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md) | Modify | 更新微型沙盒拓撲路徑為 `cache://dev/sandbox/` |
| [`CHANGELOG.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/CHANGELOG.md) | Modify | 全專案根目錄版本日誌追加本次高階發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev test --all` 達成 **110/110 Passed (100% Ready, 19.270s)**。
  - `agents-workflow`: Contract (3/3), Custom (15/15) **PASSED**
  - `core`: Contract (3/3), Custom (61/61) **PASSED**
  - `dev`: Contract (3/3), Custom (25/25) **PASSED**
- **實機 UX / 人工驗證**：
  - `UX-01`：`python yscb.py status` 診斷健康 (HEALTHY, 100% Ready)。
  - `UX-02`：`storage/agents-workflow/release_manifest.json` 正確座落，歷史目錄 `storage/core/agents-workflow/` 與 `.temp/` 已徹底清除。
  - `UX-03`：沙盒精確隔離於 `.cache/dev/sandbox/` 下，舊 `.cache/sandbox/` 已清理。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | [`docs/core/uri_protocols.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/uri_protocols.md) | ✅ 已交付 | 方案 B 8 大標準協議、`@/` 自省語法、跨模組顯式尋址與相容轉向 |
| **維度 3** | [`docs/core/lifecycle_and_hooks.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/lifecycle_and_hooks.md) | ✅ 已交付 | 資料三位一體原則、Git 版本控制策略、模組卸載與 `--purge` 機制 |
| **維度 4** | [`docs/dev/testing_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/testing_guide.md) | ✅ 已交付 | 測試沙盒環境遷移至 `.cache/dev/sandbox/` 之拓撲說明 |
| **維度 7** | [`CHANGELOG.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/CHANGELOG.md) | ✅ 已交付 | 全專案高階發布日誌追加 `2026_08_26_1747_core_dev_refinement` 區塊 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(uri): implement Option B canonical URI scheme and module data lifecycle

- Remove all *.root:// and temp:// protocols, establish 8 canonical root-level schemes
- Implement @/ active module placeholder syntax and cross-module resolution
- Enforce module data trinity: storage (Git tracked), config (Git tracked), cache (Git ignored)
- Add lifecycle cache auto-cleaning and --purge physical destroy in core:remove
- Migrate dev test sandboxes to cache://dev/sandbox/ (.cache/dev/sandbox)
- Fix agents-workflow release_manifest.json storage path and cleanup legacy directories
- Update all documentation in docs/ and project CHANGELOG.md (110/110 tests passed)
```
