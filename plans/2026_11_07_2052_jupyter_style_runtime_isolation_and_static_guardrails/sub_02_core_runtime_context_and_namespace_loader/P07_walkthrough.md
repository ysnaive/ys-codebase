# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_core_runtime_context_and_namespace_loader  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`RuntimeContext` 實例化隔離容器與 `ContextVar` 範疇綁定 (`core.context`)**：擴充 `ys_codebase/source/core/core/context.py`，建立 `RuntimeContext` 集中納管 `core` 內部 11 大子系統動態快取與狀態（提供 `reset_all_caches()` 原位清空以保持白箱測試物件參考穩定）；建立 `RuntimeScope` 與 `bind_runtime_context(virtual_cwd=..., env=..., host_dir=..., yscb_dir=..., module_name=...)`，以 `get_virtual_cwd()` 作為全模組唯一合法呼叫 `os.getcwd()` 之邊界、以 `get_env()` / `get_env_snapshot()` 取代執行期 `os.environ` 突變，並將 `ExecutionContext` 升級為 `@dataclass(frozen=True)`（相容 `args=None`）。
  2. **`module:core` 頂層可變狀態清零、PEP 562 相容代理與 12 個 `@dataclass(frozen=True)` 凍結**：將 `uri`、`config`、`contributes`、`locale`、`symbols`、`gitignore`、`validator`、`commands/dispatcher`、`platform/{process,venv}`、`space/{registry,scanner,watcher}`、`log` 之頂層可變快取收斂至 `RuntimeContext`（搭配 PEP 562 模組級 `__getattr__` 與 Metaclass property 維持 100% 向後相容），將頂層常數與 `__all__` 轉為 `tuple` / `frozenset` / `MappingProxyType`，達成 `core` 全模組 0 `global`、0 頂層可變容器字面量賦值（`C8`）；將 `uri.reconcile_undefined_uri` 移除 `input()` 與 `sys.exit(1)` 統一拋出 `UndefinedURIError`（`A2`/`B3`）、`guard.guard_dispatch` 改為 `raise SystemExit(126)`（`B3`）；將 `core` 全數 12 個 `@dataclass` 升級為 `frozen=True`（`C9`）。
  3. **單點受保護命名空間模組載入器 (`core.loader`)**：新建 `ys_codebase/source/core/core/loader.py`，實作 `load_module_from_path`、`get_cached_module`、`clear_loaded_modules`，強制驗證 `_yscb_mod_` 命名空間前綴、內建 `(st_mtime_ns, st_size)` 指紋比對快取與熱重載，並於 `exec_module` 拋出例外時自動原子回滾 `sys.modules` 快照，統一收斂 `dispatcher.py`、`events.py`、`engine.py` 與 `symbols.py` 4 處動態載入（`D10`）。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/context.py` | Modify | 實作 `RuntimeContext`、`RuntimeScope`、`bind_runtime_context`、`get_runtime_context`、`reset_runtime_context`、`get_virtual_cwd`、`get_env`、`get_env_snapshot` 與凍結 `ExecutionContext`。 |
| `ys_codebase/source/core/core/loader.py` | New | 新建受保護命名空間模組載入器 `load_module_from_path`、`get_cached_module`、`clear_loaded_modules`。 |
| `ys_codebase/source/core/core/__init__.py` | Modify | 將 `_MODULE_MAP` 轉為 `MappingProxyType`、`__all__` 轉為 `tuple`，公開匯出 `context`、`RuntimeContext`、`RuntimeScope`、`bind_runtime_context`、`get_runtime_context` 與 `loader`。 |
| `ys_codebase/source/core/core/log.py` | Modify | 將 `LogExecutionScope` 升級為 `@dataclass(frozen=True)`，將 `_get_fallback_log_state` 委派至 `RuntimeContext`，替換 `os.getcwd()` 為 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/core/telemetry.py` | Modify | 將 `_safe_getcwd()` 委派至 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/core/guard.py` | Modify | 將 `sys.exit(126)` 改為 `raise SystemExit(126)` 並改用 `get_env()`。 |
| `ys_codebase/source/core/core/installer.py` | Modify | 將 `INTERNAL_IGNORE_PATTERNS` 轉為 `tuple`。 |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 將 `KNOWN_URGENCIES` 轉為 `MappingProxyType`。 |
| `ys_codebase/source/core/core/validator.py` | Modify | 將 `ContributesValidator.TYPE_ALIASES` 轉為 `MappingProxyType`，將 `_SIGNATURE_PARSE_CACHE` 收斂至 `RuntimeContext` 並提供 Metaclass 與 PEP 562 代理。 |
| `ys_codebase/source/core/core/uri.py` | Modify | 收斂 `_URI_TLS`、`_reconciling_tokens`、`_TOKEN_MAP_CACHE`、`_SCHEMES_CACHE`、`_URI_REENTRANCY` 至 `RuntimeContext`；移除 `reconcile_undefined_uri` 之 `input()` 與 `sys.exit()` 改拋 `UndefinedURIError`。 |
| `ys_codebase/source/core/core/config.py` | Modify | 透過 `_ConfigManagerMeta` 將 `ConfigManager._cache` 與 `_mtimes` 委派至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/contributes.py` | Modify | 收斂 `_MERGED_MEMORY_CACHE`、`_JSON_FILE_CACHE`、`_LAST_CLEAN_SCAN_TS` 至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/locale.py` | Modify | 將 `_DEFAULT_LOCALE_CHAIN` 與 `DEFAULT_HOST_DIALECT_RULES` 轉為不可變結構，收斂 3 個快取字典至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/symbols.py` | Modify | 將 `_RESOLVED_CALLABLE_CACHE` 收斂至 `RuntimeContext`，並將 VFS 動態載入委派至 `core.loader.load_module_from_path`。 |
| `ys_codebase/source/core/core/gitignore.py` | Modify | 將 `LEGACY_UNANCHORED_LINES` 轉為 `frozenset`，收斂 `_CUSTOM_ROOT_DYNAMIC_STORE` 至 `RuntimeContext`，替換 `os.getcwd()` 為 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/core/events.py` | Modify | 將 Hook 腳本動態載入委派至 `core.loader.load_module_from_path` 並改用 `get_env()`。 |
| `ys_codebase/source/core/core/engine.py` | Modify | 將 Migration 腳本動態載入委派至 `core.loader.load_module_from_path`。 |
| `ys_codebase/source/core/core/commands/__init__.py` | Modify | 將 `__all__` 轉為 `tuple`。 |
| `ys_codebase/source/core/core/commands/registry.py` | Modify | 將 `ArgSpec`、`OptionSpec`、`CommandSpec`、`ModuleSpec` 升級為 `@dataclass(frozen=True)`。 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 收斂 `_GLOBAL_REGISTRY`、`_GLOBAL_REGISTRY_ROOT`、`_MODULE_CACHE`、`_AUTO_SPAWN_WARNED` 至 `RuntimeContext`，替換 `os.getcwd()` 為 `get_virtual_cwd()`、CLI 載入委派 `core.loader`、`os.environ` 寫入改為 `bind_runtime_context(env=...)`。 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 將 `__all__` 轉為 `tuple`。 |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 收斂 `_CAN_SPAWN_DAEMON_CACHE` 至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/platform/venv.py` | Modify | 收斂 `_ACTIVE_TEST_SOURCE_PATHS` 至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/vfs/__init__.py` | Modify | 將 `__all__` 轉為 `tuple`。 |
| `ys_codebase/source/core/core/space/__init__.py` | Modify | 將 `__all__` 轉為 `tuple`。 |
| `ys_codebase/source/core/core/space/schema.py` | Modify | 將 `SpaceConfig` 升級為 `@dataclass(frozen=True)` 並改用 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/core/space/registry.py` | Modify | 收斂 `_DEFAULT_REGISTRIES` 至 `RuntimeContext` 並改用 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 將 `FileFingerprint`、`ScanDiffDetail`、`ScanDiffResult`、`SnapshotState` 升級為 `@dataclass(frozen=True)` 並收斂 `_DEFAULT_SCANNERS` 至 `RuntimeContext`。 |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | 收斂 `_SUBSCRIBERS` 與 `_ACTIVE_WATCHER_WORKER` 至 `RuntimeContext` 並改用 `get_virtual_cwd()`。 |
| `ys_codebase/source/core/tests/test_runtime_context.py` | New | 新建 `TestCoreRuntimeContextAndLoader` 測試套件（覆蓋 `FT-01` ~ `FT-04`, `ET-01` ~ `ET-05`）。 |
| `docs/core/README.md` | Modify | 新增第 3.9 節 `core.context` 與 `core.loader` 架構說明。 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `TestCoreRuntimeContextAndLoader` (`FT-01` ~ `FT-04`, `ET-01` ~ `ET-05`)：4/4 (100% Passed)
  - `module:core` 全量回歸 (`dev test core -q --sync`)：281 Passed, 0 Failed, 1 Skipped
  - `dev check core`：PASSED (0 Errors, 0 Warnings)
  - `Pre-UX Static Blind Review`：`REVIEW_STATUS: PASSED`
- **實機 UX / 人工驗證**：
  - `UX-01` (`[測試通過]`)：於本機 `core@1.2.7.build` 實機調用 `uri list`、`config list --mod=core`、`fs status`、`event list`、`status`，全數正常輸出且狀態為 `HEALTHY (100% Ready)`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 新增 `sub_02_core_runtime_context_and_namespace_loader` 結案紀錄 |
| **中觀 (Meso)** | `docs/core/README.md` | 已更新 | 更新 Frontmatter `source_paths`、Mermaid 架構圖與第 3.9 節 `core.context` / `core.loader` 說明 |
| **中觀 (Meso)** | `docs/core/uri_protocols.md` | 免更 | 語意 URI 協議未變更 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 無新增反直覺工程妥協（防膨脹守門） |
| **微觀 (Micro)** | `ys_codebase/source/core/core/{context,loader}.py` 等源碼註解 | 已更新 | 補齊 Google Style Docstring，且無殘留工單編號標記 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core): add RuntimeContext isolation container, frozen dataclasses, and protected namespace loader (sub_02)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
