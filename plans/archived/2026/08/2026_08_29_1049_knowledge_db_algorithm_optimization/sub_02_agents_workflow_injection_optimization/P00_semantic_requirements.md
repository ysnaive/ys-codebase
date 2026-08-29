# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：`sub_02_agents_workflow_injection_optimization` (agents workflow 注入內容優化)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  `@[d:\repos\ys_codebase\plans\2026_08_29_1049_knowledge_db_algorithm_optimization] 開啟子計畫 02: agents workflow 注入內容優化`
- **現有痛點與核心目標**：
  1. **消滅自覺性模糊依賴，建立剛性檢索決策樹 (Search Decision Tree)**：
     - 現行 `AGENTS.md` 僅有「優先檢索」提示，Agent 仍易隨意切換或盲目 grep。必須建立明確、可操作的決策樹，指引 Agent 在何種情況下使用 grep、何種情況下使用複合關鍵詞或語意敘述調用 `knowledge-db search`。
  2. **確立「定位 ➔ 定向閱讀」核心哲學**：
     - 強調並非完全禁止 grep，而是透過 `knowledge-db search -s` 快速定位關鍵符號、檔案與精確行號，結合 `--snippet` 即時預覽，再進行極小範圍的定向閱讀 (`view_file`) 或單一符號 grep，杜絕無條件的全專案大範圍暴力正則/廣蒐。
  3. **移除過時手動維護指引**：
     - `phase07_guild.md` 移除要求手動執行 `knowledge-db index` / `scan` 的過時敘述（因 `sub_01` 已達成 JIT 查詢時智能變更感知與背景熱自愈）。
  4. **調用參數最佳實踐指引**：
     - 全面推薦 `-s` (`--snippet`) 取得帶行號代碼切片，適時搭配 `--space` 進行空間過濾。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `knowledge-db` 底層搜尋演算法本體與 AST 解析器（維持 `sub_01` 之穩定產物）。
  - 不破壞 `agents-workflow` 既有 Token 注入機制與語意 URI 協議架構。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫範疇界定**：
  本子計畫為 `knowledge_db_algorithm_optimization` Umbrella 計畫之第二個子計畫，專注於優化 `knowledge-db` 對 `agents-workflow` 所注入之資產（`assets/KnowledgeAgentsStandards.md`、`assets/phase00_guild.md`、`assets/phase07_guild.md`、`assets/research_guild.md` 等）及 `contributes/agents-workflow.json`。
- **[P00:DR-02] 剛性檢索決策樹 (Search Decision Tree)**：
  確立代碼探索與檢索之標準決策路徑：
  ```mermaid
  graph TD
      Q1{"當前需求是否已包含明確、<br/>獨一無二的符號/簽章？<br/>(例如：<code>foo.doSomething</code>)"}
      Q1 -- 是 --> A1["調用原生精準工具 (grep_search)<br/><i>精準單一字串匹配</i>"]
      Q1 -- 否 --> Q2{"當前需求是否知道明確分類或模組功能概念？<br/>(例如：'實體智能尋路模組')"}
      Q2 -- 是 --> A2["調用複合關鍵詞檢索<br/><code>python yscb.py knowledge-db search '&lt;關鍵詞組合&gt;' -s</code><br/><i>(例如：'實體 A* 尋路 pathfinding entity')</i>"]
      Q2 -- 否 --> A3["調用語意化敘述檢索<br/><code>python yscb.py knowledge-db search '&lt;語意化需求&gt;' -s</code><br/><i>(例如：'修改角色尋路行為')</i>"]
  ```
- **[P00:DR-03] 定向閱讀與非暴力廣蒐哲學 (Targeted Reading Axiom)**：
  檢索工具職責為「以極低代價迅速收斂目標候選集與行位址」，由 `knowledge-db search -s` 輸出之行號與 Docstring 切片直接提供決策依據，僅在需要完整上下文時才對精確行號區間進行 `view_file`，嚴禁在未知精準簽章前發起全域暴力正則或盲目全文掃描。
- **[P00:DR-04] 過時手動索引指引移除**：
  `phase07_guild.md` 移除強制手動執行 `python yscb.py knowledge-db index` 敘述，改為說明知識庫已具備 JIT 熱自愈機制（亦可選擇手動全量校準）。
- **[P00:DR-05] 注入範疇採行方案 B（聚焦既有 4 大錨點）**：
  保持體系極簡清晰，不擴充新的注入 Token。專注於優化既有 4 大注入資產：
  1. `AGENTS_STANDARDS` ➔ `KnowledgeAgentsStandards.md`（完整注入檢索決策樹、定向閱讀哲學與 Docstring 符號防護規範）
  2. `PHASE00_AGENTS_GUILD` ➔ `phase00_guild.md`（Phase 0 定向檢索指引）
  3. `RESEARCH_AGENTS_GUILD` ➔ `research_guild.md`（Research 調研預檢指引）
  4. `PHASE07_AGENTS_GUILD` ➔ `phase07_guild.md`（移除過時手動 index 強制指引）

---

## 3. 開放議題與確認紀錄

- [x] **議題 1 (SOP 階段注入錨點擴充與策略)**：已由開發者確認採行 **方案 B（聚焦既有 4 大錨點，極簡清晰）**。

