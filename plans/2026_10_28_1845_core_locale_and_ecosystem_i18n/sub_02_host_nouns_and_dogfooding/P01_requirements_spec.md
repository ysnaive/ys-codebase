# 需求規格說明書 (Requirements Specification)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **無模組前綴之全域穿透查找 (`Caller-First Global Lookup`) 與跨模組佔位符校驗** | 1. 當呼叫 `core.locale.resolve_raw(key)` 或 `core.locale.t(key)`（含二階遞迴插值 `{placeholder}`）且 `key` 未指定 `<module>:` 前綴時，優先查找呼叫端所屬模組（Caller Module）；若未命中且未限定單一 `base_dir` 隔離模式，自動遍歷全系統已註冊 `locales` 之所有模組（依模組名稱字典序穩定查找，且優先將 `agents-workflow` 與 `core` 納入查找序列）。<br/>2. `validate_module_locales` 在靜態校驗某模組的語言包時，若模板內含未傳入於該條目 `placeholders` 清單但存在於同模組或跨模組 `locales/definition.json` 之全域專有名詞（如 `{agent_tool.file_read_range}`），允許於 `definition.json` 的 `placeholders` 中宣告並在語言包模板中使用，確保靜態契約 100% 閉環。 | P0 | [P00:DR-03] |
| **FR-02** | **執行期多平台並發宿主環境變數自動嗅探 (`detect_active_host_dialect`)** | 1. 於 `core.locale` 新增 `detect_active_host_dialect(env: Optional[Mapping[str, str]] = None) -> Optional[str]`，依序嗅探當前進程環境變數特徵：<br/>   - 含 `CLAUDECODE` 或任何非空 `CLAUDE_CODE_*` $\to$ 回傳 `"nouns-claude"`<br/>   - 含 `CODEX_SANDBOX`、`CODEX_CI` 或任何非空 `CODEX_*` $\to$ 回傳 `"nouns-codex"`<br/>   - 含 `ANTIGRAVITY_AGENT`、`ANTIGRAVITY_CLI_ALIAS` 或任何非空 `ANTIGRAVITY_*` $\to$ 回傳 `"nouns-antigravity"`<br/>2. `core.locale.get_active_chain(explicit_chain=None)` 在未傳入 `explicit_chain` 且未設定 `YSCB_LOCALE` 覆寫時，自動將 `detect_active_host_dialect()` 偵測到之 `"nouns-<host>"` 前置於 `config://core` `"locale"` 自然語系鏈（如 `["zh"]`）的最前端，組合成 `["nouns-<host>", "zh"]`。 | P0 | [P00:DR-02] |
| **FR-03** | **`agents-workflow` 宿主專有名詞庫 (`agent_tool.*`) 建立與註冊** | 1. 於 `ys_codebase/source/agents-workflow/contributes/core.json` 宣告 `"locales"` 擴充點，映射 `definition`、`zh`、`nouns-antigravity`、`nouns-claude`、`nouns-codex` 五份 JSON 檔案。<br/>2. 於 `locales/definition.json` 完整定義 6 個核心宿主工具專有名詞契約：`agent_tool.file_read_range`、`agent_tool.file_read`、`agent_tool.file_edit`、`agent_tool.file_grep_single`、`agent_tool.shell_exec`、`agent_tool.shell_bg_daemon`。<br/>3. `dev check agents-workflow` 與 `contributes check agents-workflow` 執行靜態契約校驗 100% 通過。 | P0 | [P00:DR-01] |
| **FR-04** | **`agents-workflow` 編譯器 Stage 2 `` `__%{key}__` `` 專有名詞標籤轉譯** | 1. 擴充 `ArtifactCompiler.resolve_stage2_uri(..., target_name: Optional[str] = None)`（及 `check_unenclosed_tags` 反引號防呆檢核），支援辨識 `` `__%{key}__` `` 專有名詞佔位符。<br/>2. 在針對特定 `target_name`（如 `"antigravity"`、`"claude"`、`"codex"`）執行 Stage 2 轉譯時，自動以 `chain=[f"nouns-{target_name}", *get_active_chain()]` 呼叫 `core.locale.t(key, chain=...)`：<br/>   - 當為純 Standalone 標籤 `` `__%{key}__` `` 時，保留外層反引號（展開為 `` `<resolved_noun>` ``，因為工具名稱在 Markdown 正文中作為行內代碼呈現最清晰）或於穿插代碼區塊 / Fenced Code Block 內直接替換內部 `__%{key}__`。<br/>3. `ReleasePublisher._get_sources_digest()` 將已註冊之 `locales` JSON 檔案納入來源指紋計算，確保修改專有名詞字典時自動觸發增量重編譯。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-05** | **`knowledge-db` 與 `agents-workflow` 技能手冊首輪 Dogfooding 實機驗證** | 1. 於 `ys_codebase/source/knowledge-db/contributes/core.json` 註冊 `"locales": {"definition": "locales/definition.json", "zh": "locales/zh.json"}`，定義 `cli.search.snippet_truncated_hint`（含 `{omitted}`、`{start_line}`、`{end_line}` 與 `{agent_tool.file_read_range}` 佔位符），並於 `ys_codebase/source/knowledge-db/scripts/cli.py` 取代硬編碼截斷字串。<br/>2. 於 `knowledge-db/assets/skills/knowledge-db-search/SKILL.md` 及 `agents-workflow/assets/skills/yscb-cli-guide/SKILL.md` 導入 `` `__%{agent_tool.*}__` `` 標籤，驗證多 Target 投影與 CLI 實機輸出。 | P0 | [P00:DR-01], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **跨模組無前綴 Key 同名衝突** | 若模組 A 與模組 B 定義了相同無前綴 Key，當模組 A 內部呼叫 `locale.t(key)` 時，強制優先命中模組 A 自身定義（Caller-First Shadowing 防護）；若第三方模組 C 無前綴呼叫時，按已註冊模組字典序確定性解析，且支援隨時以 `mod_a:key` 顯式消歧義。 |
| **EC-02** | **手冊中出現未定義之 `` `__%{unknown_key}__` `` 標籤** | `ArtifactCompiler.resolve_stage2_uri` 若解析後發現 `core.locale.resolve_raw(key)` 為 `None`（未定義之專有名詞 Key），向 `sys.stderr` 輸出 `[compiler:warning] Unresolved locale noun tag: '__%{unknown_key}__' in '<doc>'` 並安全保留原字串，不引發編譯崩潰。 |
| **EC-03** | **非 AI IDE 之純人工終端環境（無任何 `ANTIGRAVITY_*` / `CLAUDE_*` / `CODEX_*` 環境變數）** | `detect_active_host_dialect()` 回傳 `None`，`get_active_chain()` 維持純自然語系鏈 `["zh"]`；此時任何 `{agent_tool.*}` 皆平滑退避至 `agents-workflow/locales/zh.json` 的中文通用工具描述（如 `"原生檔案讀取工具（指定起訖行號區段）"`）。 |
| **EC-04** | **`knowledge-db` 在獨立沙盒測試環境中（未載入 `agents-workflow` 運行模組時）解析 `{agent_tool.file_read_range}`** | `core.locale._resolve_module_base_dir` 已支援 `module://` 與 `module.source://` 雙軌探索；若在極端完全無 `agents-workflow` 源碼與模組的環境下，二階插值依據 `sub_01` `[EC-03]` 保留或由 `knowledge-db/locales/zh.json` 提供本地同名預設保底，絕不拋出 `KeyError`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **效能 (Performance)** | 執行期環境變數嗅探 `detect_active_host_dialect()` 僅掃描記憶體 `os.environ` 鍵名，單次耗時 $< 0.05\text{ms}$；無前綴跨模組查找受惠於 `_LOCALE_FILE_CACHE` 記憶體快取，熱路徑耗時 $< 0.5\text{ms}$。 |
| **NFR-02** | **零第三方依賴 (Zero Dependency)** | 100% 使用 Python 標準庫實現，零外部套件依賴。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Stage 2 Literal Fenced Block 保護 (`<!-- yscb:literal -->`)**：在 `compiler.py` 的 `resolve_stage2_uri` 中，帶有 `<!-- yscb:literal -->` 標記的範例區塊已被提前抽離保護；新增 `` `__%{key}__` `` 替換時，必須放在 `literal_blocks` 抽離之後、還原之前，以免教學文件中的語法範例被誤替換。
- **`[!NOTE]`Standalone Code Span 反引號保留與剝除差異**：
  - 在 `compiler.py` 中，`` `__#{uri}__` `` 與 `` `__${uri}__` `` 作為 Markdown 連結 `[text](`__#{uri}__`)` 或路徑時，Standalone 模式會剝除外層反引號；
  - 但在手冊正文中撰寫工具專有名詞（例如 `調用` `` `__%{agent_tool.shell_exec}__` `` `執行指令`）時，替換後的工具名稱（如 `` `run_command` `` 或 `` `Bash` ``）**保留外層反引號作為 Inline Code** 最符合 Markdown 排版習慣；唯有當 `zh` 保底為中文描述或穿插在其他反引號內時，維持一致的行內代碼格式即可（`[P01:DR-01]`：`` `__%{key}__` `` 位於反引號 `` `...` `` 內部時，直接替換 `__%{key}__` 本身並保留外層反引號 `` `...` ``，如此無論是單獨寫 `` `__%{agent_tool.shell_exec}__` `` 變成 `` `run_command` ``，還是穿插寫 `` `請使用 __%{agent_tool.shell_exec}__` ``，行為 100% 統一且直覺！）。

