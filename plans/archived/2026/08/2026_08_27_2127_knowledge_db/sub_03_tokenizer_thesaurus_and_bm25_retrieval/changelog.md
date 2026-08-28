# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-28 13:54 | `PHASE` | 推進 Phase 7 (成果展示與結案)，交付 docs/knowledge-db/tokenizer.md、retrieval.md 與 README.md 更新，產出 P07_walkthrough.md (Completed)，追加 CHANGELOG.md |
| 2026-08-28 13:53 | `TEST` | 開發者指示 UX-01 免測，P06_test_plan.md 標記為 Passed |
| 2026-08-28 13:52 | `TEST` | 推進 Phase 6 (測試與驗證)，實機執行 python yscb.py dev test knowledge-db，全模組 32/32 測試案例 100% Passed (3.268s)，回填 P06_test_plan.md |
| 2026-08-28 13:52 | `PHASE` | 推進 Phase 5 (依序程式碼實作)，依拓撲完成 TASK-01~05 實作，包含 CodeTokenizer, ThesaurusEngine, InvertedIndex, BM25Engine, CLI search 與單元測試套件 |
| 2026-08-28 13:50 | `PHASE` | 推進 Phase 4 (實作計畫與定稿審查)，產出 P04_implementation_plan.md (Confirmed)，交叉驗證 FR/EC/NFR，通過 2 項架構靈魂拷問，同步剛性定稿 P06_test_plan.md (Confirmed) |
| 2026-08-28 13:50 | `PHASE` | 推進 Phase 3 (API 與介面規格定義)，產出 P03_api_spec.md (Confirmed)，定義 CodeTokenizer, ThesaurusEngine, InvertedIndex, BM25Engine 介面 |
| 2026-08-28 13:50 | `PHASE` | 推進 Phase 2 (架構與模組設計)，產出 P02_architecture_plan.md (Confirmed)，同步 Test-First 初始化 P06_test_plan.md (Draft)，規劃 FT-01~07、ET-01 與 RT-01 |
| 2026-08-28 13:50 | `PHASE` | 推進 Phase 1 (需求規格轉譯)，產出 P01_requirements_spec.md (Confirmed)，1:1 轉譯 FR-01~08、EC-01~08 與 NFR-01~04 |
| 2026-08-28 13:49 | `PHASE` | 開發者審查確認定稿 P00_semantic_requirements.md (狀態：`Confirmed`)，收斂分詞策略、BM25 權重與雙層同義詞規格 |
| 2026-08-28 13:46 | `PHASE` | 開立 sub_03 子計畫目錄，伴隨建立 P00_semantic_requirements.md 與 changelog.md (狀態：`Discussing`) |
