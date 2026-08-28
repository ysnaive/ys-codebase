# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Passed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `CodeTokenizer` 程式碼駝峰 (`camelCase`, `PascalCase`)、底線 (`snake_case`) 與全大寫縮寫切分，保留原始詞與子詞 | FR-01 | `test_tokenizer.py:TestTokenizer.test_code_identifier_tokenization` |
| **FT-02** | 單元測試 | 驗證 `CodeTokenizer` CJK 中文字元 1-gram 與 2-gram 窗口滑動切分、英數混合與停用詞過濾 | FR-01, EC-01 | `test_tokenizer.py:TestTokenizer.test_cjk_and_stopword_tokenization` |
| **FT-03** | 單元測試 | 驗證 `ThesaurusEngine` 內建軟工詞庫載入、自訂詞庫無衝突合併與查詢詞雙向擴展 | FR-02, EC-05 | `test_thesaurus.py:TestThesaurus.test_thesaurus_merging_and_query_expansion` |
| **FT-04** | 單元測試 | 驗證 `InvertedIndex` 多欄位倒排索引建立、詞頻統計、文件平均長度計算與 IDF 平滑防負數 | FR-03, EC-03 | `test_retrieval.py:TestRetrieval.test_inverted_index_building_and_idf` |
| **FT-05** | 單元測試 | 驗證 `BM25Engine` 多欄位加權評分 (Name 3.5, Sig/Mem 2.0, Doc 1.5) 與 Exact Match 2.0x 置頂加權 | FR-04 | `test_retrieval.py:TestRetrieval.test_bm25_multi_field_scoring_and_boost` |
| **FT-06** | 單元測試 | 驗證 `QueryFilter` 空間、程式語言、符號類型過濾與最低評分截斷限制 | FR-05, FR-06 | `test_retrieval.py:TestRetrieval.test_query_filtering_and_top_k` |
| **FT-07** | 單元測試 | 驗證 `InvertedIndex` 倒排索引字典序列化導出與持久化載入還原一致性 | FR-07 | `test_retrieval.py:TestRetrieval.test_inverted_index_serialization` |
| **ET-01** | 例外測試 | 驗證面對空 Query、未命中詞條、特殊字元與非正則安全檢索，安全回傳空清單不拋出未處理異常 | FR-04, EC-01, EC-02, EC-06 | `test_retrieval.py:TestRetrieval.test_edge_cases_empty_and_special_chars` |
| **RT-01** | 回歸測試 | 全模組單元測試回歸，執行 `python yscb.py dev test knowledge-db` 達成 100% Passed | NFR-01~04 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_code_identifier_tokenization`: 代碼標識符駝峰/底線/縮寫切分與全詞保留 100% 通過 | 2026-08-28 13:52 |
| **FT-02** | `Passed` | `test_cjk_and_stopword_tokenization`: CJK 1-gram/2-gram 滑動窗口與停用詞過濾 100% 通過 | 2026-08-28 13:52 |
| **FT-03** | `Passed` | `test_thesaurus_merging_and_query_expansion`: 軟工詞庫載入、自訂詞庫合併與雙向查詢擴展 100% 通過 | 2026-08-28 13:52 |
| **FT-04** | `Passed` | `test_inverted_index_building_and_idf`: 倒排索引建立、平均長度統計與平滑 IDF 計算 100% 通過 | 2026-08-28 13:52 |
| **FT-05** | `Passed` | `test_bm25_multi_field_scoring_and_boost`: 多欄位加權評分與 Exact Match 2.0x 置頂加權 100% 通過 | 2026-08-28 13:52 |
| **FT-06** | `Passed` | `test_query_filtering_and_top_k`: QueryFilter 語言、類型過濾與 limit 數量截斷 100% 通過 | 2026-08-28 13:52 |
| **FT-07** | `Passed` | `test_inverted_index_serialization`: InvertedIndex 序列化與反序列化無損一致 100% 通過 | 2026-08-28 13:52 |
| **ET-01** | `Passed` | `test_edge_cases_empty_and_special_chars`: 空 Query、未命中詞條與特殊正則字元安全防禦 100% 通過 | 2026-08-28 13:52 |
| **RT-01** | `Passed` | 實機執行 `python yscb.py dev test knowledge-db`，全套件 32/32 測試案例 100% Passed (3.268s) | 2026-08-28 13:52 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者指示免測 (2026-08-28 13:53)。

