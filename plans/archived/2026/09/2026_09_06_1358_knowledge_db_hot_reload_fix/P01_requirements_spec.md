# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 熱重載新增與修改檔案靜默 no-op 修復 (Hot Reload Silent No-op Fix)  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立標準計畫)  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 倒排索引磁碟懶加載 | `IndexingPipeline.hot_patch_unified_index` 在 `self._unified_index is None` 時，若 `bin_file.exists()` 存在，必須以 `InvertedIndex.load_binary(bin_file)` 載入記憶體後再進行熱補丁，不得無條件返回 `False`。 | P0 | [P00:DR-01] |
| **FR-02** | Daemon 熱修補失敗剛性兜底 | 在 `HotReloadServer._execute_debounced_patch` 與 `_run_startup_check` 中，若 `pipeline.hot_patch_unified_index` 回傳 `False` 或遭遇例外，必須剛性兜底調用 `pipeline.build_unified_index(force=True, current_files=full_files_map)` 完成全量自癒重建。 | P0 | [P00:DR-02] |
| **FR-03** | 熱修補日誌與可觀測性強化 | 在 `_execute_debounced_patch` 中，詳細記錄嗅探到之 diff 明細（added/modified/deleted 數量）；若觸發全量重建兜底，明確於日誌輸出觸發原因。 | P1 | [P00:DR-03] |
| **FR-04** | 物理級 SSOT (廢除 JSON 指紋) | 徹底廢除 `fingerprints.json` 實體檔案，移除 JSON 指紋相關測試；SDK 各介面 (`engine.status()`, `engine.scan()`, `FingerprintScanner`) 統一以 `unified.meta.bin` 為唯一快照來源。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 磁碟快取二進位檔損毀 | 若 `bin_file` 損毀或反序列化失敗，記錄警告日誌並回退回傳 `HotPatchResult(False)`，進而觸發 FR-02 之全量自癒重建。 |
| **EC-02** | 磁碟無任何索引快照 | 若 `bin_file` 不存在，`self._unified_index` 維持 None 並回傳 `HotPatchResult(False)`，觸發全量初始建置。 |
| **EC-03** | 掃描後實質無語意變更 | 若 `diff_detail.has_changes` 為 False，維持輸出 `No semantic changes found after scan`，不進行重工寫檔。 |
| **EC-04** | unified.meta.bin 遺失或毀損 | 若二進位快照不存在或損毀，`check_invalidation` 與 `scan` 自動視為全量變更 (all added) 並自癒寫回。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相依純淨性 | 0 新增第三方 pip 依賴、0 跨模組依賴引進。 |
| **NFR-02** | 效能與延遲 | 倒排索引磁碟二進位還原耗時 $\le 50\text{ms}$，全量兜底重建僅在熱修補失敗時單次觸發。 |
| **NFR-03** | 既有測試守門 | `knowledge-db` 全模組單元與邏輯測試 100% 通過（無回歸）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]`** 原先的 `fingerprints.json` 已徹底廢除（拍板路線 2），所有狀態完全收斂至 `unified.meta.bin`（BinarySnapshotManager），達成物理級單一真理來源 (SSOT)。
- **`[!IMPORTANT]`** CLI 前台於探測到背景 Daemon 在線時，會跳過 JIT 檢查直接使用磁碟二進位索引；因此背景 Daemon 必須 100% 保證磁碟上的 `unified.index.bin.gz` 與 `unified.meta.bin` 處於最新狀態。
