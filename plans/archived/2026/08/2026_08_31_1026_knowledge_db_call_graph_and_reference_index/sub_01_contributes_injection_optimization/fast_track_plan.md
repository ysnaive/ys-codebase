# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_01_contributes_injection_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1026_knowledge_db_call_graph_and_reference_index  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：優化 `knowledge-db` 模組對生態系（`core` 與 `agents-workflow`）之 Contributes 與導引規範注入資產，補齊調用圖譜 CLI 權限規範、決策矩陣指引與效益評測，並額外擴充同義詞庫（Thesaurus）之前端 Web 技術棧（HTML/JS/TS/CSS）語義詞條。
- **影響範圍**：
  - `source/knowledge-db/contributes/core.json`
  - `source/knowledge-db/contributes/knowledge-db.json`
  - `source/knowledge-db/assets/KnowledgeAgentsStandards.md`
  - `source/knowledge-db/assets/research_guild.md`
  - `source/knowledge-db/assets/phase00_guild.md`
  - `source/knowledge-db/assets/retro_check.md`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 `source/knowledge-db/contributes/core.json` 登錄 `callers`、`callees` 與 `impact` 指令權限分級 (`safe`) 與 Pros/Cons 守門規範。
- [x] **TASK-02**：在 `source/knowledge-db/assets/KnowledgeAgentsStandards.md` 決策矩陣新增調用圖譜與影響面分析分流規則，明訂禁止文字盲搜排查調用鏈。
- [x] **TASK-03**：在 `source/knowledge-db/assets/research_guild.md`、`phase00_guild.md` 與 `retro_check.md` 注入調用圖譜指引與效益評測維度。
- [x] **TASK-04**：在 `source/knowledge-db/contributes/knowledge-db.json` 擴充調用圖譜術語及前端技術棧術語（HTML / DOM、JS / TS / JSX / TSX、CSS / Flexbox / Grid / 樣式排版與常見前端詞彙）。
- [x] **TASK-05**：執行編譯、沙盒測試與自部署閉環（`dev test knowledge-db`、`install knowledge-db@build --force`），驗證全域物化與合規性。
- **測試案例**：
  - `FT-01`：`dev check knowledge-db` 靜態合規性 100% 通過。
  - `FT-02`：`dev test knowledge-db` 單元與合約測試 100% 通過。
  - `FT-03`：`AgentsCliGuild.md` 與 `AGENTS.md` 自動同步產出 `callers`/`callees`/`impact` 守門與分流條款。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - `contributes/core.json` 成功登錄 `callers`、`callees`、`impact` 三大指令為 `safe` 權限等級。
  - `KnowledgeAgentsStandards.md` 與 `AGENTS.md` 成功更新目標導向決策矩陣，禁止 Grep 多檔盲搜取代調用圖譜。
  - `research_guild.md`、`phase00_guild.md` 與 `retro_check.md` 完成調用圖譜導引與評測欄位注入。
  - `contributes/knowledge-db.json` 成功擴充調用圖譜及 HTML/JS/TS/CSS 前端全棧詞條與別名關聯。
- **實機測試日誌**：
  - `dev check knowledge-db`：PASSED (100% 合規)。
  - `dev test knowledge-db`：PASSED (125/125 Passed, 1.13s)。
  - `install knowledge-db@build --force`：自動觸發 Hook 物化更新 `AGENTS.md` 與 `AgentsCliGuild.md`。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **文檔與日誌交付**：同步更新 `CHANGELOG.md` 追加發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_31_1026_knowledge_db_call_graph_and_reference_index/sub_01_contributes_injection_optimization` 驗證 100% Passed。
- **結案狀態**：`Completed`
