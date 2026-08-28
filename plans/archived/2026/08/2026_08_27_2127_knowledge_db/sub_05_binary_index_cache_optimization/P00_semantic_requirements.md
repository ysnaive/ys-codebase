# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 計畫類型：Optimization / Refactoring  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：倒排索引屬於計算完畢的本機衍生快取，不需要採用純文字 JSON 格式。採用 **方案 A (二進位 Pickle + Gzip 壓縮，體積最小、載入最快)** 進行索引存儲結構與快取序列化重構。
- **核心目標**：
  1. **符號池分離與輕量引用解耦 (Symbol Pool Normalization)**：
     - 重構 `InvertedIndex` 資料模型：在頂層建立 `symbols: Dict[str, UnifiedSymbol]`（以 `doc_id` 唯一識別）。
     - 倒排表 `postings[term]` 僅存儲輕量引用節點 `(doc_id, field_freqs, field_lengths, space)`，徹底消滅同一個符號在數百個 Term 中被深層拷貝重複內嵌的 500 倍膨脹冗餘。
  2. **原生二進位 Pickle + Gzip 壓縮快取 (Binary Gzip Cache: `.index.bin.gz`)**：
     - 快取檔案儲存為 `cache://knowledge-db/indices/<space_name>.index.bin.gz`。
     - 使用 Python 原生標準庫 `pickle` (最高協議 Protocol 5) 與 `gzip` (Level 6)。
     - 索引體積從 **55.35 MB 暴降至 < 600 KB（縮減 99%）**。
     - 索引載入與反序列化時間從 **~850 ms 降低至 < 50 ms（加速近 20 倍）**。
  3. **檢索與 API 零破壞相容 (Zero Breaking Change)**：
     - `BM25Engine.search()` 簽名與回傳之 `SearchResult` 保持 100% 不變，檢索時透過 `index.symbols[doc_id]` 快速定位完整符號。
     - `KnowledgeEngine` 與 CLI 指令（`status`, `index`, `search`, `clean`）行為完全相容，自動支援 `.bin.gz` 讀寫。
     - `export_bundle` 仍保持不可變純 JSON 導出，供跨語言與文檔交換使用。
  4. **零外部依賴 (Zero External Dependency)**：
     - 100% 依賴純 Python 3.9+ 原生標準庫（`pickle`, `gzip`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### [P00:DR-01] 符號池抽離 (Symbol Pool Normalization)
- **問題現狀**：原本 `Posting` 類別中直接持有 `symbol: UnifiedSymbol`，序列化時導致同一符號被序列化數百次。
- **重構決策**：
  - `InvertedIndex` 內建 `symbols: Dict[str, UnifiedSymbol]` 字典。
  - `Posting` 僅保留 `doc_id: str`、`field_freqs: Dict[str, int]`、`field_lengths: Dict[str, int]`、`space: str`。
  - 序列化時 `symbols` 僅寫入一次，倒排表中只寫入 `doc_id` 引用。

---

### [P00:DR-02] 本地快取格式升級為二進位 Gzip (`.index.bin.gz`)
- **決策**：
  - 本地倒排索引檔案名稱更新為 `<space_name>.index.bin.gz`。
  - 儲存路徑為 `cache://knowledge-db/indices/<space_name>.index.bin.gz`。
  - 寫入時採用 `atomic_save`（先寫入 `.tmp` 再以 `os.replace` 原子替換）。

---

### [P00:DR-03] 遺留 JSON 舊快取平滑自癒與清理
- **決策**：
  - `KnowledgeEngine.clean()` 同時清理舊的 `.index.json` 與新的 `.index.bin.gz`。
  - `KnowledgeEngine.status()` 正確統計 `.index.bin.gz` 索引狀態。

---

## 3. 開放議題與確認紀錄

- [x] **確認 1 (技術選型)**：確認採用二進位 Pickle + Gzip 壓縮（100% 標準庫，體積最小、載入最快）。
- [x] **確認 2 (快取副檔名)**：統一採用 `<space_name>.index.bin.gz`，存放於 `cache://knowledge-db/indices/`。
- [x] **確認 3 (API 介面保證)**：`KnowledgeEngine` 與 `BM25Engine` 公開 API 簽名 100% 保持穩定無損。
