# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `skill-creator/SKILL.md` 存在且行數 $\le 180$ 行，Frontmatter `name: skill-creator` 與主動指令型 `description` 契約合規，內含四步進度檢核表、三軌擴充判定矩陣（軌跡 ①/②/③）、尾部 `` `__@{SKILL_CREATOR_STANDARDS}__` `` 錨點與 `## 常見踩坑指南 (Gotchas)`。 | FR-01, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **FT-02** | 單元測試 | 驗證 `skill-creator/SKILL.md` 步驟 2 規範調用 `agents-workflow tokens` 與 `uri list`、按需讀取 `references/extension-guide.md`，並強制包含「🛠️ /SkillCreator 專案擴充藍圖確認卡」與 End Turn 守門。 | FR-02 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **FT-03** | 單元測試 | 驗證 `skill-creator/SKILL.md` 步驟 3 與步驟 4 規範第一層扁平路徑（`config://agents-workflow/skills/<name>/SKILL.md` 與 `snippets/<name>.md`）、同技能相對路徑 vs. 跨空間語意 URI 分流，以及 `contributes check` $\to$ `compile` $\to$ `release` 三步編譯驗證守門。 | FR-03 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **FT-04** | 單元測試 | 驗證 `references/extension-guide.md` 存在、頂部含 `## 目錄 (Contents)`，完整收錄全系統 22 個 Stage 1 Token 錨點名稱、Stage 2 語意 URI 轉換規則與軌跡 ①/②/③ `contribute.json` 最小增量範本。 | FR-04, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **FT-05** | 單元測試 | 驗證 `contributes/agents-workflow.json` 與 `_manifest.md` 已註冊 `skill-creator` 與 `SKILL_CREATOR_STANDARDS`，`development-sop/SKILL.md` 與 `skill-optimizer/SKILL.md` 已補齊 `/skill-creator` 互指導流，且 `agents-workflow tokens` 實機輸出包含 `SKILL_CREATOR_STANDARDS`。 | FR-05 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **ET-01** | 邊界測試 | 驗證 `skill-creator/SKILL.md` 與 `references/extension-guide.md` 通過 `UNENCLOSED_TAG_REGEX` 零裸寫標籤掃描、零特化污染禁字掃描，且實機執行 `ArtifactCompiler.compile_stage1()` 與 `release()` 0 Error / 0 Warning。 | EC-01, NFR-02 | `python yscb.py dev test agents-workflow -k "test_ft_08 or test_ft_11"` |
| **ET-02** | 邊界測試 | 驗證三軌分流防呆（局部階段微調優先推薦軌跡 ① 純錨點注入、避免技能路由表無謂膨脹）與雙軌路徑引用防呆（同技能 `./references/...` vs. 跨空間語意 URI）。 | EC-02, EC-03 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **ET-03** | 邊界測試 | 驗證步驟 4 錯誤阻斷防呆（`contributes check` 或 `compile` 出現 Error/Warning 時嚴禁執行 `release`）及 `AGENTS_SKILL_ROUTING` 表格行錨點與獨立區塊錨點之結構區隔說明。 | EC-04, EC-05 | `python yscb.py dev test agents-workflow -k test_ft_11` |
| **RT-01** | 回歸測試 | 執行 `agents-workflow` 全模組單元測試套件與 `dev check agents-workflow`、`contributes check`，驗證 100% 通過且無回歸破壞。 | FR-01~FR-05, EC-01~EC-05, NFR-01~NFR-02 | `python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_11` 驗證 `skill-creator/SKILL.md` (114 行 $\le 180$ 行)、主動指令型 `description`、四步檢核表、三軌判定矩陣、`SKILL_CREATOR_STANDARDS` 錨點與 Gotchas 通過 | 2026-10-25 |
| **FT-02** | `Passed` | `test_ft_11` 驗證步驟 2 調用 `agents-workflow tokens`、`uri list`、讀取 `references/extension-guide.md` 及「🛠️ /SkillCreator 專案擴充藍圖確認卡」End Turn 守門通過 | 2026-10-25 |
| **FT-03** | `Passed` | `test_ft_11` 驗證第一層扁平路徑、同技能相對路徑 vs. 跨空間語意 URI 分流，以及 `contributes check` $\to$ `compile` $\to$ `release` 三步守門順序通過 | 2026-10-25 |
| **FT-04** | `Passed` | `test_ft_11` 驗證單層 `references/extension-guide.md` 含 `## 目錄 (Contents)`、全系統 22 個 Stage 1 Token 錨點地圖、Stage 2 URI 規則與三軌 JSON 範本通過 | 2026-10-25 |
| **FT-05** | `Passed` | `test_ft_11` 驗證 `contributes/agents-workflow.json`、`_manifest.md`、`development-sop/SKILL.md` 與 `skill-optimizer/SKILL.md` 雙向導流同步通過 | 2026-10-25 |
| **ET-01** | `Passed` | `test_ft_08` & `test_ft_11` 驗證零裸寫標籤、零特化污染，且實機 Stage 1 (`resolve_single_artifact`) 與 Stage 2 (`resolve_stage2_uri` + `<!-- yscb:literal -->` 字面量保護) 0 Error / 0 Warning 通過 | 2026-10-25 |
| **ET-02** | `Passed` | `test_ft_11` 驗證 `EC-02` 過度建技攔截（推薦軌跡 ① 純錨點注入，0 路由表膨脹）與 `EC-03` 雙軌路徑分流防呆通過 | 2026-10-25 |
| **ET-03** | `Passed` | `test_ft_11` 驗證 `EC-04` 三步驗證失敗阻斷與 `EC-05` `AGENTS_SKILL_ROUTING` Markdown 表格列結構屬性防呆通過 | 2026-10-25 |
| **RT-01** | `Passed` | `python yscb.py dev check agents-workflow` (`[PASS]`)、`python yscb.py dev test agents-workflow -q` (`Pass: 134(100.0%), Fail: 0`) 與支柱三獨立唯讀靜態盲審 (`REVIEW_STATUS: PASSED`) 全數通過 | 2026-10-25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視物化後之 `.agents/skills/skill-creator/SKILL.md` 與 `.agents/skills/skill-creator/references/extension-guide.md`，確認語意 URI 已正確轉譯為目標平台相對路徑、22 個錨點地圖清晰可讀，且 `python yscb.py agents-workflow tokens` 可查得 `SKILL_CREATOR_STANDARDS`。 | `[測試通過]` | 開發者審閱並指示將 `.agents/` / `.claude/` 改為 `release_target.projections` 通用敘述後驗收通過 |

