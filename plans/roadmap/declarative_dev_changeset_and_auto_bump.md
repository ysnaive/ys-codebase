# 技術路線圖：宣告式開發期變更集與發布期自動版號折疊治理機制 (Roadmap)

> 主題：宣告式開發期變更集與發布期自動版號折疊治理機制  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：dev / agents-workflow 模組版本生命週期治理、開發期變更登記與發布自動化  
> 前置解鎖條件：完成開發期變更載體形式（單檔組態清單 vs 獨立碎片檔）與多變更摘要聚合策略之細節討論  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **上下文壓縮與多輪迭代下之版號失控遞增**：在現行機制中，開發期與發布期共用模組 `manifest.json` 之版本欄位，且工作流提示詞中包含版號遞增指令說明。當 AI 代理歷經長對話上下文壓縮（Context Compaction）或跨多個子計畫連續開發時，極易因慣性在未獲發布授權下自行反覆遞增版號（人類開發者亦可能誤操作），導致單次發布週期內出現多次無效跳號。
  - **多人與跨環境並行開發之版本欄位衝突**：當多名開發者或本地與雲端代理於不同分支同時修改同一模組時，若各自直接修改 `manifest.json` 的版本號與單一 `release` 欄位，極易在合併或雙向同步時引發衝突與變更摘要相互覆寫。
  - **延遲發布時之變更脈絡遺失**：當模組累積多個階段或子計畫的 `@build` 修改後才統一執行正式發布時，發布當下難以完整回溯並精確匯總所有中間修改的語意類型、緊急度與摘要。
- **長期願景與目標定位**：
  - 將「**開發期記錄變更意圖（What Changed）**」與「**發布期計算版號與更新索引（Version Bump & Release Ledger Update）**」徹底物理分離。日常開發完全移除手動或指令式遞增版號的行為，改由開發者或代理以增量方式填入開發期變更組態；正式發布時由腳本自動讀取、確定性折疊計算最終版號、聚合發布元數據並一次性寫入正式組態與版本帳本。
- **範疇與邊界約束**：
  - 涵蓋 `dev` 模組開發期變更登記機制、發布預檢（`release-check`）與打包發布（`release`）之自動折疊演算法，以及 `agents-workflow` 相關開發技能（如 `yscb-module-dev`、`/bump-revision`）之提示詞去版號化重構。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **開發期版號凍結不變量 (Development-Time Version Immutability)**：在日常功能開發、測試與 `@build` 熱部署期間，`manifest.json` 中的正式版號維持凍結；AI 代理與開發者在開發期僅登記「變更內容與建議升版幅度」，不直接操作版號數值。
  - **多源增量寫入無衝突不變量 (Additive Non-Conflicting Accumulation)**：同一模組在兩次正式發布之間，允許由不同開發者、不同子計畫或跨環境代理多次增量追加變更紀錄，各筆紀錄彼此獨立不互蓋。
  - **發布期確定性單次折疊不變量 (Deterministic Release-Time Folding)**：無論開發期某模組累積了多少筆變更紀錄，執行正式發布時均由腳本自動收斂為**單次版本晉升**（取所有待發布變更中最高之語意升版幅度：`major` > `minor` > `patch` > `revision`），並在完成 `manifest.json` 與 `index.json` 更新後自動清空已消費之開發期變更集。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **開發期變更集載體 (Pending Changeset Carrier)**：提供專屬之開發期變更記錄結構（具體採模組內單檔開發期清單或獨立變更碎片檔待立項時拍板），記錄每次修改之升版幅度（`bump`）、變更類型（`type`）、緊急度（`urgency`）、變更摘要（`summary`）及選填之相依契約調整。打包正式 `.zip` 時由忽略規則自動剝除開發期暫存組態。
  - **發布期自動折疊與拓撲對齊引擎 (Auto-Fold & Topological Release Engine)**：正式發布腳本掃描所有含待消費變更集（或處於 `@build` 狀態）之模組，依 DAG 相依拓撲順序自動計算目標版號、取最高緊急度（`critical` > `recommended` > `optional`）、合併變更摘要，自動寫入 `manifest.json` 與 `release/<mod>/index.json` 並執行打包。
  - **工作流技能去版號化 (Prompt De-Versioning)**：從日常開發技能手冊移除直接遞增版號之指令指引，統一改為引導登記開發期變更意圖，從根源杜絕上下文壓縮後之自主升版幻覺。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：立項前於 `P00` 討論拍板以下細節即可啟動：
  1. **載體物理形式**：採用單一開發期組態檔（如 `changes.dev.json` / `manifest.json` 內嵌開發區塊）或目錄碎片檔（如 `.changes/*.json` 以最大化跨分支零衝突）。
  2. **多筆摘要合成格式**：多筆變更紀錄折疊寫入 `index.json["releases"][<ver>]["summary"]` 時之文字拼接或去重規範。
  3. **未登記變更之 `@build` 兜底策略**：當模組處於 `@build` 但未顯式填入變更紀錄時，發布腳本之預設升版行為（如預設 `revision` 升版或提示補填）。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（變更集規格與 CLI 登記介面）**：敲定開發期變更組態 Schema 與 `dev` 增量寫入/檢視介面，並整合 `dev check` 靜態校驗。
  2. **Stage 2（發布腳本自動折疊與帳本同步）**：升級 `dev release` 與 `/bump-revision` 管線，實作自動讀取變更集、計算單次升版、更新 `manifest.json` 與 `index.json` 並清理已發布變更集。
  3. **Stage 3（工作流技能與規範同步）**：更新 `yscb-module-dev`、`bump-revision` 等技能與文檔，全面切換至宣告式變更集工作流。

