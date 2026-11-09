# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_core_runtime_context_and_namespace_loader  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：完成 `sub_01` 後，啟動第二個子計畫 `sub_02_core_runtime_context_and_namespace_loader`。
- **核心目標**：
  1. **`RuntimeContext` 實例化隔離容器與 `ContextVar` 執行期作用域（`core/context.py`）**：
     - 擴充 `ys_codebase/source/core/core/context.py`，建立 `RuntimeContext`（支援 `virtual_cwd`、請求級環境變數覆寫視圖 `env`、以及 URI / Config / Contributes / Locale / Commands / Symbols / Space 等子系統快取桶）與 `bind_runtime_context(...)` / `get_runtime_context(...)`（基於 `contextvars.ContextVar`），使同一進程內可安全隔離不同 `yscb_root` 沙盒實例與併發請求。
  2. **收斂 `module:core` 頂層可變快取、消除 `global`、`os.getcwd()` / `Path.cwd()`、裸 `input()`、`os.environ` 突變與非啟動器 `sys.exit()`**：
     - 收斂 `core` 內部 29 個頂層可變快取容器（`uri.py`, `config.py`, `contributes.py`, `commands/dispatcher.py`, `locale.py`, `symbols.py`, `gitignore.py`, `platform/process.py`, `platform/venv.py`, `space/registry.py`, `space/scanner.py`, `space/watcher.py`）至 `RuntimeContext`（或受控執行期單例容器），並透過 PEP 562 模組級 `__getattr__` 或委派屬性維持既有白箱測試（如 `uri._SCHEMES_CACHE`, `contributes._LAST_CLEAN_SCAN_TS`, `symbols._RESOLVED_CALLABLE_CACHE`, `dispatcher._MODULE_CACHE`）100% 向後相容。
     - 徹底消除 `core` 內部所有函式級 `global` 敘述、`os.getcwd()` / `Path.cwd()` 呼叫（統一改走 `RuntimeContext.get_cwd()` / `core.uri`）、`dispatcher.py` 執行期原地寫入 `os.environ`、`uri.py:reconcile_undefined_uri` 之裸 `input()` 與 `sys.exit(1)`，以及 `guard.py:guard_dispatch` 之 `sys.exit(126)`（改為 `raise SystemExit(126)`，100% 相容 `assertRaises(SystemExit)` 且消除 `B3` AST 違規）。
  3. **跨模組資料契約唯讀化（`@dataclass(frozen=True)` 與 `MappingProxyType`）**：
     - 將 `core` 內部 9 個未設 `frozen=True` 之 `@dataclass`（`commands/registry.py` 之 `ArgSpec`, `OptionSpec`, `CommandSpec`, `ModuleSpec`；`space/scanner.py` 之 `FileFingerprint`, `ScanDiffDetail`, `ScanDiffResult`, `SnapshotState`；`space/schema.py` 之 `SpaceConfig`）升級為 `frozen=True`（或於 `__post_init__` 使用 `object.__setattr__` 完成正規化後鎖定不可變），並移除 `SpaceConfig._project_root` 對 `default_factory=Path.cwd` 的隱式工作目錄綁定。
  4. **統一受保護模組命名空間載入器（Protected Namespace Loader）**：
     - 於 `core` 建立單點受保護命名空間載入器（如 `core/loader.py` 或 `core/symbols.py` 內聚載入核心），統一收斂 `core/symbols.py`、`core/commands/dispatcher.py`、`core/events.py`、`core/engine.py`（遷移腳本）與 `server/server/service.py` 共 5 處分散之 `spec_from_file_location` + `sys.modules` 動態載入邏輯，支援 `(mtime_ns, size)` 世代指紋比對自動熱重載與載入失敗 `sys.modules` 原子回滾，將 `D10`（直接操作 `sys.modules` / `sys.path`）收斂至單一豁免核心。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 經檢視 `core/context.py`（現僅有 14 行 `ExecutionContext`）、`core/uri.py`（`_URI_TLS` 與 `host_scope` / `yscb_scope` / `module_scope`）與 `core/symbols.py`（`resolve_callable` Track 2 VFS 載入），本子計畫直接在既有 `core/context.py` 上擴充 `RuntimeContext`，並將 `uri.py` 的作用域管理與 `symbols.py` 的動態模組載入邏輯統一收斂，不另起平行重複機制。
