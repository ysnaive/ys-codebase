# 當前進度與暫停交接現場 (Handoff Context)

> 暫停時間：2026-10-24 16:54  
> 所屬計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 當前所在階段：Umbrella In Progress（跨主計畫 Global Steps 1~8 已 100% 完成並 Commit；下一動為啟動 Global Step 9：`sub_05_skill_creator_extension_workflow`）  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 現場已完成事項（含跨主計畫 Global Step 全局脈絡）

- [x] **【全局戰略背景】跨主計畫「4 階段 10 步 (4-Stage 10-Step Global Priority Order)」交錯落地架構**：
  - **為什麼設計 Global Step 交錯順序**：
    專案先前同時規劃了兩大史詩級 Umbrella 主計畫——**`AW` 主計畫 (`2026_10_23_1314_agents_workflow_aci_and_delegation_evolution`)** 與 **`ECO` 主計畫 (`2026_10_23_1122_ecosystem_modules_hardening_and_test_purification`)**。
    1. 為了讓 `ECO` 四大核心模組（`core`、`dev`、`server`、`knowledge-db`）在重構與純化測試集時，能直接受惠於新版的 `roadmap promote` 物理遷入機制與 `testing-sop` 六大測試鐵律／Subagent 審查守門，因此將 **`AW/sub_01` ~ `AW/sub_03` 排在 Stage 1（Global Steps 1~2）最優先執行**。
    2. 接著暫停 `AW` 主計畫，切入 **Stage 2 & Stage 3（Global Steps 3~7）完整執行並結案歸檔 `ECO` 主計畫 (`2026_10_23_1122`)**，將 `core`、`dev`、`server`、`knowledge-db` 的架構、CLI 契約與測試集徹底加固純化完畢。
    3. 待四大模組 API 與 CLI 完全穩定後，再回到本主計畫進入 **Stage 4（Global Steps 8~10）**：先於 **Global Step 8 (`AW/sub_04`)** 建立 `/how-to-config-yscb`、`/how-to-yscb` 與 `PROJECT_ROLE_AND_BOUNDARIES` 錨點並注入四大模組最新鮮準確的指南片段；再於 **Global Step 9 (`AW/sub_05`)**（此時全系統所有新增 Token 錨點已 100% 定型）建立 `/skill-creator` 與完整錨點擴充手冊；最後於 **Global Step 10 (`AW/sub_06`)** 對 `agents-workflow/tests/` 執行測試集純化與全主計畫二次驗收結案。

