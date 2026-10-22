# 技術調研報告：Agents-Workflow 技能全面優化與 Skill-Optimizer 標準資產建置 (R01_skills_optimization_and_optimizer_asset.md)

> 調研主題：AI Agent Skills 業界最佳實踐調研、既有 11 項技能無損重構與 `skill-optimizer` 標準資產整合
> 建立日期：2026-10-22
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations
> 調研狀態：Concluded
> 模型：Gemini 4 Argon (Low)
> 模板版本：v1.1

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **業界標準快速演進**：隨著 [Anthropic Claude 平台技能規範](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)、[OpenAI ChatGPT 與 Codex Skills 架構](https://learn.chatgpt.com/docs/build-skills) 以及 [Agent Skills 開放標準 (agentskills.io)](https://agentskills.io/specification) 成為跨平台共識，技能的自動觸發（Implicit Invocation）高度依賴 YAML Frontmatter 之 `description` 欄位（預載預算上限為上下文視窗之 2% 或 8,000 字元，單一 `description` 上限 1,024 字元）。
  2. **既有技能觸發邊界重疊（Over/Under-triggering）**：在 `ys_codebase/source/agents-workflow/assets/skills/` 中，既有 11 個活躍技能（已排除棄用之 `session-analysis`）雖然內文精煉（27~135 行），但 `description` 普遍缺少**顯式觸發指令（如 `/auto`、`/continue`）**與**負向排他邊界（Negative Boundaries，如 `請勿用於...`）**，容易在「新建計畫（`new-plan`）vs. 接續計畫（`continue`）vs. 自動連續推進（`auto`）」以及「知識庫文檔（`documentation`）vs. 開發計畫產物（`development-sop`）」之間發生誤觸發。
  3. **缺乏標準化技能審查資產**：團隊在擴充與維護通用技能時，缺乏一套結構化的五維度靜態審查與重構技能（`skill-optimizer`）。
  4. **外部優化包合入前的雙重校正需求**：外部 SKILL 優化端提交之 `ys-codebase-agents-workflow-optimized.zip` 雖提供了高品質的 `description` 負向邊界、步驟檢核表、Gotchas 與 `skill-optimizer` 資產，但存在兩項必須在合入時修正的偏差：
     - **編譯器語意標籤契約**：`ys-codebase` 的 `ArtifactCompiler`（參見 `[DN-AW-03]` 與 `FT-14`）要求所有 `__@{...}__`、`__#{...}__`、`__${...}__` 標籤必須以單反引號包覆（`EXACT_REGEX` 會在展開時一併剝除反引號）；外部優化包誤將反引號移除並刪除 `contributes/agents-workflow.json` 的 `insert` / `release_target` 區塊與近期 `sub_02` 確立之規則（如 `handoff.md` 閱後即焚、Umbrella 狀態連動、`P07` 三步管線順序）。
     - **通用技能去特化（Zero Specialization Pollution）**：`agents-workflow` 基底提供的通用技能（包含新增之 `skill-optimizer` 及其 3 份 `references/`）必須為純淨、跨專案通用的工作流工具，不得混入針對 `ys-codebase` 內部編譯器標籤語法的特化教學（僅明確特化項目如 `yscb-cli-guild` 例外）。

- **調研目標**：
  1. 彙整各大廠（Anthropic、OpenAI、Agent Skills 標準、Snyk 資安實驗室）與最新多語系實證研究對 `SKILL.md` 設計與優化的核心指標。
  2. 在**100% 保留 `ys-codebase` 單反引號語意標籤契約、`contributes/agents-workflow.json` 完整結構與 `sub_02` 狀態規則**的前提下，合入 11 個活躍技能與 10 份 `references/*.md` 的描述與結構增強。
  3. 將通用型技能審查優化器 **`skill-optimizer`** 去特化洗鍊後封裝為 `agents-workflow` 的第一層標準資產（含 `SKILL.md`、3 份 `references/` 量表與 `contributes/agents-workflow.json` 註冊）。

## 2. 候選方案分析與對比 (Candidate Evaluation)

### 2.1 技能審查與優化器（`skill-optimizer`）運作模式對比

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：純靜態單步直接改寫** | 讀取 `SKILL.md` 後不經討論直接輸出改寫後檔案，不產出測試集 | 單輪對話即可完成、Token 消耗最低 | 容易在未經開發者確認下誤刪專案特殊約束；無量化基準可驗證觸發率是否改善 | ⭐⭐⭐ |
| **方案 B：純自動化子代理跑測迴圈 (Heavy Eval-Only)** | 每次修改強制啟動多個 Subagents 跑 60 次以上實際觸發測試與盲測 | 量化數據最完整，可自動迭代收斂 | 高度依賴特定 CLI 環境，耗時長且消耗數十萬 Tokens，不適合快速跨環境維護 | ⭐⭐⭐ |
| **方案 C：分級報告討論卡點 ＋ 雙模式分流收尾（推薦採納）** | 先執行五維度靜態審查並輸出 `Critical / Warning / Suggestion` 分級報告與開發者對齊（Gate），重構後依啟動前選定的 **Mode A（純靜態交付）** 或 **Mode B（附加 A/B 測試集與基準比對）** 收尾 | 兼顧「零臆測討論卡點」與「量化可驗證性」，且契合 `agents-workflow` 的 Checkpoint 守門哲學 | 需維護 `audit-rubric.md`、`refactoring-patterns.md` 與 `ab-eval-guide.md` 三份漸進式揭露參考檔 | ⭐⭐⭐⭐⭐ |

### 2.2 `SKILL.md` 撰寫語言策略對比（依據 2026 多語系 Token 與推理實證）

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：全英文撰寫** | Frontmatter 與內文全數使用英文 | 在 `o200k_base` / `cl100k_base` 下最省 Token（1.0x 基準） | 每個英文單字約佔 5.4 字元，`description` 容易塞滿 1,024 字元上限；與繁中開發團隊日常指令及模板語境割裂 | ⭐⭐⭐ |
| **方案 2：純中文散文撰寫（含技術名詞中譯）** | 將所有概念、API 與狀態名全數翻譯為中文長句 | 團隊閱讀直覺 | 長篇中文散文在歐美分詞器下多消耗 **1.34x~1.55x** Tokens，且硬譯技術識別符易造成模型對齊偏差 | ⭐⭐ |
| **方案 3：繁中結構化條列 ＋ 英文技術識別符與雙語觸發詞（推薦採納）** | 以精煉繁體中文條列/表格撰寫規則，保留英文技術識別符（`Confirmed`、`SSOT`、`DAG`），並在 `description` 並陳中英觸發詞 | 漢字高資訊密度使 `description` 字元數僅需英文的 **37%~41%**（遠離 1,024 字元截斷線）；短指令與表格在 `o200k_base` 下僅為 **1.06x** Token，且中英雙語提問皆能精準觸發 | 撰寫時需嚴格剔除中文口語贅字 | ⭐⭐⭐⭐⭐ |

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 大廠與開放標準五大審查維度（五維度體檢模型）

本調研整合 Anthropic 技能最佳實踐、Agent Skills 觸發優化指南、OpenAI Codex Skills 規範與 Snyk 資安稽核報告，將審查標準收斂為五大維度並內建於 `skill-optimizer/references/audit-rubric.md`：

1. **Metadata 與觸發精準度**：強制第三人稱能力陳述 ＋ 祈使觸發句型（`"當...時觸發"`）、關鍵字前置（Front-loading 防範 2% 上下文預算截斷）、顯性與隱性意圖覆蓋、相鄰技能負向排他邊界（`"請勿用於..."`），並防範未加雙引號的 YAML 保留字元引發解析崩潰。
2. **上下文經濟與漸進式揭露（Progressive Disclosure）**：`SKILL.md` 主體嚴控於 **500 行 / 5,000 tokens** 內；剔除基礎模型已知常識；附屬 `references/` 維持**嚴格單層連結深度（1-level deep）**且標明按需載入條件；超過 100 行的參考檔頂部強制配置 `## 目錄 (Contents)`。
3. **控制自由度校準與平台契約保護**：依步驟脆弱度校準高／中／低自由度；以「單一預設工具＋降級備援（Fallback）」取代多工具選單；以因果解釋（Explain the Why）取代盲目大寫禁令；100% 保護技能內既有的模板變量與超連結契約。
4. **工作流、腳本與驗證閉環**：多步驟工作流植入可複製勾選之進度檢核表（`- [ ] 步驟 1...`）、`Plan -> Validate -> Execute` 驗證閉環、極簡狀態卡（5~10 行）強制 End Turn 紀律，以及主檔尾部的 `## 常見踩坑指南 (Gotchas)`。
5. **資安與供應鏈防護**：排查提示詞注入、混淆外洩指令（`base64`、`curl | bash`）、硬編碼機密、未授權記憶檔修改，並落實危險命令的明確使用者授權守門（Default-Deny）。

### 3.2 選擇性融合與去特化落地明細

1. **新增純淨通用資產 `skill-optimizer`**：
   - 建立 `assets/skills/skill-optimizer/SKILL.md` 及 `references/{audit-rubric.md, refactoring-patterns.md, ab-eval-guide.md}`，移除所有針對特定專案編譯器語法的特化說明，保持 100% 通用性。
   - 於 `contributes/agents-workflow.json` 註冊 `skill-optimizer` 匯出項與 `SKILL_OPTIMIZER_STANDARDS` 擴充錨點（完整保留既有 `insert`、`release_target` 與全部 15 個動態錨點）。
2. **既有 11 個活躍技能與 10 份 References 強化**：
   - 全數升級 `description`（補齊顯式觸發詞與 `"請勿用於..."` 負向排他邊界）。
   - 為各技能與 `phase_00`~`phase_07` 植入執行檢核表與 `## 常見踩坑指南 (Gotchas)`，並為超過 100 行的 `plan_modes.md` 與 `author_guide_and_checklist.md` 補齊頂部 `## 目錄 (Contents)`。
   - 100% 保留單反引號語意標籤契約與 `sub_02` 狀態規則（`handoff.md` 閱後即焚、Umbrella 主從狀態連動、`P07` 三步管線順序、預設標頭狀態與模型紀錄規則）。

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **調研結論**：採納「選擇性融合＋通用技能去特化（Zero Specialization Pollution）」策略，於 `sub_04_agents_workflow_refinement` 之 `[REV-02]` 完成合入，並透過 `agents-workflow` 單元測試套件驗證編譯零警告與規則完整性。

