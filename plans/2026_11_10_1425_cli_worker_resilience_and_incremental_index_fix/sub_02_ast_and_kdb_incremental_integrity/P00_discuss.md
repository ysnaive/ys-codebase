# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 與 Knowledge-DB 增量更新一致性與鎖競爭修復  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：深度評估並修復 `ast` 與 `knowledge-db` 增量更新、快取失效與鎖競爭的確定性問題。
- **核心目標**：修復 `core.space` 組態變更吞沒刪除清單、`GrammarProvisioner` 跨進程鎖失效、`ASTEngine` 水合圖譜不落盤與並發字典變異崩潰、`Knowledge-DB` 同行號改內文舊向量殘留、行號平移重複推論、倒排幽靈詞、前景/背景禮讓殘缺向量 RRF 污染及鎖內慢速推論阻塞。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `hashlib.blake2b`、`core.platform.lock.InterProcessLock`、`ast_engine.io_utils.compute_project_relpath` 與既有 `atomic_save_gzip_pickle`。
- **邊界排除 (Explicitly Excluded)**：不變動 `UnifiedSymbol.compute_id` 雜湊公式、不物理移除舊軌 `TopologyLinker`（僅修補刪檔全域模糊誤連），維持二進位快取向下相容讀取。
- **架構影響範圍**：`core`（`core/space/scanner.py`）、`ast`（`provisioner.py`、`engine.py`、`bundler.py`、`schema.py`、`scripts/cli.py`）、`knowledge-db`（`embedding.py`、`pipeline.py`、`retrieval.py`、`hybrid.py`、`engine.py`、`io_utils.py`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `SpaceScanner.diff` 組態變更刪檔保留與 `GrammarProvisioner` 鎖修正**：`SpaceScanner.diff()` 保存原 `prev_from_gen` 並在 `config_hash` 變更時將所有 `fp.is_deleted` 納入 `detail.deleted`；`GrammarProvisioner._provision_lock()` 改傳正確參數 `timeout_sec=60.0` 並驗證取鎖成功布林值，補齊 `--retries 1 --timeout 5` 與 `.cache/ast/` 負快取持久化。
- **[P00:DR-02] `ASTEngine` 圖譜落盤、CoW 快照與交易鎖完整性**：`get_workspace_graph()` 水合新建 4-Pass `workspace_graph` 後若快照未過期即寫回 `unified.graph.bin.gz`；`hot_patch_index` 以 Copy-on-Write 建立新 `ASTSnapshot` 字典再原子替換指標，擴大 `.ast_index.lock` 涵蓋 RMW 同步週期並校驗雙檔 `ast_generation` 一致性；補齊 `schema_version` + `ast_config_hash` 快取指紋與受限空間刪檔偵測，並阻斷已刪符號無匯入表之全域模糊誤連。
- **[P00:DR-03] `Knowledge-DB` 向量文本雜湊追蹤、行號平移向量重用與倒排世代校驗**：於 `VectorIndex` 維護 `doc_text_hashes`（`blake2b` 8-byte hex），同行號內文修改時必觸發向量重算，而上方插入空行導致行號平移但 `(file_path, name, kind, text_hash)` 相同時直接 O(1) 遷移重用既有向量（免重跑 ONNX）；修正 `_align_index_symbols_with_ast_snapshot` 僅在世代一致時共享參照，且 `InvertedIndex.patch_incremental` 以歷史 `doc_lengths` 精確扣減欄位總長。
- **[P00:DR-04] `Knowledge-DB` 鎖外推論、禮讓降級與規範路徑隔離**：`EmbeddingService.reconfigure_model` 於參數未變時無鎖短路返回並移除拔除 `local_files_only=True` 之危險回退；將 ONNX 批次推論移出 `_index_lock`；當背景處於 `yielded_to_foreground` 且仍有向量缺口時強制降級 `lexical_bm25`；將 `bundle_dirty_files` 與 `_collect_all_dirty_files` 中位於 `project_root` 內的絕對路徑正規化為專案相對路徑，補齊 `kdb_config_hash`（含 `indexed_spaces` 與 `space_weights`）動態刷新，並消除 `HybridSearchEngine.search()` 共享欄位無鎖突變。

---

## 3. 開放議題與確認紀錄

- 全部決策均為確定性修復，無開放待決議題。