- [x] **Global Steps 1 ~ 8 逐歩完成狀態總覽**：
  - **(前置已完成) `AW/sub_01_python_aci_toolchain` (`Completed`)**：
    - `plan status --resume` 確定性狀態機領航與 `handoff.md` 原子閱後即焚 (`Consume & Delete`)、`plan verify --phase` 左移雙檔檢核與 `P01<->P06` 需求追溯差集比對、`--log` 免讀盲寫追加 `changelog.md`（遷入 `sub_01/roadmap.md`）。
  - **Global Step 1 — `AW/sub_02_roadmap_and_todo_refactoring` (`Completed`)**：
    - 拆分 Tier 1 `/todo`（`plans/roadmap/TODO.md` 單調遞增計數器、免讀盲寫 `todo add`、`todo promote` 批次拔除立項）與 Tier 2 `/roadmap`（`roadmap promote` `Consume-on-Promote` 物理搬移與 `ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}` `Seeded` 狀態領航）（遷入 `sub_02/roadmap.md`）。
  - **Global Step 2 — `AW/sub_03_testing_sop_and_subagent_isolation` (`Completed` + `revision_log.md [REV-01]`)**：
    - 建立環境型技能 `testing-sop`（六大測試鐵律、`TESTING_SOP_STANDARDS` 錨點、`references/test_suite_audit_and_purification.md` `T-01~T-06` 存量體檢模型）並植入 `AgentsStandards.md`、`phase_04`~`phase_06`、`plan_modes.md` 連鎖守門；支援 `RoadmapManager.promote_roadmap()` 同目錄多路線圖無損追加合併（合流遷入 2 份路線圖至 `sub_03/roadmap.md`）。
    - *註：後續經獨立修訂計畫 `2026_10_24_1112_subagent_review_timing_revision` (Commit `36501a3`) 正式廢除「支柱二 Phase 05 實作隔離委派（2-Strike Limit）」，改由主 Agent 直接執行 Phase 05；並將「支柱三 Fresh-Eyes 唯讀靜態冷眼審查」左移至 Phase 06 請求開發者 UX 驗收前（強制零劇透傳址、僅用唯讀工具禁跑實機測試），於 Phase 07 設為條件式複審（僅在 UX 階段曾修改代碼時觸發）。*
  - **Global Steps 3 ~ 7 — `ECO` 主計畫 `2026_10_23_1122` 全數結案並歸檔 (`Completed & Archived`, Commit `96819f1`)**：
    - Step 3 (`ECO/sub_01`): `core` 微內核去耦與測試純化（21 支測試檔，193/193 Passed）。
    - Step 4 (`ECO/sub_02`): `dev` 3-Gate 全庫防回退、`UNKNOWN > 0` 剛性阻斷與測試純化（7 支測試檔，79/79 Passed）。
    - Step 5 (`ECO/sub_03`): `server` Worker IPC 管道硬隔離、兩階段停機與測試純化（3 支測試檔，40/40 Passed）。
    - Step 6 (`ECO/sub_04`): `knowledge-db` 冷啟動向量死鎖解除、調用圖譜熱修補雙階入度保真與測試純化（12 支測試檔，150/150 Passed）。
    - Step 7 (`ECO/sub_05`): 四大模組 E2E 聯合驗收與 8 份已消費 Roadmap 100% `Consume-on-Promote` 閉環歸檔。
  - **Global Step 8 — `AW/sub_04_onboarding_and_config_coaching` (`Completed` + `revision_log.md [REV-01, REV-02]`, Commit `21b43b4`)**：
    - 合流遷入 2 份路線圖（`how_to_config_yscb_and_project_role_roadmap.md` + `how_to_yscb_interactive_coaching_roadmap.md`）至 `sub_04/roadmap.md`。
    - 修正 `ArtifactCompiler._resolve_source_path()` 支援跨模組 `module://<mod>/<rel_p>` 同級模組目錄 Fallback 防串線；修正 `scripts/cli.py:tokens()` 兼容 `value` 與 `name` 欄位（`KNOWLEDGE_DB_SPACE` 正常顯示，全系統目前已註冊 21 個 Token）。
    - 於 `AgentsStandards.md` 增設 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` `` 錨點；更新 `context-init/SKILL.md`。
    - 建立 `/how-to-config-yscb`（含 `HOW_TO_CONFIG_MODULES` 錨點、四步閉環、全綠免改短路、本體空間三處一次對齊、依 `release_target` `projections` 動態解析二層物化唯讀空間禁硬編碼 `.agents/` 或 `.claude/`、三步編譯發布守門）與 `/how-to-yscb`（含 `HOW_TO_YSCB_MODULES` 錨點、資深教練 `Coach / Mentor Persona` 切換與狀態卡格式豁免、雙入口自適應領航與角度 A~D、兩階段隨包手冊調度、新開實戰 Session 起手式打包）。
    - 於 `core`、`dev`、`server`、`knowledge-db` 四大模組各新增三要素結構之 `assets/config_guide.md` 與 `assets/usage_guide.md`（各 15~25 行）並註冊 `contributes/agents-workflow.json`。
    - 對宿主 Windows NTFS 歷史大寫目錄（`source/{core,dev,server,knowledge-db}/Scripts` 與 `docs/Core`）完成一次性兩段式正名，根除跨平台 `virtiofs` 大小寫雙影與 `--sync` 解壓衝突；全生態系 5 大模組沙盒測試 **595/595 (100.0%)** 全綠。
    - 實機執行 `/how-to-config-yscb` 完成本倉 Dogfooding：由未配置狀態自動探勘、呈遞草案、經開發者確認後代寫 `ys_codebase/config/agents-workflow/snippets/project_role.md` 與 `testing_guide.md` 並掛載至 `ys_codebase/config/agents-workflow/contribute.json`，已正式物化至根目錄 `AGENTS.md`（`## 0. 專案角色與主客體空間邊界`）與 `.agents/skills/testing-sop/SKILL.md`（`## 4. 專案特化測試流程與注意事項`）。

---

## 2. 現場未完成 / 進行中待辦（Stage 4 最後兩步：Global Steps 9 & 10）

