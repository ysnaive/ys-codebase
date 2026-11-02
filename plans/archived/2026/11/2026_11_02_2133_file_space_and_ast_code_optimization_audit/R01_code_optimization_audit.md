# 專題調研與分析報告：`module:file-space` 與 `module:ast` 業務代碼五維度靜態診斷與重構審計 (`R01_code_optimization_audit.md`)

> 調研主題：file-space 與 ast 模組業務代碼五維度靜態診斷與重構審計  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_2133_file_space_and_ast_code_optimization_audit  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  在完成 `2026_11_02_1009_ast_topology_engine_modularization`（建立 Layer 1 `module:file-space` 與 Layer 2 `module:ast` 並與 Layer 3 `module:knowledge-db` 形成三階單向無環圖）後，為確保新落成之核心基礎設施模組不殘留演進過渡期的相容別名、薄轉發殼層、孤兒死代碼、方法內延遲循環依賴與跨方法重複樣板，特啟動 `/blind-subagent` + `/code-optimizer` 雙盲五維度靜態診斷。
- **調研目標與範疇**：
  針對 `ys_codebase/source/file-space/` 與 `ys_codebase/source/ast/` 全量業務生產程式碼執行 `D1`~`D5` 五維度靜態診斷與 `S1`~`S6` 外科手術重構處方設計。

### 1.1 定錨基準與範圍摘要
- **檢視範圍**：多模組範圍（`ys_codebase/source/file-space/` 與 `ys_codebase/source/ast/`，涵蓋模組內所有業務 `.py` 檔案、模組內跨檔拓撲，以及跨模組消費者 `knowledge-db` 與 `tests/` 引用查驗）。
- **生命週期模式**：**`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**（強制單一正統入口，零容忍拔除過渡別名、薄轉發層、孤兒死代碼與歷史標記噪音，並同步更新內部/跨模組與 `tests/` 調用點）。
- **代理執行軌道**：**`軌道 2B/3B：主代理統籌 + 雙路盲眼子代理平行盲審`**（分別由 `96adcabe` 審計 `module:file-space`、`75802a6a` 審計 `module:ast`）。
- **現行測試基線狀態**：
  - `module:file-space`：`dev check file-space [PASS]`、`dev test file-space 15/15 PASSED`。
  - `module:ast`：`dev check ast [PASS]`、`dev test ast 18/18 PASSED`。
  - 下游消費者 `module:knowledge-db`：`dev check knowledge-db [PASS]`、`dev test knowledge-db 103/103 PASSED`。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- **核心分析與實證內容**：以下彙整雙路盲眼子代理透過 `ast callers` 與 `knowledge-db search` 跨全空間雙重查證後之契約邊界盤點、五維度診斷矩陣與 `S1`~`S6` 外科手術處方箋。

### 2.1 契約邊界與內部工具函式查驗表 (`Mode A` 收斂清單)

#### A. `module:file-space` (`ys_codebase/source/file-space/`)
| 類別 | 目標符號與位置 | 全空間引用查驗 (`callers` + `search`) | `Mode A` 處置與需同步改寫之調用點 |
| :--- | :--- | :--- | :--- |
| **相容別名與舊建構子** | 1. `FileSpaceDef = FileSpaceConfig` (`file_space/schema.py:180`, `__init__.py:28,214`)<br/>2. `FileFingerprint` 舊版相容參數（`relpath, mtime, sha1`）與唯讀別名屬性 (`schema.py:211-247`)<br/>3. `ScanDiffResult` 手寫 `__init__` 相容參數 (`schema.py:312-369`) | 1. `FileSpaceDef` 僅 `knowledge-db/tests/test_file_space.py:23,226` 引用<br/>2. `FileFingerprint` / `ScanDiffResult` 舊相容參數全空間 `0` 引用 | 物理移除舊相容參數與別名；將 `knowledge-db/tests/test_file_space.py:23,226` 同步改為正統 `FileSpaceConfig` |
| **舊空間發現回退與建構別名** | 1. `FileSpaceManager` 內對 `"knowledge-db"` 與 `config://knowledge-db/contribute.json` 之舊空間發現回退 (`manager.py:229,316`)<br/>2. `FileSpaceManager.__init__` 之 `storage_dir, contributes_data, core_context` 與 `.storage_dir` 別名 (`manager.py:96-120,217-220`)<br/>3. `get_space_config()` 1 行別名與 `get_space_storage_dir()` (`manager.py:565-583`) | 1 & 3 全空間 `0` 引用；2 調用點位於 `ast_engine/engine.py:120`、`knowledge_db/engine.py:94-96,116`、`knowledge_db/providers.py:20`、`knowledge_db/tests/test_file_space.py:66,97,112,136,151` | 物理移除舊 `knowledge-db` 空間發現回退、`get_space_config` 與 `get_space_storage_dir`；收斂或同步對齊跨模組建構參數（`cache_dir`） |
| **Scanner / Providers 舊方法與別名** | 1. `BinarySnapshotManager.save()` 與 `load()` 舊版 tuple/dict 轉發方法 (`scanner.py:304-367`，正統入口為 `save_state` / `load_state`)<br/>2. `FingerprintScanner` 尾段 6 個 Legacy 方法（`scan_all`, `scan_all_spaces`, `compute_diff`, `check_invalidation`, `save_snapshot`, `load_snapshot` 於 `scanner.py:1184-1275`）與 `ack(..., consumer=None)` (`scanner.py:1077`)<br/>3. `providers.py:9-18,48-49` 之 `get_file_space_names`、`get_space_names`、`get_registered_spaces_table` | 1 & 2 全空間 `0` 引用；3 僅 `file-space/tests/test_service_and_cli.py:33,223` 引用 | 物理移除 `scanner.py` 共 8 個 0 引用舊方法與 `providers.py` 舊別名，同步更新 `test_service_and_cli.py:33,223` 調用正統 `get_registered_file_spaces_table` |
| **沙盒與死屬性** | `service.py:408,425` (`self._watcher_active`)、`scripts/cli.py:340` (`scanner.mgr_check`)、`scripts/hook.dev.py:2,8,21,24`（殘留舊名 `.cache/space`） | 全空間 `0` 讀取 | 清除死屬性寫入，將 `hook.dev.py` 對齊為 `file-space` |

