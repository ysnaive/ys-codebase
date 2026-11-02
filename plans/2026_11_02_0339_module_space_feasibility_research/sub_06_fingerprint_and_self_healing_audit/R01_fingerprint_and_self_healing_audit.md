# 全生態系指紋追蹤與熱自癒機制完善度審視 (Ecosystem Fingerprint & Self-Healing Audit)

> 調研主題：全生態系指紋快取與熱自癒機制完善度審視調研
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research
> 建立日期：2026-11-02
> 調研狀態：Concluded
> 模型：Gemini 4 Argon (Low)
> 模板版本：v1.2

---

## 1. 背景與調研目標 (Background & Objectives)

隨 `sub_01` ~ `sub_05` 完成 `core` 宣告式 Contributes 合併策略、`file-space` 模組抽離與 `knowledge-db` 空間委派解耦後，YS-Codebase 母倉已形成涵蓋 **`core` (Contributes / URI / Locale / Installer)**、**`file-space` (YFP2 二進位指紋快照 / CursorStore / Watcher)**、**`knowledge-db` (Stage 1 AST/BM25 熱修補 / Stage 2 向量漸進自癒)**、**`agents-workflow` (三階段編譯器 / Stage 0 指紋短路 / Hook 自癒發布)** 與 **`server` (ModulesWatcher / Master-Worker 熱重載)** 的多層次指紋與自癒體系。

本調研（`sub_06`）旨在透過第一手源碼靜態審計與原型 ③ Devil's Advocate 反向事實查驗，全面體檢當前五大核心模組在「指紋計算完整性（有無漏追蹤輸入導致 Cache Poisoning 或假陽性短路）」、「跨進程/常駐 Worker 快取一致性」及「增量自癒邊界（競態、刪除、行號不變修改）」是否存在潛在死角，並直接轉入 `/auto` 落地修復。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 現有五大模組指紋與自癒運作閉環盤點

| 模組層級 | 指紋 / 快照載體 | 髒檢查與自癒觸發點 | 核心實作座標 |
| :--- | :--- | :--- | :--- |
| **`core`** | `cache://core/contributes.meta.json` (`mtime`, `size`) + `cache://<target>/contributes.merged.json` | `contributes.get()` 呼叫 `_is_contributes_dirty()` 比對 `yscb.config.json`、`module://*/contributes/*.json`、`config://*/contribute.json` 與語系檔；髒時自動觸發 `ContributesAggregator.scan_and_inject()` 重算。 | `ys_codebase/source/core/core/contributes.py:269-362` |
| **`file-space`** | `cache://file-space/snapshots/<space>.yfp2.bin`、`unified.yfp2.bin` (Blake2b-160 Merkle Root + Tombstone) 與 `cursors/<consumer>.json` | `FingerprintScanner` 支援 4 種 `HashPolicy` 與 10ms Racy-Clean 防護；`FileSpaceWatcherServiceWorker` 經 500ms 防抖與 `.yscb.lock` 避讓後更新快照並廣播 `on_file_space_changed`。 | `ys_codebase/source/file-space/file_space/scanner.py:534-805`、`service.py:183-429` |
| **`knowledge-db`** | `file-space` Consumer Cursor (`knowledge-db.json`) + `index.meta.json` + 向量集差集 (`sym_ids - vec_ids`) | `hook.file-space.py` 喚醒 `KnowledgeDBServiceWorker` 執行 Stage 1（AST/BM25/Graph 局部熱修補）與 Stage 2（32 筆微批次向量補齊）；前台搜尋透過 `_ensure_jit_index_ready` 執行 JIT 修補或超時降級。 | `ys_codebase/source/knowledge-db/knowledge_db/service.py:357-495`、`pipeline.py:960-1099` |
| **`agents-workflow`** | `cache://agents-workflow/release_manifest.json` (`source_fingerprint`) + `source_sha1_cache.json` | `hook.core.py` 於 `on_reload` 與 `on_pre_cli_dispatch` 觸發 `ReleasePublisher.release_all()`；Stage 0 `_check_short_circuit()` 比對來源指紋與目標檔案存在性，吻合則 0-I/O 短路。 | `ys_codebase/source/agents-workflow/agents_workflow/publisher.py:120-501`、`hooks/hook.core.py:29-61` |
| **`server`** | `ModulesWatcher` 記憶體快照（每秒輪詢 `.modules/` 下 `.py/.json/.zip/.dist-info` 之 `mtime`） | 避開 `.cache/.yscb.lock` 交易期；`core/server` 異動觸發 `MasterSupervisor.restart_server()`，其餘模組異動觸發 `restart_worker()`。 | `ys_codebase/source/server/server/watcher.py:37-138`、`master.py:387-457` |

---

### 2.2 審計發現之實質漏洞與 Devil's Advocate 反向查驗結論

