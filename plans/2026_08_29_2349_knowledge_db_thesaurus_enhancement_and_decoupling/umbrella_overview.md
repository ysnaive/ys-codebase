# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：knowledge_db_thesaurus_enhancement_and_decoupling  
> 建立日期：2026-08-29  
> 狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：升級 `knowledge-db` 語意同義詞與關聯詞擴展機制，達成「大幅提升檢索廣度 (Recall)、100% 不稀釋首屏精準度 (Precision) 與查詢防漂移 (Anti-Query-Drift)」，並將詞彙庫徹底與核心引擎源碼解耦，轉由宣告式 Contributes 體系管理與豐富化。
- **架構邊界**：
  - `knowledge-db` 模組：`schema.py`, `thesaurus.py`, `retrieval.py`, `space.py`, `contributes/knowledge-db.json`。
  - Donor 模組宣告與初始詞彙庫豐富化（涵蓋軟工通用、架構概念、常用程式語言與 SPICE 等領域詞表）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_three_tier_weighted_expansion` | Full Track | `Completed` | 實現方案 A+B+C：三階加權擴展管線 (原始詞 1.0 / 嚴格同義詞與單向別名 0.6 / 領域關聯詞 0.25) 與 BM25 衰減計分引擎重構。 |
| **sub_02** | `sub_02_thesaurus_pool_decoupling_and_enrichment` | Full Track | `Pending` | 詞彙池解耦：刪除源碼內硬編碼 `BUILTIN_THESAURUS`，改由 Contributes 宣告式載入，並建置高質量初始同義詞、別名與關聯詞庫。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成 sub_01 三階加權同義詞/別名/關聯詞檢索演算法與單元測試。
- [ ] **里程碑 2**：完成 sub_02 源碼硬編碼詞表徹底解耦與宣告式詞庫豐富化。
- [ ] **里程碑 3**：全生態系全量測試驗證 (100% Passed) 與知識庫文檔交付。
