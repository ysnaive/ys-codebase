# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_benchmark_evaluation  
> 建立日期：2026-09-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 計畫類型：Research  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「建立調研計畫，將兩分 benchmark 納入並歸檔」
- **核心目標**：
  1. 針對專案既有兩份 knowledge-db Benchmark（`benchmark/` 與 `benchmark2/`）進行獨立客觀審計與效能評估，論證 knowledge-db 工具在工程導航、依賴拓撲分析與 Token 節省上的真實效益。
  2. 統整跨 Agent 實測數據（4 位 Agent：f1cbe57e, 90a6547f, cc7c1fb5, 11c70f4b）、消除統計雜訊、校驗 Ground Truth 偏差（如 Q1.1 簽名定義），產出正式技術調研報告 `R01_knowledge_db_benchmark_research.md`。
  3. 將兩份 Benchmark 資產整合納入計畫資料包中，依專案 SOP 完成調研審查與歷史封存歸檔。
- **邊界排除 (Explicitly Excluded)**：
  - 不涉及修改既有 knowledge-db 核心源碼或 Public API。
  - 不修改任何生產環境運行組態。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 判定採用「調研計畫 (Research Plan - 調研 Track)」模式推進，產出檔案矩陣包含 `P00_discuss.md`、`R01_knowledge_db_benchmark_research.md` 及 `changelog.md`。
- **[P00:DR-02]** 釐清 System Prompt 先驗知識設計原則：兩組 Agent 皆不給予路徑，`--space` 空間抽象屬於工具核心架構能力而非 Prompt 偏見；審計核心聚焦真實工具調用數、Token 消耗比率與語意檢索精確度。
- **[P00:DR-03]** 記錄 Benchmark 1 Q1.1 之 Ground Truth 定義偏差（代碼真實簽名為 `pip_deps: List[str]`），納入 R01 調研報告作為校準依據。

---

## 3. 開放議題與確認紀錄

- [x] 審計評估兩份 Benchmark 報告與 4 位 Agent 完整對話 Trajectory 日誌。
- [x] 建立調研計畫目錄與 P00 需求討論說明書。
- [x] 撰寫並產出 R01 調研報告 (`R01_knowledge_db_benchmark_research.md`)。
- [x] 納入 Benchmark 原始測試資產並執行安全歸檔。
