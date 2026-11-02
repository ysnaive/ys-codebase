# 技術調研報告 (Technical Research Report)

> 調研主題：`knowledge-db` 空間與指紋底座遷移重構之五維度靜態診斷報告 (`Mode A`)  
> 建立日期：2026-11-02  
> 所屬計畫：2026_11_02_0339_module_space_feasibility_research / sub_02_knowledge_db_space_migration  
> 狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

隨 `module:space`（`R03` 生態系共享空間、指紋快照與單一 `space-watcher` 契約）確立，`ys_codebase/source/knowledge-db/` 內部原生的空間幾何解析（`knowledge_db/space.py`）、`YFP1` 二進位指紋掃描器（`knowledge_db/scanner.py`）與專屬 `watchdog` 常駐工作者（`knowledge_db/service.py`）已演變為跨模組重複基建。

本報告以 `/code-optimizer` 之 `Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)` 對 `ys_codebase/source/knowledge-db/` 展開五維度（`D1~D5`）冷眼靜態審查，旨在：
1. 盤點應**物理刪除**之重複底座檔案、組態與冗餘測試（零容忍保留薄轉發包裝層或相容別名）。
2. 鎖定所有引用舊符號之內部與測試調用點（`Callers to Update`）及跨模組協同邊界（`[Cross-Module Mode A Handoff]`）。
3. 診斷保留業務模組（`engine.py`、`pipeline.py`、`bundler.py`、`retrieval.py`、`formatter.py`、`providers.py` 等）之結構病徵，開立 `S1~S6` 外科手術重構處方箋。

### 1.1 定錨基準與範圍摘要

| 定錨維度 | 核定基準 |
| :--- | :--- |
| **檢視範圍 (Scope)** | **單一模組 (`Module Scope: ys_codebase/source/knowledge-db/`)**：涵蓋 `manifest.json`、`contributes/*.json`、`knowledge_db/**/*.py`、`scripts/*.py`、`tests/*.py` 及宿主組態 `ys_codebase/config/knowledge-db/contribute.json` |
| **生命週期模式 (Lifecycle Mode)** | **`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**：強制收斂為 `from space import ...` 單一正統入口，物理移除舊空間與掃描底座，同步改寫所有內部與測試調用點 |
| **代理執行軌道 (Execution Track)** | **`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`**：原型 ② 冷眼靜態審查員（`Mode II` 直接落檔 + 極簡收據） |
| **對齊前置契約** | `plans/2026_11_02_0339_module_space_feasibility_research/R03_ecosystem_contracts_and_cli_design.md` |

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 契約邊界與內部工具函式查驗表

#### 一、物理刪除清單 (`Mode A` 零轉發包裝層 — 共 6 項)

| 檔案路徑 | 行數 | 刪除理據与 `module:space` 替代映射 |
| :--- | :--- | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/space.py` | L1-L208 | `SpaceManager` 空間幾何解析、URI 映射與 `include/exclude` 邏輯 100% 由 `space.SpaceManager` 取代 |
| `ys_codebase/source/knowledge-db/knowledge_db/scanner.py` | L1-L430 | `BinarySnapshotManager (YFP1)`、`FingerprintScanner`、`FileFingerprint`、`ScanDiffResult`、`ScanDiffDetail` 100% 由 `space` 之 `YFP2` 快照與 `space.consume_diff` 游標交易取代 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | L1-L336 | `KnowledgeDBServiceWorker` (`knowledge-db-watcher`) 與 `resolve_watch_extensions` 由 `module:space` 單一 `space-watcher` + `scripts/hook.space.py` 事件訂閱取代 |
| `ys_codebase/source/knowledge-db/contributes/server.json` | L1-L10 | 移除 `knowledge-db-watcher` 常駐服務宣告，確保全系統僅保留 `module:space` 單一 `watchdog.Observer` |
| `ys_codebase/source/knowledge-db/tests/test_scanner.py` | L1-L182 | 純 `scanner.py` (`YFP1` / `FingerprintScanner`) 單元測試，職責已上移至 `module:space` 測試集 |
| `ys_codebase/config/knowledge-db/contribute.json` | L1-L19 | 原宣告宿主 `spaces.source` 幾何邊界；依 `R03` §2.3 遷移至 `ys_codebase/config/space/contribute.json`（若無專案自訂 `space_weights` 可直接移除或清空） |

