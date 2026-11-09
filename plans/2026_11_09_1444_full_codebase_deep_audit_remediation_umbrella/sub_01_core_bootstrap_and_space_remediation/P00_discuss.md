# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_bootstrap_and_space_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將全倉深度審計報告（[`R01_full_codebase_deep_audit_report.md`](../R01_full_codebase_deep_audit_report.md)）中針對 `Unit 01`（[`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) + `module:core` 核心引擎、命令分派、日誌、上下文、載入器、遷移腳本）與 `Unit 02`（`module:core` 之 `platform/`、`vfs/`、`space/` 檔案空間引擎）檢出之全部問題（`CORE-AUD-01` ~ `CORE-AUD-10` / `AUD-U01-01~09` & `AUD-U02-01~08`），以及架構與演進債審計報告（[`R02_architecture_and_evolutionary_debt_audit.md`](../R02_architecture_and_evolutionary_debt_audit.md)）中之 `ARCH-CORE-01` ~ `ARCH-CORE-16`、`ARCH-SRV-06` 與 Mode A 手術 `S4` 全量轉化為 `sub_01` 修補計畫並完成實作驗證。
- **核心目標**：
  1. **落實 Mode A 手術 `S4` 與 `ARCH-CORE-01` ~ `ARCH-CORE-16` 架構收斂**：
     - **`ARCH-CORE-01` (`RuntimeScope` 與 `uri_tls` 雙軌同步)**：於 `core/uri.py` 與 `core/context.py` 確保 `set_host_dir()`、`set_yscb_root()`、`set_module_context()`、`host_scope()`、`yscb_scope()` 與 `module_scope()` 在活躍 `bind_runtime_context` 內同步更新當前 `RuntimeScope` 與 `uri_tls`，消除內層作用域被外層 `RuntimeScope` 遮蔽之問題，並保留白箱測試相容性。
     - **`ARCH-CORE-02` & `ARCH-CORE-06` (統一快取失效與符號熱重載同步)**：於 `core/context.py` 提供 `RuntimeContext.invalidate_host_caches(scope="all")`（並自 `core.context` 匯出），原子清空 `contributes`、`loader`、`dispatcher`、`symbols` 與 `uri` 快取；確保 `core/symbols.py` 支援套件 `__init__.py` 定位並於檔案 `(mtime_ns, size)` 變動時自動切換至 `core.loader` 重新載入。
     - **`ARCH-CORE-03` (`ContributesAggregator` 原子寫入與單一真實來源)**：確保 `core/contributes.py` 以 `atomic=True` 寫入 `contributes.merged.json`，支援頂層 `module://<mod>/contributes.json` 命令提取與 `get_merged_contributes()` 聚合讀取。
     - **`ARCH-CORE-05` (`sys.path` / `sys.argv` 執行緒安全與非破壞性清理)**：於 `core/context.py` 新增 `sys_path_lock`，在 `core/platform/venv.py`、`core/events.py` 與 `core/commands/dispatcher.py` 以鎖保護 `sys.path` / `sys.argv` 變異，並以 `remove_inserted_sys_paths()` 取代破壞性的 `sys.path[:] = orig_sys_path` 全量覆寫。
     - **`ARCH-CORE-06` / `ARCH-SRV-06` (`core/service_contract.py` 輕量常駐契約下沉)**：新建 `ys_codebase/source/core/core/service_contract.py` 匯出純標準庫之 `BaseServiceWorkerContract`（含 `STATE_STARTING`、`STATE_UPDATING`、`STATE_READY`、`STATE_DEGRADED_OFFLINE`、`STATE_STOPPED`、`state`、`set_state`、`is_busy`、`start_managed_thread`、`stop_managed_thread`、`bind_worker_context`、`touch_activity`），供 `server`、`knowledge-db` 與 `gdrive-support` 共享單一基底契約。
  2. **根除 2 項 P1 狀態殘留與熱重載契約缺口（`CORE-AUD-01`, `CORE-AUD-02`）**：
     - 清理 `file-space` 收編至 `core.space` 後於 `core/engine.py` 與 `scripts/migrations/1.2.8.x.py` 的快取與儲存空間殘留，並於 `AtomicEngine.act_reload` 同步刷新 `SpaceRegistry` / `SpaceScanner` 單例與 `invalidate_host_caches("all")`（`CORE-AUD-01`）；
     - 修復 `core/commands/dispatcher.py:_load_registry` 支援單檔 `contributes.json` 並將 `.modules` 與 `contributes.merged.json` 之 `(mtime_ns, size)` 納入快取世代指紋（`CORE-AUD-02`）。
  3. **修復 P2 鎖重入、Zip Slip 守門、離線 Pip 自舉、日誌輪替碰撞、VFS 大小寫與負時間戳記邊界問題（`CORE-AUD-03` ~ `CORE-AUD-07`）**：
     - 將 `AtomicEngine.act_lock` / `act_unlock` 改為對齊實體鎖檔 `cache://.yscb.lock` 的跨操作共用可重入鎖與引用計數，並於 `core/platform/lock.py` 集中提供 `is_transaction_locked()`，且在 `lock.py` 與 `process.py` 確保檔案句柄與子進程管道於 `finally` 確定性關閉（`0 ResourceWarning`）（`CORE-AUD-03`）；
     - 強化 `yscb.py` 與 `core/engine.py` 之 Zip 解壓路徑穿越攔截（Zip Slip Guard），並於 `yscb.py` 與 `core/vfs/os_backend.py` 提供帶 `.old` 失敗自動回滾之 `atomic_swap_directory`；
     - 於 `core/pip_manager.py:_bootstrap_pip` 新增 `_try_copy_host_pip_to_site_packages()` 離線容器回退機制；
     - 修復 `core/log.py:_rotate_lines_file` 保留原始副檔名，並為 `yscb.py:cmd_self_update` 暫存檔補上 `os.getpid()`（`CORE-AUD-04`）；
     - 移除 `core/uri.py` 零引用之 3 個舊互動函式，並收斂 `yscb.py:cmd_restore` 轉發邏輯（保留無 `core/scripts/cli.py` 時之標準庫最小自舉回退與 `_restore_module_package` 相容別名）（`CORE-AUD-05`）；
     - 修復 `core/vfs/os_backend.py:_safe_copytree` 僅於大小寫不敏感系統跳過大小寫碰撞，並驗證 symlink 目標位置不越出複製目標樹（`CORE-AUD-06`）；
     - 對齊 `core/space/scanner.py` 與 `core/space/registry.py` 對負值 `mtime_ns` / `ctime_ns` 的 `max(0, ...)` 夾限正規化，並將快照檔尾部 16-byte 校驗碼納入 `_snapshot_mem_cache` 快取鍵（`CORE-AUD-07`）。
  4. **落實 P3 結構與批次空間掃描去重優化（`CORE-AUD-08` ~ `CORE-AUD-10`, `AUD-U02-08`）**：
     - `core/contributes.py:_deep_merge` 在 `extend` 策略下對可雜湊純量使用輔助 `set` 消除 $O(N^2)$ 查找（`CORE-AUD-08`）；
     - `core/scripts/cli.py` 透過 PEP 562 `__getattr__` 動態解析 `file_space_<subcmd>` / `fs_<subcmd>`，消除 16 個重複包裝函式並保持 `dev check` 零頂層賦值違規（`CORE-AUD-09`）；
     - `core/installer.py:cmd_restore` 搭配 `AtomicEngine.act_reload(skip_materialize_modules=...)` 消除重複解壓（`CORE-AUD-10`）；
     - `core/space/registry.py`、`scanner.py` 與 `schema.py` 新增 `batch_walk_session()` 批次目錄走訪與 `os.scandir` 記憶化及 `CompiledRuleSet._fallback_compiled` 快速短路，將全空間強制掃描延遲由 `2253.41 ms` 降至 `534.96 ms`（加速 `4.21x`）。
