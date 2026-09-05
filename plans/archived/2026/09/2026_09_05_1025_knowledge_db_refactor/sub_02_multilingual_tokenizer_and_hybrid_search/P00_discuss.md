# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「同意抽離概念後重寫，但我想順便優化，現在是 BM25 + 同義詞 + 相關詞 搜尋，是不是可以考慮藉由本次機會，真正優化成 BM25 + 語意向量複合式搜尋?」
  - 「如果是多語言混雜的環境怎麼辦?」
  - 「Tokenizer 能處裡多語言問題嗎?」
  - 「方案 A，標準依賴，但依然需要降級機制，保證可執行 AST & BM25 搜尋」
- **核心目標**：
  1. **多語言混雜 Tokenizer**：升級分詞引擎，同時支援中英混雜標記切分、駝峰/蛇形標識符提煉，克服跨語言代碼與註解斷詞瓶頸。
  2. **輕量向量嵌入 (Embedding)**：透過 YSCB 微環境引入成熟 Pip 相依（基於 ONNX Runtime 離線輕量多語言模型 `fastembed`），實現純本機、零雲端依賴的向量化。
  3. **BM25 + 向量 RRF 複合檢索 (Hybrid Search)**：實作 Reciprocal Rank Fusion (RRF) 倒數排名融合演算法，將 BM25 精確關鍵字命中與向量泛化語意相關度融合排序。
  4. **剛性平滑降級守門**：若向量依賴未就緒或微環境資源受限，100% 優雅降級為純 BM25 檢索，保障系統極致穩定。
  5. **手刻同義詞庫徹底移除**：徹底汰換並刪除 `thesaurus.py` 與靜態同義詞對照表，由向量語意距離自然解決同義/關聯詞搜尋。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁引入龐大 PyTorch / CUDA 或外部雲端 API 依賴（僅限 ONNX Runtime 輕量本機微環境）。
  - 不改動調用圖譜與拓撲鏈接（NetworkX 重構留在 sub_03）。
  - 不改動 CLI 外部門面介面契約（維持 `--json`、`-s` 輸出格式）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 向量推論引擎選型**：採用 `fastembed`（基於 ONNX Runtime，Wheel-Only 易安裝，無 PyTorch 龐大依賴，推論記憶體佔用小且無冷啟動延遲）。
- **[P00:DR-02] 多語言向量模型選型**：預設選用輕量多語言 Embedding 模型（例如 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 或 `BAAI/bge-small-zh-v1.5`），模型檔離線快取於 `cache://knowledge-db/models/`。
- **[P00:DR-03] RRF 融合演算法與常數**：採標準 RRF 倒數排名融合公式 $RRF(d) = \sum_{m} \frac{w_m}{k + rank_m(d)}$，其中預設常數 $k=60$，$w_{bm25}=0.5, w_{vector}=0.5$。
- **[P00:DR-04] 剛性平滑降級守門 (Zero-Failure Fallback)**：當 `fastembed` 未安裝、模型載入失敗或指定 `--lexical-only` 時，自動且 100% 降級為純 BM25 倒排檢索，系統零崩潰。
- **[P00:DR-05] 手刻同義詞庫與舊代碼清理**：徹底刪除 `knowledge_db/thesaurus.py`、`tests/test_thesaurus.py` 與靜態同義詞對照表，消除過時規則負擔。
- **[P00:DR-06] 外部相依管理方針 (方案 A 標配 + 剛性降級)**：定調將 `fastembed` 與 ONNX Runtime 列為 `knowledge-db` 的標準 `pip_dependencies` 宣告，但檢索管線架構層強制實作動態 import 攔截與例外防護，確保即便無網路/未下載模型時，AST 與 BM25 核心檢索 100% 正常運作。

---

## 3. 開放議題與確認紀錄

- [x] **向量模型偏好**：定調以輕量多語言模型（`BAAI/bge-small-zh-v1.5` 或 `paraphrase-multilingual-MiniLM-L12-v2`，約 65~115MB）為標配。
- [x] **向量快取存儲路徑**：符號向量特徵序列化儲存於 `cache://knowledge-db/vectors.bin.gz`，受 `.gitignore` 隔離，檢索時 JIT 懶載入。
- [x] **降級保證**：確認採方案 A，以標準依賴形式物化，並在程式層實現雙重保險之 AST & BM25 降級保證。