#### 二、正統入口收斂與死代碼清理清單 (`Canonical Entry & Dead Symbols`)

| 模組 / 檔案 | 處置動作 | 目標符號與位置 | `Mode A` 正統收斂契約 |
| :--- | :--- | :--- | :--- |
| `knowledge_db/__init__.py` | **移除重導出** | `FileFingerprint`, `FingerprintScanner`, `ScanDiffResult` (L11-L15, L62-L64)、`SpaceManager` (L17, L76)、`FingerprintCorruptedError`, `InvalidSpaceConfigError`, `SpaceNotFoundError` (L38, L45, L52, L65, L69, L80)、`SpaceConfig`, `SpaceOrigin` (L24-L25, L73, L79) | 外部與測試統一改為 `from space import SpaceManager, SpaceConfig, SpaceOrigin, FileFingerprint, ScanDiffResult, ScanDiffDetail, SpaceNotFoundError, InvalidSpaceConfigError, consume_diff` |
| `knowledge_db/exceptions.py` | **刪除類別** | `SpaceNotFoundError` (L12-L16)、`InvalidSpaceConfigError` (L19-L23)、`FingerprintCorruptedError` (L26-L33) | 空間與指紋異常統一由 `space` 拋出；`FingerprintCorruptedError` 於 `scanner.py` 刪除後在 `knowledge-db` 內為 `0` 引用死代碼 |
| `knowledge_db/schema.py` | **刪除/瘦身** | `SpaceOrigin` (L51-L55)、`SpaceConfig` (L340-L391)、`SpaceDef` (L394-L399) | 刪除幾何 Schema；`KnowledgeDBContributes` (L401-L418) 將 `spaces: Dict[str, SpaceConfig]` 替換為 `space_weights: Dict[str, float]`（校驗 `> 0`） |
| `knowledge_db/formatter.py` | **移除死參數** | `ResultFormatter.__init__(..., space_manager=None)` (L228, L233) | `self.space_manager` 在 `ResultFormatter` 全檔 `0` 處讀取，直接移除該建構子參數與屬性賦值 |
| `knowledge_db/bundler.py` | **消除越界調用** | `self.scanner._iter_eligible_files(sp)` (L315, L357) | 嚴禁跨物件調用底線私有方法；改調用 `space_manager` 公開列舉 API 或當前快照紀錄 |
| `knowledge_db/engine.py` | **消除越界調用** | `self.scanner._file_belongs_to_space(p, sp)` (L205) | 改由 `space` 公開空間歸屬查詢或 `consume_diff(space=name)` 取得各空間統計 |

#### 三、`Mode A` 需同步改寫之調用方清單 (`Callers to Update`)

