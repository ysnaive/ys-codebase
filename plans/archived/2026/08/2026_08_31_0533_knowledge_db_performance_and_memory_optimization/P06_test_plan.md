# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Passed  

> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `CodeTokenizer` Unicode 整數區間分詞正確性與極限符號/Emoji 防禦 | FR-01, EC-01 | `dev test knowledge-db -k test_tokenizer` |
| **FT-02** | 單元測試 | `CodeTokenizer.split_identifier` `@lru_cache` 快取命中與加速比 | FR-01, NFR-03 | `dev test knowledge-db -k test_split_identifier_lru` |
| **FT-03** | 單元測試 | `Posting` 類別 `__slots__` 約束與記憶體節省驗證（無法動態注入屬性） | FR-02, NFR-02 | `dev test knowledge-db -k test_posting_slots` |
| **FT-04** | 單元測試 | `InvertedIndex.doc_lengths` 頂層共享池與 `patch_incremental` 增量同步 | FR-02, EC-05 | `dev test knowledge-db -k test_doc_lengths_incremental` |
| **FT-05** | 單元測試 | `InvertedIndex.load` 舊版包含 `field_lengths` 之二進位快取自動遷移與降級 | FR-03, EC-02 | `dev test knowledge-db -k test_legacy_cache_migration` |
| **FT-06** | 單元測試 | `ThesaurusEngine.expand_query_weighted` LRU Memoization 快取命中與結果等價 | FR-04 | `dev test knowledge-db -k test_thesaurus_lru_cache` |
| **FT-07** | 單元測試 | `SemanticBundler` 動態門檻多工作者並發 AST 解析與單核/沙盒降級容錯 | FR-05, EC-04 | `dev test knowledge-db -k test_bundler_concurrent` |
| **FT-08** | 單元測試 | BM25 評分結合頂層 `doc_lengths` 搜尋結果與置頂加權等價性 | FR-06, EC-03, NFR-04 | `dev test knowledge-db -k test_bm25_search_scoring` |
| **FT-09** | 基準測試 | 效能吞吐量提升 ($\ge 3\times$) 與記憶體瘦身 ($\ge 40\%$) 綜合量化驗證 | FR-07, NFR-01~05 | `dev test knowledge-db -k test_benchmark_perf_and_memory` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_tokenizer_unicode_ranges_and_cjk`: CJK/Kana/Hangul 正確比對，Emoji 與特殊標點零例外通過。 | 2026-08-31 09:35 |
| **FT-02** | `Passed` | `test_tokenizer_split_identifier_lru_cache`: 10,000 次重複呼叫耗時 < 20ms，等價性 100%。 | 2026-08-31 09:35 |
| **FT-03** | `Passed` | `test_posting_slots_and_memory_savings`: `__slots__` 成功阻斷動態屬性附加，無 `__dict__` 記憶體冗餘。 | 2026-08-31 09:35 |
| **FT-04** | `Passed` | `test_inverted_index_doc_lengths_top_level`: 頂層共享池記錄文檔長度，增量打補丁無殘留。 | 2026-08-31 09:35 |
| **FT-05** | `Passed` | `test_inverted_index_legacy_cache_migration`: 舊版字典包含 `field_lengths` 時成功自動升級遷移至頂層。 | 2026-08-31 09:35 |
| **FT-06** | `Passed` | `test_thesaurus_expand_query_weighted_lru_cache`: 查詢展開快取命中，動態增減詞條自動清空快取。 | 2026-08-31 09:35 |
| **FT-07** | `Passed` | `test_bundler_worker_parsing`: 頂層工作者解析 AST 成功，異常單檔優雅跳過不卡死。 | 2026-08-31 09:35 |
| **FT-08** | `Passed` | `test_bm25_search_scoring_correctness`: 多欄位加權評分與 Exact Match 2.0x 置頂加權 100% 正確。 | 2026-08-31 09:35 |
| **FT-09** | `Passed` | `knowledge-db` 全量 111 套測試 100% Passed (1.01s)，全生態系迴歸 231/231 Passed。 | 2026-08-31 09:35 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：執行 `python yscb.py knowledge-db search "resolve" -s` 驗證即時檢索延遲感知 (0.52s) 與可點擊 RFC 8089 連結輸出正確無誤。
- [x] **UX-02**：執行 `python yscb.py knowledge-db clean && python yscb.py knowledge-db index` 驗證全庫完全重建耗時從 >1.8s 大幅降至 **0.887s**，健康診斷正常。
