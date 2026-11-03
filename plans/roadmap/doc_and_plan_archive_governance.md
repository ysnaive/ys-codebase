# 技術路線圖：文檔與歷史計畫治理體系演進 (Roadmap)

> 主題：文檔與歷史計畫治理體系演進（尚未完整調研）  
> 歸檔日期：2026-11-03  
> 狀態：Backlog  
> 目標範疇：agents-workflow / knowledge-db / docs / plans 知識與決策歸檔體系  
> 前置解鎖條件：完成文檔體系、歸檔計畫索引與 CHANGELOG 分層策略之專項深度調研  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：*(註：本主題源自外部審計議題，目前尚未執行完整架構調研)* 隨著專案長期演進，封存計畫庫（`plans/archived/`）與變更歷史（`CHANGELOG.md`）規模持續增長，現有體系在「跨時期歷史架構決策快速反查」、「預設搜尋範圍對歸檔產物的權重/隔離控制」、「發布日誌與細部實作紀錄的資訊分層」以及「文檔量化宣稱與基準測試的雙向綁定」四個維度尚待系統性調研與規劃。
- **長期願景與目標定位**：在維持「`plans/` 為演進過程紀錄、`docs/` 為系統唯一真理來源（SSOT）、`plans/archived/` 為歷史決策反查庫」之核心分工下，建立低維護成本、高檢索信噪比且可自動驗證的長期知識治理機制。
- **範疇與邊界約束**：涵蓋 `agents-workflow` 結案生命週期契約、`knowledge-db` 與外部搜尋工具之空間隔離策略、`CHANGELOG.md` 結構規範及 `docs/` 宣稱驗證機制；啟動實作前必須先執行 `/research` 完成完整調研與方案權衡。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **三層真理分工不變量**：`docs/` 反映當前系統狀態與架構決策（`DESIGN_NOTES.md`），`CHANGELOG.md` 聚焦可觀測之變更摘要，`plans/archived/` 保留完整推演脈絡供按需追溯。
  - **預設檢索高信噪比不變量**：日常代碼與現行規格檢索不得被歷史歸檔計畫稀釋排序權重，同時保留顯式指定歷史空間時的完整可查性。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **待調研方向 1（歷史決策索引）**：評估於計畫結案封存時自動提取結構化決策摘要索引之可行性，以及與既有 `docs/<module>/DESIGN_NOTES.md` 的職責邊界。
  - **待調研方向 2（搜尋隔離策略）**：評估原生檢索工具忽略規則（如 `.ignore` / `.rgignore`）與 `file-space` / `knowledge-db` 空間權重配置之協同機制。
  - **待調研方向 3（變更日誌分層與量化宣稱驗證）**：評估 `CHANGELOG.md` 滾動歸檔或版本聚合格式，以及 `docs/` 效能/規模宣稱與自動化測試斷言之對齊規範。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：需先針對上述三個待調研方向啟動專項 `/research` 調研，釐清與現有 `DESIGN_NOTES.md`、`plan archive` 及 `plan verify` 契約的相容性後，方得晉升為 `Ready`。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（專項調研）**：盤點現有 `DESIGN_NOTES.md`、`CHANGELOG.md` 與 `plans/archived/` 的實際檢索摩擦點，確立不重複造輪子的最小治理閉環。
  2. **Stage 2（工具鏈與規範落地）**：依據調研結論擴充 `agents-workflow` 封存/檢核工具鏈與知識庫空間規範。

