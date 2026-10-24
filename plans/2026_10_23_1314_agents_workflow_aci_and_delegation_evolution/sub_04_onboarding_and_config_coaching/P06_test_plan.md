# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `AgentsStandards.md` 包含 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``、支援 `PROJECT_ROLE_AND_BOUNDARIES` 動態注入與空值抹除，且 `context-init/SKILL.md` 包含邊界提取與 `/how-to-yscb`、`/how-to-config-yscb` 提示。 | FR-01 | `python yscb.py dev test agents-workflow -k test_ft_10_sub04` |
| **FT-02** | 單元測試 | 驗證 `how-to-config-yscb/SKILL.md` 匯出註冊、`HOW_TO_CONFIG_MODULES` 錨點、四步體檢代寫閉環、三處聯動對齊（`project_role.md` 極簡三要素 + `testing_guide.md` + `knowledge-db` spaces）、二層物化空間動態解析（嚴禁硬編碼 `.agents/` 或 `.claude/`）與三步編譯驗證守門。 | FR-02, EC-02, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_10_sub04` |
| **FT-03** | 單元測試 | 驗證 `how-to-yscb/SKILL.md` 匯出註冊、`HOW_TO_YSCB_MODULES` 錨點、資深教練角色切換（`Coach / Mentor Persona`）與狀態卡格式豁免、雙入口自適應開場（A~D 角度選單 vs. 直接解答）、唯讀教學護欄與新開實戰 Session 隔離打包規範。 | FR-03, EC-03, EC-04, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_10_sub04` |
| **FT-04** | 整合測試 | 驗證 `core`、`dev`、`server`、`knowledge-db` 四大模組之 `assets/{config_guide.md,usage_guide.md}` 三要素結構、每檔 15~25 行預算及單反引號隨包手冊語意連結 Stage 1/2 完整解析。 | FR-04, EC-05, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_10_sub04` |
| **FT-05** | 單元測試 | 驗證 `scripts/cli.py:tokens()` 同時支援 `value` 與 `name` 欄位（`KNOWLEDGE_DB_SPACE` 正常顯示非空白），以及 `ArtifactCompiler._resolve_source_path()` 針對跨模組 `module://<mod>/...` 不誤退回 `agents-workflow` 目錄。 | FR-05 | `python yscb.py dev test agents-workflow -k test_resolve_source_path_cross_module` |
| **ET-01** | 邊界測試 | 驗證當未提供 `PROJECT_ROLE_AND_BOUNDARIES` 注入時，`resolve_single_artifact` 自動清除獨立行錨點，不殘留裸標籤或斷裂空行；且所有新建與注入 Markdown 檔案 `0` 裸寫標籤警告。 | EC-01, EC-05 | `python yscb.py dev test agents-workflow -k test_resolve_source_path_cross_module` |
| **RT-01** | 回歸測試 | 執行全生態系靜態合規檢查 (`dev check --all`)、`contributes check` 與受影響模組沙盒回歸測試 (`agents-workflow`, `core`, `dev`, `server`, `knowledge-db`) 100% 通過。 | NFR-02 | `python yscb.py dev check --all && python yscb.py dev test --all -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_10_sub04_onboarding_and_config_coaching_skills` 通過：驗證 `AgentsStandards.md` 之 `PROJECT_ROLE_AND_BOUNDARIES` 錨點、`project_role.md` 注入與 `context-init` 提示正常。 | 2026-10-24 |
| **FT-02** | `Passed` | `test_ft_10_sub04_onboarding_and_config_coaching_skills` 通過：驗證 `/how-to-config-yscb` 四步體檢閉環、全綠短路、三位一體對齊與三步驗證守門正常。 | 2026-10-24 |
| **FT-03** | `Passed` | `test_ft_10_sub04_onboarding_and_config_coaching_skills` 通過：驗證 `/how-to-yscb` 雙入口自適應領航、兩階段知識調度與純唯讀教練護欄正常。 | 2026-10-24 |
| **FT-04** | `Passed` | `test_ft_10_sub04_onboarding_and_config_coaching_skills` 通過：驗證 `core`、`dev`、`server`、`knowledge-db` 四大模組 `assets/{config_guide.md,usage_guide.md}` 均符合 15~25 行預算且單反引號語意連結完整解析。 | 2026-10-24 |
| **FT-05** | `Passed` | `test_resolve_source_path_cross_module_and_tokens_cli` 通過：驗證跨模組 sibling fallback 與 `tokens` CLI 顯示 21 個 Token（含 `KNOWLEDGE_DB_SPACE` 非空白）正常。 | 2026-10-24 |
| **ET-01** | `Passed` | `test_ft_10_sub04_onboarding_and_config_coaching_skills` 與 `agents-workflow compile` / `release --force` 驗證通過（55 檔物化，0 未包覆標籤警告）。 | 2026-10-24 |
| **RT-01** | `Passed` | `dev check --all` (5/5 PASS)、`contributes check` (14 files PASS)、全生態系 5 大模組沙盒回歸與 `--sync` 100% 通過（`core`: 193/193、`dev`: 79/79、`server`: 40/40、`knowledge-db`: 150/150、`agents-workflow`: 133/133；同時完成宿主 NTFS 歷史大寫 `Scripts`/`Core` 目錄兩段式正名消除跨平台大小寫雙影），且支柱三 Pre-UX 唯讀冷眼盲審 Subagent 回傳 `REVIEW_STATUS: PASSED`。 | 2026-10-24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視物化後之根目錄 `AGENTS.md`（包含 `## 0. 專案角色與主客體空間邊界`）、`.agents/skills/how-to-config-yscb/SKILL.md` 與 `.agents/skills/how-to-yscb/SKILL.md`（包含四大核心模組自動注入之設定體檢卡、標準用法速查卡與可點擊之隨包手冊連結），以及 `python yscb.py agents-workflow tokens` 輸出。 | `[測試通過]` | 開發者於 2026-10-24 確認通過 |