| 類別 | 檔案路徑與行號 | 現況舊符號引用 | `Mode A` 同步改寫規格 |
| :--- | :--- | :--- | :--- |
| **組態與宣告** | `ys_codebase/source/knowledge-db/manifest.json:L6-L33` | 無 `space` 依賴；宣告 `watchdog>=4.0.0`；`onboarding` 指向 `config/knowledge-db/contribute.json` | `dependencies` 加入 `"space": ">=1.0.0"`；移除 `pip_dependencies` 之 `watchdog`；`onboarding` 改指 `config/space/contribute.json` |
| **組態與宣告** | `ys_codebase/source/knowledge-db/contributes/_format.json:L1-L34` | 定義 `_types.SpaceDef` 與 `spaces` | 移除 `SpaceDef` 與 `spaces`，改定義 `"space_weights": {"format": {"*": "float!"}}` |
| **組態與宣告** | `ys_codebase/source/knowledge-db/contributes/core.json:L24-L30` | `status` 子命令含 `--scan` / `--diff` (`mode.scan`) | 移除 `--scan` / `--diff` 旗標（指紋掃描歸屬 `yscb.py space scan/diff`） |
| **組態與宣告** | `ys_codebase/source/knowledge-db/contributes/agents-workflow.json:L1-L16` | 現有 `skill_injections` 與 `standards` | 維持現有注入，無空間幾何耦合（`Pass`） |
| **核心引擎** | `ys_codebase/source/knowledge-db/knowledge_db/engine.py:L20-L22, L44-L55, L88-L107, L184-L267` | 匯入 `.scanner`、`.space`；以 `space_manager.storage_dir` 作為索引根目錄；`status()` 直接讀 `unified.meta.bin`；提供 `scan()` | 改為 `from space import SpaceManager, consume_diff`；`storage_dir` 獨立透過 `core.uri.resolve("knowledge.storage://")` 解析（避免與 `cache://space/` 混用）；移除 `engine.scan()`；`status()` 結合 `space` 狀態與 `space_weights` |
| **索引管線** | `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:L28-L30, L86, L97, L231, L326-L330, L562-L568, L710-L795, L836-L841` | 讀寫 `unified.meta.bin` (`BinarySnapshotManager`)、檢查 `.watcher_active`/`.watcher_dirty`、調用 `scanner.check_invalidation`、從 `SpaceConfig.weight` 取權重 | 移除 `unified.meta.bin` 與 `.watcher_*` 私有檔案協議；JIT 與熱更新統一透過 `with space.consume_diff(consumer_id="knowledge-db") as diff:` 驅動；檢索權重改讀 `knowledge-db` 自身之 `space_weights` |
| **打包器** | `ys_codebase/source/knowledge-db/knowledge_db/bundler.py:L17-L19, L274-L280, L315, L357, L500-L524` | 匯入 `FingerprintScanner`, `ScanDiffDetail`, `SpaceManager`；透過 `storage_dir.parent.parent / "bundles"` 推算路徑 | 改從 `space` 匯入 `SpaceManager`, `ScanDiffDetail`；檔案列舉改用 `space` 公開 API；`bundles` 路徑直接對齊 `knowledge-db` 自身 `storage_dir / "bundles"`，並改用 `core.vfs` 原子寫入 |
| **檢索與呈現** | `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py:L187-L200` | `SnippetExtractor.resolve_file_path` 調用 `space_manager` | 對齊 `space.SpaceManager` 公開介面（方法簽名相容，僅需確認型別標註） |
| **CLI Provider** | `ys_codebase/source/knowledge-db/knowledge_db/providers.py:L8-L52` | `get_knowledge_db_spaces` 匯入 `.space.SpaceManager` 並讀取 `cfg.weight` | 改匯入 `from space import SpaceManager` 並合併 `contributes.get("knowledge-db")` 之 `space_weights` |
| **腳本入口** | `ys_codebase/source/knowledge-db/scripts/cli.py:L15, L66-L82, L115-L124` | 匯入 `SpaceNotFoundError` 自 `knowledge_db.exceptions`；處理 `mode == "scan"` | 改自 `space` 匯入 `SpaceNotFoundError`；移除 `mode == "scan"` 分支 |
| **事件鉤子** | `ys_codebase/source/knowledge-db/scripts/hook.space.py` *(新增)* | 原依賴 `service.py` 內部 `watchdog` | 新增 `on_space_changed(context, spaces, diff_summary)` 訂閱腳本，以 `consume_diff(consumer_id="knowledge-db")` 驅動 `engine.pipeline.hot_patch_unified_index(diff)` |
| **事件鉤子** | `ys_codebase/source/knowledge-db/scripts/hook.dev.py:L25-L30` | 建立 `cache_dir / "spaces"` | 改為確保 `cache_dir / "indices"`、`cache_dir / "bundles"`、`cache_dir / "models"` 存在，移除冗餘 `"spaces"` 子目錄建立 |
| **測試套件** | `tests/test_space.py`, `test_service_worker.py`, `test_hot_reload.py`, `test_engine.py`, `test_bundler.py`, `test_graph.py`, `test_schema.py` | 匯入 `knowledge_db.space` / `knowledge_db.scanner` / `knowledge_db.service` 或構造舊版 `"spaces"` contributes | 全面切換至 `from space import ...` 與 `space_weights` 組態契約；`test_service_worker.py` 移除 `KnowledgeDBServiceWorker` 測試並改測 `hook.space.py` 增量消費閉環 |