- [ ] **Global Step 9 — 子計畫 `sub_05_skill_creator_extension_workflow`（下一動立即開立與執行，來源儲備：`plans/roadmap/skill_creator_and_layer2_extension_roadmap.md`）**：
  1. **Consume-on-Promote 物理遷入（本主計畫第 7 份、也是最後 1 份待消費之目標 Roadmap）**：
     - 執行 `python yscb.py agents-workflow roadmap promote skill_creator_and_layer2_extension_roadmap --plan 2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_05_skill_creator_extension_workflow --model "<當輪平台宣告模型>"`，將 `plans/roadmap/skill_creator_and_layer2_extension_roadmap.md` 物理遷入為 `sub_05_skill_creator_extension_workflow/roadmap.md`。
     - *(註：`plans/roadmap/` 下其餘 3 份檔案 `multi_platform_release_targets_expansion_roadmap.md`、`release_binary_storage_optimization.md`、`skill_release_prefix_isolation.md` 為長期儲備，不屬於本主計畫範疇，切勿誤遷。)*
  2. **建立主動指令型技能 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md`**：
     - Frontmatter `description`（主動指令型極簡契約）：`引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，自動對接語意 URI 與雙層編譯註冊閉環。僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。`
     - 內建四步擴充與建置工作流閉環：
       - **步驟 1（需求意圖訪談與三軌分流 `3-Track Triage`）**：
         - **軌跡 ①（純錨點注入模式 `Anchor-Only Injection`）**：局部階段／熱啟動注意事項 $\to$ 不建新 Skill，直接於 `config://agents-workflow/snippets/<name>.md` 撰寫片段並注入既有 `__@{...}__` 錨點（0 額外路由開銷）。
         - **軌跡 ②（被動環境攔截型 Skill `Ambient Skill`）**：專案全局注意事項／工具攔截 $\to$ 於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（採三段式 `核心用途 → 觸發情境 → 排除情境` `description`）並注入 `AGENTS_SKILL_ROUTING`。
         - **軌跡 ③（功能特化型 Skill `Feature Skill`）**：專案特定子系統多步驟工作流 $\to$ 於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（Slash 主動呼叫採極簡指令契約；意圖自動觸發採三段式邊界）並註冊匯出與中樞/路由掛載。
       - **步驟 2（可用錨點與語意 URI 自動檢索與「擴充藍圖確認卡」Gate）**：
         - 調用 `python yscb.py agents-workflow tokens` 與 `python yscb.py uri list` 搭配 `./references/extension-guide.md`，向開發者呈遞 **「🛠️ /SkillCreator 專案擴充藍圖確認卡」**（含需求分類、預計產出資產、掛載錨點、引用語意 URI）並強制 End Turn 等待拍板。
       - **步驟 3（合規資產生成與單反引號語法封裝）**：
         - 第一層固定存放於扁平路徑 `config://agents-workflow/skills/<name>/SKILL.md`（及單層 `references/`）或 `config://agents-workflow/snippets/<name>.md`（不額外套 `assets/`）。
         - **防呆 1（同技能內部 vs. 跨技能語意 URI）**：指向同技能自身 `references/` 使用標準相對路徑 `./references/xxx.md`；指向其他技能、模板或專案目錄強制使用單反引號包覆之語意 URI（`` [`text`](`__#{uri}__`) ``、`` `__${uri}__` ``）。
         - 保持通用去特化（Zero Specialization Pollution），並於尾部預留 `` `__@{SKILL_CREATOR_STANDARDS}__` `` 擴充錨點與 `## 常見踩坑指南 (Gotchas)`。
       - **步驟 4（宣告式組態註冊與三步嚴格編譯驗證守門 — 防呆 2）**：
         - 以最小增量（Additive Edit）更新 `config://agents-workflow/contribute.json`，強制依序執行：① `python yscb.py contributes check` $\to$ ② `python yscb.py agents-workflow compile`（確認 0 Error / 0 Warning，無拼錯 Token 或裸寫標籤）$\to$ ③ 100% 通過後方可執行 `python yscb.py agents-workflow release` 物化至目標平台。
  3. **建立附屬單層參考手冊 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md`**：
     - 頂部具備 `## 目錄 (Contents)`（TOC）。
     - 完整彙整全系統 **22 個已註冊 Stage 1 Token 錨點地圖**（含 `sub_03` 新增之 `TESTING_SOP_STANDARDS`、`sub_04` 新增之 `PROJECT_ROLE_AND_BOUNDARIES` / `HOW_TO_CONFIG_MODULES` / `HOW_TO_YSCB_MODULES`、`knowledge-db` 註冊之 `KNOWLEDGE_DB_SPACE` 及 `sub_05` 新增之 `SKILL_CREATOR_STANDARDS`）、Stage 2 語意 URI 轉換規則、單反引號防呆範例與 `config://agents-workflow/contribute.json` (`export` / `insert`) 最小增量註冊範本。
  4. **組態註冊、單元測試與三層文檔同步**：
     - 於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 及 `_manifest.md` 註冊 `skill-creator` 技能匯出與 `SKILL_CREATOR_STANDARDS` Token（內建匯出技能總數將由 16 個增為 17 個）。
     - 於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 更新 `test_ft_08` 之 `expected_skills` 與 `command_driven_skills`（加入 `"skill-creator"`），並新增 `test_ft_11_sub05_skill_creator_extension_workflow` 驗證三軌分流、藍圖確認卡、單層參考手冊與 0 裸寫標籤。
     - 更新 `ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`。

