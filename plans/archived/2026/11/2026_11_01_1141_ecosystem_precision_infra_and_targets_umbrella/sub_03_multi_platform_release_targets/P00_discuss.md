# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：主流 AI 開發平台 release_target 矩陣擴充、同路徑並聯渲染告警與宣告式環境嗅探  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `multi_platform_release_targets_expansion_roadmap.md` 與 `TODO-05`, `TODO-06` 整合為 Umbrella 子計畫 `sub_03`；議題一採方案 A（物化時若有多個 Target 共用同一實體路徑，執行並聯去重渲染並順帶輸出 `[WARNING]` 提示開發者考慮於 `config.local.json` 覆蓋為個人實際使用的單一 Target），議題二與議題三全數同意。
- **核心目標**：
  1. **同實體路徑多 `release_target` 並聯去重渲染與 `config.local.json` 分流告警 (`TODO-05`)**：
     - 當專案（例如團隊共享之 `config.project.json`）同時啟用多個指向相同實體路徑（如共用 `project://AGENTS.md` 或 `project://.agents/skills/`）之 `release_target` 時：
       - **專有名詞 (`__%{agent_tool.*}__`) 與路由連結並聯去重**：對指向同一實體路徑之多個 Target，收集各 Target 對應之專有名詞或技能路由路徑並以 `" / "` 去重並聯渲染，徹底根除後執行 Target 無聲覆寫前一個 Target 內容的問題。
       - **物化碰撞告警 (`[WARNING]`)**：於 `ReleasePublisher.release` 物化期間，一旦偵測到 $\ge 2$ 個啟用之 Target 共用同一實體輸出路徑（如 `antigravity` 與 `codex` / `cursor` 共用 `AGENTS.md` 或 `.agents/`），除了執行並聯相容渲染外，強制於終端輸出醒目 `[WARNING]`，明確列出共用路徑之 Target 名稱，並建議開發者於個人本地組態 `config/agents-workflow/config.local.json` 設定專屬的 `"release_targets"` 以覆蓋團隊共用清單。
  2. **子目錄 `agents_md` 相對連結基準路徑對齊 (`copilot` 等平台支援)**：
     - 修正 `ReleasePublisher` / `ArtifactCompiler` 在渲染 Target 專屬 `agents_md`（如 `copilot` 之 `project://.github/copilot-instructions.md`）時的 Stage 2 基準目錄計算：以 `agents_md` 檔案實際所在的父目錄（如 `.github/`）而非固定專案根目錄計算 `__#{...}__` 相對路徑，確保 `.github/copilot-instructions.md` 內的技能超連結精準指向 `./skills/...`。
  3. **執行期 CLI 環境變數嗅探與方言對照宣告化 (`TODO-06`)**：
     - 將 `ys_codebase/source/core/core/locale.py` 中 `detect_active_host_dialect` 硬編碼之環境變數前綴對照表（`ANTIGRAVITY_`, `CLAUDE_`, `CODEX_` 等）正規化為宣告式規則（可由 `contributes` 或結構化平台定義表驅動），使新擴充之 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 均可透過宣告式環境變數規則自動嗅探並回退至對應或通用方言詞庫。
  4. **8 大預設 `release_target` 矩陣擴充與「外殼 vs. 模型」選型文檔同步 (`roadmap.md`)**：
     - 於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 完整提供 8 大預設 Target：`antigravity`（Google Antigravity / Gemini CLI / Cline）、`claude`（Claude Code）、`codex`（OpenAI Codex）、`cursor`（Cursor IDE）、`copilot`（GitHub Copilot）、`windsurf`（Windsurf IDE）、`opencode`（OpenCode CLI）、`roo`（Roo Code）。
     - 同步更新 `docs/agents-workflow/{README.md,user_guide.md}` 與配置引導說明，明確闡述「依客戶端外殼（Client Harness）而非底層大模型（GLM / DeepSeek / Qwen / Ollama）選擇 `release_target`」及 `config.local.json` 個人覆蓋最佳實踐。
- **邊界排除 (Explicitly Excluded)**：
  - 不涉及 IDE 專用非標準二進位資料庫或雲端 API 同步，維持 100% 純本地 Markdown 檔案物化。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/`（`contributes/agents-workflow.json`、`agents_workflow/{compiler.py,publisher.py}`、`assets/`、`tests/`）、`ys_codebase/source/core/`（`core/locale.py`、`contributes/`、`tests/`）與 `docs/agents-workflow/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **同實體路徑多 Target 並聯渲染 + `config.local.json` 覆蓋告警雙重機制**：當多個已啟用 Target 映射至同一目標檔案路徑（如 `AGENTS.md` 或 `.agents/skills/...`）時，編譯/發布器按目標路徑聚合 Target 群組，對不同之 `__%{agent_tool.*}__` 專有名詞與 `__#{...}__` 路由連結執行 `" / "` 去重並聯（避免後寫覆前寫）；同時強制在 `release` 輸出 `[WARNING]` 提示存在 Target A/B 共用路徑，引導開發者在 `config/agents-workflow/config.local.json` 覆蓋 `release_targets` 以獲得最純淨的單一平台體驗。
- **[P00:DR-02]** **宣告式環境變數嗅探與方言對照 (`TODO-06`)**：將宿主環境變數嗅探規則（如 `CURSOR_TRACE_ID` / `VSCODE_GIT_ASKPASS_MAIN`、`WINDSURF_*`、`OPENCODE_*` 等）改為結構化宣告配置並支援由 `contributes` 擴充；對於未定義特化工具名詞之新平台，平滑共用或回退至標準通用工具詞庫 (`default` / `antigravity`)。
- **[P00:DR-03]** **8 大預設 `release_target` 與子目錄 `agents_md` 基準對齊**：擴充 `cursor` (`.cursor/`)、`copilot` (`.github/copilot-instructions.md` + `.github/`)、`windsurf` (`.windsurf/`)、`opencode` (`.opencode/`)、`roo` (`.roo/`) 五大 Target，並修正 `publisher.py` 傳入 `resolve_stage2_uri` 之 `cur_doc_dir` 為 `os.path.dirname(agents_md_abs)`。

---

## 3. 開放議題與確認紀錄

- 議題一（方案 A + 輸出 Warning 提示 `config.local.json` 覆蓋）、議題二（宣告式環境嗅探）、議題三（8 大平台投影設定）均已由開發者確認定案。

