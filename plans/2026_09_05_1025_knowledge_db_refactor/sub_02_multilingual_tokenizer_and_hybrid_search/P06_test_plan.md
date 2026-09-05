# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `MultilingualTokenizer` 中英混雜、CJK 雙向切分、駝峰蛇形標識符提煉與停用詞過濾 | FR-01 | `python yscb.py dev test knowledge-db -k test_tokenizer --quiet` |
| **FT-02** | 單元測試 | 驗證 `EmbeddingService` 向量生成、餘弦相似度計算與二進位快取持久化 | FR-03, FR-07 | `python yscb.py dev test knowledge-db -k test_embedding --quiet` |
| **FT-03** | 單元測試 | 驗證 `HybridSearchEngine` RRF 融合排序邏輯，核算 Rank 權重計算正確性 | FR-04 | `python yscb.py dev test knowledge-db -k test_rrf_fusion --quiet` |
| **FT-04** | 單元測試 | 驗證雙軌剛性降級守門：模擬 `fastembed` 缺失或 `--lexical-only` 時 100% 退化為純 BM25 | FR-05 | `python yscb.py dev test knowledge-db -k test_fallback --quiet` |
| **FT-05** | 單元測試 | 驗證舊同義詞庫 (`thesaurus.py`) 與舊測試完全移除，系統無殘留符號引用 | FR-06 | `python yscb.py dev test knowledge-db --quiet` |
| **FT-06** | 端到端測試 | 驗證 `KnowledgeEngine.search()` 之 Hybrid 檢索與 `--json` 結構化輸出相容性 | FR-04, NFR-04 | `python yscb.py dev test knowledge-db -k test_hybrid_search --quiet` |
| **ET-01** | 邊界測試 | 驗證空字串、純標點與無效查詢輸入之安全防護，不觸發昂貴推論 | EC-04 | `python yscb.py dev test knowledge-db -k test_empty_query --quiet` |
| **ET-02** | 邊界測試 | 驗證 512+ tokens 超長內容之安全切片與特徵提煉 | EC-03 | `python yscb.py dev test knowledge-db -k test_long_content --quiet` |
| **ET-03** | 邊界測試 | 驗證本地向量快取損毀時捕獲驗證失敗並安全降級 | EC-05 | `python yscb.py dev test knowledge-db -k test_corrupted_cache --quiet` |
| **RT-01** | 回歸測試 | 驗證 `knowledge-db` 全套件與全生態系單元測試 100% 通過 | NFR-04 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `MultilingualTokenizer` 中英混雜、CJK 1/2-gram、駝峰蛇形拆解與邊界測試 100% 通過 | 2026-09-05 |
| **FT-02** | `Passed` | `EmbeddingService` 向量生成、L2 正規化與二進位快取持久化測試 100% 通過 | 2026-09-05 |
| **FT-03** | `Passed` | `HybridSearchEngine` RRF 倒數排名融合公式與權重核算測試 100% 通過 | 2026-09-05 |
| **FT-04** | `Passed` | `HybridSearchEngine` 剛性平滑降級（`lexical_only=True`、模型未就緒）測試 100% 通過 | 2026-09-05 |
| **FT-05** | `Passed` | 舊同義詞庫 (`thesaurus.py`) 與舊測試用例徹底移除，全套件無殘留引用 | 2026-09-05 |
| **FT-06** | `Passed` | `KnowledgeEngine.search()` 複合檢索與結構化報告格式測試 100% 通過 | 2026-09-05 |
| **ET-01** | `Passed` | 空字串、純空白與 None 輸入邊界防護測試 100% 通過 | 2026-09-05 |
| **ET-02** | `Passed` | 512+ tokens 超長文本特徵提煉與 L2 正規化測試 100% 通過 | 2026-09-05 |
| **ET-03** | `Passed` | 損毀快取安全退化為空向量索引測試 100% 通過 | 2026-09-05 |
| **RT-01** | `Passed` | `dev test knowledge-db` 全套件 116 筆測試用例 100% 通過 (0 failures, 0 errors) | 2026-09-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py knowledge-db search "倒排索引" --json -s`，驗證中英混雜語意檢索正確返回相關符號與代碼切片 | `[跳過/免測]` | 開發者指示免測 (2026-09-05) |
| **UX-02** | 實機執行 `python yscb.py knowledge-db search "InvertedIndex" --lexical-only`，驗證剛性降級旗標可強制退化為純 BM25 檢索 | `[跳過/免測]` | 開發者指示免測 (2026-09-05) |