- **既有組件復用與查重 (Reuse Discovery)**：直接復用 `core.space`、`core.contributes`、`core.platform.lock.InterProcessLock` 與 `core.vfs.os_backend`，100% 純 Python 標準庫零外部依賴。
- **邊界排除 (Explicitly Excluded)**：不修改 `core` 對外公開 CLI 命令名稱與參數結構；嚴禁於源碼註解留下任何審計單號。
- **架構影響範圍**：`yscb.py`、`ys_codebase/source/core/core/{context,uri,symbols,contributes,events,service_contract,engine,installer,pip_manager,log,__init__}.py`、`core/commands/dispatcher.py`、`core/platform/{venv,lock,process,__init__}.py`、`core/vfs/{os_backend,__init__}.py`、`core/space/{schema,registry,scanner}.py`、`core/scripts/{cli.py,migrations/1.2.8.x.py}`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `AtomicEngine.act_lock` / `act_unlock` 統一鎖句柄與可重入計數 (`CORE-AUD-03`)**：因為底層皆鎖定同一實體檔案 `cache://.yscb.lock`，所有 `operation` 共用同一已鎖定之 `InterProcessLock` 實例並維護各 `operation` 引用計數，僅在總計數歸零時釋放底層實體鎖，並於 `core.platform.lock` 提供 `is_transaction_locked()` 統一探針。
- **[P00:DR-02] `OSBackend._safe_copytree` 依目標路徑大小寫敏感度條件啟用衝突檢測與 `atomic_swap_directory` 回滾 (`CORE-AUD-06`)**：僅在大小寫不敏感之檔案系統才以 `seen_lower` 攔截大小寫碰撞；在 Linux 大小寫敏感系統上保留大小寫相異檔案並存，且 `atomic_swap_directory` 在替換失敗時自動從 `.old` 備份回滾原目錄。
- **[P00:DR-03] `RuntimeScope` 與 `uri_tls` 雙向同步及 `BaseServiceWorkerContract` 下沉 (`ARCH-CORE-01`, `ARCH-CORE-06`, Surgery `S4`)**：於 `core.context.update_current_scope_roots` 同步更新活躍 `RuntimeScope`，使 `bind_runtime_context` 內呼叫 `uri.set_host_dir` 或 `with uri.host_scope(...)` 即時生效；同時將常駐背景服務契約下沉至 `core.service_contract.BaseServiceWorkerContract`，透過 `core.log.create_managed_thread` 建立受管背景執行緒，100% 符合 `dev check` 靜態守門規範。

---

## 3. 開放議題與確認紀錄

- 全部需求規格、架構手術 `S4` 與修復處方均已確認並完成實作驗證。
