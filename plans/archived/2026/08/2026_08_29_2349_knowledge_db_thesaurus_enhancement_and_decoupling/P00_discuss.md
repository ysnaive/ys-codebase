# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_thesaurus_enhancement_and_decoupling  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 計畫類型：Feature / Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 希望提升搜尋廣度、但不稀釋精度。
  2. 方案 A+B+C 之綜合（同義詞權重衰減 + 分層關聯詞 + 單向別名）。
  3. 採分類型主計畫 (Umbrella Plan)：
     - `sub_01`：三階加權同義詞/別名/關聯詞檢索擴展與計分演算法重構。
     - `sub_02`：詞彙池解耦，刪除所有原始碼內建詞表，統一由 contributes 提供，並建置較為完善的初始內建詞彙表。
- **核心目標**：
  - 升級 `ThesaurusEngine` 與 `BM25Engine`，支援權重衰減（原始 1.0、同義詞/別名 0.6、關聯詞 0.25）與單向別名映射 (`A => B`)，兼顧廣度 (Recall) 與精度 (Precision)。
  - 解耦 `thesaurus.py` 內部的 `BUILTIN_THESAURUS`，轉為宣告式 contributes 載入機制，並建立涵蓋跨領域的高品質詞彙庫。
- **邊界排除 (Explicitly Excluded)**：
  - 本主計畫不更動微核心 `core` 模組的底層通訊協議或 VFS 基礎架構。
  - 本主計畫不引入龐大第三方外部 NLP/Embedding 模型，保持純 Python 標準庫自包含。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 三階加權語意擴展架構 (Three-Tier Weighted Expansion)**：
  - Tier 1（原始查詢詞）：權重 `1.0`，享完全計分與 Exact Match 2.0x Boost。
  - Tier 2（嚴格同義詞 Synonyms & 單向別名 Directed Aliases）：權重 `0.6`，支援雙向等價與單向特化展開。
  - Tier 3（領域關聯詞 Related Terms）：權重 `0.25`，作為底層微弱加分或寬鬆召回，100% 杜絕首屏噪音。
- **[P00:DR-02] 詞彙池解耦與 Contributes 體系統整 (Decoupled Contributed Thesaurus)**：
  - 徹底移除 `thesaurus.py` 內建之硬編碼靜態詞表。
  - 由 `SpaceManager` 透過 `contributes/knowledge-db.json`（或各模組 contributes）統一動態注入 `thesaurus`（雙向）、`aliases`（單向）與 `related`（關聯）。
- **[P00:DR-03] 分類型主計畫 (Umbrella Level 2) 雙子計畫分工**：
  - `sub_01`：專注於核心演算法、資料模型與加權檢索引擎實作（Full Track）。
  - `sub_02`：專注於詞表源碼解耦、contributes 格式拓展與高品質初始詞表建置（Full Track）。

---

## 3. 開放議題與確認紀錄

- [x] 確認採用分類型主計畫 (Umbrella) 模式推進。
- [x] 確認 sub_01 與 sub_02 職責邊界與推進順序（先 sub_01 演算法後 sub_02 詞庫解耦）。
