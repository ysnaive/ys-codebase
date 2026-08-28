# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **符號池分離儲存 (Symbol Pool)** | 在 `InvertedIndex` 內建立頂層 `symbols: Dict[str, UnifiedSymbol]`，每個被索引之符號以其 `doc_id` 作為唯一鍵僅儲存一份。 | P0 | [P00:DR-01] |
| **FR-02** | **倒排節點輕量化 (Lightweight Posting)** | 重構 `Posting` 資料模型，僅包含 `doc_id: str`、`field_freqs: Dict[str, int]`、`field_lengths: Dict[str, int]` 與 `space: str`，徹底移除直接持有之 `symbol` 物件。 | P0 | [P00:DR-01] |
| **FR-03** | **二進位 Gzip 序列化核心** | 在 `InvertedIndex` 實作 `save_binary(path: Path)` 與 `load_binary(path: Path) -> InvertedIndex`，使用 `pickle.HIGHEST_PROTOCOL` (Protocol 5) 與 `gzip.compress` (Level 6) 進行原子讀寫。 | P0 | [P00:DR-02] |
| **FR-04** | **快取檔案路徑升級** | `KnowledgeEngine` 與 `BM25Engine` 預設倒排索引快取檔案全面更新為 `cache://knowledge-db/indices/<space_name>.index.bin.gz`。 | P0 | [P00:DR-02] |
| **FR-05** | **狀態統計與清理適配** | `KnowledgeEngine.status()` 正確偵測並顯示 `.index.bin.gz` 狀態；`KnowledgeEngine.clean()` 同步支援清理 `.index.bin.gz` 與舊 `.index.json`。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **二進位快取檔案損毀 (Corrupt Gzip / Pickle)** | 捕獲 `gzip.BadGzipFile` 或 `pickle.UnpicklingError`，記錄警告日誌並透明觸發重新建立索引，不引發崩潰。 |
| **EC-02** | **快取檔案缺失或不存在** | `load_binary` 或 `_get_or_build_index` 透明觸發 `bundle_space` 即時重新建置並快取。 |
| **EC-03** | **多空間聯集檢索存在重複 doc_id** | 透過 `symbols` 符號池安全去重，確保檢索結果完整且無重複。 |
| **EC-04** | **查詢詞命中但符號已自符號池移除** | 防禦 `doc_id` 缺失異常，安全略過孤立 Posting 節點。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **體積大幅縮減 (Size Reduction)** | 倒排索引檔案大小相比原始 JSON 縮減 $\ge 90\%$（預期 55MB 降至 < 600 KB）。 |
| **NFR-02** | **極速載入 (Load Latency)** | 二進位倒排索引檔案反序列化載入耗時 $\le 100\text{ ms}$（實測目標 $\le 50\text{ ms}$）。 |
| **NFR-03** | **零外部相依 (Zero External Dependency)** | 100% 純 Python 3.9+ 原生標準庫（`pickle`, `gzip`）。 |
| **NFR-04** | **全量測試與合規守門** | 執行 `python yscb.py dev test knowledge-db` 達成 100% Passed。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **Pickle 安全性與純本機約束**：`pickle` 二進位快取僅用於本機 `.cache/knowledge-db/` 空間，嚴禁用於不可信之網路傳輸。跨專案與外部導出仍由 `SemanticBundle`（純 JSON）負責。
- > [!TIP]
  > **Protocol 5 二進位協議**：使用 `pickle.HIGHEST_PROTOCOL` 可啟用 Python 3.8+ 引入之 Out-of-band Buffers 與緊湊資料編碼，效率最高。