#### 四、跨模組協同邊界 (`[Cross-Module Mode A Handoff]`)

| 外部模組 / 路徑 | 協同變更項目（列入 Umbrella 計畫其他子計畫對接，本模組不越界修改） |
| :--- | :--- |
| `ys_codebase/config/space/contribute.json` | 承接原 `ys_codebase/config/knowledge-db/contribute.json` 之 `spaces.source` 幾何定義（`R03` §2.3） |
| `ys_codebase/source/agents-workflow/contributes/space.json` | 新增檔案，承接原 `agents-workflow/contributes/knowledge-db.json` 之 `docs` 與 `plans` 空間幾何定義（`R03` §2.3） |
| `ys_codebase/source/agents-workflow/contributes/knowledge-db.json` | 瘦身僅保留 `"space_weights": {"docs": 1.2, "plans": 0.85}`（`R03` §2.3） |

---

### 2.2 D1 ~ D5 五維度分級診斷矩陣

> **Pass 清單（高內聚且無結構病徵之檔案）**：
> `knowledge_db/config.py`、`knowledge_db/linker.py`、`knowledge_db/hybrid.py`、`knowledge_db/topology_query.py`、`knowledge_db/io_utils.py`、`knowledge_db/selector.py`、`knowledge_db/tokenizer.py`、`knowledge_db/parsers/base.py`、`knowledge_db/parsers/css_parser.py`、`knowledge_db/parsers/html_parser.py`、`knowledge_db/parsers/spice_parser.py`、`scripts/hook.server.py`、`tests/test_cli.py`、`tests/test_parsers.py`、`tests/test_retrieval.py`、`tests/test_selector.py`。

