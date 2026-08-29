# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_thesaurus_pool_decoupling_and_enrichment  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 計畫類型：Refactor / Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 詞彙池解耦：刪除所有原始碼內建詞表，統一由 contributes 提供，並建置較為完善的初始內建詞彙表。
- **核心目標**：
  - 徹底移除 `thesaurus.py` 原始碼中的 `BUILTIN_THESAURUS` 硬編碼靜態常數，使 `ThesaurusEngine` 成為純淨無狀態的加權展開容器。
  - 將內建詞庫轉移至宣告式 `source/knowledge-db/contributes/knowledge-db.json`，由 `SpaceManager` 統一載入與聚合。
  - 建立高質量、全方位的初始詞彙庫，涵蓋軟工核心動名詞、語言特化單向別名（如 SPICE、HDL、C++、Python）與領域相依關聯詞（編譯/AST、檢索/BM25、測試/沙盒、電路/網表等）。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `sub_01` 已驗收定稿之三階加權展開演算法與 BM25 衰減計分核心邏輯。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 詞彙池源碼解耦與 Contributes 單一來源原則 (SSOT)**：
  - `thesaurus.py` 內部不保留任何硬編碼詞表，`ThesaurusEngine` 預設初始化為空容器或接收外部載入之 `ThesaurusConfig`。
  - `knowledge-db` 模組透過自身之 `contributes/knowledge-db.json` 宣告系統預設之 `thesaurus`、`aliases` 與 `related` 詞庫。
- **[P00:DR-02] 初始詞庫三維豐富化規範 (Thesaurus Enrichment Standard)**：
  - 同義詞 (Tier 2, 0.6)：擴展為 20+ 組涵蓋 CRUD、檢索、配置、解析、測試、轉換等高頻軟工動名詞。
  - 單向別名 (Tier 2, 0.6)：涵蓋語系縮寫與上下位概念（如 `ngspice => spice, circuit`, `verilog => hdl`, `cpp => cxx`）。
  - 領域關聯詞 (Tier 3, 0.25)：涵蓋編譯分析、資訊檢索、硬體電路、測試防護、工作流治理等相依主題。

---

## 3. 開放議題與確認紀錄

- [x] 確認 `ThesaurusEngine` 構造函式支援接收 `ThesaurusConfig` 或三個獨立集合。
- [x] 確認將內建詞庫放置於 `source/knowledge-db/contributes/knowledge-db.json`。
