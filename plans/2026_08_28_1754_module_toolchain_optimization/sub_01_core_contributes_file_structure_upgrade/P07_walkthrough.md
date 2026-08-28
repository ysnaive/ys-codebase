# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **目錄化 Contributes 標準確立**：確立 `source/<module>/contributes/<target>.json` 為全生態系唯一官方標準，徹底廢除根目錄散落檔案與 Manifest 內嵌宣告。
  - **Manifest 徹底瘦身**：全 4 大核心模組 (`core`, `dev`, `knowledge-db`, `agents-workflow`) 剝除 `"contributes"` 物件，`agents-workflow/manifest.json` 由 554 行縮減至 10 行（瘦身 >98%）。
  - **雙階聚合引擎重構與專案特化覆蓋**：重構 `core.contributes.ContributesAggregator`，支援模組貢獻（階層 ①）與專案級 `config://` 空間特化注入（階層 ②），並提供 Auto-Healing 自愈物化快取機制。
  - **消費端 SDK 100% 收斂與歷史壞味道清算**：徹底清理 `agents-workflow/compiler.py` 與 `core/providers.py` 中 `module.source://` 空間穿透反模式，全模組消費端 100% 收斂至 `core.contributes.get(target, key)`。
  - **測試沙盒構建產物覆蓋增強**：`dev.testing.sandbox` 支援自動解壓覆蓋 `module.build://` 最新產物，保障沙盒測試高保真。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/core/contributes/core.json` | **New** | 獨立宣告 core 的 `uri_schemes` 與 `commands` |
| `source/core/contributes/agents-workflow.json` | **New** | 獨立宣告 core 向 agents-workflow 的 `AGENTS_CLI_GUILD` insert |
| `source/dev/contributes/core.json` | **New** | 獨立宣告 dev 的 `uri_schemes` 與 10 大開發指令 |
| `source/dev/contributes/agents-workflow.json` | **New** | 獨立宣告 dev 向 agents-workflow 的 `WORKFLOW_SOP_STANDARDS` insert |
| `source/knowledge-db/contributes/core.json` | **New** | 獨立宣告 knowledge-db 的 `knowledge.storage` 協議與 6 大指令 |
| `source/agents-workflow/contributes/core.json` | **New** | 獨立宣告 agents-workflow 的 3 大 `workflow.*` 協議與 7 大指令 |
| `source/agents-workflow/contributes/agents-workflow.json` | **New** | 獨立宣告 agents-workflow 的 export, token, insert, release_target |
| `source/core/manifest.json` | **Modify** | 移除 contributes，恢復純粹輕量元數據 |
| `source/dev/manifest.json` | **Modify** | 移除 contributes，恢復純粹輕量元數據 |
| `source/knowledge-db/manifest.json` | **Modify** | 移除 contributes，恢復純粹輕量元數據 |
| `source/agents-workflow/manifest.json` | **Modify** | 移除 contributes（554 行 ➔ 10 行），恢復純粹輕量元數據 |
| `source/core/core/contributes.py` | **Modify** | 重構雙階聚合引擎與 Auto-Healing SDK，支援專案特化覆蓋 |
| `source/core/core/providers.py` | **Modify** | 改調用 contributes.get SDK，移除 module.source 探針 |
| `source/core/core/engine.py` | **Modify** | 改調用 contributes.get SDK 彙整指令清單 |
| `source/knowledge-db/knowledge_db/space.py` | **Modify** | 改調用 contributes.get SDK，廢除手寫檔案掃描 |
| `source/agents-workflow/agents_workflow/compiler.py` | **Modify** | 改調用 contributes.get SDK，廢除手寫檔案掃描與 source 探針 |
| `source/dev/dev/testing/sandbox.py` | **Modify** | 支援沙盒自動解壓覆蓋 module.build 測試包 |
| `source/core/tests/test_contributes.py` | **Modify** | 升級單元測試套件驗證新目錄掃描與 SDK 查詢 |
| `source/core/tests/test_cli_guild.py` | **Modify** | 升級單元測試套件驗證 SDK 驅動之防呆手冊產出 |
| `source/dev/tests/test_checker.py` | **Modify** | 升級測試驗證 `contributes/agents-workflow.json` 宣告 |
| `source/agents-workflow/tests/test_initializer.py` | **Modify** | 升級測試驗證 `contributes/core.json` 宣告 |
| `source/agents-workflow/tests/test_auto_workflow.py` | **Modify** | 升級測試驗證 `contributes/agents-workflow.json` 宣告 |
| `CHANGELOG.md` | **Modify** | 追加 sub_01 完整發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev test --all` 全系統 4 大核心模組虛擬沙盒跑測：**164/164 測試案例 100% Passed (19.632s)**。
  - `python yscb.py dev check --all` 全模組靜態合規檢查：**4/4 模組 100% PASSED**。
- **實機 UX / 人工驗證**：
  - 實機執行 `python yscb.py status` 輸出乾淨 Healthy。
  - 開發者已於 Phase 6 Checkpoint 明確確認驗收通過。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `source/core/contributes.format.md` | ✅ 已交付 | 更新為 `contributes/core.json` 目錄化規格手冊 |
| **維度 2** | `source/knowledge-db/contributes.format.md` | ✅ 已交付 | 更新為 `contributes/knowledge-db.json` 目錄化規格手冊 |
| **維度 3** | `source/agents-workflow/contributes.format.md` | ✅ 已交付 | 更新為 `contributes/agents-workflow.json` 目錄化規格手冊 |
| **維度 4** | `source/dev/contributes.format.md` | ✅ 已交付 | 更新為 `contributes/core.json` 與 `contributes/agents-workflow.json` 規格手冊 |
| **維度 5** | `CHANGELOG.md` | ✅ 已交付 | 於專案根目錄最上方登載 sub_01 完整升級發布摘要 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(core): upgrade contributes to canonical directory structure and slim manifests

- Establish canonical source/<module>/contributes/<target>.json structure
- Slim down manifest.json across core, dev, knowledge-db, agents-workflow (>98% reduction)
- Refactor ContributesAggregator with 2-stage scanning and project config overrides
- Unify downstream consumer modules to core.contributes.get() SDK
- Strip historical module.source:// probing antipatterns across compiler and providers
- Enhance dev testing sandbox with build package overlaying
- Pass all 164/164 regression test cases (100% Passed)
```
