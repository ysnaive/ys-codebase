# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證無 `<module>:` 前綴之全域穿透查找（`locale.t("agent_tool.file_read_range")`）與二階插值跨模組解析 | FR-01, FR-03 | `python yscb.py dev test core -k test_sub02_unqualified_global_lookup_and_host_dialect_sniffing` |
| **FT-02** | 單元測試 | 驗證 `detect_active_host_dialect()` 對 `CLAUDECODE`、`CODEX_SANDBOX`、`ANTIGRAVITY_AGENT` 環境變數之自動嗅探 | FR-02, EC-03, NFR-01 | `python yscb.py dev test core -k test_sub02_unqualified_global_lookup_and_host_dialect_sniffing` |
| **FT-03** | 整合測試 | 驗證 `ArtifactCompiler.resolve_stage2_uri` 依 `target_name` (`antigravity` / `claude` / `codex`) 展開 `` `__%{key}__` `` 專有名詞 | FR-04, NFR-02 | `python yscb.py dev test agents-workflow -k test_ft_13_stage2_locale_noun_projection_across_targets` |
| **FT-04** | 整合測試 | 驗證 `knowledge-db search -s --json` 截斷提示透過 `core.locale` 與 `agent_tool.file_read_range` 動態替換工具名 | FR-05, EC-04 | `python yscb.py dev test knowledge-db -k test_cli_options_extraction_and_orthogonal_filter` |
| **ET-01** | 邊界測試 | 驗證跨模組同名無前綴 Key 時呼叫端自身定義優先（Caller-First Shadowing） | EC-01 | `python yscb.py dev test core -k test_sub02_unqualified_global_lookup_and_host_dialect_sniffing` |
| **ET-02** | 邊界測試 | 驗證 Stage 2 遭遇未知專有名詞 `` `__%{agent_tool.non_existent}__` `` 時輸出 `[compiler:warning]` 並安全保留原標籤 | EC-02 | `python yscb.py dev test agents-workflow -k test_ft_13_stage2_locale_noun_projection_across_targets` |
| **RT-01** | 回歸測試 | 驗證 `core` (206/206)、`agents-workflow` (135/135)、`knowledge-db` (150/150) 全模組單元測試與靜態檢查 100% 通過 | FR-01 ~ FR-05 | `python yscb.py dev test core -q && python yscb.py dev test agents-workflow -q && python yscb.py dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 無前綴查找 `agent_tool.file_read_range` 於 `nouns-antigravity`、`nouns-claude`、`nouns-codex`、`zh` 下精確命中 | 2026-10-29 |
| **FT-02** | `Passed` | `detect_active_host_dialect` 正確回傳對應 `nouns-<host>`，無匹配環境變數時回傳 `None` | 2026-10-29 |
| **FT-03** | `Passed` | Stage 2 按 `target_name` 分別展開為 `` `read_file (StartLine/EndLine)` ``、`` `Read (offset/limit)` ``、`` `read_file` `` | 2026-10-29 |
| **FT-04** | `Passed` | `knowledge-db search -s --max-snippet-lines 5 --json` 截斷字串動態包含 `use Read (offset/limit) to view` | 2026-10-29 |
| **ET-01** | `Passed` | 本地定義 `agent_tool.file_read_range` 正確遮蔽全域定義，而未遮蔽之 `{agent_tool.shell_exec}` 穿透命中全域定義 | 2026-10-29 |
| **ET-02** | `Passed` | 未知專有名詞標籤正確向 `stderr` 輸出 `[compiler:warning]` 並保留原始標籤文字 | 2026-10-29 |
| **RT-01** | `Passed` | `core` 206/206、`agents-workflow` 135/135、`knowledge-db` 150/150 全數 100% 通過，且 `dev check` 全數 `PASSED` | 2026-10-29 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視已編譯發布之 `.agents/skills/yscb-cli-guide/SKILL.md`、`.agents/skills/knowledge-db-search/SKILL.md` 專有名詞投影結果（如 `` `read_file (StartLine/EndLine)` ``、`` `run_command` ``），或執行 `python yscb.py contributes check` 與 `knowledge-db search` 實機體驗 | `[測試通過]` | 開發者確認通過 |
