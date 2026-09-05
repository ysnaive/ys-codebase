# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 多語言混雜分詞器 (`MultilingualTokenizer`) | 實作支援中英混雜、CJK 雙向切分、駝峰/蛇形標識符提煉（如 `InvertedIndex` ➔ `inverted`, `index`）與程式碼常用符號斷句的分詞引擎。 | P0 | [P00:DR-01] |
| **FR-02** | Pip 相依宣告與環境治理 | 於 `source/knowledge-db/manifest.json` 宣告 `fastembed` (含 `onnxruntime`, `tokenizers`, `numpy`) 相依規格，納入私有微環境管轄。 | P0 | [P00:DR-06] |
| **FR-03** | ONNX 向量嵌入服務 (`EmbeddingService`) | 封裝 FastEmbed 輕量多語言模型（預設 `BAAI/bge-small-zh-v1.5`），模型權重快取於 `cache://knowledge-db/models/`，提供批次向量推論與餘弦相似度計算。 | P0 | [P00:DR-02] |
| **FR-04** | BM25 + 向量 RRF 複合檢索 (`HybridSearchEngine`) | 實作標準 Reciprocal Rank Fusion 演算法 ($RRF(d) = \sum \frac{w_m}{k + rank_m(d)}$)，融合 BM25 關鍵字與向量語意分數，支援權重調節。 | P0 | [P00:DR-03] |
| **FR-05** | 剛性平滑降級守門 (Zero-Failure Fallback) | 當 `fastembed` 未就緒、模型載入失敗或帶 `--lexical-only` 旗標時，100% 自動無感降級為純 BM25 倒排檢索，系統絕不崩潰。 | P0 | [P00:DR-04] |
| **FR-06** | 舊同義詞庫徹底淘汰 | 刪除手刻 `thesaurus.py`、`tests/test_thesaurus.py` 與靜態同義詞庫，直接以向量語意距離取代手動同義詞維護。 | P1 | [P00:DR-05] |
| **FR-07** | 向量二進位快取與增量同步 | 符號向量特徵使用 Protocol 5 Gzip 快取儲存於 `cache://knowledge-db/vectors.bin.gz`，支援 JIT 增量比對與熱補丁更新。 | P1 | [P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 微環境離線或無網路無法下載 ONNX 模型 | 初始化時捕獲例外並標記 `is_available=False`，自動降級為純 BM25，日誌記錄警告但不中斷檢索。 |
| **EC-02** | 中英混雜無空格文本（如 `解析InvertedIndex倒排索引`） | 分詞器精準切分 CJK 字元與英文標識符（`解析`, `inverted`, `index`, `倒排`, `索引`），不發生拼貼漏詞。 |
| **EC-03** | 極長註解或代碼內容超過模型 Context Window (512 tokens) | 提取符號之 FQN、結構化簽名與 Docstring 前 250 字元作為向量特徵輸入，避免截斷異常。 |
| **EC-04** | 查詢關鍵字為純空白字元或純標點 | 安全回傳空候選清單，不觸發昂貴之模型推論計算。 |
| **EC-05** | 本地模型權重損毀 (Corrupted ONNX) | 捕獲推論驗證錯誤，清空損毀快取並即時降級至 BM25 檢索。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 單次 CPU 向量推論延遲 $< 30\text{ms}$，RRF 融合排序耗時 $< 5\text{ms}$。 |
| **NFR-02** | 快取體積 | 1,000 個符號之向量特徵在 Gzip 壓縮下磁碟佔用 $< 500\text{KB}$。 |
| **NFR-03** | 記憶體約束 | ONNX Runtime 模型載入後，推論記憶體常駐開銷 $< 250\text{MB}$。 |
| **NFR-04** | 退化性回歸 | 既有 130+ 個單元測試在純 BM25 或 Hybrid 模式下 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`fastembed` 會在首次調用時自 HuggingFace 下載模型權重；在測試與沙盒環境中，必須提供 Mock/Dummy 向量生成器以確保單元測試完全離線、無網路相依且極速完成。