經原型 ① 盲眼探索與原型 ③ Devil's Advocate 反向事實查驗（反推真實性與修復副作用），確認如下：

#### 🔴 P1（高嚴重度：導致功能性漏自癒、靜默遺失變更或索引陳舊）

1. **`[F-01]` `knowledge-db` 符號行號不變之內容修改逃逸 Stage 2 向量自癒（快取陳舊）** — **`[CONFIRMED_REAL_ISSUE]`**
   - **代碼座標**：`ys_codebase/source/knowledge-db/knowledge_db/schema.py:222-226` (`UnifiedSymbol.compute_id`)、`service.py:480-483` (`_run_stage1_sync`)、`pipeline.py:679-685, 748-751, 799-805` (`get_vector_deficit_info`)
   - **根因與反向查驗確證**：`UnifiedSymbol.compute_id` 僅由 `space:file_path:name:kind:line_number` 計算 SHA-1。當背景 Worker 執行 `_sync_stage1_lexical_and_graph` 時傳入 `skip_vectors=True`（`pipeline.py:679`），完全跳過 `_patch_vector_index_with_probe`，未從 `vector_index` 剔除 `old_doc_ids`；隨後 Stage 2 `sync_vector_deficit_step` 僅以集合差集 `sym_ids - vec_ids` 尋找缺失向量，導致起始行號未變之已修改符號永遠留在 `vec_ids` 中而不重算嵌入。
   - **Devil's Advocate 副作用攔截**：嚴禁修改 `UnifiedSymbol.compute_id` 加入內容雜湊（否則每次編輯都會改變 Symbol ID，破壞 `pipeline.py:490-528` 呼叫圖譜 `old_callee_id` 跨版本追蹤）。應於 `hot_patch_unified_index(skip_vectors=True)` 時，將 `old_doc_ids` 從 `vector_index` 中剔除並持久化，零副作用銜接 Stage 2 `sym_ids - vec_ids` 差集自癒。

2. **`[F-02]` `file-space` 全空間 `ack(None)` 世代覆寫競態與 `watch=False` 自動刷新死角** — **`[CONFIRMED_REAL_ISSUE]` & `[VERIFIED_SAFE]`**
   - **代碼座標**：`ys_codebase/source/file-space/file_space/scanner.py:1007-1040, 1068-1077, 1116-1130`、`service.py:330-335, 410-412`
   - **根因與反向查驗確證**：
     1. `ack(None)` 在遍歷子空間時忽略了 `diff_result` 當時讀取的各子空間世代，重新從磁碟讀取 `s_state.head_generation` 無條件覆寫各子空間 Cursor；若在 Consumer 執行 Stage 1 索引期間 Watcher 剛刷新了某子空間的新快照（`gen + 1`），`ack(None)` 將直接把未處理的 `gen + 1` 標記為已消費（Lost Update）。
     2. `FileSpaceWatcherServiceWorker.run()` 僅對 `cfg.watch=True` 的空間建立初始快照與監聽；當同進程 `is_watcher_active() == True` 時，`consume_diff` 將 `auto_refresh` 設為 `False`，且 `_diff_all_spaces` 內部強制 `self.diff(s_name, auto_refresh=False)`（`scanner.py:1014`），導致 `watch=False` 的空間在 Watcher 啟動時永遠不會自動 `refresh`。

3. **`[F-03]` `core.uri._get_merged_uri_schemes` 繞過 `contributes` JIT 髒檢查，直讀未自癒快取** — **`[CONFIRMED_REAL_ISSUE]`（含遞迴風險攔截）**
   - **代碼座標**：`ys_codebase/source/core/core/uri.py:242-261` (`_get_merged_uri_schemes`)
   - **根因與反向查驗確證**：雖然一般 CLI 在 `pre_cli_dispatch` 會經由 `agents-workflow` 間接觸發 `contributes.get()`，但在 `WarmWorker.pre_warm()`（Hook 觸發前）、`--help` 早退路由或純 SDK 調用下，`uri.py` 直接讀取 `.cache/core/contributes.merged.json` 而未檢查 `_is_contributes_dirty()`。
   - **Devil's Advocate 副作用攔截 (`[RECURSION_HAZARD]`)**：`_is_contributes_dirty()` 內部會呼叫 `vfs.exists("cache://...")` 與 `uri.resolve("module://...")`，而 `cache://`、`module://` 並非 `uri.resolve` 的硬編碼 fast-path，若在 `_get_merged_uri_schemes()` 直接呼叫 `contributes.get()` 或 `_is_contributes_dirty()` 會引發 `RecursionError` 無窮遞迴。必須於 `uri.py` 設置重入保護旗標（Reentrancy Guard），在髒檢查重入期間直接返回 `{}` 退回 `_BOOTSTRAP_FALLBACK_SCHEMES`（已涵蓋 `cache`/`module`/`config`），方可安全觸發自癒。

