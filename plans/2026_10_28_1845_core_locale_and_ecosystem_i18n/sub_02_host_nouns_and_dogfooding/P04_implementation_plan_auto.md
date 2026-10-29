# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-05` 在 API 規格書中有對應介面（`detect_active_host_dialect`、`_get_all_registered_locale_modules`、`resolve_raw`、`ArtifactCompiler.resolve_stage2_uri`）
- [x] **邊界防護**：`EC-01` ~ `EC-04` 有具體錯誤處理策略（Caller-First Shadowing、未知 `__%{key}__` 告警降級、無環境變數回退 `["zh"]`、沙盒跨模組自動尋址）
- [x] **依賴純淨**：符合 `NFR-01` ~ `NFR-02` 指標約束（100% Python 標準庫，環境嗅探 $< 0.05\text{ms}$）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 補充無 `<module>:` 前綴之全域穿透查找與執行期宿主環境變數嗅探說明 |
| **專題手冊** | `docs/agents-workflow/compiler_and_publisher.md` | Modify | 補充 Stage 2 `` `__%{key}__` `` 宿主專有名詞投影語法與 `agent_tool.*` 詞庫表 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 檢視是否需補充多平台並發環境嗅探與 `YSCB_LOCALE` 顯式覆寫優先權註記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `core/locale.py` 與 `agents_workflow/compiler.py` 介面 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_02` 宿主專有名詞庫、Stage 2 `__%{key}__` 轉譯與 `knowledge-db` Dogfooding 摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：在 Antigravity IDE 中執行 `dev test` 單元測試時，因為當前外層進程已經帶有 `ANTIGRAVITY_*` 環境變數，會不會導致測試 `get_active_chain()` 時被自動塞入 `"nouns-antigravity"` 而影響預設值斷言？  
> [*] **防護解法**：
> 1. 依 `[P03:DR-01]`，當設定了 `YSCB_LOCALE` 或顯式傳入 `chain` 時，完全以顯式設定為準。
> 2. 在 `detect_active_host_dialect()` 中，支援讀取環境變數並於測試案例內精準驗證各平台環境變數映射；同時在 `get_active_chain()` 中，將環境嗅探到的 `nouns-<host>` 前置於自然語系鏈（如 `["nouns-antigravity", "zh"]`），而基礎自然語系設定 `DEFAULT_LOCALE_CHAIN` 仍保持 `["zh"]`，不會影響既有指定 `chain=...` 的測試。

> [?] **尖銳問題 2**：當 `knowledge-db` 在 `dev test knowledge-db` 拋棄式沙盒中執行時，`core.locale` 能否無前綴找到 `agents-workflow` 提供的 `agent_tool.file_read_range`？  
> [*] **防護解法**：在 `_get_all_registered_locale_modules` 中，除了從 `core.contributes.get("core", "locales")` 取得已聚合模組外，固定將 `"agents-workflow"` 與 `"core"` 納入候選清單；而 `_resolve_module_base_dir("agents-workflow")` 已內建 `module://agents-workflow` 與 `module.source://agents-workflow` 雙軌解析，因此在沙盒與運行期皆可 100% 穩定解析。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`core.locale` 無前綴全域穿透查找與執行期宿主嗅探)**：修改 `ys_codebase/source/core/core/locale.py`，實作 `detect_active_host_dialect()`、`_get_all_registered_locale_modules()`，擴充 ` get_active_chain()` 與 `resolve_raw()`，並於 `ys_codebase/source/core/tests/test_locale.py` 補齊單元測試。
2. **TASK-02 (`agents-workflow` 宿主專有名詞庫與 `contributes/core.json` 宣告)**：建立 `ys_codebase/source/agents-workflow/locales/{definition,zh,nouns-antigravity,nouns-claude,nouns-codex}.json`，並於 `ys_codebase/source/agents-workflow/contributes/core.json` 註冊 `"locales"`。
3. **TASK-03 (`agents-workflow` Stage 2 `` `__%{key}__` `` 專有名詞轉譯與指紋連動)**：修改 `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` 與 `publisher.py`，支援依 `target_name` 展開 `` `__%{key}__` ``，更新 `yscb-cli-guide/SKILL.md`，並於 `ys_codebase/source/agents-workflow/tests/test_compiler.py` 補齊測試。
4. **TASK-04 (`knowledge-db` 截斷提示與 `knowledge-db-search/SKILL.md` 實機 Dogfooding)**：建立 `ys_codebase/source/knowledge-db/locales/{definition,zh}.json`，註冊 `ys_codebase/source/knowledge-db/contributes/core.json`，更新 `ys_codebase/source/knowledge-db/scripts/cli.py` 與 `SKILL.md`，並更新測試與本機 `@build` 熱部署回測。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** `ArtifactCompiler.resolve_stage2_uri` 在展開 `` `__%{key}__` `` 時，無論是在行內反引號 `` `__%{key}__` `` 或穿插反引號 `` `cmd __%{key}__` `` 還是 Fenced Code Block 內，均直接將 `__%{key}__` 子字串替換為解析後的專有名詞（保留外層反引號），使投影出的 Markdown 技能檔中工具專有名詞自動呈現為標準行內代碼（如 `` `read_file (StartLine/EndLine)` `` 或 `` `Read (offset/limit)` ``）。