- **邊界排除 (Explicitly Excluded)**：
  - `server` 常駐三平面解耦、`WarmWorker` 移除 `os.chdir()`、`BaseServiceWorker` 受管獨立執行緒與 `knowledge-db` 離線模型守門屬 `sub_03` 範疇（惟 `server/server/service.py` 之 `_load_service_class_from_uri` 可一併對接 `core` 命名空間載入器）。
  - 上層 7 大業務模組之狀態容器與 AST 合規遷移屬 `sub_04` 範疇；`dev/checker.py` 13 項 AST 靜態守門正式啟用屬 `sub_05` 範疇。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/context.py`（擴充 `RuntimeContext`、虛擬環境與 `virtual_cwd` 作用域管理）
  - `ys_codebase/source/core/core/loader.py`（或 `symbols.py`，單點受保護模組命名空間載入器）
  - `ys_codebase/source/core/core/{uri,config,contributes,locale,symbols,gitignore,guard,events,engine}.py`
  - `ys_codebase/source/core/core/commands/{dispatcher,registry}.py`
  - `ys_codebase/source/core/core/platform/{process,venv}.py`
  - `ys_codebase/source/core/core/space/{schema,registry,scanner,watcher}.py`
  - `ys_codebase/source/core/tests/`（新增 `test_runtime_context.py` 並確保既有 `core` 全量測試 100% 通過）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `RuntimeContext` 階層化狀態桶與既有模組屬性白箱相容策略（軸一 & 軸二：既有組件復用與無副作用過渡）**：
  - 於 `core/context.py` 實作 `RuntimeContext`，以標準化 `(yscb_root, host_dir)` 為隔離維度管理各子系統狀態桶，並提供 `get_runtime_context()`、`bind_runtime_context(virtual_cwd=..., env=..., ...)`、`get_virtual_cwd()`、`get_env(key, default=None)`。
  - 為確保既有單元測試直接存取模組內部快取屬性（如 `uri._SCHEMES_CACHE`、`uri._TOKEN_MAP_CACHE`、`contributes._LAST_CLEAN_SCAN_TS`、`symbols._RESOLVED_CALLABLE_CACHE`、`dispatcher._MODULE_CACHE`、`dispatcher._AUTO_SPAWN_WARNED`）100% 不中斷，各模組透過 PEP 562 `__getattr__`（或綁定至當前 `RuntimeContext` 之代理視圖）動態映射至當前 `RuntimeContext` 對應狀態桶，同時在模組頂層達成 **0 處可變容器字面量賦值與 0 處 `global` 敘述（100% 符合 `C8` 守門）**。
- **[P00:DR-02] 非啟動器 `sys.exit()`、裸 `input()`、`os.getcwd()` / `Path.cwd()` 與 `os.environ` 突變之根除方案（軸二 & 軸三：生命週期與逆向拆卸）**：
  - **消除 `B3` (`sys.exit`)**：`guard.py:guard_dispatch` 將 `sys.exit(126)` 改為 `raise SystemExit(126)`（既有 `test_guard.py` 斷言 `with self.assertRaises(SystemExit)` 100% 原生相容，且不會在常駐進程中觸發未捕獲之 `sys.exit` 函式呼叫）；`uri.py:reconcile_undefined_uri` 移除互動式 `input()` 與 `sys.exit(1)`，統一拋出結構化 `UndefinedURIError` 並附上 `format_undefined_uri_hint` 修復指令提示（同時消除 `A2` 與 `B3` 違規）。
  - **消除 `B4` (`os.getcwd` / `Path.cwd`)**：將 `uri.py`、`gitignore.py`、`commands/dispatcher.py`、`space/registry.py`、`space/schema.py`、`space/watcher.py` 中的 `os.getcwd()` 與 `Path.cwd()` 統一替換為 `context.get_virtual_cwd()`（底層單點封裝於 `core/context.py` 並優先讀取 `ContextVar` 之 `virtual_cwd` 或 `YSCB_HOST_DIR`）。
  - **消除 `B5` (`os.environ` 執行期寫入)**：`dispatcher.py` 中對 `--verbose` / `--debug` 與 `YSCB_HOST_DIR` / `YSCB_HOST_DISPATCH_TOKEN` 的設定改透過 `bind_runtime_context(env=...)`（並由 `context.get_env` 優先讀取上下文覆寫表再退回 `os.environ`），不在 `dispatcher.py` 直接突變 `os.environ`。
- **[P00:DR-03] 9 個 `@dataclass(frozen=True)` 凍結與 `__post_init__` 正規化相容契約（軸四：跨切面不變量）**：
  - 將 `ArgSpec`、`OptionSpec`、`CommandSpec`、`ModuleSpec`、`FileFingerprint`、`ScanDiffDetail`、`ScanDiffResult`、`SnapshotState`、`SpaceConfig` 全部標註 `@dataclass(frozen=True)`。
  - 對於需要在 `__post_init__` 內執行欄位正規化（如 `SpaceConfig` 將字串 `hash_policy` 轉為 `HashPolicy` 枚舉或編譯 `_compiled_include` / `_compiled_exclude`）或建構期組裝（如 `CommandsRegistry` 組裝 `CommandSpec` / `ModuleSpec`、`SpaceScanner` 組裝 `SnapshotState`）之處，統一在建構前完成字典/集合組裝，或在 `__post_init__` 中透過 `object.__setattr__(self, ...)` 寫入衍生快取欄位，確保外部拿到實例後 100% 唯讀不可竄改。
- **[P00:DR-04] 單點受保護模組命名空間載入器 (`core/loader.py`) 與 `(mtime_ns, size)` 世代熱刷新（軸三：生命週期與異常回滾）**：
  - 新建 `ys_codebase/source/core/core/loader.py`，提供 `load_module_from_path(module_key, file_path, *, alias_keys=(), reload_if_changed=True)`：
    1. 自動讀取目標檔案之 `(st_mtime_ns, st_size)` 世代指紋；若快取命中且指紋未變，直接回傳已載入模組。
    2. 若首次載入或檔案已變更，使用 `importlib.util.spec_from_file_location` 載入，並在執行 `exec_module` 前備份 `sys.modules` 既有條目；若 `exec_module` 拋出任何例外（如 `SyntaxError`），於 `except` 區塊 100% 原子回滾 `sys.modules` 與快取，杜絕半初始化髒模組殘留。
    3. 統一替換 `symbols.py`、`dispatcher.py`、`events.py` 與 `engine.py` 的分散載入邏輯。

---

## 3. 開放議題與確認紀錄

- 全數架構邊界與 `R01` 支柱二量化清單已 100% 對齊，無未決開放議題。
