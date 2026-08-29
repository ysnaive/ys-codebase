# 需求規格說明書 (Requirements Specification)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **JIT 嗅探 100% 完整清冊保證** | `check_invalidation()` 必須完整掃描全專案空間聯集檔案，嚴禁提早中斷返回殘缺字典；精準輸出 `(is_dirty, scanned_count, reason, full_files_map, dirty_diff)`，其中 `dirty_diff` 包含 `added`, `modified`, `deleted` 檔案集合，`full_files_map` 100% 包含所有存續檔案之 `(mtime, size)` 快照。 | P0 | [P00:DR-01] |
| **FR-02** | **JIT 走訪 Win32/NTFS 效能優化** | 檔案遍歷採用 `os.scandir()` 遞迴走訪，直接自 `DirEntry.stat()` 提取 `st_mtime` 與 `st_size`，結合前置排除路徑剪枝，減少 50% 以上之系統呼叫開銷。 | P1 | [P00:DR-01] |
| **FR-03** | **單檔符號記憶體快取 (Per-File Cache)** | 在 `SemanticBundler` / `KnowledgeEngine` 維護 `_file_symbols_cache: Dict[str, List[UnifiedSymbol]]` (canonical path -> symbols)。熱重載時僅對 `added` 與 `modified` 檔案重新呼叫 AST Parser，其餘檔案 100% 零 I/O 復用；`deleted` 檔案即時自快取中剔除。 | P0 | [P00:DR-02] |
| **FR-04** | **倒排索引差量打補丁 (Differential Patching)** | `InvertedIndex` 實作 `patch_incremental(dirty_canonical_keys, new_symbols_by_file, tokenizer)`：精確拔除異動/刪除檔案舊符號對應之 Postings，扣減 `field_total_lengths` 與 `doc_count`；對新符號執行分詞並追加 Postings，動態重新計算 `field_avgdl`。 | P0 | [P00:DR-03] |
| **FR-05** | **快速持久化與端到端極速熱自愈** | 倒排索引二進位持久化時採用 `compresslevel=1` 快速壓縮落盤；`KnowledgeEngine` 熱自愈管線優先以差量模式修補記憶體 `_unified_index`，並持久化 100% 完整清冊之 `unified.meta.bin` 與 `unified.index.bin.gz`；單檔熱自愈耗時目標 $\le 100\text{ms}$。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **檔案被直接刪除 (Deleted File)** | `check_invalidation()` 比對 `cached_map` 找出消失的 canonical keys 並標記為 `deleted`；`patch_incremental()` 將該檔案的所有符號與 Posting 清理乾淨，`_file_symbols_cache` 移除該檔案。 |
| **EC-02** | **變更檔案未產出符號 (Empty / Non-symbol File)** | 檔案被清空或僅包含被忽略的註解，AST Parser 返回空清單 `[]`；差量修補正確清理舊符號，不引發例外。 |
| **EC-03** | **快照遺失、損毀或 `force=True`** | 當 `unified.meta.bin` / `unified.index.bin.gz` 遺失、二進位格式校驗失敗或呼叫者傳入 `force=True` 時，自動優雅降級為全量建置 (Full Rebuild) 並重建完整符號快取與快照。 |
| **EC-04** | **多空間重疊歸屬與 Space 元數據保持** | 增量重新解析單檔時，正確自 `SpaceManager` 判定該檔案所命中的多個空間清單，注入 `UnifiedSymbol.metadata["spaces"]`，確保與全量打包邏輯 100% 一致。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 (Latency) | 150 檔規模下，單檔微小修改觸發之端到端熱自愈檢索延遲 $\le 100\text{ms}$（相較於全量 2,500ms 提速 25 倍以上）。 |
| **NFR-02** | 介面相容性 (Compatibility) | `KnowledgeEngine.search`、`KnowledgeEngine.build_unified_index` 等 Public API 簽名與回傳型態 100% 向後相容。 |
| **NFR-03** | 記憶體與資源約束 | 符號快取為純記憶體物件參照，不額外產生巨型磁碟暫存檔；`unified.meta.bin` 儲存開銷維持在數十 KB 內。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 快照截斷危害**：`check_invalidation()` 回傳之 `current_files` 若不完整，會破壞二進位快照的一致性。任何走訪流程必須保證收集 100% 存續檔案清冊。
- **`[!NOTE]` Postings 清理效率**：在倒排索引移除舊 Postings 時，若以線性過濾每個 term 的 list，因 Python 內部 list comprehension 速度極快且單檔 doc_id 數量有限（通常 < 50），使用 `doc_id` 集合過濾可於數毫秒內完成。
- **`[!NOTE]` 檔案路徑鍵一致性**：全系統必須統一採用 `str(Path(p).resolve()).replace("\\", "/")` 作為 canonical key，避免 Windows 大小寫或斜線差異導致快取漏失。
