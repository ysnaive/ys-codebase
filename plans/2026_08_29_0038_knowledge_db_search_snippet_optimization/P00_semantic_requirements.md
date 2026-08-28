# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「最近剛開發出 knowlege db 的功能，但不知道具體有效性、提升如何，有沒有辦法提出一個較公正的評測方案。我想知道對 agents 的提升才是關鍵。規劃該優化計畫，先將本次統整整理為 R01。」
- **核心目標**：
  1. 完成 Knowledge-DB 對 AI Agent 開發效益之實戰 A/B 評測，並將數據、根因與優化方案固化為 `R01` 技術調研報告。
  2. 針對評測中暴露之「雙重檢索 (Double-Look)」與「資訊密度不足」核心痛點，為 `knowledge-db search` 實作 `--snippet` / `--preview` 代碼片段與 Docstring 預覽能力，使 Agent 能在 1-Turn 內獲取完整資訊，杜絕無效二次檔案讀取。
  3. 標準化搜尋結果之路徑輸出，與工作區根目錄嚴格對齊，消除路徑重試開銷。
- **邊界排除 (Explicitly Excluded)**：
  - 本計畫不重構底層 BM25 評分公式或倒排索引二進位壓縮架構（該部分於先前 sub-plans 已驗證成熟）。
  - 不引入任何外部 heavy-weight 依賴（如 tree-sitter C-binding 或向量資料庫），持續恪守 100% Python 標準庫零相依原則。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 雙輪 Benchmark (R01/R02) 結論收斂**：
  - R01（具體關鍵字題）與 R02（日常概念語意題）兩輪實測證實：在面對自然語言語意需求時，Knowledge-DB 展現強大定向能力（0 次盲目 Grep，耗時差距由 2.04x 大幅收窄至 1.35x）。
  - 但兩輪評測皆 100% 暴露出「Double-Look」惡性循環（R02 執行 11 次 Search 後被迫再執行 19 次 ViewFile），核心突破口在於大幅提升 Search 輸出的資訊密度。
- **[P00:DR-02] 引入 `--snippet` / `-s` / `--preview` 程式碼預覽模式**：
  在 `knowledge-db search` 新增代碼預覽旗標。當啟用時，搜尋結果除標識符與行號外，自動提取目標符號之 Docstring 摘要以及上下文 3~5 行代碼片段，使 Agent 無需再次調用 `view_file` 即可掌握實作細節。
- **[P00:DR-03] 工作區路徑自動正規化**：
  搜尋結果展示之路徑自動根據當前 Workspace 根目錄解算為可直接跳轉與讀取之標準相對路徑，徹底消除跨空間路徑前綴漂移。
- **[P00:DR-04] Agents-Workflow 注入資產與 CLI 指引同步更新**：
  在實作 `--snippet` / `-s` 後，必須同步更新 `knowledge-db` 注入至 `agents-workflow` 的規範與資產（包含 `KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 以及 `contributes/core.json`），使 Agent 能第一時間掌握 `--snippet` 語法，從根本上引導 Agent 主動使用代碼預覽，消除「Double-Look」二次讀取行為。

---

## 3. 開放議題與確認紀錄

- [ ] 確認 `--snippet` 代碼預覽的預設截取行數（建議預設為前後 3~5 行或整個函式簽名區塊）。
- [ ] 確認預設輸出格式是否維持極簡模式，或在終端具備足夠寬度時自動適度擴展資訊。
