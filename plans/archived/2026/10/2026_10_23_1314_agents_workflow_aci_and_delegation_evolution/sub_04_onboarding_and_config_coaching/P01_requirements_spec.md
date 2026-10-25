# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `AgentsStandards.md` 專案角色與空間邊界錨點 (`PROJECT_ROLE_AND_BOUNDARIES`) 與 `context-init` 熱啟動提取 | 1. 於 `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md` 導言下方、`## 1. 核心原則` 上方預留獨立行 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``，並於 `contributes/agents-workflow.json` 註冊 `PROJECT_ROLE_AND_BOUNDARIES` Token。<br/>2. 專案層級之 `config://agents-workflow/snippets/project_role.md`（以 `## 0. 專案角色與主客體空間邊界 (Project Role & Scope Boundaries)` 獨立成節，涵蓋極簡三要素：① 開發者角色與專案使命、② 本體業務空間 `First-Party Scope`、③ 外部工具包與黑盒依賴 `External Toolkits` 含 `.modules/` 與依 `release_target` `projections` 動態解析之二層物化唯讀空間）交由 `/how-to-config-yscb` 實機探勘草擬並於開發者確認後代寫掛載。<br/>3. 於 `context-init/SKILL.md` 步驟 1 補充提取專案角色與空間邊界（若已配置），並於熱啟動狀態卡底部附上 `/how-to-yscb` 與 `/how-to-config-yscb` 輕量提示。 | P0 | [P00:DR-01], [P00:DR-05] |
| **FR-02** | 主動指令型技能 `/how-to-config-yscb`（設定體檢、三處聯動對齊代寫與三步編譯守門） | 1. 建立 `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`，Frontmatter `description` 採用主動指令型極簡契約，並於 `contributes/agents-workflow.json` 註冊 `how-to-config-yscb` 技能匯出與 `HOW_TO_CONFIG_MODULES` Token。<br/>2. 內建四步閉環：① 全專案設定與空間拓撲自動探勘（執行 `[SAFE]` 診斷指令、檢查 `.gitignore` 是否涵蓋 `*.local.json`、檢查各模組組態與第一層片段）$\to$ ② 呈遞「設定健康度報告與代寫提案卡」（支援「全綠免改短路」；若有缺失則實現「本體空間三處一次對齊」草擬 `config://agents-workflow/snippets/project_role.md`、`config://agents-workflow/snippets/testing_guide.md` 及 `config://knowledge-db/contribute.json` 之 `spaces.source.include`，明確標示 `config.project.json` vs. `config.local.json` 層級並 End Turn 等待確認）$\to$ ③ 獲確認後直接代寫修復並強制依序執行 `contributes check` $\to$ `agents-workflow compile` (0 Error/0 Warning) $\to$ `agents-workflow release` 三步驗證守門 $\to$ ④ 新開實戰 Session 隔離提醒。 | P0 | [P00:DR-02], [P00:DR-05] |
| **FR-03** | 主動指令型技能 `/how-to-yscb`（雙入口互動式教練、兩階段知識調度與實戰 Session 隔離） | 1. 建立 `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md`，Frontmatter `description` 採用主動指令型極簡契約，並於 `contributes/agents-workflow.json` 註冊 `how-to-yscb` 技能匯出與 `HOW_TO_YSCB_MODULES` Token。<br/>2. 內建四大核心機制：① 跨模組知識底座（工作流核心觀念、6 大計畫模式選軌心法、常用指令組合拳 + `` `__@{HOW_TO_YSCB_MODULES}__` `` 各模組標準用法速查卡）$\to$ ② 雙入口自適應開場（純輸入 `/how-to-yscb` 時呈現已安裝模組與 A~D 四大探索角度選單；附帶具體問題時跳過選單直接解答）與唯讀教學護欄（僅允許唯讀工具與 `[SAFE]` 指令，禁改代碼或建計畫；若遇設定修復需求則轉介 `/how-to-config-yscb`）$\to$ ③ 兩階段知識調度（先用速查卡秒回，追問細節時按需讀取單反引號語意連結 `` [`<模組> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``）$\to$ ④ 實戰 Session 物理隔離提醒與「新 Session 專屬起手式指令區塊」打包。 | P0 | [P00:DR-03], [P00:DR-05] |
| **FR-04** | 四大核心模組（`core`、`dev`、`server`、`knowledge-db`）設定體檢卡與標準用法速查卡宣告式注入 | 1. 於 `ys_codebase/source/{core,dev,server,knowledge-db}/assets/` 各建立 `config_guide.md`（固定以 `### ⚙️ <模組名稱> 設定與體檢` 為標題，含組態項目、健康度檢查條件、隨包手冊單反引號語意連結）與 `usage_guide.md`（固定以 `### 📦 <模組名稱> (<一句話定位>)` 為標題，含模組定位、2~3 個黃金用法範例、隨包手冊單反引號語意連結），每段嚴格控制在 15~25 行以內。<br/>2. 於 `core`、`dev`、`knowledge-db` 既有 `contributes/agents-workflow.json` 及 `server` 新建之 `contributes/agents-workflow.json`（同步更新 `contributes/_manifest.md`）宣告 `mode: "below"` 注入至 `HOW_TO_CONFIG_MODULES` 與 `HOW_TO_YSCB_MODULES`。 | P0 | [P00:DR-04] |
| **FR-05** | `agents-workflow tokens` 顯示修復與 `ArtifactCompiler._resolve_source_path` 跨模組 Fallback 防串線 | 1. 修復 `ys_codebase/source/agents-workflow/scripts/cli.py:tokens()` 讀取 `tok.get("value") or tok.get("name") or ""`，並將 `knowledge-db/contributes/agents-workflow.json` 之 `token` 宣告統一補齊 `"value": "KNOWLEDGE_DB_SPACE"`，確保 `python yscb.py agents-workflow tokens` 完整顯示所有 Token 名稱無空白列。<br/>2. 修正 `ys_codebase/source/agents-workflow/agents_workflow/compiler.py:_resolve_source_path()` Step 2 本地模組相對路徑 Fallback：當 `path_or_uri` 為 `module://<mod>/<rel_p>` 且 `<mod> != "agents-workflow"` 時，定向至同級模組目錄 `os.path.join(os.path.dirname(self.module_root), mod_name, rel_p)`，杜絕跨模組同名資產誤讀。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 下游專案尚未配置 `PROJECT_ROLE_AND_BOUNDARIES`（無 `project_role.md` 注入） | `ArtifactCompiler.resolve_single_artifact` 自動清除獨立行 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``，物化後之 `AGENTS.md` 不殘留裸標籤、空標題或斷裂分隔線。 |
| **EC-02** | 執行 `/how-to-config-yscb` 時專案所有設定、`.gitignore` 與片段均已 100% 就緒 | 觸發「全綠免改短路（All-Green Short-Circuit）」，直接輸出全綠健康報告卡並詢問是否有特定參數欲微調，嚴禁無意義覆寫既有正常組態檔。 |
| **EC-03** | 使用者於 `/how-to-yscb` 教練視窗直接要求修改業務程式碼或建立開發計畫 | 觸發「唯讀教學護欄」，禮貌攔截實作請求，說明教練視窗與實戰視窗隔離原則，並為使用者生成可直接複製到全新 Session 貼上執行的「起手式 Prompt 區塊」。 |
| **EC-04** | 使用者輸入 `/how-to-yscb <具體問題>` 附帶明確提問，而非空指令 | 觸發「雙入口自適應開場」之入口 B，跳過 A~D 探索角度選單，直接針對該問題回答黃金用法並附上新開實戰 Session 提醒。 |
| **EC-05** | 跨模組注入之 `config_guide.md` 或 `usage_guide.md` 包含指向 `module://<mod>/README.md` 之語意連結 | 強制使用單反引號包裹 `` [`<模組> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``；Stage 1 編譯 `0` 裸寫標籤警告，Stage 2 正確解算為相對於目標 Skill 目錄之可點擊相對路徑。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 上下文經濟與行數預算 | 1. 每個模組注入之 `config_guide.md` 與 `usage_guide.md` 嚴格控制在 `15 ~ 25` 行以內。<br/>2. 匯聚四大模組注入後，物化之 `how-to-config-yscb/SKILL.md` 與 `how-to-yscb/SKILL.md` 總行數均控制在 `< 250` 行（遠低於 500 行上限）。 |
| **NFR-02** | 零外部依賴與 100% 測試守門 | 維持 100% Python 標準庫零外部依賴；`dev check --all`、`contributes check` 與受影響模組沙盒測試 100% 通過，跑測後工作區零殘留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 遵守 `[DN-AW-03]` 單反引號包覆鐵律**：所有跨模組注入片段與新建 `SKILL.md` 內之 `__@{...}__`、`__#{...}__`、`__${...}__` 必須 100% 以單反引號包裹（除非位於 Fenced Code Block 內），確保 `check_unenclosed_tags` 零警告。
- **`[!CAUTION]` 階段決策 `[P01:DR-01]` 二層物化空間動態解析**：在 `how-to-config-yscb` 草擬 `project_role.md` 時，禁止硬編碼僅寫死 `.agents/`，須 instructs Agent 依據當前啟用之 `release_targets` 動態標註對應之二層物化唯讀空間（如 `.agents/`、`.claude/`）。

