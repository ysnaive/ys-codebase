<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時必須遵守的通用核心原則與條件技能分流導航。

---

## 1. 核心原則：零臆測 (Zero Speculation Axiom)

1. **零臆測 (Zero Speculation)**：
   - 不確定細節必須向開發者釐清；嚴禁自行假設需求、猜測 API 或臆測解法。
   - **寬泛指令防呆**：開發者下達抽象或寬泛目標時（例如「優化/打磨」），**嚴禁主動發散腦補具體需求清單**；必須優先反問確認具體目標與期望範圍。
   - **分析授權例外**：唯有開發者明確指示「幫我分析/評估」時，方可基於代碼現況展開客觀架構分析與候選方案對比。

---

## 2. 條件式技能分流導航矩陣 (Conditional Skill Trigger Routing)

除「零臆測原則」為全域強制遵循外，所有具體開發場景與工程規範均依條件分流至專屬 Skill。**執行對應任務前必須強制觸發並遵循該技能手冊**：

| 任務情境與行為目標 (Trigger Condition) | 強制觸發之技能 (Mandatory Skill) |
| :--- | :--- |
| **開立計畫 / 階段推進 / 代碼實作 / 任務交付** | `development-sop` |
| **執行任何 CLI 命令列指令** | `yscb-cli-guild` |
| **編寫代碼註解 / 撰寫或維護專案文檔** | `documentation` |
| **實作遇阻 / 連續修復失敗 / 範疇越界** | `/Discuss` (工作流) |
| **生態系模組開發 / 多模組熱調試 (Dogfooding)** | `yscb-module-dev` |
| **代碼檢索 / 閱讀探索 / 調用圖譜 / 影響面評估** | `knowledge-db-search` |
<!-- YSCB_AGENTS_END -->
