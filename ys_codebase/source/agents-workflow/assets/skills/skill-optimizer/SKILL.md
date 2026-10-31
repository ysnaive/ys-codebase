---
name: skill-optimizer
description: 針對既有 Skill 執行五維度靜態診斷、漸進式揭露重構與 A/B 基準評測生成。僅於顯式輸入 /skill-optimizer 時觸發，嚴禁主動觸發。
---

# AI Agent 技能審查與優化工作流 (Skill Optimizer)

本工作流依據業界 Agent Skills 開放標準與資安最佳實踐，專門針對**既有 Skill（`SKILL.md` 與附屬資源目錄）**進行系統化五維度診斷、漸進式揭露（Progressive Disclosure）拆分與無損重構。

---

## 適用情境與觸發時機

- **適用情境**：
  - 審查並優化專案內既有之 `SKILL.md` 及其附屬 `references/`、`scripts/` 資源。
  - 診斷並修正既有 Skill 的「漏觸發（Under-triggering）」或「誤觸發（Over-triggering）」問題。
  - 精簡超過 500 行的肥大 `SKILL.md`，執行漸進式揭露拆分並補齊按需載入條件。
  - 為既有 Skill 補齊步驟檢核表、`Plan -> Validate -> Execute` 驗證閉環、`## 常見踩坑指南 (Gotchas)` 與資安防護。
- **觸發時機**：**100% 純手動觸發（B-Strict）**——僅於開發者顯式輸入 `/skill-optimizer` 時觸發，**嚴禁主動觸發**。
- **排除情境（負向邊界）**：
  - **從零建立專案特化 Skill 或階段錨點注入規則**：當開發者尚無現成 `SKILL.md` 草稿、希望從零新建專案專屬 Skill 或於 `config://agents-workflow/` 配置錨點注入時，請改用 [`/skill-creator`](`__#{module://agents-workflow/assets/skills/skill-creator/SKILL.md}__`)。
  - **從零建立全新業務功能或開發計畫**：當開發者僅要求開發一般業務程式碼功能時，請走標準 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 流程，切勿使用本技能。

---

## [!] 核心原則與熔斷機制

1. **功能等價與零業務語意流失（Functional Equivalence）**：重構僅能提升觸發精準度、結構清晰度與上下文效率，嚴禁刪減原有的守門條件、熔斷規則、追溯鏈 ID 或回應狀態卡欄位。
2. **動態佔位符與連結完整性保護（Placeholder & Link Integrity）**：若受審 Skill 含有專案模板變數、路徑佔位符、跨檔案相對連結或 HTML 託管邊界註解，重構時必須 **100% 原樣保留其語法結構**，嚴禁誤刪或破壞。
3. **強制討論卡點（Mandatory Discussion Gate）**：在產出重構版檔案前，必須先提交「分級審查報告（`Critical` / `Warning` / `Suggestion`）」並向開發者確認收尾模式（模式 A 或模式 B），獲確認後方可執行修改。

---

## 執行步驟

開始執行時，請依序追蹤以下四階段優化進度：

```markdown
/skill-optimizer 四階段進度檢核表：
- [ ] 階段一：檢視目標 Skill 檔案並確認收尾模式（模式 A：純靜態重構 vs. 模式 B：附加 A/B 評測套件）
- [ ] 階段二：依 audit-rubric.md 執行五維度靜態審查，輸出「分級審查報告」並 End Turn 等待討論
- [ ] 階段三：依開發者確認範圍與 refactoring-patterns.md，產出重構後之 SKILL.md 與 references/
- [ ] 階段四：依選定模式執行收尾（模式 A 最終合規檢核 / 模式 B 依 ab-eval-guide.md 產出 evals/）
```

### 階段一：啟動前確認收尾模式 (Pre-Flight Mode Selection)

1. 讀取開發者指定的目標 Skill 目錄（包含 `SKILL.md`、`references/`、`scripts/`、`assets/`）。
2. 若開發者尚未指定收尾模式，於提出審查報告時一併詢問希望採用哪一種收尾操作：
   - **模式 A（純靜態重構交付）**：完成分級報告討論後，直接產出重構後的 `SKILL.md`、優化後的 `references/` 與修改前後對照摘要（Diff Changelog）。
   - **模式 B（靜態重構 ＋ A/B 基準測試集）**：除交付重構後檔案外，額外依據 [`references/ab-eval-guide.md`](./references/ab-eval-guide.md) 產出觸發率測試集（`trigger_evals.json`）與功能型 A/B 測試集（`evals.json` 與 `benchmark.json`）。

