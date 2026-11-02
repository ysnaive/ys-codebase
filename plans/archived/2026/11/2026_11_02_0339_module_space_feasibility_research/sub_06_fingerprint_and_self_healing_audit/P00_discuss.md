# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全生態系指紋快取與熱自癒機制完善度審視與修復  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「那先不處理好了， sub 06 改為審視檢查當前指紋 & 自癒機制是否完善之調研」
  2. 「立即實作， /auto ，開始前依照 /blind-subagent 從發現之問題反推真實性」
- **核心目標**：
  - 針對 `R01_fingerprint_and_self_healing_audit.md` 審計發現並經原型 ③ Devil's Advocate 反向查驗確證之指紋與自癒漏洞（涵蓋 `core`、`file-space`、`knowledge-db`、`agents-workflow` 四大模組共 6 大項實質缺陷），以 `/auto` 模式完成規格定義、源碼修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core/contributes.py` (`_is_contributes_dirty`, `_scan_contributes_inputs`)、`core/uri.py` (`_get_merged_uri_schemes`)、`file_space/scanner.py` (`ScanDiffResult`, `CursorStore`, `FingerprintScanner`)、`knowledge_db/pipeline.py` (`hot_patch_unified_index`)、`knowledge_db/bundler.py` & `io_utils.py` (`is_dirty_file_match`)、`agents_workflow/publisher.py` (`ReleasePublisher`).
- **邊界排除 (Explicitly Excluded)**：
  - 經 Devil's Advocate 反向查驗證偽之 `core.locale._MODULE_BASE_DIR_CACHE`（`[REJECTED_FALSE_POSITIVE]`，已有 `WarmWorker` 進程重啟與 `_LOCALE_FILE_CACHE` `mtime` 雙重保障）明確排除不予無謂修改。
  - 嚴禁修改 `UnifiedSymbol.compute_id` 雜湊組成（以保護呼叫圖譜 `old_callee_id` 跨版本穩定性）。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/{uri,contributes}.py` 及 `tests/`
  - `ys_codebase/source/file-space/file_space/scanner.py` 及 `tests/`
  - `ys_codebase/source/knowledge-db/knowledge_db/{pipeline,bundler,io_utils}.py` 及 `tests/`
  - `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` 及 `tests/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採行雙盲眼子代理平行探索（原型 ①）與 Devil's Advocate 反向查驗（原型 ③）**：
  - 先以原型 ① 完成 `R01_fingerprint_and_self_healing_audit.md`，再啟動 2 名原型 ③ Devil's Advocate 子代理從第一手源碼反向查驗 `[F-01]` ~ `[F-07]` 真實性與修復副作用，排除 `[F-07]` `core.locale` 假陽性，並攔截 `[F-01]` Symbol ID 變更副作用與 `[F-03]` `uri.py` 無窮遞迴風險。
- **[P00:DR-02] `knowledge-db` Stage 1 向量失效與精確路徑匹配修復 (`[F-01]`, `[F-05]`)**：
  - 於 `hot_patch_unified_index(..., skip_vectors=True)` 中，當 `old_doc_ids` 非空且向量索引檔存在時，主動從 `vector_index` 移除 `old_doc_ids` 並持久化，使起始行號未變但內容已修改之符號能被 Stage 2 `sym_ids - vec_ids` 差集自動重算向量。
  - 於 `bundler.py` / `pipeline.py` 將單空間 `dirty_files` 結合空間 `include` 根目錄正規化為 `project://` 相對路徑，並收斂 `io_utils.is_dirty_file_match` 移除無 `/` 時僅比對 `sym_filename == p` 的寬鬆條件，杜絕跨空間同名頂層檔案（如 `README.md`、`__init__.py`）誤判。
- **[P00:DR-03] `file-space` 世代精確 Ack、`watch=False` 自癒與 `CursorStore` 執行緒安全 (`[F-02]`, `[F-07]`)**：
  - 於 `ScanDiffResult` 新增 `space_generations: Dict[str, int] = field(default_factory=dict)`，在 `_diff_all_spaces` 記錄各子空間當下讀取的 `to_generation`，並由 `consume_diff(None)` / `ack(None)` 依該映射精確更新各子空間 Cursor，消除跨執行緒/進程 Lost Update。
  - 在 `consume_diff` 與 `_diff_all_spaces` 中，針對 `not cfg.watch` 的空間維持 `auto_refresh=True`（即使 `is_watcher_active()` 為 `True`）。
  - 於 `CursorStore` 加入 `threading.RLock()` 保護 `set_cursor` 與 `reset_cursor` 的 Read-Modify-Write 區段。
- **[P00:DR-04] `core` URI 重入安全 JIT 髒檢查與 Contributes 輸入追蹤補齊 (`[F-03]`, `[F-06]`)**：
  - 於 `core/uri.py` `_get_merged_uri_schemes()` 引入執行緒安全重入保護旗標（Reentrancy Guard），在非重入狀態下若偵測到 `contributes._is_contributes_dirty()` 為真，自動觸發 `contributes.get("core", "uri_schemes")` 重算快取；重入期間直接返回 `{}` 退回 `_BOOTSTRAP_FALLBACK_SCHEMES` 打破循環依賴。
  - 於 `core/contributes.py` `_scan_contributes_inputs()` 補齊 `module.source://<donor>/contributes/_format.json` fallback 檔案與 `config://core/contribute.json` 宣告之專案級語系實體檔追蹤。
- **[P00:DR-05] `agents-workflow` 目錄 SHA-1 快取複用與 Stage 0 指紋/區塊完整性 (`[F-04]`)**：
  - `ReleasePublisher._get_source_file_sha1` 走訪目錄時逐檔複用 `self._sha1_cache` (`mtime_ns`, `size`)，消除每次 `pre_cli_dispatch` 重複讀取 Skill 目錄檔案內容的 I/O 開銷。
  - `compute_source_fingerprint()` 納入 `core.locale.get_active_chain()` 與 `config://core` 摘要；`_check_short_circuit()` 確認 `agent_rules` 目標檔（如 `AGENTS.md`）同時包含 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 標記。

---

## 3. 開放議題與確認紀錄

- 開發者已指示：「立即實作， /auto ，開始前依照 /blind-subagent 從發現之問題反推真實性」，現已完成反向查驗並轉入 `/auto` 推進。
