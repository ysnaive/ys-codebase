# 技術路線圖：知識庫檢索管線修復、熱修補圖譜保真與遺留同義詞純化 (`knowledge_db_retrieval_pipeline_and_purity_roadmap`) (Roadmap)

> 主題：知識庫檢索管線修復、熱修補圖譜保真與遺留同義詞純化 (`knowledge_db_retrieval_pipeline_and_purity_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在對 `ys-codebase / module:knowledge-db`（`v1.1.0.6`）進行全模組功能性與架構邊界審查後，確認存在 **8 項功能缺陷與架構純度問題（`K-01` ～ `K-08`）**：

1. **`K-01` [Critical] `pipeline.search()` 向量索引載入「雞生蛋」死鎖，導致冷啟動查詢 100% 略過向量檢索**：
   - `knowledge_db/pipeline.py:search()`（L768–779）在呼叫 `self._ensure_jit_index_ready(require_vectors=can_use_vector)` **之前**，先以 `self.hybrid_engine.is_vector_available`（`hybrid.py` L46–53）計算 `can_use_vector`。
   - 當新進程啟動（或 `_unified_index` 尚未載入）時，`self.hybrid_engine.vector_index` 為空實例（`len(doc_ids) == 0`），導致 `is_vector_available` 必回傳 `False`，進而傳入 `require_vectors=False` 使 `_ensure_indices_loaded(load_vectors=False)` **完全跳過載入磁碟上已建置完成的 `unified.vectors.bin.gz`**。
   - 隨後第 796 行再次檢查 `can_use_vector` 時依然為 `False`，造成所有獨立 CLI `python yscb.py knowledge-db search` 呼叫 **100% 退化為純 BM25 檢索**，已建置之向量索引在跨進程查詢時完全失效。
2. **`K-02` [High] 調用圖譜增量熱修補 (`CallGraphIndex.patch_incremental`) 直接移除節點，導致跨檔案上游調用邊 (`Callers`) 100% 遺失**：
   - 當修改檔案 `a.py`（含函式 `bar`）並觸發 JIT 熱修補或背景 Watcher 熱修補時，`pipeline.py:hot_patch_unified_index()`（L413–426）僅針對 `dirty_files`（即 `a.py`）重新提取出度調用點 `dirty_sites`。
   - 接著呼叫 `_call_graph_index.patch_incremental(..., old_symbol_ids=old_doc_ids)`（`graph.py` L71–99, L206–221），對 `old_doc_ids` 執行 `self._graph.remove_node(sid)`。
   - 在 NetworkX `DiGraph` 中，`remove_node(old_bar_id)` 會同時拔除該節點的所有出度邊與**所有來自未修改檔案（如 `c.py -> a.py:bar`）的入度邊**；而 `new_edges` 僅含 `a.py` 的出度邊，導致熱修補後查詢 `callers bar` 或 `impact bar` 時，所有跨檔案上游調用者 **100% 清零消失**。
3. **`K-03` [High] 常駐 Watcher 雙軌重複啟動衝突（`hook.server.py` 私自啟動 vs. `contributes/server.json`）與 `source/server` 路徑注入**：
   - `contributes/server.json` 已正式註冊 `knowledge-db-watcher`（`knowledge_db.service:KnowledgeDBServiceWorker`）交由 `server.ServiceManager` 統一託管，但 `scripts/hook.server.py`（L27–39）在 `server_worker_warming` 事件中又私自實例化並啟動一個未受管的 `_watcher_instance = KnowledgeDBServiceWorker()`。
   - 該私自啟動之實例不受 `ServiceManager.stop_all()` 管控，且在 `server` 修復 `S-01` 後會在同一 Worker 進程內產生**兩個 Watchdog `Observer` 實例**爭搶 `.watcher_active` / `.watcher_dirty` 與索引寫鎖。
   - 此外，`knowledge_db/service.py`（L20–26）將平級 `source/server` 注入 `sys.path`（違反 `.modules/` 剛性約束），且 `knowledge_db/engine.py`（L454）呼叫了不存在的 `from core.events import on`。
4. **`K-04` [High] 複合檢索 `--ftype=c,cpp,py` 多副檔名過濾失效，且 `callers/callees/impact` 漏傳 `ftypes` 並重複讀盤反序列化**：
   - `pipeline.py:search()`（L784）未對 `ftypes` 呼叫 `_normalize_ftypes()` 拆解逗號，傳入 `hybrid.py`（L182–185）時以 `ext not in ["c,cpp,py"]` 比對，導致多副檔名過濾時 **100% 的向量召回結果被誤殺**。
   - `act_callers`（L1132）、`act_callees`（L1200）、`act_impact`（L1256）呼叫 `self.find_target_symbol(target_query, space=space)` 時全數漏傳 `ftypes=ftypes`。
   - `find_target_symbol()`（L1085）內部直接呼叫 `self.build_unified_index()`，繞過 `_GLOBAL_INDEX_CACHE` 每次重新自磁碟解壓反序列化 `unified.index.bin.gz`、`unified.graph.bin.gz` 與 `unified.vectors.bin.gz`，徹底抵銷了 `require_vectors=False` 與常駐記憶體快取優化。
5. **`K-05` [Medium] 舊版同義詞庫 (`thesaurus / aliases / related`) 遺留包袱未純化清除**：
   - 模組導入 FastEmbed 多語言向量模型與 `MultilingualTokenizer` 後，已廢棄 `ThesaurusEngine`（`engine.py` 與 `pipeline.py` 皆硬編碼 `thesaurus=None`，且無 `thesaurus.py`），但 `contributes/_format.json`、`contributes/knowledge-db.json`（L81–263）、`space.py`、`bundler.py`、`schema.py`、`retrieval.py`、`linker.py`、`cli.py` 與 `SKILL.md` 仍殘留大量同義詞定義、載入邏輯與 `68 組同義詞` 狀態輸出。
6. **`K-06` [Medium] CLI 選項契約 (`contributes/core.json`) 與實作 (`scripts/cli.py`) 脫鉤，且 `-d` (`--detail`) 遺失代碼切片與除錯欄位**：
   - `callers / callees / impact` 支援 `--limit`、`search` 支援 `--kind` / `--lang`、`status` 支援 `--space` / `--all`，但均未在 `contributes/core.json` 宣告（導致帶空白傳參如 `--limit 10` 被 `OptionResolver` 當成無參布林旗標）。
   - `preview`（`-s`）與 `detail`（`-d`）在 `core.json` 同屬互斥群組 `display`，但 `scripts/cli.py`（L263, L422, L586）寫成 `tier == "detail" and bags.has_option("s")`，導致單獨傳 `-d` 時 `is_snippet=False` 反而不擷取程式碼切片；且 `search --json -d` 漏輸出 `id`（40 碼 SHA-1）、`matched_terms` 與 `spaces`。
   - `impact` 在 `core.json` 宣告了 `--preview`（`-s`），但 `cli.py:impact()` 完全忽略該選項。
7. **`K-07` [Medium] 組態載入優先級倒置、常駐單例未熱刷新組態，且降級提示指引舊版 `yscb.config.json`**：
   - `KnowledgeDBConfig.load()`（`config.py` L53–81）先讀 `core.config` 後又用 `yscb.config.json` 覆蓋，優先級顛倒。
   - `pipeline.py` 向量熔斷降級訊息（L456, L463, L505）仍指引手動修改 `yscb.config.json`，應改為 `python yscb.py config set knowledge-db enable_vector_search false`。
   - 常駐 Worker 中 `get_engine()` 單例不會感知 `config://knowledge-db/` 的後續組態更新。
8. **`K-08` [Low] 文檔與契約清冊脫鉤（`README.md` SDK 範例方法名不符、`_manifest.md` 指令過時、`core.json` 漏註冊 `hooks`）**：
   - `README.md` §4 SDK 範例呼叫 `engine.callers()`、`engine.callees()`、`engine.impact(max_depth=2)` 與 `engine.search(file_types=..., tier=...)`，與 `KnowledgeEngine` 實際方法名（`act_callers` 等）及參數名（`ftypes`、`depth`）不符；同時需確保 `README.md` 內之技能引用連結統一對齊為正確名稱 `yscb-cli-guide`。
   - `contributes/_manifest.md` 仍記載已廢棄的 `build` / `symbol` 指令；`contributes/core.json` 漏註冊 `hooks`（`hook.dev.py`、`hook.server.py`）。

### 1.2 現況與影響範圍評估
- **架構定調：打通冷啟動向量檢索載入、落實調用圖譜入度邊增量保真、純化移除遺留同義詞包袱，並統一 `server` 常駐服務託管與 CLI 契約**：
  1. **雙軌複合檢索 100% 真實生效**：修正 `pipeline.search()` 前置載入條件與 `_normalize_ftypes()`，確保冷啟動與多副檔名查詢皆能正確載入並融合 `VectorIndex`。
  2. **增量熱修補圖譜零掉邊（Zero Edge Loss on Hot Patch）**：在 `CallGraphIndex.patch_incremental` 與 `hot_patch_unified_index` 中完整保留並重連外部未修改檔案指向髒檔案符號的入度調用邊。
  3. **架構純化與單一權責（Single Source of Truth）**：徹底移除已淘汰的 `thesaurus / aliases / related` 遺留結構，並將 `KnowledgeDBServiceWorker` 100% 收歸 `server.ServiceManager` 單一託管。

### 1.3 核心根因
1. **狀態依賴順序倒置（Pre-Load State Check Bug）**：在索引尚未從磁碟載入前即檢查記憶體 `vector_index` 的文件數，造成「因為沒載入所以判定不可用、因為判定不可用所以不載入」的邏輯死鎖。
2. **有向圖局部更新未保護外部入度邊（Directed Graph Partial-Update Hazard）**：僅重新解析修改檔的 AST 出度調用，卻直接呼叫 `DiGraph.remove_node()` 連根拔除未修改檔指向該節點的入度邊。
3. **演進過程遺留未清理**：由早期純 BM25＋人工同義詞庫演進至 FastEmbed 向量複合檢索，以及修補早期 `server` 載入問題時，留下了雙軌過渡代碼。

---

## 2. 候選架構方案對比 (Candidate Solutions)

針對 `K-02`（調用圖譜增量熱修補遺失跨檔案入度邊）與 `K-05`（同義詞庫遺留處置），對比以下三種方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：熱修補時退回全專案重新提取所有檔案之調用點** | 每次單檔修改觸發 `hot_patch_unified_index` 時，重跑 `extract_all_call_sites_and_imports()` 掃描全專案所有檔案 | 實作簡單，不會漏掉入度邊 | 單檔修改卻需重讀並重跑全專案所有檔案的 Tree-sitter 查詢，使熱修補退化為 O(N) 全量重建，違背 500ms 極速增量初衷 | ⭐️⭐️ |
| **方案 2：僅以舊符號名稱硬映射新符號 ID** | 在 `remove_symbol_edges` 前記住 `old_id -> new_id`，若同名則直接搬移入度邊 | 速度快（O(1)） | 若檔案重構將方法改名、搬移類別或刪除方法，硬映射會產生指向錯誤符號的幽靈邊（Ghost Edges）或漏連 | ⭐️⭐️⭐️ |
| **方案 3：保留外部入度 `SymbolCallSite` 並經 `TopologyLinker` 增量重連 ＋ 徹底純化移除 `thesaurus`（推薦採納）** | 1. 拔除 `old_doc_ids` 前，自 `CallGraphIndex` 提取所有「`caller_id not in old_doc_ids` $\to$ `callee_id in old_doc_ids`」邊上的原始 `SymbolCallSite` 清單。<br/>2. 將這批外部入度 `SymbolCallSite` 與髒檔案新提取的 `dirty_sites` 合併，交由 `TopologyLinker.link_call_sites()` 對更新後的 `_unified_index.symbols` 重新執行四階消歧鏈結。<br/>3. 徹底純化移除全模組 `thesaurus / aliases / related` 遺留定義與死分支。 | 1. **O(Dirty + IncomingEdges) 極速增量**：免重讀未修改檔案磁碟與 AST<br/>2. **100% 消歧精準度**：若目標方法仍存在（即使行號改變致 SHA-1 ID 變更）自動重連新 ID；若目標方法被刪除則自動斷開不留幽靈邊<br/>3. 減少約 350 行同義詞遺留代碼與 185 行 JSON 包袱 | 需同步更新 `pipeline.py`、`graph.py` 與清理 `thesaurus` 相關引用及測試 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：全量重掃調用點 | 方案 2：同名硬映射 ID | 方案 3：入度 `SymbolCallSite` 增量重連 ＋ 純化移除同義詞（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高**（`CallGraphIndex` 每條邊原本即完整保存了 `call_sites: List[SymbolCallSite]`） |
| **增量熱修補耗時** | 差（隨專案規模線性膨脹） | 極快 | **極快**（僅重連受影響的少數調用邊，維持毫秒級熱修補） |
| **拓撲圖譜準確性** | 高 | 中（易殘留幽靈邊） | **極高**（行號變動 100% 自動對齊新 SHA-1 ID，方法刪除自動清退） |
| **架構純淨度與維護成本** | 低 | 中 | **極高**（徹底消除 `thesaurus` 死分支與雙 Watcher 競態） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 `K-01` & `K-04` 檢索與拓撲管線修復 (`knowledge_db/pipeline.py`, `knowledge_db/hybrid.py`)
1. **解除 `pipeline.search()` 向量索引載入死鎖（`K-01`）**：
   - 於 `knowledge_db/pipeline.py:search()`（L767–802）中，將載入前的需求判定與載入後的可用性判定分離：
     ```python
     enable_vec = getattr(self.config, "enable_vector_search", True)
     want_vectors = bool(
         enable_vec
         and not getattr(self, "_vector_degraded", False)
         and not lexical_only
     )
     unified_index = self._ensure_jit_index_ready(
         require_vectors=want_vectors,
         auto_rebuild=auto_rebuild,
         verbose=verbose,
     )
     if not unified_index or unified_index.doc_count == 0:
         return []
     can_use_vector = want_vectors and self.hybrid_engine.is_vector_available
     ```
2. **修復 `--ftype` 多副檔名正規化與拓撲查詢效能／過濾（`K-04`）**：
   - 於 `pipeline.search()`（L784）改用 `target_ftypes = self._normalize_ftypes(ftypes)`（將 `"c,cpp,py"` 正規化為 `["c", "cpp", "py"]`），並於 `hybrid.py:search()`（L182–185）同步支援無點號與含點號副檔名比對（含 `md` $\leftrightarrow$ `markdown` 等價映射）。
   - 於 `act_callers`（L1132）、`act_callees`（L1200）、`act_impact`（L1256）呼叫 `self.find_target_symbol(target_query, space=space, ftypes=ftypes)` 補齊 `ftypes` 傳遞。
   - 於 `find_target_symbol()`（L1085）將 `idx = self.build_unified_index()` 修正為 `idx = self._ensure_jit_index_ready(require_vectors=False, auto_rebuild=True)`，消除每次查詢重複解壓反序列化磁碟檔案的無謂開銷。

### 4.2 `K-02` 調用圖譜增量熱修補入度邊保真 (`knowledge_db/graph.py`, `knowledge_db/pipeline.py`)
1. **於 `CallGraphIndex` 新增外部入度調用邊提取方法（`knowledge_db/graph.py`）**：
   - 新增 `get_external_incoming_edges(self, target_symbol_ids: Set[str]) -> List[Tuple[str, str, SymbolCallSite]]`：
     遍歷 `target_symbol_ids`，找出所有 `caller_id not in target_symbol_ids` 的入度邊 `(caller_id, old_callee_id)`，回傳完整的 `(caller_id, old_callee_id, call_site)` 三元組清單。
2. **於 `hot_patch_unified_index` 執行「同檔案符號身分優先對映 (`Identity Remap`) ＋ `TopologyLinker` 次選消歧」雙階重連（`knowledge_db/pipeline.py` L413–426，防裸調用丟邊陷阱）**：
   - **關鍵防呆**：若外部未修改檔 `c.py` 透過 `from a import bar` 並以無前綴裸調用 `bar()`（`site.context_prefix == ""`）呼叫 `a.py` 的函式，在單純修改 `a.py` 觸發熱修補時，我們並未重解析 `c.py` 的 `file_imports`；若直接將 `site` 丟進 `TopologyLinker.resolve_call_site(site, dirty_imports)`，會因 `c.py` 無 `file_imports` 且 `not prefix` 被 `linker.py` L341 守門直接攔截返回 `None` 而丟邊！
   - 因此在 `_unified_index.patch_incremental` 拔除舊符號前，先建立舊符號身分快照 `old_identities = {sid: (sym.file_path.replace("\\", "/").lower(), sym.name, (sym.fqn or "").lower(), sym.kind) for sid in old_doc_ids if sid in self._unified_index.symbols}` 並提取 `incoming_edges = self._call_graph_index.get_external_incoming_edges(old_doc_ids)`。
   - 待 `all_new_symbols` 注入 `_unified_index` 後，建立新符號之 `(norm_file_path, name, lower_fqn, kind) -> new_sid`（及退化之 `(norm_file_path, name) -> new_sid`）映射表：
     1. **第一階（Identity Remap，O(1) 精準保真）**：針對每條 `(caller_id, old_callee_id, site)`，若 `old_callee_id` 對應之 `(file_path, name, fqn)` 在更新後的同檔案中依然存在（即使行號位移導致 SHA-1 ID 變更），直接將邊重連至 `new_sid` `(caller_id, new_sid, site)`，100% 不受缺少外部檔 `file_imports` 影響。
     2. **第二階（Fallback Linker 消歧）**：僅當原符號在該檔案中被刪除或改名時，才將 `site` 交由 `linker.link_call_sites([site], dirty_imports)` 嘗試跨檔案消歧（若已徹底刪除則自然斷開，不留幽靈邊）。

### 4.3 `K-03` 常駐背景服務單一託管與 `.modules/` 剛性邊界對齊 (`scripts/hook.server.py`, `knowledge_db/service.py`, `knowledge_db/engine.py`)
1. **純化 `scripts/hook.server.py`**：
   - 移除 `_watcher_instance` 與私自啟動 `KnowledgeDBServiceWorker` 的邏輯，`on_server_worker_warming` 僅負責執行 `KnowledgeEngine.pre_warm()`，將 `KnowledgeDBServiceWorker` 生命週期 100% 交由 `contributes/server.json` 與 `server.ServiceManager` 託管。
2. **移除 `service.py` 的 `source/server` 路徑注入與 `engine.py` 的無效事件註冊**：
   - 於 `knowledge_db/service.py`（L19–28）移除向 `sys.path` 插入 `_src_parent / "server"` 的程式碼，當 `from server.service import BaseServiceWorker` 發生 `ImportError` 時直接退回內建的 `BaseServiceWorker(ABC)` 抽象基底類別。
   - 於 `knowledge_db/engine.py`（L452–457）移除無效的 `from core.events import on` 區塊。

### 4.4 `K-05` 徹底純化移除遺留同義詞庫 (`thesaurus / aliases / related`)
1. **清理 `contributes/` 契約與預設詞庫**：
   - 自 `contributes/_format.json` 移除 `"thesaurus"`、`"aliases"`、`"related"` 三個擴充點定義（僅保留 `"spaces"` 與 `"languages"`）。
   - 自 `contributes/knowledge-db.json` 移除第 81–263 行的 `"thesaurus"`、`"aliases"`、`"related"` 陣列與字典（僅保留 10 大 `"languages"` 宣告）。
   - 自 `contributes/_manifest.md` 移除 `thesaurus` 說明。
2. **清理 Python 核心程式碼、Schema 與未引用死代碼**：
   - `knowledge_db/schema.py`：移除 `ThesaurusGroup`、`ThesaurusConfig` 與生產環境 0 呼叫之死代碼 `CallGraphNode`（並自 `knowledge_db/__init__.py` 的 `__all__` 移除）；同步物理刪除生產環境 0 引用之 `knowledge_db/protocol.py`（`LanguageTopologyProtocol`, `TreeSitterTopologyAdapter`, `TopologyProtocolRegistry`）。
   - `knowledge_db/space.py`：自 `_load_contributes()` 移除 `thesaurus / aliases / related` 讀取，刪除 `load_thesaurus_config()`、`load_thesaurus()` 與 `create_thesaurus_engine()`。
   - `knowledge_db/bundler.py`：自 `SemanticBundle` 移除 `thesaurus` 欄位。
   - `knowledge_db/retrieval.py`、`knowledge_db/linker.py`、`knowledge_db/engine.py`、`scripts/cli.py`：移除 `BM25Engine` 與 `TopologyLinker` 的 `thesaurus` 參數、移除 `engine.thesaurus_engine`、移除 `engine.status()` 的 `thesaurus_groups` 統計與 `cli.py:status()` 的 `，X 組同義詞` 輸出。
   - `assets/skills/knowledge-db-search/SKILL.md`：將速查表中的 `search 'ThesaurusEngine'` 替換為現行真實類別 `search 'HybridSearchEngine' --json`。

### 4.5 `K-06`, `K-07`, `K-08` CLI 契約對齊、組態熱刷新與 SDK／文檔同步
1. **補齊 `contributes/core.json` 選項與 `hooks` 宣告，並修復 `scripts/cli.py` `-d` 行為（`K-06`、`K-08`）**：
   - 於 `contributes/core.json`：
     - 頂層新增 `"hooks"` 區塊宣告 `dev`（`on_test_setup`, `on_test_teardown`）與 `server`（`on_server_worker_warming`）。
     - 為 `callers`、`callees`、`impact` 補齊 `limit` 選項；為 `search` 補齊 `kind` 與 `lang` 過濾選項；為 `status` 補齊 `all`（`-a`）、`space` 與 `json` 選項；自 `impact` 移除未使用的 `preview`（`-s`）選項。
   - 於 `scripts/cli.py`：
     - 將 `search`、`callers`、`callees` 的 `is_snippet` 判定修正為 `is_snippet = tier in ("snippet", "detail")`，確保 `-d`（Tier 3 Detail）必然包含完整代碼切片。
     - 於 `search` 的 `tier == "detail"` JSON 輸出補齊 `"id": itm.symbol.id`、`"matched_terms": itm.matched_terms` 與檔案層級 `"spaces": res.spaces`。
2. **修正 `KnowledgeDBConfig` 優先級、常駐熱刷新與降級提示（`K-07`）**：
   - 於 `knowledge_db/config.py:KnowledgeDBConfig.load()` 中，以 `core.config.get_all("knowledge-db")`（`config://knowledge-db/config.local.json > config.project.json`）為最高優先級（僅在外部顯式傳入 `project_config` / `local_config` 覆寫參數時疊加），移除讀取根目錄 `yscb.config.json` 覆蓋 `core.config` 的倒置邏輯。
   - 於 `knowledge_db/engine.py:get_engine()`（或 `pipeline.search` / `build_unified_index` 入口）同步檢查 `KnowledgeDBConfig.load()`，動態更新 `self.config` 與 `self.embedding_service.enable_vector_search`。
   - 將 `knowledge_db/pipeline.py`（L456, L463, L505）中的降級提示統一更新為 `請執行 python yscb.py config set knowledge-db enable_vector_search false 關閉向量語意搜尋`。
3. **對齊 `KnowledgeEngine` Python SDK 方法別名與 `README.md` / `_manifest.md`（`K-08`）**：
   - 於 `KnowledgeEngine` 新增 `callers()`、`callees()`、`impact()` 公開方法（對齊 `act_callers`、`act_callees`、`act_impact`，並支援 `max_depth` 與 `file_types` 參數別名），確保 `README.md` §4 的 SDK 範例 100% 可直接執行。
   - 更新 `contributes/_manifest.md` 的 CLI 指令清冊（`status`, `index`, `search`, `callers`, `callees`, `impact`, `model`, `clean`），並確認 `README.md` 之技能連結統一對齊為正確名稱 `yscb-cli-guide`。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術路線圖，以單次版本迭代（如 `v1.1.1.0`）完成複合檢索死鎖修復、熱修補圖譜保真、同義詞庫純化移除與 CLI/SDK 契約對齊。
- **跨模組部署順序防呆**：本路線圖之 `K-03`（移除 `hook.server.py` 私自啟動的 `_watcher_instance`）必須在 `server` 模組完成 `S-01 / S-02`（`ServiceManager` `import os` 修復與 `.modules/<provider>` 路徑注入）之後或同步部署，確保 `knowledge-db-watcher` 能無縫由 `server.ServiceManager` 單一接手託管。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：檢索管線死鎖修復與調用圖譜熱修補保真（`K-01`、`K-02`、`K-04`）**
   - 修復 `pipeline.search()` 的 `want_vectors` 前置載入條件與 `_normalize_ftypes()`。
   - 於 `CallGraphIndex` 與 `hot_patch_unified_index()` 實作外部入度 `SymbolCallSite` 提取與增量重連。
   - 補齊 `act_callers / callees / impact` 對 `find_target_symbol(ftypes=...)` 的傳遞，並將 `find_target_symbol()` 改為呼叫 `_ensure_jit_index_ready(require_vectors=False)`。
2. **Stage 2：遺留同義詞庫純化移除與常駐服務單一託管（`K-03`、`K-05`）**
   - 自 `contributes/`、`schema.py`、`space.py`、`bundler.py`、`retrieval.py`、`linker.py`、`engine.py`、`cli.py` 與 `SKILL.md` 徹底移除 `thesaurus / aliases / related`。
   - 純化 `scripts/hook.server.py`（移除私自啟動的 `_watcher_instance`）、移除 `service.py` 的 `source/server` 路徑注入與 `engine.py` 的無效 `core.events.on` 呼叫。
3. **Stage 3：CLI 契約對齊、組態優先級修復與 SDK／文檔同步（`K-06`、`K-07`、`K-08`）**
   - 補齊 `contributes/core.json` 的 `limit`、`kind`、`lang`、`space`、`all`、`json` 選項與 `hooks` 宣告，並修復 `scripts/cli.py` 在 `-d` 模式下的切片與欄位輸出。
   - 修正 `KnowledgeDBConfig.load()` 優先級與 `pipeline.py` 降級提示文字，為 `KnowledgeEngine` 補齊 SDK 方法別名並更新 `README.md` 與 `contributes/_manifest.md`。