| 嚴重度 | 維度 | 檔案路徑與行號 | 結構病徵實證 (Code Smell Evidence) | 對應處方 |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | `D1` 職責與邊界<br/>`D5` 基建重複 | `knowledge_db/space.py:L1-L208`<br/>`knowledge_db/scanner.py:L1-L430`<br/>`knowledge_db/service.py:L1-L336`<br/>`contributes/server.json:L1-L10` | 與 `module:space` 100% 重複之空間解析、`YFP1` 快照讀寫及獨立 `watchdog.Observer` 背景服務，造成雙重磁碟 `stat` 走訪與雙常駐 watcher 資源競爭。 | `S6` 物理刪除，切換至 `from space import ...` 與 `scripts/hook.space.py` |
| **P0** | `D1` 職責與邊界<br/>`D5` 儲存根混用 | `knowledge_db/engine.py:L90-L107`<br/>`knowledge_db/bundler.py:L500-L505` | `KnowledgeEngine.__init__` 直接將 `self.storage_dir` 綁定為 `self.space_manager.storage_dir`。當 `space_manager` 切換至 `module:space`（指向 `cache://space/`）時，若不解耦，`knowledge-db` 的索引與模型將誤寫入 `cache://space/`；且 `bundler.py:L503` 依賴 `storage_dir.parent.parent / "bundles"` 脆弱相對階層推算路徑。 | `S5` 解耦 `knowledge-db` 專屬 `storage_dir`（`knowledge.storage://` $\to$ `cache://knowledge-db/`） |
| **P0** | `D1` 職責與邊界<br/>`D2` 耦合與狀態 | `knowledge_db/pipeline.py:L231, L326-L330, L562-L568, L710-L795` | `SearchPipeline` 自行維護 `unified.meta.bin` (`YFP1`) 與 `.watcher_active`/`.watcher_dirty` 標記檔，並在 `_ensure_jit_index_ready_locked` 內觸發全量 `scanner.check_invalidation`。 | `S1`, `S5` 廢除私有 `meta.bin` 與 `.watcher_*` 標記，全面改用 `space.consume_diff(consumer_id="knowledge-db")` 游標增量協議 |
| **P0** | `D2` 耦合與封裝 | `knowledge_db/bundler.py:L315, L357`<br/>`knowledge_db/engine.py:L205` | `ContextBundler.build_bundle` 與 `patch_bundle` 跨物件呼叫私有方法 `self.scanner._iter_eligible_files(sp)`；`engine.status` 跨物件呼叫 `self.scanner._file_belongs_to_space(p, sp)`，嚴重破壞封裝邊界。 | `S5` 改用 `space` 公開檔案列舉與空間歸屬 API |
| **P1** | `D1` 職責與邊界 | `contributes/_format.json:L1-L34`<br/>`knowledge_db/schema.py:L51-L55, L340-L418`<br/>`knowledge_db/exceptions.py:L12-L33`<br/>`knowledge_db/pipeline.py:L836-L841` | `knowledge-db` 仍持有幾何 Schema (`SpaceDef`, `SpaceConfig`, `SpaceOrigin`) 與空間/指紋異常定義，且檢索權重直接耦合於幾何結構 `SpaceConfig.weight`。 | `S5`, `S6` 移除幾何 Schema 與重複異常，收斂為純語意權重映射 `space_weights: Dict[str, float]` |
| **P1** | `D3` 結構同構重複 | `knowledge_db/pipeline.py:L385-L404`<br/>`knowledge_db/retrieval.py:L473-L489` | `SearchPipeline._evict_dirty_file_artifacts` 與 `InvertedIndex.patch_incremental` 存在 **100% 結構同構**之 18 行髒檔案路徑正規化與後綴/檔名匹配迴圈（`dirty_paths_norm` + `endswith("/" + dp)`）。 | `S2`, `S3` 提煉純函式 `match_dirty_path(file_path, dirty_paths_norm)` 至 `io_utils.py` 共用 |
| **P1** | `D3` 結構同構重複 | `knowledge_db/bundler.py:L540-L614` | `extract_all_call_sites_and_imports` (L540-L570) 與 `extract_dirty_call_sites_and_imports` (L572-L614) 主體迴圈（走訪 `unique_files`、計算 `primary_space`、查 `_file_symbols_cache`、開檔呼叫 `extract_call_sites` 與 `extract_imports`）高度重複，僅差在 `dirty_keys_norm` 過濾條件。 | `S3` 合併為單一共用提取核心 `_extract_call_sites_and_imports_core(..., dirty_file_paths=None)` |
| **P1** | `D5` 架構慣例偏離 | `knowledge_db/bundler.py:L508-L524` | `ContextBundler.export_bundle` 手動呼叫 `tempfile.mkstemp` + `os.fdopen` + `os.replace` 寫入 JSON，繞過專案標準 `core.vfs` 原子寫入基建（而同模組 `pipeline.py:L551` 已使用 `self.vfs`）。 | `S5` 統一透過 `core.vfs` 執行原子寫入 |
| **P2** | `D2` 死參數與死屬性 | `knowledge_db/formatter.py:L228, L233`<br/>`knowledge_db/engine.py:L150` | `ResultFormatter.__init__` 接收並保存 `self.space_manager = space_manager`，但全類別 `0` 處使用。 | `S2` 移除 `ResultFormatter` 之 `space_manager` 參數與 `engine.py:L150` 傳參 |
| **P2** | `D5` 歷史噪音註解 | `knowledge_db/graph.py:L159`<br/>`knowledge_db/embedding.py:L69, L399, L425`<br/>`knowledge_db/parsers/treesitter.py:L255, L294`<br/>`knowledge_db/parsers/registry.py:L93` | 殘留歷史計畫修訂標記註解，如 `(移除未使用參數 dirty_file_paths M-10)`、`(移除未使用之 _doc_id_to_idx M-10)`、`(FR-06)`、`(EC-01~03)`，違反 `documentation` 技能「註解只寫 Why 與不變量、嚴禁留存任務編號與變更歷史」之紀律。 | `S6` 順手清除歷史計畫編號噪音，保留純粹業務意圖說明 |

