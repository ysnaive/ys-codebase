# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 熱重載新增與修改檔案靜默 no-op 修復 (Hot Reload Silent No-op Fix)  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立標準計畫)  
> 狀態：Completed  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：下游專案回報缺陷：在 `source` 空間所涵蓋且 daemon 正在監看的目錄新增 `.mjs` 檔案後，daemon 有偵測到該檔（450 → 451）並觸發 hot patch，但回報 `Patched: False`，索引未更新，6 分鐘內 30 次 `knowledge-db search` 全部 `total: 0`。
- **核心目標**：
  1. 根絕 HotReloadServer / IndexingPipeline 熱修補靜默失效問題，確保在服務冷啟動（記憶體無快取）情況下，新增檔案與修改檔案均能即時寫入倒排索引、調用圖譜與向量特徵快取。
  2. 補齊 `pipeline.hot_patch_unified_index` 於 `_unified_index is None` 時的磁碟快取懶加載 (`load_binary`) 機制。
  3. 實作 Daemon 端 `_execute_debounced_patch` 與 `_run_startup_check` 熱修補失敗時的剛性全量重建兜底 (`build_unified_index`)，徹底消除靜默未修補。
  4. 強化可觀測性日誌，詳細記錄變更檔案、修補狀態與降級原因。
  5. 於單元測試套件驗證懶加載與兜底機制，維持全生態系既有測試 100% 通過。
- **邊界排除 (Explicitly Excluded)**：
  - 排除新增端到端整合測試（依使用者指示，不額外編寫跨進程實體整合測試，聚焦單元邏輯與既有測試回歸）。
  - 不變更 `contributes.json` 或各空間定義與語意 URI 協議。
  - 不異動前台 CLI 旁路 JIT 機制的基本合約（僅需確保背景 Daemon 產物始終新鮮一致）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 磁碟二進位倒排索引懶加載 (Lazy Load Inverted Index)**：在 `IndexingPipeline.hot_patch_unified_index` 中，當 `self._unified_index is None` 時，若 `bin_file.exists()` 存在，強制使用 `InvertedIndex.load_binary(bin_file)` 載入記憶體後再行打補丁，與 `_call_graph_index` 及 `vector_index` 現有磁碟還原邏輯一致，不再無條件短路回傳 `False`。
- **[P00:DR-02] Daemon 熱修補失敗之雙重兜底機制 (Fallback Full Rebuild Guard)**：在 `HotReloadServer._execute_debounced_patch` 與 `_run_startup_check` 中，若 `pipeline.hot_patch_unified_index` 因任何原因回傳 `False` 或拋出異常，強制呼叫 `pipeline.build_unified_index(force=True, current_files=full_files_map)` 進行全量自癒重建，徹底杜絕磁碟快照過期而前台持續命中舊資料之盲區。
- **[P00:DR-03] 日誌可觀測性強化 (Enhanced Observability)**：詳細記錄 debounced patch 掃描到的 added/modified/deleted 檔案清單與原因，若發生降級或全量重建，於 daemon 日誌明確打印原因 (`reason`)。
- **[P00:DR-04] 測試邊界約束 (Testing Scope Boundary)**：依據使用者明確指示，不增加端到端整合測試，專注於 `IndexingPipeline` 磁碟懶加載與 `HotReloadServer` 兜底邏輯之單元測試，並確保既有 148+ 測試案例 100% 通過。
- **[P00:DR-05] 路線 2：物理級 SSOT (Abolish JSON Fingerprints, unified.meta.bin as SSOT)**：徹底廢除 `fingerprints.json` 實體檔案與序列化，移除 JSON 指紋相關過時測試；SDK（包含 `engine.status()`、`engine.scan()`、`FingerprintScanner` 等）全面改以 `unified.meta.bin` (`BinarySnapshotManager`) 作為單一真理來源。

---

## 3. 開放議題與確認紀錄

- [x] 是否影響現有 Public API 簽名？（否，完全向下相容內部邏輯修補與二進位真理來源整合）
- [x] 是否牽涉跨模組依賴？（否，僅限 `source/knowledge-db` 模組內部）
- [x] 是否徹底廢除 JSON 指紋？（是，已拍板路線 2 物理級 SSOT）
- [x] Phase 1~3 需求規格已更新等待確認。
