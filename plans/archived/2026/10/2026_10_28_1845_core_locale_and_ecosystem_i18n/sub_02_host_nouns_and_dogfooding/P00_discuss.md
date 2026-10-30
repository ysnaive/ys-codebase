# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 現階段為求精簡，最終 Fallback 採用開發團隊母語 `zh`，先不處理 `en` 等多語系翻譯（CLI、模板、文檔多語系支援已列入 Roadmap），100% 專注於宿主環境專有名詞（Dialect / Host Proper Nouns）治理與 Dogfooding 實機驗證。
  2. 通用宿主工具專有名詞庫放在 `agents-workflow`（而 `knowledge-db` 在 `agents-workflow` 未安裝時不應輸出特化給 Agents 的提示已登記為 `[TODO-04]`）。
  3. 需支援多個不同平台 IDE / Agent（如 Antigravity IDE、Claude Code CLI、Codex CLI）於同一工作區同時運行：設定檔（`config.project.json` / `config.local.json`）僅存放自然語系（如 `["zh"]`），編譯期依 `target_name` 綁定對應 `nouns-<target>`，執行期則自動嗅探當前呼叫端宿主環境變數前置 `nouns-<host>`。
  4. `core.locale` API 支援直接呼叫無模組前綴之 Key（如 `agent_tool.file_read_range`），優先查呼叫端模組自身，未命中則自動穿透掃描全域已註冊 `locales` 模組（`<module>:` 前綴僅於衝突消歧義或顯式指定時使用）；因此宿主工具專有名詞統一採用高辨識度之 `agent_tool.*` 領域命名空間。
  5. `agents-workflow` 手冊（`SKILL.md` / `AgentsStandards.md`）中之專有名詞替換採用方案 A：`` `__%{key}__` `` 標籤語法，於 Stage 2 依目標 `target_name` 展開。
- **核心目標**：
  1. 擴充 `core.locale.resolve_raw` 支援無 `<module>:` 前綴之全系統已註冊模組穿透查找（Caller Module First $\to$ Global Registered Modules Fallback），並支援執行期宿主環境變數自動嗅探（`detect_active_host_dialect()`）。
  2. 於 `agents-workflow` 建立宣告式 `locales/` 專有名詞體系（`definition.json`、`zh.json`、`nouns-antigravity.json`、`nouns-claude.json`、`nouns-codex.json`，定義 `agent_tool.file_read_range`、`agent_tool.file_read`、`agent_tool.file_edit`、`agent_tool.file_grep_single`、`agent_tool.shell_exec`、`agent_tool.shell_bg_daemon`）並註冊至 `ys_codebase/source/agents-workflow/contributes/core.json`。
  3. 擴充 `agents-workflow` 之 `ArtifactCompiler.resolve_stage2_uri`（及 `ReleasePublisher` 指紋計算）支援 `` `__%{key}__` `` 專有名詞標籤，於投影至各 `release_target` 時自動以 `chain=[f"nouns-{target_name}", ...]` 渲染對應平台專有名詞。
  4. 於 `knowledge-db`（CLI 截斷提示 `{agent_tool.file_read_range}` 與 `knowledge-db-search/SKILL.md`）及 `agents-workflow`（`yscb-cli-guide/SKILL.md`）完成首輪 Dogfooding 實機驗證與回測。
- **邊界排除 (Explicitly Excluded)**：
  - **不包含 `en` 等非 `zh` 自然語言翻譯包**：全系統自然語系退避終點統一為 `zh`，多語系翻譯歸屬長期路線圖 [i18n_workflow_and_downstream_governance.md](file:///workspace/ys-codebase/plans/roadmap/i18n_workflow_and_downstream_governance.md)。
  - **`[TODO-04]` 獨立管控**：`knowledge-db` 在 `agents-workflow` 未安裝時完全隱藏 Agent 特化提示之整體門控留待 `[TODO-04]` 處理。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/locale.py`（無前綴全域穿透查找 + `detect_active_host_dialect()` 執行期環境變數嗅探）
  - `ys_codebase/source/agents-workflow/contributes/core.json` 與 `ys_codebase/source/agents-workflow/locales/{definition,zh,nouns-antigravity,nouns-claude,nouns-codex}.json`
  - `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` 與 `publisher.py`（Stage 2 `` `__%{key}__` `` 專有名詞渲染與 SHA-256 指紋連動）
  - `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`
  - `ys_codebase/source/knowledge-db/contributes/core.json`、`ys_codebase/source/knowledge-db/locales/{definition,zh}.json`、`ys_codebase/source/knowledge-db/scripts/cli.py` 與 `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 專有名詞集中於 `agents-workflow`（`agent_tool.*` 精確命名）與母語 `zh` 最終保底**：
  - 宿主環境工具專有名詞統一宣告於 `agents-workflow/locales/`，採用 `agent_tool.*` 精確語意前綴（`agent_tool.file_read_range`、`agent_tool.file_read`、`agent_tool.file_edit`、`agent_tool.file_grep_single`、`agent_tool.shell_exec`、`agent_tool.shell_bg_daemon`），最終 Fallback 固定為開發團隊母語 `zh`。
- **[P00:DR-02] 多平台 IDE 並發運行之「設定檔純淨化 + 編譯期/執行期雙軌動態綁定」**：
  - `config://core` 的 `"locale"` 設定僅保留自然語系（如 `["zh"]`）。
  - 編譯期依 `target_name` 顯式綁定 `[f"nouns-{target_name}", ...]`；執行期由 `core.locale.get_active_chain()` 透過 `detect_active_host_dialect()` 自動嗅探呼叫端環境變數前置 `nouns-<host>`。
- **[P00:DR-03] 無前綴全域穿透查找（Caller-First Global Lookup）與 Stage 2 `` `__%{key}__` `` 語法**：
  - `core.locale.resolve_raw` 遇到無 `<module>:` 前綴之 Key 時，優先查找呼叫端模組，若未命中則自動遍歷 `contributes.merged.json` 中所有已註冊 `locales` 之模組（按模組名稱字典序穩定查找）；`<module>:` 前綴僅在跨模組同名 Key 衝突消歧義時需要。
  - `agents-workflow` 手冊採用方案 A `` `__%{key}__` `` 語法，於 Stage 2（`resolve_stage2_uri`）依當前 `target_name` 渲染為目標宿主專有名詞。

---

## 3. 開放議題與確認紀錄

- **Q1：通用宿主工具專有名詞庫歸屬模組？**
  - **A1（已確認）**：歸屬於 `agents-workflow`；同時將「`knowledge-db` 在 `agents-workflow` 未安裝時不輸出特化給 Agents 的相關資訊」登記為 `[TODO-04]`。
- **Q2：是否需考慮多個不同平台 IDE 同時運行？**
  - **A2（已確認）**：是，採「設定檔僅放自然語系 `["zh"]` + 編譯期依 `target_name` 綁定、執行期依呼叫端環境變數自動嗅探前置 `nouns-<host>`」方案。
- **Q3：API 是否支援無 `<module>:` 前綴直接查找，以及手冊中如何替換專有名詞？**
  - **A3（已確認）**：支援無前綴直接查找（僅衝突時需 `<module>:` 前綴），並以 `agent_tool.*` 精確命名 Key；手冊採用方案 A `` `__%{key}__` `` 標籤於 Stage 2 依 `target_name` 替換。