---

### 2.3 S1 ~ S6 外科手術重構處方箋 (Refactoring Blueprint)

#### 處方 1：管線與事件階段聚合 (`S1: Phase Extraction` + `S6: Module Consolidation`)
- **目標檔案**：`knowledge_db/pipeline.py`、`scripts/hook.space.py` *(新增)*、`knowledge_db/service.py` *(刪除)*、`contributes/server.json` *(刪除)*
- **手術步驟**：
  1. **物理刪除** `knowledge_db/service.py` 與 `contributes/server.json`，卸載 `knowledge-db-watcher`。
  2. **建立 `scripts/hook.space.py`**：實作 `on_space_changed(context, spaces: List[str], diff_summary: dict)`，內部使用 `with space.consume_diff(context=context, consumer_id="knowledge-db") as diff:`，當 `diff.has_changes` 為真時呼叫 `get_shared_engine(context).pipeline.hot_patch_unified_index(diff.detail)`，成功退場時由 Context Manager 自動執行 `ack()` 更新游標。
  3. **重構 `SearchPipeline._ensure_jit_index_ready_locked` (`pipeline.py:L726-L795`)**：
     - 移除 `_is_watcher_active` (L710-L724) 與 `.watcher_dirty` / `unified.meta.bin` 檢查。
     - 改為三段式清晰控制流：
       - **階段 A（冷啟動檢查）**：若 `unified.bm25.json` 不存在，直接呼叫 `build_unified_index()` 並以 `space.consume_diff` 同步游標。
       - **階段 B（游標增量檢查）**：開啟 `with space.consume_diff(context=self.context, consumer_id="knowledge-db") as diff:`，若 `!diff.has_changes`，僅在檔案 `mtime` 更新時執行 `_reload_caches_from_disk()` 後直接返回（零磁碟走訪開銷）。
       - **階段 C（增量熱修補或重建）**：若 `diff.has_changes` 且快取已載入，直接呼叫 `hot_patch_unified_index(diff.detail)`；否則重建。

#### 處方 2：儲存根解耦與組態契約收斂 (`S5: Contract Decoupling`)
- **目標檔案**：`knowledge_db/engine.py`、`knowledge_db/bundler.py`、`knowledge_db/schema.py`、`knowledge_db/exceptions.py`、`knowledge_db/providers.py`、`contributes/_format.json`、`manifest.json`
- **手術步驟**：
  1. **獨立解析 `knowledge-db` 儲存根 (`engine.py:L90-L107`)**：
     - `self.space_manager = SpaceManager(context=self.context)`（來自 `from space import SpaceManager`，其內部管理 `cache://space/`）。
     - `self.storage_dir` 獨立由傳入之 `storage_dir` 或 `self.context.get_module("core").uri.resolve("knowledge.storage://")` 解析（指向 `cache://knowledge-db/`），徹底切斷與 `space_manager.storage_dir` 的耦合。
  2. **修正 `ContextBundler.export_bundle` 路徑與 VFS 寫入 (`bundler.py:L500-L524`)**：
     - 將 `bundles_dir = storage_dir.parent.parent / "bundles"` 修正為直接使用 `knowledge-db` 自身 `storage_dir / "bundles"`，並透過 `self.context.get_module("core").vfs` 執行原子寫入。
  3. **替換私有掃描器調用 (`bundler.py:L315, L357` & `engine.py:L205`)**：
     - 移除 `self.scanner`，檔案清單取得改用 `space` 公開接口（如 `space_manager.iter_space_files(name)` 或快照記錄）。
  4. **組態與 Schema 純化 (`_format.json`, `schema.py`, `exceptions.py`, `pipeline.py:L836-L841`)**：
     - `_format.json` 與 `schema.py` 移除 `SpaceDef`、`SpaceConfig`、`SpaceOrigin`，改定義 `space_weights: Dict[str, float]`。
     - `pipeline._prepare_search_context_and_filters` 從 `knowledge-db` 自身 contributes 讀取 `space_weights`（未配置之空間預設權重為 `1.0`）。
     - `exceptions.py` 刪除 `SpaceNotFoundError`、`InvalidSpaceConfigError`、`FingerprintCorruptedError`，統一自 `space` 匯入空間異常。

