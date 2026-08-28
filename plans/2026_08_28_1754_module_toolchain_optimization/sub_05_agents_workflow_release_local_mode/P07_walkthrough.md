# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

本子計畫 (`sub_05_agents_workflow_release_local_mode`) 解決了多人協作時各開發者 AI 工具不同導致的專案目錄與 Git 倉庫污染問題，並同步增強微內核組態溯源能力：
1. **Core Config 來源層級探測 API (`core.config`)**：
   - 實作 `core.config.get_raw(module, key, local, default)`：可精確讀取單一層級 (Local 或 Project) 的原始未合併設定。
   - 實作 `core.config.inspect(module, key)`：可深度診斷鍵值來源（`"local"`、`"project"`、`"both"`、`"none"`）與 `is_overridden` 覆蓋狀態。
2. **Release Target 預設 Local 模式 (`ReleaseTargetManager`)**：
   - `release-target --add <t>` 與 `--remove <t>` 預設操作本機私有之 **`config.local.json`**（Tier 1，不入 Git）。
   - 支援 `--proj` / `--project` 旗標以顯式切換寫入 **`config.project.json`**（Tier 2，團隊共享）。
3. **多層來源標註清冊 (`release-target --list`)**：
   - 終端排版清楚標註各 Target 啟用層級：`[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]`、`[ENABLED (BOTH)]`、`[DISABLED]`。
4. **`project://.gitignore` 100% 嚴格檔案級精準軟合併 (`ReleasePublisher.sync_gitignore`)**：
   - 4 步發布交易中自動維護 `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 標記區塊。
   - **採 100% 嚴格單一檔案路徑映射 (Strict 1-to-1 File Mapping)**：零目錄濃縮、零私有目錄特例。發布引擎產出的每一個實體檔案（包含 templates、standards、workflows）均各自獨立列為一筆精確路徑規則（如 `/.agents/.yscb/templates/P00_semantic_requirements.md`、`/.agents/workflows/Auto.md`）。
   - **無盲區、不誤傷**：使用者在 `.agents/` 任何子目錄（含 `.yscb/`、`skills/`、`rules/`）內自訂的任何檔案均 100% 保持 Git 追蹤能力。
   - 若 `.gitignore` 不存在則自動建立；若已存在則非破壞性替換區塊，用戶自訂規則 100% 完好保留。


5. **本地部屬與設定遷移實機驗證**：
   - 全生態系 `@build` 本地部屬完成，已成功將當前 `antigravity` target 從 Project 遷移至 Local 組態，並驗證 `.gitignore` 自動同步生效。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/core/core/config.py` | Modify | 新增 `ConfigManager.get_raw()` 與 `inspect()`，並匯出至頂層 Facade |
| `source/agents-workflow/agents_workflow/targets.py` | Modify | 升級 `ReleaseTargetManager` 預設 Local、`--proj` 支援與多層清單來源診斷 |
| `source/agents-workflow/agents_workflow/publisher.py` | Modify | 支援多層 Targets 聯集發布，並於發布交易中執行 `sync_gitignore()` 軟合併 |
| `source/agents-workflow/scripts/cli.py` | Modify | 升級 `cmd_release_target` 支援 `--proj` 旗標與多層彩色排版 |
| `source/core/tests/test_config.py` | Modify | 新增 `test_config_get_raw_and_inspect` 單元測試 (FT-01, FT-02) |
| `source/agents-workflow/tests/test_targets.py` | Modify | 新增 `test_ft_05_local_by_default_and_proj_flag` 與 `test_ft_06_sync_gitignore_soft_merge` (FT-03~08) |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：全生態系 4 大核心模組沙盒回歸測試 **181/181 Passed (100% Ready, 14.589s)**。
- **實機 UX 驗證**：
  - `python yscb.py agents-workflow release-target --list`：正確展示 `antigravity [ENABLED (LOCAL)]`。
  - `python yscb.py dev build --all` 與 `python yscb.py install <mod>@build --force`：本機 `@build` 部屬 100% 完成。
  - `project://.gitignore`：自動生成並維持 `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 軟合併區塊。
  - `plan check sub_05_agents_workflow_release_local_mode`：**100% PASS**。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/core/README.md` | ✅ 已更新 | 增補 `core.config.get_raw()` 與 `core.config.inspect()` API 說明 |
| **維度 1** | `docs/agents-workflow/README.md` | ✅ 已更新 | 增補 `release-target` Local 預設與 `--proj` 旗標操作手冊 |
| **維度 3** | `docs/agents-workflow/TOPICS/release_targets.md` | ✅ 已更新 | 多層 Target 解析、來源診斷與 `.gitignore` 軟合併機制手冊 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow,core): default release targets to local config and sync .gitignore soft-merge

- Add `core.config.get_raw()` and `core.config.inspect()` for microkernel config origin diagnostics.
- Update `ReleaseTargetManager.add_target()` and `remove_target()` to default to `config.local.json` (Tier 1).
- Add `--proj` / `--project` flag to CLI `release-target` commands to support explicit project-level configurations.
- Display multi-tier status labels (`[ENABLED (LOCAL)]`, `[ENABLED (PROJECT)]`, `[ENABLED (BOTH)]`) in `release-target --list`.
- Implement non-destructive `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` soft-merge in `ReleasePublisher.sync_gitignore()`.
- Pass 181/181 hermetic sandbox regression tests across all 4 modules.
```
