# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 計畫類型：Architecture Refactor / Performance Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「開始前先調研，於 knowledge db 模組中，原建立資料庫索引後，是儲存於 cache (因體積太大)，但現已有較為完善的壓縮機制，是否應考慮改為儲存在 storage ? 但這樣會不會導致 git 容易衝突? 有沒有神麼好的方案能異地同步更新? (現在最怕 A 開發者新功能，B 開發者沒及時調用索引重建導致搜尋結果不佳)」
  2. 「那如果我們建檔不要分空間，直接作連集會不會更好?」
- **核心目標**：
  1. **全域聯集單一索引架構 (Unified Index with Space Tags)**：
     - 放棄過往對各 Space 獨立割裂建檔的做法，改為以全專案空間聯集 (Union Scope) 進行檔案實體路徑去重，**所有檔案 100% 僅讀取與 AST 解析一次**。
     - 符號結構 (`UnifiedSymbol`) 與倒排索引 (`Posting`) 支援多空間標籤（`spaces: List[str]`），天然杜絕重複符號與重複搜尋結果。
     - 建立單一 `unified.index.bin.gz`，使 BM25 的 `doc_count`、IDF 與 `avgdl` 統計指標達到數學級精準。
     - 查詢時若指定 `--space`，以 O(1) 標籤過濾支援，效能大幅提升。
  2. **JIT 查詢時智能變更感知與熱自愈 (Just-In-Time Invalidation & Auto-Healing)**：
     - 在每次 `search` 檢索入口，以超低開銷（< 3ms，基於 mtime / size 比對）快速嗅探全域來源檔案。
     - 若檢測到任何檔案新增、修改或刪除（如開發者剛 pull 代碼），自動在背景執行增量/局部熱自愈並同步快取，同時於 `stderr` 輸出直觀進度提示（例如 `[knowledge-db:auto-rebuild] ...`），隨後立即回傳 100% 精準的最新搜尋結果。
     - 若檔案無變更，直接短路（Fast Short-Circuit）瞬間載入快取索引。
  3. **儲存空間選型與 Git 純淨保證**：
     - 依據 [`R01 調研結論`](../R01_index_storage_and_sync_strategy.md)，索引檔案剛性保留在 `cache://knowledge-db/`，絕不寫入 `storage://`，徹底杜絕二進位 Git 衝突與版本庫膨脹。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁將二進位索引檔（`.index.bin.gz`）寫入 `storage://` 或納入 Git 追蹤。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 索引維持存儲於 `cache://`，以 JIT 查詢熱自愈取代將二進位檔案加入 Git 的做法 ([R01 調研結論](../R01_index_storage_and_sync_strategy.md))。
- **[P00:DR-02]** 索引建置架構全面升級為「全域聯集單一索引 + 空間標籤化 (Unified Index with Space Tags)」，根絕重複 AST 解析與重複搜尋結果，並校正 BM25 統計模型。
- **[P00:DR-03]** 查詢入口在觸發背景熱自愈時，於 `stderr` 輸出提示訊息以提供即時回饋。

---

## 3. 開放議題與確認紀錄

- [x] **索引儲存位置**：維持 `cache://`。
- [x] **空間建置架構**：採全域聯集去重建檔 + 符號空間標籤。
- [x] **JIT 自愈回饋**：於 `stderr` 輸出簡明耗時提示。