#### B. `module:ast` (`ys_codebase/source/ast/`)
| 類別 | 目標符號與位置 | 全空間引用查驗 (`callers` + `search`) | `Mode A` 處置與需同步改寫之調用點 |
| :--- | :--- | :--- | :--- |
| **頂層薄轉發包裝群** | `ast_engine/__init__.py:108-221` 之 8 個包裝函式（`outline`, `callers`, `callees`, `impact`, `ensure_jit_synced`, `get_snapshot`, `status`, `clean`） | 全空間 `0` 引用（`knowledge-db` 與 `scripts/cli.py` 均直接操作 `ASTEngine` / `get_engine()`） | 物理移除 8 個頂層轉發包裝，保留 `get_engine()`、`reset_default_engine()` 與核心類別匯出 |
| **Formatter 轉發殼與別名** | `ast_engine/formatter.py:644-676` 之 `format_outline/callers/callees/impact/status` 函式、`ASTResultFormatter.format_* = staticmethod(...)` 與 `ASTFormatter = ASTResultFormatter` | 生產碼 `0` 引用；僅 `tests/test_overload_and_topology.py:17,182` 與 `tests/test_partial_and_outline.py:20,152,256` 使用 `ASTFormatter.format_*` | 物理移除轉發殼與別名；將上述 2 個測試檔共 5 處調用同步改為正統 `ASTResultFormatter().format_*_output(...)` |
| **過渡參數與雙鍵字典** | 1. `engine.py:934-1046` 雙參數（`spaces` vs `space`, `include_snippet` vs `snippet`, `space_name` vs `space`）<br/>2. `linker.py:59,464` `_overloads_by_fqn` 與 `resolve_call_site(..., file_symbols)`<br/>3. `resolver.py:119-125,361-367,432,749-1066` 屬性別名與 `query_*` 回傳雙鍵重複（`status`/`resolution_status`, `query`/`target_query`, `target`/`target_symbol`, `total_impacted_symbols`/`total_affected_symbols`）<br/>4. `schema.py:435,521-522` `ASTSnapshot.space_stats` 與 `OutlineNode.to_dict()` 雙鍵 `children`/`members` | 僅 `tests/test_overload_and_topology.py:92,100,128,146,174,177` 與 `docs/ast/README.md:94` 使用舊別名鍵 | 收斂為單一正統參數與單一字典鍵名（`OutlineNode.to_dict()` 統一為 `members`），同步更新 `test_overload_and_topology.py` 與 `formatter.py` |
| **孤兒死代碼** | 1. `formatter.py:18-45` `AUTO_BUDGET_CHARS` 等 7 個常數與 `compute_dynamic_snippet_lines`<br/>2. `bundler.py:675-729,940-949` `bundle_space`, `import_bundle`<br/>3. `linker.py:614-626` `TopologyLinker.build_graph`<br/>4. `resolver.py:300-328` `SymbolSelector.find_matches`<br/>5. `provisioner.py:48-50` `GrammarProvisioner.get_instance`<br/>6. `schema.py:133-159` `ASTContributes` 與 `exceptions.py:18-28` 3 個未拋出例外類別 | 全空間 `0` 引用 | 直接物理移除（或將 `TopologyLinker.build_graph` 改由 `engine.py:291-294` 實際呼叫以消除手動迴圈） |

