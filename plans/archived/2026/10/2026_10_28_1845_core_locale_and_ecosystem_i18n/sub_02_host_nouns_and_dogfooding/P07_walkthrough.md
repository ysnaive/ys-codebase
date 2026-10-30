# 成果展示與結案報告 (Walkthrough)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **無模組前綴之全域穿透查找 (`FR-01`, `EC-01`)**：擴充 `core.locale.resolve_raw` 與 `_interpolate_template`，支援不加 `<module>:` 前綴直接呼叫全域專有名詞（如 `agent_tool.file_read_range`），優先查找呼叫端模組自身（Caller-First Shadowing），未命中則自動穿透掃描全系統已註冊 `locales` 之模組（並引入 `_MODULE_BASE_DIR_CACHE` 維持 $< 0.5\text{ms}$ 極速熱路徑）。
  2. **執行期多平台並發宿主環境變數自動嗅探 (`FR-02`, `EC-03`)**：於 `core.locale` 實作 `detect_active_host_dialect()`，自動從子進程環境變數識別當前呼叫端 AI IDE / CLI（`CLAUDECODE` $\to$ `nouns-claude`、`CODEX_*` $\to$ `nouns-codex`、`ANTIGRAVITY_*` $\to$ `nouns-antigravity`）並前置於自然語系退避鏈 `["zh"]` 前端，讓 `config.project.json` 保持純淨自然語系且支援多開 IDE 並發運行。
  3. **`agents-workflow` 宿主專有名詞庫 (`agent_tool.*`) 與 Stage 2 `` `__%{key}__` `` 投影轉譯 (`FR-03`, `FR-04`, `EC-02`)**：於 `agents-workflow/locales/` 建立 `definition.json`、`zh.json`、`nouns-antigravity.json`、`nouns-claude.json`、`nouns-codex.json`（定義 6 項 `agent_tool.*` 專有名詞），並擴充 `ArtifactCompiler.resolve_stage2_uri` 支援依 `target_name` 展開 `` `__%{key}__` `` 專有名詞佔位符，同時將 `locales/` 納入 `ReleasePublisher._get_sources_digest()` 指紋計算。
  4. **`knowledge-db` 與技能手冊首輪 Dogfooding 實機驗證 (`FR-05`, `EC-04`)**：於 `knowledge-db` 建立 `locales/{definition,zh}.json` 並在 `scripts/cli.py` 截斷提示中引用 `{agent_tool.file_read_range}`，同時於 `knowledge-db-search/SKILL.md` 與 `yscb-cli-guide/SKILL.md` 導入 `` `__%{agent_tool.*}__` `` 完成編譯期與執行期雙軌 Dogfooding 驗收。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/locale.py` | Modify | 新增 `detect_active_host_dialect`、`_get_all_registered_locale_modules`、`_MODULE_BASE_DIR_CACHE` 與無前綴全域穿透查找 |
| `ys_codebase/source/core/tests/test_locale.py` | Modify | 新增 `test_sub02_unqualified_global_lookup_and_host_dialect_sniffing` 測試 |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 註冊 `"locales"` 擴充點（`definition`、`zh`、`nouns-antigravity`、`nouns-claude`、`nouns-codex`） |
| `ys_codebase/source/agents-workflow/locales/definition.json` | New | 定義 `agent_tool.*` 6 項宿主工具專有名詞語意契約 |
| `ys_codebase/source/agents-workflow/locales/zh.json` | New | 提供 `agent_tool.*` 開發團隊母語 (`zh`) 通用工具描述保底 |
| `ys_codebase/source/agents-workflow/locales/nouns-antigravity.json` | New | 提供 Google Antigravity IDE 工具專有名詞映射 |
| `ys_codebase/source/agents-workflow/locales/nouns-claude.json` | New | 提供 Anthropic Claude Code 工具專有名詞映射 |
| `ys_codebase/source/agents-workflow/locales/nouns-codex.json` | New | 提供 OpenAI Codex CLI 工具專有名詞映射 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 新增 `LOCALE_NOUN_INNER_REGEX` (`__%{key}__`) 與 Stage 2 依 `target_name` 專有名詞展開 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 傳遞 `target_name` 至 `resolve_stage2_uri` 並於 `_get_sources_digest` 納入 `locales/` 指紋 |
| `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md` | Modify | 導入 `` `__%{agent_tool.shell_exec}__` `` 與 `` `__%{agent_tool.shell_bg_daemon}__` `` |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 新增 `test_ft_13_stage2_locale_noun_projection_across_targets` 測試 |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 註冊 `"locales"` 擴充點（`definition`、`zh`） |
| `ys_codebase/source/knowledge-db/locales/definition.json` | New | 定義 `cli.search.snippet_truncated_hint` 契約 |
| `ys_codebase/source/knowledge-db/locales/zh.json` | New | 定義 `cli.search.snippet_truncated_hint` 模板（含 `{agent_tool.file_read_range}`） |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | `_cap_json_snippet` 接入 `core.locale.t("cli.search.snippet_truncated_hint")` |
| `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md` | Modify | 導入 `` `__%{agent_tool.file_read_range}__` `` 與 `` `__%{agent_tool.file_grep_single}__` `` |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | 新增 `search -s --json` 截斷提示動態專有名詞替換驗證 |
| `docs/core/README.md` | Modify | 補充無前綴全域穿透查找與執行期多平台環境變數自動嗅探說明 |
| `docs/agents-workflow/FACTORY_PIPELINE.md` | Modify | 補充 Stage 2 `` `__%{key}__` `` 宿主專有名詞投影機制說明 |
| `CHANGELOG.md` | Modify | 記錄 `sub_02_host_nouns_and_dogfooding` 發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 206/206 (100%)、`agents-workflow` 135/135 (100%)、`knowledge-db` 150/150 (100%)，且 `contributes check` (15 files) 與 `dev check` 100% 通過。
- **實機 UX / 人工驗證**：`UX-01` `[測試通過]`（已驗證 `.agents/skills/` 投影產物與 CLI 截斷提示動態替換）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 追加 `sub_02_host_nouns_and_dogfooding` 架構與功能發布摘要 |
| **中觀 (Meso)** | `docs/core/README.md` | 已更新 | 補充無前綴全域穿透查找與 `detect_active_host_dialect` 多平台嗅探說明 |
| **中觀 (Meso)** | `docs/agents-workflow/FACTORY_PIPELINE.md` | 已更新 | 補充 Stage 2 `` `__%{key}__` `` 宿主專有名詞投影規則 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 屬正交擴充，已完整記錄於 `README.md` 與 `FACTORY_PIPELINE.md` |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | `core/locale.py` 與 `agents_workflow/compiler.py` 公開介面 Docstring 完整對齊 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(locale,workflow,kdb): add agent_tool.* host proper nouns, Stage 2 __%{key}__ projection, and multi-IDE runtime dialect sniffing
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

