# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 計畫類型：Feature / Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 提升搜尋廣度、但不稀釋精度。
  2. 實現方案 A+B+C 之綜合（同義詞權重衰減 + 分層關聯詞 + 單向別名）。
- **核心目標**：
  - 升級 `ThesaurusEngine` 與 `BM25Engine`，支援三階加權展開管線（原始詞 1.0、同義詞/別名 0.6、關聯詞 0.25）與單向別名映射 (`A => B`)。
  - 重構 BM25 計分公式以整合 Token 衰減權重，確保高查全率且徹底消除 Query Drift。
- **邊界排除 (Explicitly Excluded)**：
  - 本子計畫專注於核心資料結構、展開狀態機與 BM25 檢索演算法，詞表解耦與豐富化留待 `sub_02` 處理。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 三階加權語意擴展架構 (Three-Tier Weighted Expansion)**：
  - Tier 1（原始查詢詞）：權重 `1.0`，享完全計分與 Exact Match 2.0x Boost。
  - Tier 2（嚴格同義詞 Synonyms & 單向別名 Directed Aliases）：權重 `0.6`，支援雙向等價與單向特化展開。
  - Tier 3（領域關聯詞 Related Terms）：權重 `0.25`，作為微弱加分或寬鬆召回，100% 杜絕首屏噪音。
- **[P00:DR-02] 最高權重優先保留原則 (Max-Weight Retention)**：
  - 同一個詞若經由多種途徑（如既是原始詞又是其他詞之同義詞/關聯詞）被命中，強制保留最高權重。

---

## 3. 開放議題與確認紀錄

- [x] 確認加權權重數值基準（Tier 1: 1.0, Tier 2: 0.6, Tier 3: 0.25）。
- [x] 確認向後相容 `expand_query` 與既有 `BM25Engine` 介面。