---

### 2.2 D1 ~ D5 五維度分級診斷矩陣

| 模組 | 檔案路徑:行號區間 | 維度 | 嚴重度 | 具體結構病徵 | 對應策略 |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **`file-space`** | `file_space/scanner.py:304-367, 1024, 1159, 1184-1275` & `service.py:11-12` | `D2` | **P1** | `BinarySnapshotManager.save/load` 與 `FingerprintScanner` 尾段 6 個 Legacy 方法 0 引用；且 `scanner.py` 方法內延遲匯入 `from .service import is_watcher_active` 與 `service.py` 形成雙向依賴 | `S2` |
| **`file-space`** | `file_space/schema.py:180, 211-247, 312-369` & `manager.py:96-120, 217-220, 229, 316, 565-583` | `D2` | **P1** | `Mode A` 殘留 `FileSpaceDef`、`FileFingerprint`/`ScanDiffResult` 舊版相容建構子、`knowledge-db` 舊空間發現回退、`get_space_config` 別名與 `get_space_storage_dir` 死代碼 | `S2`, `S5` |
| **`file-space`** | `file_space/scanner.py:167-185, 448-466` & `scripts/cli.py:65-389` | `D3` | **P1** | `save_state` 與 `set_cursor` 重複編寫 `tempfile.mkstemp + fsync + os.replace` 原子寫入樣板；`cli.py` 5 個命令重複異常攔截與雙模輸出骨架 | `S3` |
| **`file-space`** | `file_space/manager.py:221-293, 378-500, 811-828` & `scanner.py:652-831` | `D1` | **P2** | `load_spaces` 與 `scan_space` 單一方法超過 120~170 行；`_is_dir_excluded` 與 `FileSpaceConfig.is_file_included` 路徑排除匹配可提取共用純函式 | `S1`, `S2` |
| **`file-space`** | `file_space/providers.py:9-18, 48-49`、`service.py:408, 425`、`scripts/cli.py:340`、`scripts/hook.dev.py:2,8,21,24` | `D4`/`D5` | **P2** | 未註冊之 `get_file_space_names` 與舊名別名、未讀取之死屬性寫入 (`_watcher_active`, `mgr_check`) 及 `hook.dev.py` 舊模組名 `.cache/space` | `S2`, `S5` |
| **`ast`** | `ast_engine/engine.py:353-508, 617-932`、`bundler.py:451-594`、`scripts/cli.py:234-402` | `D1` | **P1** | `hot_patch_index` (156L)、`outline` (316L，內嵌 5 個深層閉包)、`_normalize_space_dirty_paths` (144L) 與 `_run_topology_cli_command` (169L) 混雜高階編排與底層轉換細節 | `S1`, `S2` |
| **`ast`** | `ast_engine/{__init__.py:108-221, formatter.py:18-45,644-676, bundler.py:675-729,940-949, linker.py:59,614-626, resolver.py:119-125,300-328, schema.py:133-159,435, exceptions.py:18-28}` | `D2` | **P1** | `Mode A` 殘留頂層與 Formatter 轉發殼、相容別名及經雙重查證 0 引用之孤兒死代碼 | `S2`, `S6` |
| **`ast`** | `ast_engine/{bundler.py:414-421,477,646,704-713,806-816,902-912, resolver.py:741-1068, parsers/css_parser.py:23, parsers/html_parser.py:41}` | `D3` | **P1** | 跨方法/跨檔案重複出現「專案相對路徑推導」、「檔案讀取+解析+Overload 去重」、「`query_callers/callees/impact` 前置解析與歧義/未命中回傳字典」同構樣板 | `S3`, `S4` |
| **`ast`** | `ast_engine/{schema.py:508-524, resolver.py:422-434,746-1068, engine.py:934-1046, linker.py:459-497}` | `D4` | **P1** | `OutlineNode.to_dict()` 同時包含 `children` 與 `members` 雙重鍵；`query_*` 回傳字典含雙套同義鍵；`resolve_call_site` 回傳型別隨 `file_symbols` 變異 | `S5` |
| **`ast`** | `ast_engine/{parsers/treesitter.py:437, parsers/registry.py:223-224, bundler.py:3, engine.py:8,626, linker.py:3, resolver.py:4,380}` | `D5` | **P2** | `treesitter.py` 殘留探測上層 `knowledge-db/assets/queries` 路徑、`registry.py` 殘留 `knowledge_db.parsers.` 字串轉換；Docstring 含 `Migrated from...` 與 `uitk.net Boundary` 歷史標記 | `S5`, `S6` |

