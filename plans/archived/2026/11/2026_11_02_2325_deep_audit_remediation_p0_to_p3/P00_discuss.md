# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：deep_audit_remediation_p0_to_p3  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對全專案八維度單點序列深度審計報告之 22 項發現（`AUD-01` ~ `AUD-22`）執行事實性查證後，全量納入單一新計畫（`/new-plan` + `/auto`）一次性立項並自動推進修復；由於皆屬確定性問題修復，僅在驗收時派發子代理，以避免過多探索 Token 花銷。
- **核心目標**：
  1. **修復 🔴 P0 致命競爭與注入風險 (`AUD-01` ~ `AUD-03`)**：將 `Installer` (`cmd_install`, `cmd_update`, `cmd_remove`, `cmd_restore`) 的 `act_snapshot` 與失敗回滾 `act_restore_snapshot` 嚴格納入 `transaction_lock` 臨界區內，防止搶鎖超時觸發無鎖回滾摧毀進行中環境；將 `server/master.py:spawn_detached_master` 改為透過 `sys.argv` 安全傳遞路徑與參數；於 `MasterSupervisor.restart_worker` 補齊 `_dispatch_lock -> _worker_lock` 固定鎖序。
  2. **修復 🟠 P1 跨平台相容性、資源洩漏與跨模組契約 (`AUD-04` ~ `AUD-11`)**：補齊 Windows 64-bit `ctypes` `wintypes.HANDLE` 型別宣告與 `msvcrt.locking` 前之 `os.lseek(fd, 0, os.SEEK_SET)`；強化 VFS `OSBackend.assert_safe_path` 對 Symlink 越界的防禦（兼顧 Windows 虛擬磁碟機/沙盒與 macOS `/private/var` 對稱解析）並於 `exists`/`is_file`/`is_dir` 落實邊界校驗；為 `PipManager` 補上 `--no-input` 與 `timeout`；對齊 `file-space` 與 `knowledge-db` 之 `on_server_worker_warming` Hook、`is_transaction_locked` 鎖探測與 `_is_daemon_pid_alive`；修正 `ast_engine` 之 `SnapshotState.head_generation` 讀取、同檔重載符號重連與 `ProcessPoolExecutor` `sys.path` 初始化器；修正 `treesitter.py` 重載方法去重與 `resolve_out_of_line_scope` `kind` 計算時序；消除 `knowledge_db.service.wait_until_worker_idle` 跨進程等待時之 100% CPU 空轉；為 `SandboxProvisioner.cleanup_sandbox` 補上 Windows 唯讀檔案屬性清除回呼。
  3. **收斂 🟡 P2 / 🔵 P3 資安、狀態隔離與代碼衛生 (`AUD-12` ~ `AUD-22`)**：`daemon.json` `0o600` 權限與 `secrets.compare_digest` 鑑權；`dispatcher.py` `_GLOBAL_REGISTRY` 綁定 `yscb_abs` 隔離；`is_dirty_file_match` $O(1)$ 查找與無斜線檔名防誤判；`agents-workflow` 本地軌 `release_manifest.json` URI 正規化與原子寫入；`telemetry.py` `.tmp` 清理與 `CursorStore.reset_cursor` 原子寫入；`embedding.py` `os.environ.setdefault` 與 `is_available` 快取優化；`dev/testing` 單測方法級輸出緩衝隔離；清理 `yscb.py` 未使用之 `CORE_COMMANDS` 與 `_MODULE_CACHE`（保留使用中之 `INTERNAL_IGNORE_BEGIN/END`）；補齊 `installer.py` fallback 模組清單之 `file-space` 與 `ast`；收斂 `knowledge_db/io_utils.py` 委派 `ast_engine/io_utils.py`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.platform.is_process_alive` 與 `core.platform.lock.InterProcessLock` 取代 `file_space` 內的手寫 `os.kill(pid, 0)` 與 `.exists()` 鎖檢查。
  - 復用 `ast_engine.io_utils` 作為 `knowledge_db.io_utils` 之單一真理來源（SSOT）。
- **邊界排除 (Explicitly Excluded)**：
  - 審計報告第 4 節已排除之偽陽性（`RFP-01` ~ `RFP-05`）不作無謂改動。
  - `AUD-19` 中報告誤列之 `INTERNAL_IGNORE_BEGIN` / `INTERNAL_IGNORE_END` 於 `yscb.py:L218-L234` 仍有實際呼叫，嚴格保留不刪除。
- **架構影響範圍**：`yscb.py`、`core`、`server`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`dev`（全 7 大核心模組）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `Installer` 跨進程交易鎖與快照生命週期邊界 (`AUD-01`)**：
  - 在 `cmd_install`、`cmd_update`、`cmd_remove` 與 `cmd_restore` 中，先進入 `with self.engine.transaction_lock("<op>"):`，在持有跨進程鎖之後才建立 `snap_id = self.engine.act_snapshot(...)`，並於內層 `try ... except Exception:` 執行 `self.engine.act_restore_snapshot(snap_id)`（同時在 `finally:` 中清理臨時成功快照目錄以防 `.snapshots/` 無限膨脹，但保留顯式或回滾所需安全性）。若 `transaction_lock` 拋出 `TimeoutError`（其他進程持鎖中），直接報錯返回 `1`，絕不覆寫快照或執行回滾。
- **[P00:DR-02] `Server` 參數傳遞安全、鎖序與鑑權強化 (`AUD-02`, `AUD-03`, `AUD-12`)**：
  - `spawn_detached_master` 改以 `sys.argv[1..5]` 傳遞 `core_dir`、`server_dir`、`yscb_root`、`idle_timeout_sec`、`enable_watcher`，徹底消除單引號字串插值。
  - `MasterSupervisor.restart_worker` 改為先獲取 `self._dispatch_lock` 再獲取 `self._worker_lock`，確保正在執行中的 `dispatch_task` 完成後才重啟 Worker。
  - `_write_state` 寫入 `daemon.json` 後以 `os.chmod(self.state_file, 0o600)` 限制權限，且 `_authenticate` 改用 `secrets.compare_digest`。
- **[P00:DR-03] `Core` 跨平台系統呼叫、VFS 符號連結防禦、Pip 超時與全局註冊表隔離 (`AUD-04`, `AUD-05`, `AUD-06`, `AUD-13`, `AUD-16`, `AUD-19`, `AUD-20`)**：
  - `process.py:is_process_alive` 在 Windows 下顯式宣告 `OpenProcess`、`GetExitCodeProcess`、`CloseHandle` 之 `wintypes` 簽名；`lock.py:_try_lock_fd` 在 `msvcrt.locking` 前補上 `os.lseek(fd, 0, os.SEEK_SET)`。
  - `os_backend.py:assert_safe_path` 除了檢查 `abspath` 邊界外，當 `boundary_root` 存在時同步驗證 `os.path.realpath(norm_target)` 是否位於 `os.path.realpath(boundary_root)` 內（阻斷指向沙盒外的 Symlink 逃逸，同時對稱處理 macOS `/private/var` 與 Windows 虛擬磁碟機），且 `exists`、`is_file`、`is_dir` 統一先通過 `assert_safe_path`。
  - `pip_manager.py` 為 `ensurepip` 與 `pip install` 補上 `--no-input` 與 `timeout=300`。
  - `dispatcher.py:_load_registry` 記錄 `_GLOBAL_REGISTRY_ROOT`，當 `yscb_abs` 變更時自動重建。
- **[P00:DR-04] `File-Space`、`AST` 與 `Knowledge-DB` 跨模組契約、重載方法與空轉修復 (`AUD-07` ~ `AUD-10`, `AUD-14`, `AUD-17`, `AUD-21`, `AUD-22`)**：
  - `file-space/scripts/hook.server.py` 與 `knowledge-db/scripts/hook.server.py` 補上 `on_server_worker_warming` 標準入口；`file_space/service.py:is_transaction_locked` 改用 `InterProcessLock` 非阻塞探測 `cache://.yscb.lock`；`file_space/scanner.py:_is_daemon_pid_alive` 納入 `.cache/server/daemon.json` 並改用 `core.platform.is_process_alive`，且 `CursorStore.reset_cursor` 改用原子寫入。
  - `ast_engine/engine.py` 讀取 `getattr(snap_st, "head_generation", getattr(snap_st, "generation", 1))`；`_relink_and_reconnect_edges` 以 `List[UnifiedSymbol]` 保存同檔同名重載符號並依行號/簽名精確匹配；`bundler.py` 為 `ProcessPoolExecutor` 補上 `_init_bundle_worker` 同步 `sys.path`；`treesitter.py` 先正規化 `method` `kind` 與 `resolve_out_of_line_scope` 後再進行 `children_items` 去重（納入 `signature` 與 `start_line`）與 `UnifiedSymbol.compute_id`。
  - `knowledge_db/service.py:wait_until_worker_idle` 當本進程 `_IDLE_EVENT.is_set()` 為 `True`（代表忙碌中的 Worker 位於另一進程）時，直接執行 `time.sleep(wait_slice)` 避免 100% CPU 空轉；`embedding.py` 改用 `os.environ.setdefault` 並快取已驗證之 `.onnx` 檔案路徑加速 `is_available`；`knowledge_db/io_utils.py` 統一委派重導出 `ast_engine.io_utils`（同時修正 `is_dirty_file_match` 避免無斜線檔名誤判）。
- **[P00:DR-05] `Agents-Workflow` 本地軌 Manifest URI 與 `Dev` 沙盒清理及測試輸出隔離 (`AUD-11`, `AUD-15`, `AUD-18`)**：
  - `agents_workflow/publisher.py` Local 軌 `published_files` 與 Project 軌一致使用 `_to_project_uri` 轉譯（並在讀取清理時相容舊絕對路徑與 `project://` URI），且 `_materialize_target_files` 改用 `vfs.write_text(..., atomic=True)`。
  - `dev/testing/sandbox.py:cleanup_sandbox` 的 `shutil.rmtree` 補上 `onerror` 唯讀屬性清除回呼；`dev/testing/case.py` 與 `runner.py` 記錄單一測試方法執行期間的輸出切片，避免單一失敗案例混入全 Suite 的累積輸出。

---

## 3. 開放議題與確認紀錄

- 開發者已明確指示全量納入單一新計畫（`/new-plan` + `/auto`）一次性立項並自動推進修復，且僅於驗收階段派發盲審子代理。所有規格與邊界已 100% 確認（`Confirmed`）。

