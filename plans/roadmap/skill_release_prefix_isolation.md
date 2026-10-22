# 技術路線圖：Release 技能輸出前綴與命名空間防撞機制 (Roadmap)

> 主題：Release 技能輸出前綴與命名空間防撞機制  
> 歸檔日期：2026-10-22  
> 狀態：Proposed  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- 隨著 `agents-workflow` 及生態系模組匯出的 `skill` 資產數量持續增加（如 `auto`, `continue`, `pause`, `discuss`, `research`, `roadmap`, `new-plan`, `documentation`, `context-init`, `development-sop` 等），發布至下游專案 `.agents/skills/` 或 `.claude/skills/` 時，因多數技能使用通用動詞/名詞，若下游專案開發者已自訂同名 Skill（例如專案自有的 `research` 或 `documentation`），在執行 `agents-workflow release` 時會發生目錄與檔案撞名覆蓋。

### 1.2 現況與影響範圍評估
- `template` 與 `standard` 資產目前已輸出至 `.agents/.yscb/templates` 與 `.agents/.yscb/standards` 隱藏子目錄，具備完整命名空間隔離。
- 但 `skill` 受限於各大 IDE（Antigravity / Claude Code / Codex）探索規範，必須位於 `.agents/skills/<skill_name>/SKILL.md` 一級子目錄下，無法透過多層子資料夾隔離，只能透過「資料夾與技能名稱前綴（Prefix）」達成命名空間防撞。

### 1.3 核心根因
1. **`config/agents-workflow/config.project.json` 缺乏前綴設定項**：目前僅有 `paths`、`release_targets`、`enable_agents_md`、`enable_project_changelog`，未提供 `skill_prefix`（如預設 `"yscb-"` 或自訂前綴）組態。
2. **`ReleasePublisher` 尚未實作 Frontmatter 與交叉引用動態改寫**：即使手動修改 `release_target` 的 `target_dir` 為 `.agents/skills/yscb-{export.name}`，`SKILL.md` 頂部 YAML frontmatter 的 `name: <skill_name>` 以及 `AGENTS.md` / 各技能間的交叉連結（如 `` `__#{skills/discuss/SKILL.md}__` `` 與觸發名稱）尚未與前綴連動改寫。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：源碼硬編碼統一改名** | 直接將所有內建 Skill 源碼目錄與 frontmatter 硬編碼改為 `yscb-*` | 實作最簡單，不需改動編譯器 | 下游無法自訂前綴；破壞既有斜線指令簡潔性（如 `/auto` 變成 `/yscb-auto`） | ⭐️⭐️⭐️ |
| **方案 2：發布期可配置 `skill_prefix` 與動態投影改寫** | 於 `config.project.json` 支援 `skill_prefix`（預設可為空或 `"yscb-"`），由 `ArtifactCompiler` 與 `ReleasePublisher` 在發布時動態改寫目標資料夾名稱、`SKILL.md` frontmatter `name:`、`AGENTS.md` 路由表與 `__#{skills/...}__` 連結 | 兼顧零撞名安全性與下游專案自訂彈性；源碼維持語意純淨 | 需同步處理 frontmatter `name` 欄位、Stage 2 URI 解析映射與 `AGENTS_SKILL_ROUTING` 表格名稱替換 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（源碼硬編碼） | 方案 2（發布期動態前綴投影） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高（現有 `build_deployment_map` 已具備映射基礎） |
| **後續維護難度 (Maintenance)** | 中（所有模組貢獻都必須手動遵守命名） | 低（由框架集中管控前綴正規化，避免雙重前綴如 `yscb-yscb-cli-guide`） |
| **可靠性 (Reliability)** | 高 | 高（搭配單測驗證 frontmatter 與連結一致性） |
| **落地難度 (Implementation)** | 低 | 中（涉及 `compiler.py`, `publisher.py`, `contributes` 與 `AGENTS.md` 路由表） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：擴充 config.project.json 與 _format.json 支援 skill_prefix 設定
# 步驟 2：於 ReleasePublisher.build_deployment_map 實作前綴正規化（若已含該前綴則不重複添加）
# 步驟 3：於發布物化階段同步改寫 SKILL.md 之 YAML frontmatter name 欄位與 AGENTS.md 技能路由名稱
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 現階段先維持既有 Skill 輸出結構，將本方案列為 `Proposed` 路線圖儲備，待後續專屬計畫一次性完成編譯器與發布器改造。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1**：定義 `skill_prefix` 組態規格與防雙重前綴正規化規則。
2. **Stage 2**：升級 `ArtifactCompiler` Stage 2 與 `ReleasePublisher` 支援動態 frontmatter `name` 及技能路由表同步改寫。
3. **Stage 3**：補齊舊版無前綴技能切換為有前綴技能時的 Manifest 自動遷移與遺留目錄清理測試。

