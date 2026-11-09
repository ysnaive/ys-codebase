# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_knowledge_db_pipeline_and_sqlite_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將全倉深度審計報告（[`R01_full_codebase_deep_audit_report.md`](../R01_full_codebase_deep_audit_report.md)）中針對 `Unit 05`（`module:knowledge-db` 引擎、`IndexingPipeline`、Schema、Config、Providers、IO Utils）與 `Unit 06`（檢索、`HybridSearchEngine`、`EmbeddingService`、`ServiceWorker`、`hook.ast.py`）檢出之全部 **14 項問題（`KDB-AUD-01` ~ `KDB-AUD-14`：1 P0, 6 P1, 5 P2, 2 P3）**，以及架構與演進技術債報告（[`R02_architecture_and_evolutionary_debt_audit.md`](../R02_architecture_and_evolutionary_debt_audit.md)）中針對 `module:knowledge-db` 檢出之 **11 項架構問題（`ARCH-KDB-01` ~ `ARCH-KDB-11`）與 Mode A 手術 `S2`** 全量轉化為 `sub_03` 實作與驗證計畫。
- **核心目標**：
  1. **根除 1 項 P0 C# `partial class` 跨檔熱修補永久抹除主檔案非 partial 符號缺陷（`KDB-AUD-01`）**：
     - 修復 [`knowledge-db/knowledge_db/pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 之 `hot_patch_unified_index`：先完成 `dirty_keys` 的跨檔 `partial class` 主檔案擴展，再執行單次 `ast_snap.symbols` 遍歷收集所有屬於擴展後 `dirty_keys` 之符號與文件，防止 `_evict_dirty_file_artifacts` 永久抹除主檔案中未變更的非 partial 符號。
  2. **落實 Mode A 手術 `S2`：解除前景/背景「互讓死鎖悖論 (Mutual Yield Paradox)」與收斂單一增量熱修補管線（`ARCH-KDB-01` ~ `ARCH-KDB-11`）**：
     - 解決 `ARCH-KDB-01` 前景與背景互讓悖論：當背景 `KnowledgeDBServiceWorker` Stage 2 偵測到 `foreground_active` 禮讓前景時，先將記憶體中已計算之髒向量透過 `flush_vector_index()` 持久化，並標記 `phase="yielded_to_foreground"`（而非 `"idle"`）；同時在 `_ensure_indices_loaded` 與 `_resolve_vector_availability_with_worker_tolerance` 中保護記憶體內較新的向量不被舊磁碟快照 `force_reload=True` 洗掉。
     - 解決 `ARCH-KDB-02` 三處重複增量同步迴圈：於 `IndexingPipeline` 抽離共用方法 `sync_incremental_changes`（別名 `sync_lexical_index`），統一收斂 `pipeline.py`、`service.py` 與 `scripts/hook.core.py` 的「游標消費 $\to$ `hot_patch_unified_index` $\to$ 失敗回退 `build_unified_index`」邏輯。
     - 解決 `ARCH-KDB-03` ~ `ARCH-KDB-08`：對齊 `service.py` Cell State 快取鍵 `kdb.worker_state`、確保 `get_engine()` 僅在模型名稱變更時重置 `_model`、強化 `io_utils.py` `atomic_save_gzip_pickle` 的 `finally` `.tmp` 清理，以及收斂 `retrieval.py` 與 `pipeline.py` 的檔案級分數聚合邏輯（`aggregate_ranked_symbol_hits`）。
  3. **修復 6 項 P1 常駐空閒漏增量同步、`build_unified_index` 短路、跨多世代 `acked_ast_generation` 跳號、`hook.ast.py` 漏讀專案級貢獻、切片註解吞噬與混合檢索過早截斷（`KDB-AUD-02` ~ `KDB-AUD-07`）**。
  4. **收斂 5 項 P2 組態互斥鍵、清理鎖與狀態對齊、空向量索引維度還原、BM25 聚合排序截斷、macOS 路徑正規化（`KDB-AUD-08` ~ `KDB-AUD-12`）及 2 項 P3 權重字典快取與零模型載入維度查表優化（`KDB-AUD-13`, `KDB-AUD-14`）**。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `IndexingPipeline`、`HybridSearchEngine`、`BM25Engine`、`VectorIndex` 與 `core.contributes`，不新增外部套件。
- **邊界排除 (Explicitly Excluded)**：不修改 Binary Index 磁碟檔案魔數與公開查詢 CLI 參數；遵循 Mode B 公開相容性保留既有測試與公開方法簽名。
- **架構影響範圍**：`ys_codebase/source/knowledge-db/knowledge_db/{pipeline,engine,hybrid,retrieval,embedding,formatter,selector,config,schema,service,io_utils}.py`、`knowledge-db/scripts/{hook.ast,hook.core}.py` 及 `knowledge-db/tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `hot_patch_unified_index` 兩階段 `dirty_keys` 閉包計算與世代差值守門 (`KDB-AUD-01`, `KDB-AUD-04`)**：先掃描找出所有涉及 `partial class` 或跨檔合併之關聯主檔並擴展 `dirty_keys` 至不動點，再以閉包後之 `dirty_keys` 收集 `dirty_symbols`；若 `ast_generation - acked_ast_generation > 1`，自動比對全量符號差異併入 `dirty_keys`，禁止盲目跳號 ACK。
- **[P00:DR-02] `UniversalRedundancyFilter.purify_lines` 詞法狀態機化 (`KDB-AUD-06`)**：掃描單行時先跳過引號字串常數（`"..."` / `'...'`）與單行註解（`#` / `//`），僅在非字串區段匹配真正的 `/*` 區塊註解起點與同列 `*/` 閉合，杜絕 `"glob('src/*')"` 吞噬後續切片。
- **[P00:DR-03] Mode A 手術 `S2` 互讓死鎖悖論防禦與單一增量同步入口 (`ARCH-KDB-01` ~ `ARCH-KDB-08`)**：Stage 2 禮讓前景時先 `flush_vector_index()` 並標記 `phase="yielded_to_foreground"`，同時於 `_ensure_indices_loaded` 防止以陳舊磁碟向量覆寫記憶體中較新之髒向量；由 `IndexingPipeline.sync_incremental_changes` 統一三處增量同步迴圈。

---

## 3. 開放議題與確認紀錄

- 全部 14 項 `KDB-AUD-01` ~ `KDB-AUD-14` 與 11 項 `ARCH-KDB-01` ~ `ARCH-KDB-11`（含手術 `S2`）修復規格均已確認定案並實作完畢。
