# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：GitHub Issue #8 四大跨模組缺陷與架構完善修復 (server / knowledge-db / agents-workflow)  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `server` 狀態讀取修復與 `stop` 防孤兒鎖保護 | 1. 修正 `server/master.py:read_daemon_state(yscb_root)`，移除傳給 `vfs.read_json(state_file)` 的無效 `default=None` 參數，使 `server status`、`server stop`、`server reload` 與 `server start` 正確讀取運作中 Daemon 之 `ServerDaemonState`。<br/>2. 於 `server/scripts/cli.py:stop()` 中，當 `read_daemon_state` 為 `None` 時，刪除 `daemon.json` 前必須先以非阻塞方式探測 `.cache/server/daemon.lock`；若鎖仍被持有（Daemon 存活），嚴禁刪除 `daemon.json`。 | P0 | [P00:DR-01] |
| **FR-02** | 跨執行模式（Cold / Warm Worker / ProcessPool）自訂解析器動態載入與內建 Parser 副檔名擴充 | 1. 於 `server/master.py:_spawn_worker_locked` 與 `server/worker.py:WarmWorker.pre_warm` 中，將經解析之專案根目錄 (`project://`) 與宿主根目錄 (`yscb.host://`) 納入安全 `PYTHONPATH` / `sys.path`（嚴守不注入 `ys_codebase/source/` 護欄）。<br/>2. 於 `knowledge_db/parsers/registry.py:ParserRegistry` 中，載入 `languages` 時支援：<br/>  • `parser_entry` 為語意 URI（如 `project://yscb_parsers/site_parsers.py:AstroParser` 或 `module://<donor>/...:Cls`）或相對於 `project://` / `module://<__provider__>` 之檔案路徑，以及標準模組路徑 `pkg.mod:ClassName`（自動確保 `project://`、`yscb.host://` 與 `module://<__provider__>` 在 `sys.path` 中可達，包含 `ProcessPoolExecutor` 子進程）。<br/>  • 實例化 `mode: "custom"` 解析器後，將 `LanguageConfig.extensions` 正規化並動態合併至解析器實例之 `SUPPORTED_EXTENSIONS`（若存在）或綁定 `_configured_extensions`，使 `HtmlParser`、`CssParser`、`SpiceParser` 及自訂 `BaseParser` 可直接透過 `contribute.json` 動態擴充副檔名（如 `.astro`）。 | P0 | [P00:DR-02] |
| **FR-03** | 解析器載入異常之顯式可觀測性 (`load_errors` 暴露與警告) | 1. 於 `ParserRegistry` 新增 `self.load_errors: Dict[str, str]` 記錄所有載入失敗之語言 ID 與錯誤原因（涵蓋 `custom` 與 `tree_sitter` 模式）。<br/>2. 於 `knowledge_db/engine.py:get_engine()` 中，若既有單例之 `parser_registry.load_errors` 非空，自動重試載入以支援熱修復。<br/>3. 於 `knowledge_db/engine.py:status()` 回傳字典中新增 `"parser_load_errors"` 欄位；於 `knowledge-db/scripts/cli.py` 之 `status` 與 `index` 指令執行時，若 `parser_load_errors` 非空則向 `stderr` / 終端機顯式輸出警告訊息。 | P0 | [P00:DR-03] |
| **FR-04** | `plan verify` 與 `plan status` 提示路徑動態對齊活躍 `release_targets` | 於 `agents_workflow/plans/_common.py` 新增動態投影路徑解析函式 `resolve_active_target_projected_path(artifact_type, artifact_name, subpath)`，依據 `ReleaseTargetManager.get_classified_targets()["union"]` 與 `ArtifactCompiler.get_release_targets()` 將 `verifier.py:_build_next_phase_hint` 的模板路徑與 `status.py:PlanStatusResolver.resolve_next_action` 的技能參考路徑動態映射至當前啟用之 Target（例如僅啟用 `claude` 時輸出 `.claude/.yscb/templates/...` 與 `.claude/skills/...`）。 | P0 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `daemon.json` 寫入中或損毀，但 Master Daemon 仍持有 `daemon.lock` | `read_daemon_state` 捕獲 `(OSError, ValueError, TypeError, KeyError)` 安全回傳 `None`；`cli.py:stop()` 探測到 `daemon.lock` 被持有時不刪除 `daemon.json`，避免製造孤兒程序。 |
| **EC-02** | 使用者在 `config/knowledge-db/contribute.json` 註冊不存在的 `parser_entry` 模組或類別 | `ParserRegistry` 捕獲例外並寫入 `self.load_errors[cfg.id]`，不中斷其他語言解析器註冊，並在 `knowledge-db index` 與 `status` 輸出明確警告。 |
| **EC-03** | 使用者在 `contribute.json` 覆寫內建 `"html"` 語言的 `extensions: [".html", ".htm", ".astro"]` 或新增 `"astro"` 指向 `HtmlParser` | `ParserRegistry` 將 `cfg.extensions` 合併至該 `HtmlParser` 實例級別的 `SUPPORTED_EXTENSIONS` 副本（不污染類別屬性），使 `can_parse("page.astro")` 回傳 `True`。 |
| **EC-04** | 專案未設定或清空 `release_targets`，或在獨立沙盒測試中無 `config` | `resolve_active_target_projected_path` 自動退回預設 `.agents/.yscb/templates/...` 與 `.agents/skills/...`，確保 100% 向後相容。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構安全護欄 | 100% 遵守 `Zero Source Path Injection` 剛性約束：`server` 與 `core` 運行時嚴禁將 `ys_codebase/source/` 注入 `sys.path` 或 `PYTHONPATH`（`test_worker_and_master_zero_source_path_injection` 100% 通過）。 |
| **NFR-02** | 零外部新依賴与測試全綠 | 100% 使用 Python 標準庫與既有核心介面；`server`、`knowledge-db`、`agents-workflow` 沙盒測試 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `test_worker_and_master_zero_source_path_injection` 嚴格檢查 `PYTHONPATH` 與 `sys.path` 不得包含 `/source`；在母倉 Dogfooding 環境中，`project://` 為 `/workspace/ys-codebase`（不含 `/source`），注入 `project://` 與 `yscb.host://` 完全合規且安全。
- **`[!NOTE]`** 修改實例的 `SUPPORTED_EXTENSIONS` 時必須賦值新的 `set` 實例（`inst.SUPPORTED_EXTENSIONS = set( existing ) | configured_exts`），切勿直接 `inst.SUPPORTED_EXTENSIONS.update(...)` 原地變異類別共享集合。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Issue #8 Fix Architecture]
  ├── 1. server (Daemon State & Worker Path)
  │     ├── master.py:read_daemon_state() ──> vfs.read_json(state_file) [No default kwarg]
  │     ├── scripts/cli.py:stop()         ──> Probe InterProcessLock(daemon.lock) before removing daemon.json
  │     └── master.py & worker.py         ──> Inject project:// & yscb.host:// into worker PYTHONPATH / sys.path
  │
  ├── 2. knowledge-db (Custom Parser & Observability)
  │     ├── parsers/registry.py           ──> _ensure_parser_search_paths(project://, yscb.host://, module://<provider>)
  │     │                                 ──> Support URI/file-path & module:Class in _load_custom_parser()
  │     │                                 ──> Bind cfg.extensions onto parser instance & record load_errors
  │     └── engine.py & scripts/cli.py    ──> Expose parser_load_errors in status() and print warnings in status/index
  │
  └── 3. agents-workflow (Dynamic Target Projection Paths)
        ├── plans/_common.py              ──> resolve_active_target_projected_path(artifact_type, name, subpath)
        ├── plans/verifier.py             ──> _build_next_phase_hint() uses dynamic template path
        └── plans/status.py               ──> resolve_next_action() uses dynamic skill reference paths
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/master.py` | Modify | 移除 `read_daemon_state` 中 `vfs.read_json` 的 `default=None` 參數；於 `_spawn_worker_locked` 將宿主/專案根目錄納入 `PYTHONPATH`。 |
| `ys_codebase/source/server/server/worker.py` | Modify | 於 `WarmWorker.pre_warm` 確保 `project://` 與 `yscb.host://` 位於 `sys.path`，使 `pre_warm` 階段即可載入專案自訂解析器。 |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 於 `stop()` 刪除殘留 `daemon.json` 前先非阻塞檢查 `daemon.lock` 是否被持有。 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增 `read_daemon_state` 讀寫往返與 `stop()` 防誤刪鎖保護測試。 |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py` | Modify | 支援 `project://` / `yscb.host://` / `module://<__provider__>` 路徑注入與 URI `parser_entry` 載入；動態將 `cfg.extensions` 綁定至 `custom` Parser 實例；新增 `self.load_errors` 紀錄。 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 於 `get_engine()` 當 `load_errors` 非空時支援重試載入；於 `status()` 附加 `parser_load_errors`。 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 於 `status` 與 `index` 指令檢測並顯式輸出 `parser_load_errors` 警告。 |
| `ys_codebase/source/knowledge-db/tests/test_parsers.py` | Modify | 新增專案自訂解析器跨路徑載入、內建 `HtmlParser` 動態擴充 `.astro` 副檔名及 `load_errors` 警告測試。 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py` | Modify | 新增 `resolve_active_target_projected_path` 動態讀取活躍 `release_targets` 投影路徑。 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `_build_next_phase_hint` 改用 `resolve_active_target_projected_path("template", tmpl_name)`。 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | `resolve_next_action` 改用 `resolve_active_target_projected_path("skill", ...)`。 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增僅啟用 `claude` Target 時 `plan verify` 與 `resolve_next_action` 動態回傳 `.claude/...` 路徑之測試。 |
| `docs/knowledge-db/contributes_guide.md` | Modify | 補充專案自訂解析器 (`project://` / 專案根目錄套件) 放置規範與複用內建解析器擴充副檔名之範例。 |
| `docs/knowledge-db/parsers.md` | Modify | 同步更新自訂解析器 `contribute.json` 宣告與錯誤診斷說明。 |
| `docs/server/DESIGN_NOTES.md` | Modify | 更新 `read_daemon_state` 與 Worker `project://` 路徑載入說明。 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `ParserRegistry` 自包含路徑解析（Self-Contained Path Resolution）**：
  - 除在 `server/worker.py` 注入 `project://` 與 `yscb.host://` 外，`ParserRegistry._load_from_contributes()` 自身亦主動解析 `project://`、`yscb.host://` 與各語言定義之 `__provider__` (`module://<provider>`) 並確保其在 `sys.path` 中；這保證了即使在 `ProcessPoolExecutor` 子進程（`_get_worker_registry()`）或獨立腳本呼叫時，無須依賴外部啟動器也能 100% 載入專案與第三方模組解析器。
- **[P02:DR-02] `custom` 解析器實例級別副檔名綁定**：
  - 於 `ParserRegistry._bind_configured_extensions(parser_inst, cfg.extensions)` 中，將 `cfg.extensions` 正規化為小寫前導點號集合；若 `parser_inst` 具有 `SUPPORTED_EXTENSIONS` 屬性，則在實例上建立新集合 `parser_inst.SUPPORTED_EXTENSIONS = set(parser_inst.SUPPORTED_EXTENSIONS) | norm_exts`（不污染類別屬性），使內建 `HtmlParser`、`CssParser`、`SpiceParser` 與使用者自訂 `BaseParser` 均可直接響應 `contribute.json` 的副檔名設定。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/server/server/master.py
def read_daemon_state(yscb_root: str) -> Optional[ServerDaemonState]: ...

# ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py
class ParserRegistry:
    load_errors: Dict[str, str]
    def _ensure_search_paths(self, provider: Optional[str] = None) -> None: ...
    def _instantiate_custom_parser(self, entry_str: str, provider: Optional[str] = None) -> BaseParser: ...
    @staticmethod
    def _bind_configured_extensions(parser_inst: BaseParser, extensions: Tuple[str, ...]) -> None: ...

# ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py
def resolve_active_target_projected_path(
    artifact_type: str,
    artifact_name: str = "",
    subpath: str = "",
) -> str: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `read_daemon_state`：當檔案不存在、JSON 格式損毀或欄位不匹配時捕獲 `(OSError, ValueError, TypeError, KeyError)` 並回傳 `None`，絕不向外拋出未處理例外。
  - `ParserRegistry`：單一語言解析器載入失敗時捕獲 `Exception`，將錯誤字串存入 `self.load_errors[lang_id]` 並發送 `logger.warning`，不阻斷其餘語言載入。
  - `resolve_active_target_projected_path`：讀取組態或 Target 定義發生任何異常或無活躍 Target 時，無條件回退至預設 `.agents/...` 路徑。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有既有公開方法簽名 100% 向後相容，`status()` 字典以擴充鍵 `"parser_load_errors"` 方式提供診斷資訊。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  1. *Q：在 `master.py` / `worker.py` 將 `project://` 加入 `PYTHONPATH` / `sys.path`，是否會違反 `test_worker_and_master_zero_source_path_injection`？*
     - **A**：`test_worker_and_master_zero_source_path_injection` 檢驗的是路徑中不得含有 `/source/` 或以 `/source` 結尾（防止直接載入 `ys_codebase/source/<mod>` 未編譯模組源碼）。`project://` 與 `yscb.host://` 指向的是專案根目錄（例如 `/workspace/ys-codebase`），不含 `/source`，且我們在注入前會明確過濾任何含 `/source` 的路徑，100% 通過該安全斷言。
  2. *Q：當使用者先啟動 Server（此時 `yscb_parsers` 尚未建立，產生 `load_errors`），隨後才在專案根目錄建立 `yscb_parsers/site_parsers.py` 並執行 `knowledge-db index`，Warm Worker 能否自動載入？*
     - **A**：可以！透過在 `get_engine()` 及 `build_index()` 檢查 `if engine.parser_registry.load_errors:` 自動觸發 `importlib.invalidate_caches()` 與重新載入，使用者無須手動重啟 Server 即可自癒載入新建立的解析器。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | N/A | 既有架構總覽無變更 |
| **專題手冊** | `docs/knowledge-db/contributes_guide.md`, `docs/knowledge-db/parsers.md` | Modify | 補充專案自訂解析器 (`project://` 與模組入口) 在 Server 與 Cold 模式下的放置規範、URI 語法與內建解析器副檔名擴充說明 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 更新 `[DN-08]` 補充 `read_daemon_state` 契約與 Worker 宿主/專案路徑載入機制 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `read_daemon_state`、`ParserRegistry`、`resolve_active_target_projected_path` Docstring |
| **發布日誌** | CHANGELOG.md | Modify | 於 Phase 7 結案時記錄本計畫修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認三模組聯動修復範圍與測試矩陣，通過 Pre-Code Analyze Gate。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修復 `server` 模組 `read_daemon_state`、`cli.py:stop()` 防誤刪鎖檢查及 Worker 專案根目錄路徑載入（`FR-01`, `FR-02`, `EC-01`）
- [x] **TASK-02**：升級 `knowledge-db` 模組 `ParserRegistry`（支援 `project://`/`yscb.host://`/`module://<provider>` 與 URI `parser_entry`、動態副檔名綁定、`load_errors` 自癒與 `index`/`status` 警告輸出）（`FR-02`, `FR-03`, `EC-02`, `EC-03`）
- [x] **TASK-03**：升級 `agents-workflow` 模組 `plans/{_common,verifier,status}.py` 支援依活躍 `release_targets` 動態映射模板與技能提示路徑（`FR-04`, `EC-04`）
- [x] **TASK-04**：編寫並執行 `server`、`knowledge-db`、`agents-workflow` 單元與邊界測試，完成 `@build` 熱部署與實機驗證（`NFR-01`, `NFR-02`）
- [x] **TASK-DOC**：同步更新 `docs/knowledge-db/{contributes_guide,parsers}.md` 與 `docs/server/DESIGN_NOTES.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