*(註：兩模組之檔案拓撲職責均正交清晰，完全符合 `CodeQualityStandards.md §3.6` 三大免拆守門，故 **`P0 = 0`**，無須執行破壞高內聚狀態機的物理拆檔 `S6`)*

---

### 2.3 S1 ~ S6 外科手術重構處方箋 (Refactoring Blueprint)

1. **`S1`（業務階段拆解與主幹管線化）**：
   - **`file-space`**：將 `FileSpaceManager.load_spaces` 與 `FingerprintScanner.scan_space` 拆解為具名階段輔助函式（`_merge_space_definition`、`_prepare_previous_state`、`_evaluate_entry_fingerprint`）。
   - **`ast`**：將 `ASTEngine.outline` 內部 5 個深層巢狀閉包提昇為模組級純輔助函式（`_member_to_outline_node`, `_build_outline_tree`, `_filter_outline_nodes`），使 `outline()` 收斂為高階管線；將 `ASTEngine.hot_patch_index` 拆解為 `_evict_dirty_and_reaggregate_partials` 與 `_relink_and_reconnect_edges`；將 `scripts/cli.py:_run_topology_cli_command` 之 JSON 負載組裝拆為獨立輔助函式。
2. **`S2`（無狀態純函式剝離、解除 `scanner <-> service` 雙向匯入與零轉發殼清理）**：
   - 將 `is_watcher_active` / `mark_watcher_dirty` 狀態旗標檢查下沉或透過輕量模組級探針解耦 `scanner.py` 對 `service.py` 的反向延遲匯入。
   - 剝離 `SpiceParser._split_tokens`、`_parse_params_from_line` 為模組級純函式並刪除原類別轉發殼。
   - 按 `§2.1` 清單物理拔除 `file-space` 與 `ast` 所有 `Mode A` 過渡別名、薄轉發函式與 0 引用死代碼，並同步更新 `tests/` 調用點。
3. **`S3` & `S4`（跨方法同構模式聚合與控制流扁平化）**：
   - 於 `file_space/scanner.py` 提取共用原子寫檔輔助函式 `_atomic_write_bytes`，供 `BinarySnapshotManager.save_state` 與 `CursorStore.set_cursor` 共用。
   - 於 `ast_engine/io_utils.py` 集中專案根目錄與相對路徑正規化輔助函式，消除 `bundler.py`、`engine.py`、`formatter.py` 重複實作。
   - 於 `ast_engine/bundler.py` 提取 `_parse_and_dedup_file` 共用單檔解析與 Overload ID 去重邏輯；於 `ast_engine/resolver.py` 提取共用前置解析與 `not_found` / `ambiguous` 結構化回傳骨架。
4. **`S5`（介面契約單一化與零歷史標記純化）**：
   - 將 `OutlineNode.to_dict()` 收斂為單一 `"members"` 鍵（消除 `"children"` 雙份序列化），收斂 `ASTEngine` 與 `resolver.py` 的雙重同義參數/回傳鍵名，並使 `TopologyLinker.resolve_call_site` 固定回傳單一 `Optional[str]`。
   - 拔除 `file_space/manager.py`、`ast_engine/parsers/treesitter.py` 與 `registry.py` 對上層 `knowledge-db` 的殘留路徑/字串依賴，修正 `file-space/scripts/hook.dev.py` 為 `file-space`，並清理所有 `Migrated from...`、`uitk.net Boundary` 等歷史工單註解噪音。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  `module:file-space` 與 `module:ast` 的核心架構與模組分檔邊界均已正交健全（**`P0 = 0`**），但在快速模組化抽離與演進過程中，累積了 **7 項 `P1` 結構耦合/過渡包袱**（包含 `Mode A` 待清理的過渡別名、薄轉發殼層、0 引用孤兒死代碼、`scanner <-> service` 方法內延遲雙向匯入、`OutlineNode.to_dict()` 雙鍵序列化與長方法內嵌閉包）以及 **3 項 `P2` 歷史標記註解與跨層路徑殘留**。
- **後續建議（選填）**：

### 3.1 風險評估與推薦流轉出口
- **推薦流轉出口**：推薦選擇 **【出口 ①：立即原地升級實作（Full Track）】**，於當前計畫 `2026_11_02_2133_file_space_and_ast_code_optimization_audit` 原地升級執行 `Mode A` 無損重構與清理，並通過 `file-space`（15 項）、`ast`（18 項）與下游 `knowledge-db`（103 項）全量回歸測試驗證。