- [ ] **Global Step 10 — 子計畫 `sub_06_final_acceptance_and_suite_purification`（待 `sub_05` 完成後啟動之收官步）**：
  - 依 `testing-sop` 六大鐵律與 `references/test_suite_audit_and_purification.md` 三步純化工作流，對 `ys_codebase/source/agents-workflow/tests/` 執行六維度體檢、碎片檔整併與子系統 1:1 歸戶收斂（如同 `ECO` 主計畫對 `core`/`dev`/`server`/`knowledge-db` 所做的測試純化）。
  - 執行 `sub_01` ~ `sub_05` 跨功能端到端二次驗收，確認本主計畫所消費之全部 Roadmap（共 7 份原始檔案，收斂於 `sub_01`~`sub_05` 各目錄之 `roadmap.md`）100% 閉環，完成三層文檔最終對齊與 `2026_10_23_1314` Umbrella 主計畫結案。

---

## 3. 踩坑與注意事項 (Gotchas & Blockers)
- [WARN] **嚴禁在功能開發階段靜態預建專案層級組態片段**：前次於 `sub_03` / `sub_04` 曾誤將應由 `/how-to-config-yscb` 動態生成之片段於開發階段預先寫入 `ys_codebase/config/agents-workflow/snippets/`（已於 `sub_03 [REV-01]` 與 `sub_04 [REV-02]` 修正）。在 `sub_05` 開發 `skill-creator` 時，`agents-workflow` 僅提供通用技能與 `SKILL_CREATOR_STANDARDS` 空錨點，**切勿在 `ys_codebase/config/agents-workflow/` 預建任何測試用靜態 snippet 或 dummy skill**。
- [WARN] **遵守 `[DN-AW-03]` 單反引號包覆與範例文字逃逸防呆**：在撰寫 `skill-creator/SKILL.md` 與 `references/extension-guide.md` 說明標籤語法時，任何散文中的範例標籤若寫成真實可匹配之佔位符（或未包覆反引號），會觸發 `ArtifactCompiler` 的 `Unenclosed placeholder tag` 或 `Unresolved semantic URI tag` 警告；測試 `test_ft_08` 亦會掃描 `skills_dir.rglob("*.md")` 強制斷言 `UNENCLOSED_TAG_REGEX` 為空清單 `[]` 且 `skill-optimizer` / `skill-creator` 不含特化耦合字眼。
- [WARN] **Phase 06 Pre-UX 盲審協定**：在 `sub_05` 進入 Phase 06 自動化測試全綠後、向開發者請求 UX 驗收前，必須依最新 `phase_06_test.md` 規範派發支柱三唯讀 Reviewer Subagent（零劇透傳址：僅提供計畫目錄路徑，不告知實作細節，並強制聲明僅可使用唯讀工具進行靜態檢查、嚴禁執行實機或測試命令）。

---

## 4. 下一次接手時的第 1 步 (Immediate Next Action)
- 在新對話視窗輸入 `/continue`（將自動觸發 `python yscb.py agents-workflow plan status --resume --plan 2026_10_23_1314_agents_workflow_aci_and_delegation_evolution` 讀取並原子銷毀本 `handoff.md`）後：
  1. 讀取 `plans/2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/umbrella_overview.md` 與 `plans/roadmap/skill_creator_and_layer2_extension_roadmap.md`。
  2. 執行單行指令啟動 Global Step 9 (`sub_05`) 並物理遷入路線圖：
     `python yscb.py agents-workflow roadmap promote skill_creator_and_layer2_extension_roadmap --plan 2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_05_skill_creator_extension_workflow --model "<當輪平台宣告模型>"`
  3. 依據遷入之 `sub_05_skill_creator_extension_workflow/roadmap.md` 建立 `P00_discuss.md` 並呈遞 P00 討論卡等待開發者確認（或依 `/auto` 指示連續推進）。
