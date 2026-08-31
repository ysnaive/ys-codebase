# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Confirmed  

> 依據 P01~P03：[P01](./P01_requirements_spec.md) / [P02](./P02_architecture_plan.md) / [P03](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書（P03）與架構設計（P02）中均有具體承接。
- [x] **邊界防護**：EC-01 ~ EC-05 具備明確的異常防禦與降級機制（Unicode 極限字元、舊快取自省、單進程安全降級、增量清理）。
- [x] **依賴純淨**：100% 採用純 Python 標準庫，符合 NFR-01 要求。
- [x] **測試前置**：P06 測試案例清單（FT-01 ~ FT-09）1:1 覆蓋所有 FR/EC/NFR。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/knowledge-db/README.md` | Modify | 更新分詞器 Unicode 區間優化、倒排索引頂層共享池與多進程並發打包架構說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：多進程解析時，若遇到損毀檔案或子進程異常，是否會導致主進程死鎖阻塞？**  
> 💡 **防護解法**：`_parse_file_task` 工作者以頂層 `try...except Exception` 完整包覆，遇例外回傳 `None` 並記錄 Warning；主進程過濾無效回傳，且在環境不支援（單核/沙盒受限）時自動安全降級為串行解析，確保 100% 穩健性。

> ❓ **尖銳問題 2：Max-Score 剪枝在查詢詞帶有加權衰減 (如 0.25) 時，是否可能誤判上限而漏搜相關文檔？**  
> 💡 **防護解法**：在計算各 Term 之理論最高分 `max_term_score` 時，將權重 `weight` 直接乘入評分上限公式：$\text{MaxScore}(t, w) = w \times \text{IDF}(t) \times \dots$。由於早停判定依據的是「剩餘所有 Term 理論最大可能得分總和 $\sum \text{MaxScore}$」，數學上保證了未遍歷完的文檔總分絕對無法超越當前第 K 名分數，達成 100% 精度等價 (Zero False Negatives)。

> ❓ **尖銳問題 3：`Posting` 引入 `__slots__` 是否會導致歷史舊二進位快取加載失敗？**  
> 💡 **防護解法**：在 `InvertedIndex.load()` 中實作屬性自省遷移邏輯，若讀取到舊版包含 `field_lengths` 字典的舊物件，自動萃取至頂層 `self.doc_lengths` 並平滑升級；若快取損毀則自動觸發 JIT 增量重新建置。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`CodeTokenizer` Unicode 整數比對、預編譯正則與 `@lru_cache` 實作 (`knowledge_db/tokenizer.py`)。
- [ ] **TASK-02**：`Posting` `__slots__` 資料結構重構與內部 `field_lengths` 移除 (`knowledge_db/schema.py`)。
- [ ] **TASK-03**：`InvertedIndex.doc_lengths` 頂層共享池、增量打補丁維護與舊版快取自省升級實作 (`knowledge_db/retrieval.py`)。
- [ ] **TASK-04**：`ThesaurusEngine` 加權展開 LRU 快取實作 (`knowledge_db/thesaurus.py`)。
- [ ] **TASK-05**：`SemanticBundler` 動態門檻多進程並發解析 AST 實作 (`knowledge_db/bundler.py`)。
- [ ] **TASK-06**：`InvertedIndex.search` BM25 Max-Score 評分上限預估與 Top-K 剪枝實作 (`knowledge_db/retrieval.py`)。
- [ ] **TASK-07**：新增效能與記憶體基準測試套件 `test_benchmark_perf_and_memory.py` (`tests/`)。
- [ ] **TASK-08**：執行全量自動化跑測與靜態合規性檢核 (`dev test knowledge-db` & `dev check knowledge-db`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **`[P04:DR-01]`**：確認全棧重構嚴格遵守純 Python 零外部依賴鐵律。
- **`[P04:DR-02]`**：確認 P06 測試計畫與指標剛性定稿為 `Confirmed`，進入 Phase 5 編碼實作。
