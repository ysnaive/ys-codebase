# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `CodeTokenizer` Unicode 區間與 LRU 快取 | 廢除掃描主迴圈中的逐字元正則匹配，改採頂層 `0x4e00 <= ord(c) <= 0x9fff` 等整數範圍比對；為識別碼拆分函式注入 `@lru_cache(maxsize=8192)` 與預編譯正則。 | P0 | [P00:DR-01] |
| **FR-02** | `Posting` 資料結構瘦身與頂層共享池 | 於 `Posting` 引入 `__slots__ = ('doc_id', 'tf', 'positions', 'field_tfs')`；將 `field_lengths` 抽離至頂層 `InvertedIndex.doc_lengths` 共享池，消除冗餘字典副本。 | P0 | [P00:DR-02] |
| **FR-03** | 舊版快取平滑自省遷移 | 於 `InvertedIndex.load()` 實作 Schema 自省防禦，遇舊版含 `field_lengths` 之二進位快取時自動萃取遷移至 `doc_lengths`，若快取損毀平滑觸發 JIT 重建。 | P0 | [P00:DR-02] |
| **FR-04** | `ThesaurusEngine` 展開加權快取 | 為 `ThesaurusEngine.expand_query_weighted()` 實作查詢簽章 `@lru_cache(maxsize=1024)`，消除重複集合構造與權重字典分配開銷。 | P1 | [P00:DR-03] |
| **FR-05** | `SemanticBundler` 動態門檻並行打包 | 實作 AST 打包動態門檻分流：檔案數 `< 10` 採主進程串行（零開銷）；`>= 10` 且系統多核時調度 `ProcessPoolExecutor` 分批並發解析 AST 符號與 Docstring。 | P0 | [P00:DR-04] |
| **FR-06** | BM25 Max-Score Top-K 動態剪枝 | 於 `InvertedIndex.search()` 評分迴圈實作 Max-Score 剪枝演算法，預估剩餘 Term 分數上限並安全早停，100% 保持最高精確度。 | P1 | [P00:DR-05] |
| **FR-07** | 基準測試與迴歸驗證套件 | 建立 `test_benchmark_perf_and_memory.py`，量化評估分詞吞吐量、記憶體降幅、多進程打包加速比與搜尋等價性。 | P0 | [P00:DR-01~05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單字元、純標點、Emoji 或未知 Unicode 字元輸入分詞器 | 正確識別非單詞或單字元 Token，不得拋出例外或進入無窮迴圈。 |
| **EC-02** | 載入舊版二進位快取 (`unified.idx.bin`) 時遇到舊結構 | `InvertedIndex.load` 進行屬性自省，相容舊格式並就地升級，無縫載入。 |
| **EC-03** | 查詢單一罕見詞 (高 IDF) 或超長查詢詞串 (50+ tokens) | Max-Score 剪枝演算法正確維持 Top-K 邊界，零漏搜 (Zero False Negatives)。 |
| **EC-04** | 沙盒/受限容器環境無法派生多進程或單核 CPU | `SemanticBundler` 捕獲 `ProcessPoolExecutor` 異常並自動安全降級為串行解析，確保 100% 執行成功。 |
| **EC-05** | 增量打補丁 (`patch_incremental`) 更新與刪除文檔 | 頂層 `doc_lengths` 同步修正與刪除對應文檔記錄，不得殘留過期文檔或記憶體洩漏。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 純淨度 / 零外部依賴 | 100% 採用純 Python 原生標準庫（`unicodedata`, `functools`, `concurrent.futures`, `heapq` 等），嚴禁引入第三方套件或 C 擴充。 |
| **NFR-02** | 記憶體瘦身指標 | `InvertedIndex` 節點記憶體佔用降低 $\ge 40\%$。 |
| **NFR-03** | 分詞吞吐量指標 | `CodeTokenizer` 純文字/代碼分詞吞吐量提升 $\ge 3\times$。 |
| **NFR-04** | 搜尋等價性守門 | BM25 Max-Score 剪枝搜尋結果與暴力全量評分結果 **100% 完全等價**。 |
| **NFR-05** | 測試覆蓋率 | 全生態系迴歸測試 100% 通過（`dev test knowledge-db` 全綠燈）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 子進程 Pickle 序列化約束**：`ProcessPoolExecutor` 跨進程傳遞之資料（AST 符號清單、檔案路徑）必須為純原生可序列化型別（如 `dict`、`tuple` 或標準 dataclass），避免傳遞不可序列化之動態閉包或解析器實例。
- **`[!WARNING]` LRU Cache 生命週期防護**：單詞拆分快取 `@lru_cache` 必須應用於無副作用的純函式，並設定合理的 `maxsize=8192`，避免無界限膨脹。
- **`[!NOTE]` 空間隔離鐵律**：所有代碼修改必須 100% 在 `ys_codebase/source/knowledge-db/` 進行，嚴禁手動改動 `modules/` 運行端。