#### 🟡 P2（中嚴重度：特定組態/目錄操作下之假陽性短路與熱修補偏差）

4. **`[F-04]` `agents-workflow` Stage 0 指紋漏追蹤跨模組語系、`core` 組態、`AGENTS.md` 託管區塊與目錄 SHA-1 快取缺失** — **`[CONFIRMED_REAL_ISSUE]` & `[VERIFIED_SAFE]`**
   - **代碼座標**：`ys_codebase/source/agents-workflow/agents_workflow/publisher.py:154-173, 192-257, 456-501`
   - **根因與反向查驗確證**：
     1. **目錄型 `export` 未走 `_sha1_cache`**：`_get_source_file_sha1` 處理單一檔案時會查驗 `self._sha1_cache` (`mtime_ns`, `size`)，但遇到目錄時每次 `os.walk` 皆直接 `open(fp, "rb").read()` 重算 SHA-1。
     2. **Stage 2 語系與 URI 依賴未納入指紋**：Stage 2 編譯依賴 `core.locale.get_active_chain()` 與 `config://core`，但 `compute_source_fingerprint()` 未納入。
     3. **`AGENTS.md` 託管區塊未校驗完整性**：`_check_short_circuit()` 僅檢查 `os.path.isfile(a_abs)`，若 `<!-- YSCB_AGENTS_BEGIN -->` 區塊被刪但檔案仍在，Stage 0 將跳過自癒。

5. **`[F-05]` `knowledge-db` 局部熱修補 `is_dirty_file_match` 尾綴與檔名匹配過寬，誤傷跨空間同名檔** — **`[CONFIRMED_REAL_ISSUE]` & `[VERIFIED_SAFE]`**
   - **代碼座標**：`ys_codebase/source/knowledge-db/knowledge_db/io_utils.py:53-64` (`is_dirty_file_match`)、`bundler.py:524-546`
   - **根因與反向查驗確證**：`io_utils.py:60-63` 的 `sym_path_norm.endswith("/" + p)` 以及 `if "/" not in p and sym_filename == p: return True` 極度寬鬆——當某空間根目錄下的頂層檔案（如 `README.md`、`__init__.py`、`conftest.py`，無 `/`）發生變更或刪除時，會將全專案所有空間內同檔名檔案全部判定為 dirty 進行重解析或誤刪符號。應將 `dirty_diff` 結合空間 `include` 根目錄正規化為 `project://` 相對路徑，並移除無 `/` 單純比對 `sym_filename == p` 的危險邏輯。

#### 🟢 P3（低嚴重度：開發期 fallback 與多執行緒 RMW 鎖）

6. **`[F-06]` `core` Contributes 快照漏追蹤 `module.source://` fallback `_format.json` 與專案級語系實體檔** — **`[CONFIRMED_REAL_ISSUE]` & `[VERIFIED_SAFE]`**
   - **代碼座標**：`ys_codebase/source/core/core/contributes.py:237-260, 287-299, 365-370`
   - **根因與反向查驗確證**：`_scan_contributes_inputs` 未納入 `get_format()` fallback 讀取的 `module.source://<module>/contributes/_format.json`，且對 `config://core/contribute.json` 宣告的語系檔未追蹤實體 JSON 檔案。

7. **`[F-07]` `CursorStore.set_cursor` 多執行緒 RMW 鎖 vs. `core.locale._MODULE_BASE_DIR_CACHE`**
   - **`CursorStore.set_cursor` (`scanner.py:424-460`)**：**`[CONFIRMED_REAL_ISSUE]` & `[VERIFIED_SAFE]`** — `set_cursor` / `reset_cursor` 之 Read-Modify-Write 區間無 `threading.RLock()`，多執行緒併發更新同一 consumer 不同 space 時存在覆寫風險。
   - **`core.locale._MODULE_BASE_DIR_CACHE` (`locale.py:68-70`)**：**`[REJECTED_FALSE_POSITIVE]`** — 經 Devil's Advocate 查驗，Server 模式下 `.modules/` 異動時 `ModulesWatcher` 會直接重啟 `WarmWorker` 子進程，且 `act_reload` 為同路徑原子替換、`_LOCALE_FILE_CACHE` 已按 `st_mtime` 自動失效，故無須額外修改 `locale.py`。

---

## 3. 結論 (Conclusion)

採納經 Devil's Advocate 反向查驗確證之 **6.5 項真實漏洞（`[F-01]` ~ `[F-06]` 及 `[F-07]` 之 `CursorStore` 執行緒鎖，排除 `[F-07]` `locale.py` 假陽性）**，原地將 `sub_06` 升格為 Full Track (`/auto`) 實作計畫落地修復。
