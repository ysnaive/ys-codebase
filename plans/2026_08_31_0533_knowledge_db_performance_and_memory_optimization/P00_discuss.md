# 需求討論與問題界定紀錄 (Phase 0: Discuss)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Discussing  

---

## 1. 原始需求陳述與問題背景

繼承技術路線圖 [`knowledge_db_performance_and_memory_optimization.md`](file:///workspace/ys-codebase/plans/roadmap/knowledge_db_performance_and_memory_optimization.md)，針對 `knowledge-db` 模組目前存在的五大效能瓶頸進行原生效能重構：
1. **分詞器逐字元正則開銷**：`CodeTokenizer.is_cjk(char)` 在主迴圈中對每一個字元調用 `re.match`，且 `split_identifier()` 對高頻識別碼重複執行正則拆解。
2. **倒排索引節點記憶體冗餘**：`Posting` 未配置 `__slots__`，且 `field_lengths` 字典在同篇文檔的每一個 Term Posting 中重複持有一份拷貝。
3. **同義詞展開無快取**：`ThesaurusEngine.expand_query_weighted()` 每次搜尋皆動態構造加權字典與複製 Set 集合。
4. **語意打包 CPU 密集串行瓶頸**：`SemanticBundler.bundle_space()` 在全庫建置時採單進程逐檔循序解析 AST。
5. **高頻 Term BM25 暴力累加**：查詢常見 Term 時，BM25 對長列表 Posting 進行全量浮點運算，缺乏動態 Top-K 評分下界早停剪枝。

---

## 2. 核心討論與初步架構決策 (Discussion & Decisions)

- **[P00:DR-01]**：`CodeTokenizer` 極速化——廢除每字元正則匹配，改採 Python 頂層 Unicode 整數區間比對 (`0x4e00 <= ord(c) <= 0x9fff` 等)，並為 `split_identifier` 引入 `@lru_cache(maxsize=8192)` 與預編譯正則。
- **[P00:DR-02]**：倒排索引資料結構瘦身——於 `Posting` 引入 `__slots__`，將 `field_lengths` 字典抽離至 `InvertedIndex.doc_lengths: Dict[str, Dict[str, int]]` 頂層共享池，保持 Protocol 5 二進位快取向下相容。
- **[P00:DR-03]**：同義詞展開快取——為 `ThesaurusEngine.expand_query_weighted` 引入 LRU Memoization 快取機制。
- **[P00:DR-04]**：多工作者並發 AST 語意打包——於 `SemanticBundler` 實作分批並發檔案解析機制，動態調度多核心處理。
- **[P00:DR-05]**：BM25 Top-K 動態評分剪枝——於 `InvertedIndex.search` 評分迴圈引入候選分數上限預估與安全早停剪枝。

---

## 3. 開放議題與待深度討論清單 (Open Issues for Discussion)

- [ ] **議題 1：多工作者並發打包模型選型**（`ProcessPoolExecutor` vs `ThreadPoolExecutor` vs Chunked Batching）在沙盒與不同 OS 平台下的相容性與記憶體開銷評估。
- [ ] **議題 2：倒排索引 Protocol 5 二進位快取向後相容性**（舊版快取載入時若遇舊格式 `field_lengths` 的防禦與自動遷移策略）。
- [ ] **議題 3：BM25 Top-K 動態剪枝策略的精度守門**（如何確保動態早停 100% 不會漏掉潛在的高分相關符號）。
- [ ] **議題 4：基準測試 (Benchmark) 設計**（如何量化驗證分詞吞吐量 10x、打包提速 3.7x、記憶體節省 53% 等指標）。

---

## 4. 分流確認
- 涉及跨 4 大核心組件重構、記憶體資料結構調整與效能壓測驗證，分流確立為 **Level 1 (Full Track)**。

