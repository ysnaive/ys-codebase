# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (100% 清冊) ➔ `scanner.py:check_invalidation`，FR-02 (scandir) ➔ `DirectoryScanner` 遍歷優化，FR-03 (符號快取) ➔ `bundler.py:_file_symbols_cache`，FR-04 (差量修補) ➔ `retrieval.py:patch_incremental`，FR-05 (熱自愈與極速持久化) ➔ `engine.py:_hot_patch_unified_index`。
- [x] **邊界防護**：EC-01 (刪除檔案) ➔ `deleted` 差量與拔除，EC-02 (空檔案) ➔ 空符號容錯，EC-03 (損毀降級) ➔ Full Rebuild 回退，EC-04 (空間歸屬) ➔ 多空間元數據一致性。
- [x] **依賴純淨**：純標準庫 (`os.scandir`, `gzip`, `struct`, `collections`)，無外部新增依賴，NFR-01 耗時目標 $\le 100\text{ms}$。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 1** | `docs/knowledge-db/README.md` | Modify | 補充細粒度增量熱重載與 JIT 變更嗅探機制說明。 |
| **維度 2** | `docs/knowledge-db/incremental_hot_reload.md` | New | 建立增量熱自愈架構專題手冊（含循序圖、差量修補演算法與效能測試數據）。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在一次操作中同時進行了「修改 1 檔、新增 1 檔、刪除 1 檔」，差量修補能否保證倒排索引中的 `doc_count` 與 `field_avgdl` 數值精確無漂移？  
> 💡 **防護解法**：在 `patch_incremental()` 中，拔除舊符號時依據舊符號的實際欄位長度精準扣減 `self.field_total_lengths`，加入新符號時累加新欄位長度，`self.doc_count` 嚴格等於當前符號池 `len(self.symbols)`，最後以 `field_total_lengths[f] / max(1, doc_count)` 重算 `field_avgdl`，數值 100% 與全量重建一致。

> ❓ **尖銳問題 2**：若進程在熱修補保存 `unified.index.bin.gz` 或 `unified.meta.bin` 途中異常中斷，是否會導致下次啟動狀態損毀？  
> 💡 **防護解法**：`BinarySnapshotManager.save()` 與 `InvertedIndex.save_binary()` 均採用原子寫入機制（先寫入同目錄暫存檔 `mkstemp`，關閉後透過 `os.replace` 原子覆蓋），絕不產生中途殘缺檔案；若兩者其一損毀，`engine.py` 內建校驗安全回退至 Full Rebuild。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `scanner.py` 定義 `ScanDiffDetail`，重構 `check_invalidation()` 採用 `os.scandir` 完整掃描全庫，杜絕提早中斷，輸出 100% 完整 `full_files_map` 與差量明細。
- [ ] **TASK-02**：在 `bundler.py` 為 `SemanticBundler` 引入 `_file_symbols_cache`，實作 `bundle_dirty_files()` 差量解析與快取更新。
- [ ] **TASK-03**：在 `retrieval.py` 實作 `InvertedIndex.patch_incremental()`，並優化 `save_binary()` 支援 `compresslevel=1` 快速壓縮。
- [ ] **TASK-04**：在 `engine.py` 整合增量熱自愈管線 `_hot_patch_unified_index()`，確保 `search()` 與 `build_unified_index()` 剛性持久化完整快照。
- [ ] **TASK-05**：編寫單元、整合、邊界與效能基準測試 `tests/test_incremental_hot_reload.py`，全量執行驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿測試計畫**：確認 `P06_test_plan.md` 狀態更新為 `Confirmed`，涵蓋 FT-01~04、ET-01~03、RT-01 與 PT-01。
- **[P04:DR-02] 記憶體熱優先原則**：熱更新時以記憶體索引就緒為最高優先，落盤操作不阻礙查詢即時響應。