#### 處方 3：同構重複折疊與無狀態純函式提煉 (`S2: Stateless Helper` + `S3: Dedup` + `S4: Guard Clauses`)
- **目標檔案**：`knowledge_db/io_utils.py`、`knowledge_db/pipeline.py`、`knowledge_db/retrieval.py`、`knowledge_db/bundler.py`、`knowledge_db/formatter.py`
- **手術步驟**：
  1. **提煉髒路徑匹配純函式 (`S2` + `S3`)**：
     - 於 `knowledge_db/io_utils.py` 新增 `normalize_dirty_paths(paths: Iterable[str]) -> Set[str]` 與 `is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool`。
     - 替換 `pipeline.py:L385-L404` (`_evict_dirty_file_artifacts`) 與 `retrieval.py:L473-L489` (`InvertedIndex.patch_incremental`) 兩處重複迴圈。
  2. **折疊呼叫點與匯入提取迴圈 (`S3` + `S4`)**：
     - 於 `bundler.py:L540-L614` 提煉 `_extract_call_sites_and_imports_core(self, spaces, file_Filter_fn=None)`，令 `extract_all_call_sites_and_imports` 與 `extract_dirty_call_sites_and_imports` 共用同一套走訪、快取查找與 AST 解析邏輯，消除 35 行重複代碼。
  3. **移除死參數 (`S2`)**：
     - 移除 `ResultFormatter.__init__` (`formatter.py:L228, L233`) 之 `space_manager` 參數，並同步更新 `engine.py:L150`。

---

## 3. 結論 (Conclusion)

1. **重複基建清理規模**：透過 `Mode A` 徹底移除 `knowledge_db/space.py` (208 行)、`knowledge_db/scanner.py` (430 行)、`knowledge_db/service.py` (336 行)、`contributes/server.json` (10 行) 與 `tests/test_scanner.py` (182 行)，共計可直接削減 **~1,166 行** 跨層重複基建與測試代碼。
2. **架構邊界純化成效**：
   - `knowledge-db` 退居純粹的「AST 符號圖譜、BM25/向量混合檢索與 `space_weights` 語意加權消費者」。
   - 徹底解決 `storage_dir` 混用隱患、`scanner._iter_eligible_files` 跨物件私有調用、以及雙 `watchdog` 常駐衝突。
   - 藉由 `S2/S3` 折疊 `pipeline.py` / `retrieval.py` / `bundler.py` 內部同構迴圈，進一步提升增量熱修補（Hot-Patch）管線的可維護性。

### 3.1 風險評估與推薦流轉出口

- **關鍵遷移風險與緩解**：
  1. **儲存路徑分離風險 (`P0`)**：若 `KnowledgeEngine` 繼續沿用 `self.space_manager.storage_dir`，遷移後索引將誤寫入 `cache://space/`。實作時必須優先落實「處方 2 第 1 點」，確保 `knowledge-db` 固定使用 `knowledge.storage://` (`cache://knowledge-db/`)。
  2. **跨模組組態同步風險 (`P0`)**：刪除 `config/knowledge-db/contribute.json` 與 `_format.json` 之 `spaces` 前，必須確認 `config/space/contribute.json` 與 `agents-workflow/contributes/space.json` 已同步就位，否則 `yscb.py check` 與空間載入將報錯。

> **[調研總結與流轉建議卡 (Research Conclusion & Next Step)]**
> - **推薦出口**：**出口 ①：直接升級立項實作 (Immediate Upgrade to Implementation)**
> - **執行建議**：本報告已完成 `sub_02_knowledge_db_space_migration` 之 `Mode A` 檔案級刪除清單、調用點映射與 `S1~S6` 處方定錨；建議主代理直接依據本報告 §2.1 與 §2.3 編列 `sub_02` 實作任務清單，並於 `sub_01 (module:space)` 底座就緒後推進實作與測試遷移。
