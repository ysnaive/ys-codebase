# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：熱路徑效能與增量管線深度優化 (sub_02_hot_path_performance)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Performance  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 [R01_issue_triage.md](../R01_issue_triage.md) 與 [umbrella_overview.md](../umbrella_overview.md) §2，開立 `sub_02_hot_path_performance`，針對查核確認之 7 項 P1 ~ P2 熱路徑效能問題（T-09, T-10, T-11, T-17, T-18, T-19, T-20）進行根因優化。
- **核心目標**：
  - **T-09 (PERF-01, P1)**：`ast` 單檔增量熱修補（`ensure_jit_synced` / `hot_patch_index`）消除多達 5 次全倉目錄走訪（2 次 `scanner.refresh` + 3 次 `_collect_space_files` / `_iter_space_eligible_files`）與重複讀取 YFP2 快照，使增量熱修補回歸 $O(|\text{dirty}|)$。
  - **T-10 (PERF-03, P1)**：`core.contributes.get()` 引入程序內記憶體快取（In-Memory Cache），消除高頻呼叫（如 `locale.t()` 每次觸發 3+ 次）引發之全模組目錄走訪、80+ 次 `stat` 與重複 JSON 反序列化。
  - **T-11 (PERF-04, P1)**：`FileSpaceManager.project_root` 快取化、消除 `_walk_root` 每檔重複 `resolve()` 與 `project_root.resolve()`；`load_spaces(force=False)` 加入已載入守衛並於 `define_ephemeral_space` 維護一致性。
  - **T-17 (PERF-02, P2)**：`knowledge-db` Stage 2 背景向量微批次自癒（`sync_vector_deficit_step`）執行鎖分離（將耗時 ONNX `embed_texts` 移出 `_index_lock` 外以防阻塞前景檢索）與批次持久化節流（支援 `persist: bool = True`，背景迴圈每 $K$ 批或完成時存檔一次，消除每 32 筆重寫整份 `.vectors.bin.gz` 之 I/O 放大）。
  - **T-18 (PERF-05, P2)**：`knowledge-db` `InvertedIndex.patch_incremental` 淘汰舊符號時，收集被移除符號實際分詞出的 `removed_terms` 集合並僅針對該集合清理 Posting（附全表掃描 fallback 防禦），並於 `ASTEngine` / `InvertedIndex` 優先利用 `file_to_symbol_ids` / 路徑映射取代全符號表線性掃描。
  - **T-19 (PERF-06, P2)**：`ast` `bundle_union` 全量建置與呼叫圖提取合一：單次讀檔與語法樹解析同時產出 `(symbols, call_sites, imports)` 並緩存於 `SemanticBundler`，免除 `extract_all_call_sites_and_imports()` 第二輪全倉單執行緒重讀與重解析。
  - **T-20 (PERF-11, P2)**：`dev` `SandboxProvisioner._deploy_target_and_dependency_modules` 先建立有效 `.build.zip` 映射，對已有 build zip 之模組直接解壓部署（解壓失敗則回退 `copytree`），消除「先 `copytree` 再 `rmtree` 後解壓」之雙倍 I/O。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `core.contributes` 快取機制對齊既有 `core.config.ConfigManager` 之 mtime / 記憶體字典快取模式，並提供顯式 `invalidate_cache()` 供 `scan_and_inject()` 與測試重置呼叫。
  - `ast` 增量檔案定位直接復用 `FileSpaceManager.resolve_file_path()` 與 `FingerprintScanner` 既有 YFP2 快照 `entries` / `ASTSnapshot.files_map`，不另建平行檔案索引。
  - `ast` 單次解析復用 `ParserRegistry.parse_file`、`extract_call_sites(symbols=...)` 與 `extract_imports`。
- **邊界排除 (Explicitly Excluded)**：
  - P3 效能項目（T-28 / PERF-07 二進位直接 Pickle、T-29 / PERF-08 `TopologyLinker` 全表重建與 `deque`、T-30 / PERF-09 `uri.resolve` 快取、T-31 ~ T-38）一律歸入 `sub_04_p3_polish`，本子計畫嚴禁越界修改。
  - 不變更 `.bin.gz` 磁碟二進位序列化格式與欄位結構。