### 階段二：五維度靜態審查與分級報告 (Static Audit & Tiered Report)

**[!] 強制前置閱讀**：執行審查前，必須先讀取通用技能設計標準 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) 與 [`references/audit-rubric.md`](./references/audit-rubric.md)，針對以下五大維度逐一掃描：

1. **Metadata 與觸發精準度（對齊 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §1）**：檢查 YAML 語法（防範未加引號之特殊字元如 `[!]` 造成崩潰）、`name` 規格，以及 `description` 是否符合**高密度關鍵詞前置**、**自包含具體可觀測（輸入標的＋處理動作＋輸出交付物，禁依賴外部未知脈絡）**與**雙軌結構化邊界（A1 + B2）**：
   - **軌跡 A — 被動／環境攔截型技能（Ambient / Intent-Driven Skills — A1 正向邊界契約）**：採用**兩段式正向邊界（`{核心用途、處理對象與交付物}。觸發情境：{具體動詞、目標檔案路徑特徵與前置攔截時機}。`）**；預設不寫 `排除情境：`（根除粉紅大象效應與網狀耦合），唯獨同領域極易混淆時選配補充無點名負向邊界，**嚴禁在 `description` 點名其他技能名稱 `(改用 xxx)`**。
   - **軌跡 B — 主動指令型技能（Command-Driven / Slash Skills — B2 分級命令鎖定）**：
     - **B-Strict（重型／破壞性／長流程指令）**：採用純斜線鎖定 **`{1 句話核心目的與交付物}。僅於顯式輸入 /{cmd} 時觸發，嚴禁主動觸發。`**（關閉自然語言後門）。
     - **B-Assist（會話控制／教學輔助指令）**：採用 **`{1 句話核心目的與交付物}。僅於顯式輸入 /{cmd} 或明確要求{具體委託動作}時觸發。`**（嚴禁含 `/Cmd` 大小寫變體）。
2. **四元素目錄拓撲與漸進式揭露（對齊 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §2）**：檢查 `SKILL.md` 是否控制在 500 行／5,000 tokens 內、剔除基礎模型已知常識、確認 `references/` 連結維持單層深度（1-level deep）且具備明確按需載入條件、長參考檔（>100 行）是否具備目錄（TOC），以及機械式結構校驗是否已下沉至決定性 CLI 或 `scripts/`。
3. **控制自由度校準與跨平台解耦（對齊 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §2.2）**：檢查指令具體度是否匹配任務脆弱度、將多工具選單改為「單一預設＋降級備援」、解除特定平台硬編碼工具名耦合、補上規則背後的技術原因（Explain the why），並保護既有路徑佔位符與超連結語法。
4. **條件式工作流護欄與雙模狀態卡節流（對齊 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §3）**：檢查 3 步以上具相依性流程是否具備可勾選檢核表、高風險步驟是否具備條件式 `Plan -> Validate -> Execute` 確認守門、依 `Artifact-in-File` vs. `Artifact-in-Chat` 校準輸出節流，以及末尾是否配置 `## 常見踩坑指南 (Gotchas)`。
5. **三層縱深安全與跨技能正交（對齊 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §4）**：排查提示詞注入、混淆指令、硬編碼機密、未驗證遠端依賴、宿主工具權限收緊與跨技能職責重複抄寫。

完成掃描後，輸出以下**分級審查報告卡**並**立即 End Turn 等待開發者確認**：

