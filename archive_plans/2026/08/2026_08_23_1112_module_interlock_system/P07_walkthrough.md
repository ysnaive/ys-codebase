# 變更摘要 (Walkthrough)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 變更概述

本次開發完整建立了 YS-Codebase 的**安裝期連動協定與動態插槽注入系統 (Installation-time Interlock & Open Protocol System)**。透過主機-外掛（Host-Plugin）架構與三大剛性協定合約，實現了外掛模組（如 `agents-workflow-unity`）在安裝期向宿主模組（`agents-workflow`）宣告補丁與擴充的能力。核心引擎包含 `SOPSynthesizer`（Slot 注入與正則剝除）、`IDECacheTracker`（IDE 快取與孤兒清理）、`ExtensionRegistry`（雙層發現與專案優先覆蓋）以及 `_on_modules_changed.py` 生命週期廣播 Hook，並完成 `source/agents-workflow/workflows/commands/` 基準庫與 Slot 全集植入。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :--- | :--- |
| `ys_codebase/source/core/scripts/context.py` | Modify | 新增 `ProjectContext.get_contributions()` 與 `get_all_installed_manifests()` |
| `ys_codebase/yscb_installer.py` | Modify | 新增 `ModuleManager._broadcast_modules_changed()`，於 `install`/`pull`/`remove` 結尾單次派發（`build` 嚴格排除） |
| `ys_codebase/source/agents-workflow/scripts/sop_synthesizer.py` | Add | 實作 `SOPSynthesizer` 類別，支援 Slot 注入（append/prepend）與正則標記剝除 |
| `ys_codebase/source/agents-workflow/scripts/ide_sync.py` | Add | 實作 `IDECacheTracker` 類別，管理 `.yscb_cache/ide_workflow_manifest.json` 與孤兒檔案清理 |
| `ys_codebase/source/agents-workflow/scripts/ext_registry.py` | Add | 實作 `ExtensionRegistry` 類別，支援雙層 Extension 發現與 `sop_ext://` 優先覆蓋 |
| `ys_codebase/source/agents-workflow/workflows/commands/*.md` | Add | 建立 9 份基準 SOP 指令庫 (SSOT)，並植入 16 個標準 `YSCB_SLOT` 標記 |
| `ys_codebase/source/agents-workflow/scripts/_on_modules_changed.py` | Add | 實作 `agents-workflow` 生命週期 Hook，執行動態合成與 IDE 工作流無感同步 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | 升級 `generate_antigravity_ide_commands()`、`ext list/show` 雙層排版與 `verify_plan.py` |
| `ys_codebase/source/agents-workflow/scripts/verify_plan.py` | Modify | 升級支援動態調度跨模組貢獻之驗證腳本 |
| `test/fixtures/mock_workflow_plugin/` | Add | 建立標準 Mock 外掛測試夾具（宣告 patches 與 extensions） |
| `test/test_interlock.py` | Add | 實作連動系統全量單元與整合測試（涵蓋 FT-01~08, ET-01~08, PT-01） |
| `docs/AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md` | Add | 建立維度 3 中觀動態機制專題手冊（三大合約、Slot 插槽全集、架構圖） |
| `docs/Installer/DESIGN_NOTES.md` | Modify | 登記 `DN-07`（build 排除廣播鐵律）與 `DN-08`（Slot 標記剝除防呆） |
| `docs/AgentsWorkflow/README.md` | Modify | 更新模組說明、commands/ SSOT 與連動協定導覽 |
| `docs/Installer/README.md` | Modify | 更新 `_broadcast_modules_changed` 生命週期廣播機制 |
| `docs/Core/README.md` | Modify | 更新 `get_contributions()` 與 `get_all_installed_manifests()` API 手冊 |
| `docs/README.md` | Modify | 全域知識地圖同步更新連動協定專題索引 |
| `CHANGELOG.md` | Modify | 全專案高階日誌追加 `2026_08_23_1112_module_interlock_system` 發布摘要 |

---

## 3. 測試與品質驗證結果

- **自動化測試**：全量 53 項單元與整合測試 + E2E 下游沙盒模擬 100% 通過（`test/run_regression.py`）。
- **UX / 手動驗證**：開發者已確認 `ext list` 雙層排版清晰，且 IDE 工作流指令純淨無 Slot 標記殘留。
- **偏差記錄**：
  - **Dev-01**：在 `source/agents-workflow/workflows/` 下移除了 9 份舊版靜態指令，統一收斂至 `commands/` 基準庫管理。
  - **Dev-02**：`_on_modules_changed.py` 增設 Windows 控制台 UTF-8 編碼防呆與 `importlib.util` 模組隔離加載，徹底杜絕跨模組命名遮蔽 (Namespace Shadowing)。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的 `docs/` 文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :--- | :--- | :--- |
| `docs/AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md` | ✅ 已新建 | 完整包含三大協定合約、垂直 Mermaid TD 架構圖、全量 Slot 插槽表與雙層 Extension 發現鏈 | P03 API-03~05, P05 Task 3~5, P06 FT-01~08 |
| `docs/Installer/DESIGN_NOTES.md` | ✅ 已登記 | 登記 `DN-07`（build 排除廣播鐵律）與 `DN-08`（Slot 標記剝除防呆） | P05 Task 2/3, P06 FT-02/07 |
| `docs/AgentsWorkflow/README.md` | ✅ 已更新 | 補齊 `commands/` SSOT 架構、連動手冊索引、`ext list` 雙層排版與 IDE 無感同步 | P03 API-04, P05 Task 8 |
| `docs/Installer/README.md` | ✅ 已更新 | 補齊 `_broadcast_modules_changed()` 生命週期廣播架構說明 | P03 API-02, P05 Task 2 |
| `docs/Core/README.md` | ✅ 已更新 | 補齊 `ProjectContext.get_contributions()` 與 `get_all_installed_manifests()` 簽名與說明 | P03 API-01, P05 Task 1 |
| `docs/README.md` | ✅ 已同步 | 全域知識地圖同步更新連動協定專題手冊索引 | 全域知識庫同步 |

---

## 5. 推薦 Commit 訊息

```text
feat(interlock): implement installation-time interlock and open protocol system

- Implement ModuleManager._broadcast_modules_changed() with build command excluded
- Implement ProjectContext.get_contributions() and get_all_installed_manifests() in core
- Implement SOPSynthesizer for dynamic slot injection and regex slot marker stripping
- Implement IDECacheTracker for automatic orphan command cleanup
- Implement ExtensionRegistry with dual-layer discovery hierarchy (sop_ext:// priority)
- Establish workflows/commands/ SSOT base library and inject 16 standard YSCB_SLOT anchors
- Implement _on_modules_changed.py hook with automatic IDE sync on environment sensing
- Upgrade cli.py and verify_plan.py to support dual-layer source tags and pluggable verifiers
- Add full test suite test_interlock.py (FT-01~08, ET-01~08, PT-01) passing 53/53 tests + E2E
- Deliver documentation handbook SOP_INTERLOCK_PROTOCOL.md, DN-07, and DN-08
```
