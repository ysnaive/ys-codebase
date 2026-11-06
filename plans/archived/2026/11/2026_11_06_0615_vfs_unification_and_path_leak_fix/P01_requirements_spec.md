# 需求規格說明書 (Requirements Specification)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `file-space` 快取與儲存路徑統一經由 `core.uri` / `core.vfs` 解析 | 1. `FileSpaceWatcherServiceWorker._resolve_watcher_state_path()`、`_write_watcher_state_file()`、`_remove_watcher_state_file()` 改用 `file-space.cache://watcher_state.json`（或顯式 `context["state_file"]` / 沙盒 `storage_root`）與 `core.vfs.write_json(..., atomic=True)`，移除 `p_root / ".cache" / "file-space"` 硬編碼。<br/>2. `scanner._is_daemon_pid_alive()` 與 `_read_watcher_state_file()` 改用 `cache://server/daemon.json`、`file-space.cache://watcher_state.json` 與 `core.vfs.read_json`。<br/>3. `service.is_transaction_locked()` 改用 `cache://.yscb.lock`（相容顯式 `lock_file` 與 `p_root / ".yscb.lock"`），不再探測 `p_root / ".cache" / ".yscb.lock"`。<br/>4. `FileSpaceManager.storage_root` 的退避路徑改以 `core.uri.resolve_yscb_root()` 為基準（`<yscb_root>/.storage.local/file-space`），移除 `self.project_root / "ys_codebase"` 硬編碼。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `ast` 與 `knowledge-db` 持久儲存與快取鎖退避錨定 `yscb_root` | 1. `ast_engine.bundler._resolve_default_ast_storage_dir()` 在 `ast.storage://` 與 `storage.local://ast` 退避時，改以 `Path(uri.resolve_yscb_root()) / ".storage.local" / "ast"` 為基準，嚴禁退避至 `project_root / ".storage.local" / "ast"`。<br/>2. `ASTEngine._resolve_index_lock_path()` 在 `ast.cache://.ast_index.lock` 退避時，改以 `Path(uri.resolve_yscb_root()) / ".cache" / "ast" / ".ast_index.lock"` 為基準，嚴禁在 `self.project_root / ".cache" / "ast"` 建立目錄。<br/>3. `knowledge_db.pipeline._resolve_default_knowledge_storage_dir()` 退避時改以 `Path(uri.resolve_yscb_root()) / ".storage.local" / "knowledge-db"` 為基準。<br/>4. `knowledge_db.config.is_agents_workflow_installed()` 改用 `core.vfs.is_dir("module://agents-workflow")` 搭配 `Path(uri.resolve_yscb_root()) / ".modules" / "agents-workflow"`，移除 `Path(proj_res) / ".modules"` 錯誤拼接。 | P0 | [P00:DR-01] |
| **FR-03** | `agents-workflow` 快取與組態退避移除 `Path.cwd()` 與 `ys_codebase/` 硬編碼 | 1. `ArtifactCompiler._write_cache_file()` 統一透過 `core.vfs.write_text(cache_uri, content, atomic=True)` 寫入，退避路徑錨定 `uri.resolve_yscb_root()`。<br/>2. `PlanVerifier.__init__()` 解析預設 `templates_dir` 時移除 `Path.cwd() / ".cache" / "agents-workflow"` 探測，改以 `uri.resolve_yscb_root()` 為退避基準。<br/>3. `SessionTraceEngine._get_configured_release_targets()` 讀取 `config.local://` 與 `config://` 時透過 `core.vfs.read_json` 解析，移除 `"ys_codebase/.config.local/..."` 與 `"ys_codebase/config/..."` 硬編碼字串。 | P0 | [P00:DR-01] |
| **FR-04** | `server` WarmWorker 啟動期固化 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` | `WarmWorker.__init__()` 在實例化及 `pre_warm()` 啟動背景服務（`file-space-watcher`、`knowledge-db-worker`、`gdrive-sync`）前，主動解析並寫入 `os.environ["YSCB_ROOT_DIR"]` 與 `os.environ[GUARD_ENV_HOST]`，確保所有背景子執行緒跨執行緒呼叫 `core.uri.resolve()` 時 100% 命中正確宿主與工具庫根目錄。 | P0 | [P00:DR-03] |
| **FR-05** | 跨模組自造原子寫入輔助函式統一收口至 `core.vfs` | 1. `file_space.scanner._atomic_write_bytes()` 委派至 `core.vfs.write_bytes(str(target_path), payload, atomic=True)`。<br/>2. `ASTEngine._atomic_write_meta()` 委派至 `core.vfs.write_json(str(self.meta_index_path), meta_payload, indent=2, atomic=True)`。<br/>3. `knowledge_db.service.write_worker_state()` 委派至 `core.vfs.write_json(str(p), payload, indent=None, atomic=True)`（或 `core.vfs.write_text(..., atomic=True)`）。<br/>4. `agents_workflow` 之 `publisher._write_text_atomic`、`roadmap._atomic_write_text` 與 `plans._verifier_healer._atomic_write_text` 統一優先委派至 `core.vfs.write_text(..., atomic=True)`。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 下游專案之 `project_root` 位於獨立業務目錄或工具庫目錄名稱非 `ys_codebase`（例如 `.yscb_core` 或外部掛載） | 執行 `file-space`、`ast`、`knowledge-db`、`agents-workflow` 或啟動 `server` 後，`project_root` 下絕不產生 `.cache/`、`.storage.local/` 或 `ys_codebase/` 目錄。 |
| **EC-02** | 單元測試環境在獨立 `tempfile` 目錄下實例化 `FileSpaceManager(project_root=..., storage_root=...)` 與 `FileSpaceWatcherServiceWorker` | 當 `space_manager` 具有顯式注入之 `_explicit_storage_root` 時，Watcher 狀態檔與 `is_watcher_active` 支援在對應沙盒目錄或 `file-space.cache://` 正確讀寫與清理，且不污染真實宿主快取或 `project_root`。 |
| **EC-03** | 單元測試透過 `unittest.mock.patch` 攔截 `Path.write_text`（如 `test_roadmap.py`）或模擬 `os.replace` `PermissionError` 重試 | `roadmap._atomic_write_text` 保留對 `Path.write_text` monkeypatch 的偵測相容；`core.vfs` 的 `OSBackend.atomic_write` / `robust_replace` 原生具備 `PermissionError` 漸進重試與暫存檔異常清理保證。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴純淨與相容性 | 100% 使用 Python 標準庫與 `core.uri` / `core.vfs`，零新增第三方依賴，既有 Public API 簽名 100% 相容。 |
| **NFR-02** | 測試與靜態合規守門 | 受影響之 5 個模組（`file-space`、`server`、`ast`、`knowledge-db`、`agents-workflow`）執行 `dev check` 與 `dev test -q` 皆須 100% 通過（0 FAIL）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 修改 `FileSpaceWatcherServiceWorker.start/stop` 時，務必保證 `finally` 區塊更新/清理 `watcher_state.json` 與 `.watcher_dirty` 信標（遵循 `docs/file-space/DESIGN_NOTES.md` `[DN-SP-03]`）。
- **`[!NOTE]`** `core.vfs.OSBackend.atomic_write` 內部透過 `robust_replace` 執行 `os.replace` 重試；若 `test_fingerprint_scanner.py` 測試 `_atomic_write_bytes` 的 `PermissionError` 重試與 `.tmp` 清理，需確保委派 `core.vfs` 後或透過 `core.vfs.os_backend.os.replace` 攔截時行為一致。