```markdown
## 🔍 Skill 分級審查報告：[skill-name]

### 總體診斷摘要
- **目前行數／預估 Token 數**：[X 行 / 約 Y tokens]
- **健康度評級**：[通過 / 建議重構 / 發現嚴重風險]
- **核心瓶頸摘要**：[1~2 句話總結最關鍵的觸發、結構或資安問題]

### 1. 嚴重問題 Critical（必須修正 - 語法錯誤、觸發失效、連結損毀或資安風險）
- **[所屬維度] 問題標題**（位置：`第 X 行` 或 `章節名稱`）：
  - **問題診斷**：[具體說明違規原因與潛在失效後果]
  - **優化建議**：[具體可執行的修改方案]

### 2. 警告事項 Warning（建議修正 - 上下文肥大、跨平台耦合、邊界重疊或缺乏驗證閉環）
- **[所屬維度] 問題標題**（位置：`第 X 行` 或 `章節名稱`）：
  - **問題診斷**：[說明為何這會消耗多餘 Token 或導致 Agent 走偏]
  - **優化建議**：[具體可執行的修改方案]

### 3. 優化建議 Suggestion（進階打磨 - 自由度校準、檢核表或踩坑指南補強）
- **[所屬維度] 問題標題**（位置：`第 X 行` 或 `章節名稱`）：
  - **問題診斷**：[可提升執行穩定度或可維護性的機會點]
  - **優化建議**：[具體可執行的修改方案]

- **待確認事項**：請確認上述修改項目是否採納，並選擇收尾模式為 **[模式 A：純靜態重構]** 或 **[模式 B：附加 A/B 基準測試集]**？
```

### 階段三：執行無損重構與漸進式揭露拆分 (Skill Refactoring)

待開發者確認修改範圍後，讀取 [`references/refactoring-patterns.md`](./references/refactoring-patterns.md)（若受審技能為 YSCB 工作流託管資產，**必須一併載入 [`YscbSkillDesignToolStandards.md`](`__#{module://agents-workflow/assets/standards/YscbSkillDesignToolStandards.md}__`)**）執行重構：

1. **重寫高鑑別度 Frontmatter**：遵循「高密度關鍵詞前置、自包含具體可觀測（輸入→動作→交付物）」與雙軌結構化邊界規範（軌跡 A 環境攔截型採 **A1 正向邊界契約**並拔除跨技能點名；軌跡 B 主動指令型依風險分級採 **B-Strict 純斜線鎖定**或 **B-Assist 明確委託契約**）重寫 `description`。
2. **重構內文與 `references/`**：剔除冗長背景常識、依條件配置步驟檢核表與雙模狀態卡、收斂 `## 常見踩坑指南 (Gotchas)`，並同步優化底下的 `references/*.md` 檔案。
3. **驗證功能、連結等價與 YSCB 三步編譯守門**：逐一核對原始檔案中的所有動態佔位符、跨檔連結、追溯 ID 與狀態卡範本均 100% 完整保留；若屬 YSCB 託管技能，必須通過 `contributes check -> compile -> release` 零警告守門。

### 階段四：依選定模式執行收尾操作 (Closing Operations)

- **分支 A（模式 A - 純靜態重構交付）**：
  - 執行下方「最終品質檢核清單」，向開發者交付重構後檔案與變更摘要（Changelog）。
- **分支 B（模式 B - 產出 A/B 基準測試與觸發評測套件）**：
  - 讀取 [`references/ab-eval-guide.md`](./references/ab-eval-guide.md)，產出 `evals/trigger_evals.json`（含 60/40 訓練驗證切分與近似負向題 Near-misses）、`evals/evals.json`（含客觀可驗證斷言）與 `benchmark.json` 對照結果。

---

## 最終品質檢核清單

- [ ] `name` 僅含小寫英數與連字號（1-64 字元），`description` 低於 1024 字元、無 `< >` 標籤且無未加引號之 YAML 保留字元開頭。
- [ ] `SKILL.md` 主體低於 500 行，所有 `references/` 皆為單層直接連結（1-level deep），超過 100 行的參考檔頂部附有目錄（TOC）。
- [ ] 所有原始模板變數、路徑佔位符、超連結與回應狀態卡格式 100% 無損保留。

`__@{SKILL_OPTIMIZER_STANDARDS}__`

---

## 常見踩坑指南 (Gotchas)

- **切勿對測試集硬塞字眼導致過擬合（Overfitting）**：優化 `description` 時應提煉通用任務意圖類別，禁止直接複製貼上單一失敗測試題的字面詞彙。
- **切勿將 `## 常見踩坑指南 (Gotchas)` 拆分至外部檔案**：Agent 在踩坑前不會預知要去讀取外部檔案，核心防坑規則必須留在 `SKILL.md` 主檔內。