- **架構影響範圍**：`core`（`contributes.py`）、`file-space`（`manager.py`）、`ast`（`bundler.py`, `engine.py`）、`knowledge-db`（`pipeline.py`, `retrieval.py`, `service.py`）、`dev`（`testing/sandbox.py`）及各模組對應單元測試與 `docs/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 本子計畫分流為 Full Track（橫跨 `core`、`file-space`、`ast`、`knowledge-db`、`dev` 5 個模組之熱路徑重構，預估修改 > 150 LOC）。
- **[P00:DR-02]**（Q1 定案）`core.contributes.get()` 採 `contributes.meta.json` + `contributes.merged.json` 雙 mtime 守衛搭配 `100ms` 單調時鐘視窗免重掃 `_scan_contributes_inputs()`；`ContributesAggregator.scan_and_inject()` 完成時主動更新/清空記憶體快取，並公開 `contributes.invalidate_cache()`。
- **[P00:DR-03]**（Q2 定案）`FileSpaceManager.project_root` 快取於實例上，`_walk_root` 預先傳入 `proj_root`；當 `not is_symlink and not cfg.follow_symlinks` 時直接使用 `entry_path` 免除逐檔 `resolve()`（`follow_symlinks=True` 時維持 `resolve()` 確保 symlink 子目錄等價）；`load_spaces(self, force: bool = False)` 加入 `self._loaded and not force` 快取守衛，內部唯讀呼叫端改用 `get_all_spaces()`。
- **[P00:DR-04]**（Q3 定案）`sync_vector_deficit_step(batch_size=32, persist: bool = True)` 執行 `_index_lock` 鎖分離（將 `embed_texts` 移出鎖外，寫回時二次確認符號仍存在）；`KnowledgeDBServiceWorker` 每 8 批（256 筆）或距離上次存檔 $\ge 2.0$ 秒持久化一次，並於迴圈結束或中止（`finally`）時若存在未存檔變更強制執行 `flush_vector_index()` / `save_binary()`。
- **[P00:DR-05]**（Q4 定案）`bundle_union`（含 `ProcessPoolExecutor` worker 與序列路徑）於單次讀檔中一併提取 `(symbols, call_sites, imports)` 並緩存於 `SemanticBundler._file_call_sites_cache` 與 `_file_imports_cache`；`extract_all_call_sites_and_imports` 優先命中快取免二次讀檔解析，未命中才 fallback 讀檔。
- **[P00:DR-06]**（T-09 定案）`SemanticBundler` 新增 `_resolve_dirty_files_only` 以 $O(|\text{dirty}|)$ 定位髒檔案（免除 `bundle_dirty_files` 與 `extract_dirty_call_sites_and_imports` 之 `_collect_space_files` 全倉掃描）；`_normalize_space_dirty_paths` 支援預載 `snap_entries_by_space`；`hot_patch_index` 新增 `_cursor_already_consumed: bool = False` 消除與 `ensure_jit_synced` 之巢狀 `_consume_space_diff`，並以差量或快照 entries 更新 `files_map`。
- **[P00:DR-07]**（T-18 & T-20 定案）`InvertedIndex.patch_incremental` 收集移除符號之 `removed_terms` 僅清理對應詞條 Posting（若 tokenizer 異常為空則 fallback 全掃）；`SandboxProvisioner._deploy_target_and_dependency_modules` 先建立 `build_zip_map`，直接自 `.build.zip` 解壓（若解壓失敗則回退 `copytree`）。

---

## 3. 開放議題與確認紀錄

- **全部議題已定案**：Q1→DR-02、Q2→DR-03、Q3→DR-04、Q4→DR-05，開發者輸入 `/auto` 確認推進。以下保留原評估紀錄：

- **Q1（軸二 & 軸三 / T-10 `core.contributes.get()` 快取與 JIT 熱自癒語意）**：
  - **風險**：既有 `contributes.get()` 每次呼叫都會執行 `_scan_contributes_inputs()` 掃描全模組目錄以支援「修改 JSON 後免手動指令即時自癒」；若完全快取而不檢查，同一長駐進程（如 Warm Worker 或單一測試內動態寫入 `contribute.json`）可能讀到舊資料。
  - **推薦 (A)**：採「`contributes.meta.json` + `contributes.merged.json` 雙 mtime 守衛 + 短時窗（`100ms` 單調時鐘）免重掃 `_scan_contributes_inputs()`」，且在 `ContributesAggregator.scan_and_inject()` 完成時主動更新/清空記憶體快取，並公開 `contributes.invalidate_cache()`。如此同一 CLI 指令內數十次 `locale.t()` / `contributes.get()` 僅在首次掃描 1 次，跨指令或超過 100ms 後修改檔案仍能 100% JIT 熱自癒。
  - **(B)**：純進程級快取（一旦載入直到進程結束不重掃 `_scan_contributes_inputs`，僅靠 `scan_and_inject` 失效）。

- **Q2（軸二 & 軸四 / T-11 `FileSpaceManager` 之 `_walk_root` symlink 與 `load_spaces` 快取語意）**：
  - **風險**：① 原報告建議 `_walk_root` 對 `not is_symlink` 的檔案跳過 `entry_path.resolve()`，但查核（R01）發現當 `follow_symlinks=True` 且**父目錄**是 symlink 時，子檔案自身 `entry.is_symlink()` 為 `False`，跳過 `resolve()` 會使路徑與現行行為不等價；② `load_spaces()` 加快取後，外部直接呼叫 `load_spaces()` 原意可能是強制重載。
  - **推薦 (A)**：
    1. `project_root` 快取於 `FileSpaceManager` 實例上，並在進入 `_walk_root` 前預先解析一次 `proj_root` 傳入（消除每檔重複解析 `project_root`）；對檔案路徑，當 `not is_symlink and not cfg.follow_symlinks`（預設 `follow_symlinks=False`）時直接使用 `entry_path` 免除 `resolve()`，若 `cfg.follow_symlinks=True` 則維持 `resolve()` 確保 symlink 子目錄語意 100% 等價。
    2. `load_spaces(self, force: bool = False)` 預設若 `self._loaded and not force` 直接回傳快取副本；內部所有僅需讀取空間之呼叫端統一改用 `get_all_spaces()`，而 `define_ephemeral_space()` 會同步更新 `self._spaces`。
  - **(B)**：`load_spaces()` 維持無條件重載，僅將 `ast` / `knowledge-db` 內部誤用 `load_spaces()` 之處改為 `get_all_spaces()`。

- **Q3（軸三 / T-17 背景向量微批次自癒之持久化頻率與中止保護）**：
  - **風險**：將每批（32 筆）存檔改為每 $K$ 批存檔後，若背景 Worker 在中途收到 `_stop_event` 或發生異常退出，未存檔之批次會在記憶體中遺失。
  - **推薦 (A)**：`sync_vector_deficit_step(batch_size=32, persist: bool = True)` 預設維持 `persist=True`（單獨呼叫時行為 100% 相容）；`KnowledgeDBServiceWorker` 迴圈內設為每 **8 批（256 個符號）或距離上次存檔 $\ge 2.0$ 秒** 傳入 `persist=True`，且在迴圈結束、`finally` 區塊或 `_stop_event` 觸發退出前，若有任何未持久化之變更（`dirty_unpersisted`），強制補執行一次 `save_binary()`。同時將 `embed_texts()` 移出 `_index_lock` 外，寫回時二次確認符號仍存在於 `idx.symbols`。
  - **(B)**：維持每批存檔，僅做 `_index_lock` 鎖分離（將 `embed_texts` 移出鎖外）。

- **Q4（軸四 / T-19 `bundle_union` 單次讀檔解析之多進程跨 IPC 序列化取捨）**：
  - **風險**：`bundle_union` 在檔案數 $\ge 24$ 時使用 `ProcessPoolExecutor`。若子進程一併提取 `call_sites` 與 `imports` 並透過 IPC 傳回主進程，需序列化 `SymbolCallSite.to_dict()`。
  - **推薦 (A)**：Worker 與序列路徑在單次讀檔中一併提取 `(symbols, call_sites, imports)`（對 Tree-sitter / Python AST 而言，直接將同一次讀出的 `content` 與 `symbols` 傳入 `extract_call_sites` 與 `extract_imports`），並緩存於 `SemanticBundler._file_call_sites_cache` 與 `_file_imports_cache`；`extract_all_call_sites_and_imports()` 若檢測到快取已覆蓋目標檔案則直接讀取快取免重讀磁碟，快取未命中之檔案才 fallback 讀檔解析。
  - **(B)**：僅先消除 `extract_all_call_sites_and_imports` 重複讀檔，暫不改動 `ProcessPoolExecutor` worker 回傳結構。

