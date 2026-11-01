# 成果展示與結案報告 (Walkthrough)

> 功能名稱：主流 AI 開發平台 release_target 矩陣擴充、同路徑並聯渲染告警與宣告式環境嗅探  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **8 大主流 AI 開發平台 `release_target` 矩陣擴充 (`FR-05`, `[P00:DR-03]`)**：於 `agents-workflow/contributes/agents-workflow.json` 完整提供 `antigravity`、`claude`、`codex`、`cursor`、`copilot`、`windsurf`、`opencode`、`roo` 共 8 大預設 Target 拓撲定義。
  2. **同實體路徑多 Target 並聯去重渲染 (`Union Rendering`) 與 `[publisher:warning]` 本機覆寫提示 (`FR-01`, `FR-02`, `[P00:DR-01]`)**：於 `ReleasePublisher._prepare_target_compilations` 以目標實體路徑 (`dst_abs`) 聚合所有活躍 Target 映射；當 $\ge 2$ 個 Target 共用同一檔案（如 `AGENTS.md` 或 `.agents/skills/`）時，透過 `ArtifactCompiler.resolve_stage2_uri` 將宿主專有名詞 (`__%{...}__`) 與技能相對連結 (`__#{...}__`) 按順序去重並以 `" / "` 並聯輸出，同時向 `stderr` 輸出 `[publisher:warning]` 提示開發者可於 `config/agents-workflow/config.local.json` 覆寫。
  3. **子目錄 `agents_md` 相對連結基準對齊與規則檔動態保護 (`FR-03`, `[P00:DR-03]`)**：確保 `.github/copilot-instructions.md` 以 `.github/` 為基準將技能相對路徑解析為 `./skills/...`，並於 `sync_gitignore` 與 `_prune_orphaned_managed_files` 動態納入所有已註冊 Target 之 `agents_md`。
  4. **宣告式環境變數嗅探規則 (`FR-04`, `TODO-06`, `[P00:DR-02]`)**：於 `core/locale.py` 新增 `DEFAULT_HOST_DIALECT_RULES` 與 `get_host_dialect_rules()`，將 `detect_active_host_dialect` 重構為宣告式規則驅動（支援 8 大平台環境變數與 `config://core` / `contributes://core` 自訂規則擴充）。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 擴充 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 共 8 大預設 `release_target` |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `_resolve_local_uri_tag`、`_resolve_locale_noun_tag` 與 `resolve_stage2_uri` 支援多 Target `" / "` 並聯去重渲染與 `nouns-antigravity` 安全回退 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | `_prepare_target_compilations` 依 `dst_abs` 聚合並聯渲染與輸出 `[publisher:warning]`；`build_deployment_map` 支援顯式 `proj_root`；`sync_gitignore` 動態排除所有 `agents_md` |
| `ys_codebase/source/core/core/locale.py` | Modify | 新增 `DEFAULT_HOST_DIALECT_RULES` 與 `get_host_dialect_rules()`，重構 `detect_active_host_dialect` 為宣告式規則驅動 |
| `ys_codebase/source/agents-workflow/tests/test_targets.py` | Modify | 更新 `test_ft_01` 驗證 8 大 Target，新增 `test_ft_08` 驗證 `copilot` 子目錄相對連結、多 Target 並聯渲染與 `[publisher:warning]` |
| `ys_codebase/source/core/tests/test_locale.py` | Modify | 擴充 8 大平台環境變數嗅探與自訂 `rules` 注入測試 |
| `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` | Modify | 更新 8 大平台矩陣表、Client Harness vs. Backend LLM 選型指引、`config.local.json` 覆寫說明與 `[DN-AW-18]` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`agents-workflow` 全量 137 項測試 (`Pass: 137(100.0%), Fail: 0`) 與 `core:TestCoreLocaleEngine` 11 項測試 (`Pass: 11(100.0%), Fail: 0`) 100% 通過；`contributes check` 與 `dev check agents-workflow` 100% `PASSED`。
- **實機 UX / 人工驗證**：`UX-01` 實機執行 `release-target --list`、`--add codex` / `--add cursor` 驗證 8 大 Target 清單、`" / "` 並聯輸出與 `[publisher:warning]` 告警，開發者確認 `[測試通過]`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 登載 `sub_03` 8 大平台擴充、同路徑並聯渲染與宣告式嗅探亮點 |
| **中觀 (Meso)** | `docs/agents-workflow/README.md` | 已完成 | 更新 §4 支援 8 大預設 `release_target` 與並聯去重說明 |
| **中觀 (Meso)** | `docs/agents-workflow/user_guide.md` | 已完成 | 更新 §2.4 8 大平台矩陣表、Client Harness vs. Backend LLM 選型與本機覆寫指引 |
| **中觀 (Meso)** | `docs/agents-workflow/DESIGN_NOTES.md` | 已完成 | 新增 `[DN-AW-18]` 記錄多 Target 共用路徑並聯去重與子目錄 `agents_md` 防坑設計 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 嚴格維護 Docstring，標註動機理由 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow,core): expand 8 default release targets, support shared-path union rendering, and declarative host dialect sniffing
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella/sub_03_multi_platform_release_targets` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

