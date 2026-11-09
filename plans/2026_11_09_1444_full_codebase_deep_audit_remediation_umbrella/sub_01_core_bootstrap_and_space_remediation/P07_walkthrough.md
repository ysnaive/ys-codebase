# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_core_bootstrap_and_space_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 實作成果總覽 (Implementation Summary)

### 1.1 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **完成 Mode A 架構手術 `S4` 與 `ARCH-CORE-01` ~ `ARCH-CORE-16` 核心契約收斂**：
     - **`RuntimeScope` 與 `uri_tls` 雙向同步 (`ARCH-CORE-01`)**：於 `core/context.py` 新增 `update_current_scope_roots()`，使 `core/uri.py` 的 `set_host_dir()`、`set_yscb_root()`、`set_module_context()`、`host_scope()`、`yscb_scope()` 與 `module_scope()` 在活躍 `bind_runtime_context` 內同步更新 `RuntimeScope` 與 `uri_tls`，徹底消除內層 URI 作用域被外層 `RuntimeScope` 遮蔽的問題。
     - **統一快取失效與符號熱重載世代校驗 (`ARCH-CORE-02`, `ARCH-CORE-06`)**：於 `RuntimeContext` 與 `core.context` 實作並匯出 `invalidate_host_caches(scope="all")`，單點原子清除 `contributes`、`loader`、`dispatcher`、`symbols` 與 `uri` 快取；更新 `core/symbols.py` 支援套件 `__init__.py` 實體檔案定位，並在偵測到磁碟 `(mtime_ns, size)` 變動時自動切換至 `core.loader.load_module_from_path(..., reload_if_changed=True)` 重新載入。
     - **`ContributesAggregator` 原子寫入與 $O(1)$ 去重 (`ARCH-CORE-03`, `CORE-AUD-08`)**：於 `core/contributes.py` 採用 `atomic=True` 寫入 `contributes.merged.json`、新增 `get_merged_contributes()` 聚合讀取介面，並以 `_extend_list_dedup` 輔助 `set` 將 `_deep_merge` 列表去重複雜度由 $O(N^2)$ 降至 $O(N)$。
     - **`sys.path` / `sys.argv` 執行緒安全與非破壞性清理 (`ARCH-CORE-05`)**：於 `RuntimeContext` 新增 `sys_path_lock`，在 `core/platform/venv.py`、`core/events.py` 與 `core/commands/dispatcher.py` 以鎖保護 `sys.path` 與 `sys.argv` 變異，並以 `remove_inserted_sys_paths()` 精準移除本次新增路徑，取代會抹除其他執行緒並發新增路徑的 `sys.path[:] = orig_sys_path`。
     - **常駐背景服務輕量基底契約下沉 (`ARCH-CORE-06`, `ARCH-SRV-06`)**：新建 `ys_codebase/source/core/core/service_contract.py`（並於 `core/__init__.py` 匯出），提供純標準庫零第三方依賴之 `BaseServiceWorkerContract`（別名 `BaseServiceWorker`）與 `touch_activity`，統一管理五態狀態機（`STARTING`、`UPDATING`、`READY`、`DEGRADED_OFFLINE`、`STOPPED`）、`bind_worker_context` 與受管背景執行緒。
  2. **完成 `R01` `Unit 01` & `Unit 02` 全部審計項 (`CORE-AUD-01` ~ `CORE-AUD-10` / `AUD-U01-01~09` & `AUD-U02-01~08`) 修補**：
     - **跨操作可重入鎖與確定性資源釋放 (`CORE-AUD-03`, `AUD-U02-01`, `AUD-U02-02`)**：重構 `AtomicEngine.act_lock` / `act_unlock` 共用單一已鎖定之 `InterProcessLock` 實例與引用計數，於 `core/platform/lock.py` 集中提供 `is_transaction_locked()`，並在 `lock.py` 與 `process.py` 確保所有鎖檔案句柄、子進程管道與 `os.scandir` 迭代器於 `finally` 確定性關閉（`0 ResourceWarning`）。
     - **Zip Slip 路徑穿越防護與 `.old` 自動回滾 (`AUD-U01-01`, `AUD-U01-02`, `CORE-AUD-06`)**：於 `yscb.py` 與 `core/engine.py` 強化 Zip 解壓目標路徑邊界校驗；於 `yscb.py` 與 `core/vfs/os_backend.py` 實作帶 `.old` 失敗自動回滾之 `atomic_swap_directory`，並修正 `_safe_copytree` 僅於大小寫不敏感檔案系統執行 `seen_lower` 去重。
     - **離線容器 Pip 自舉回退與 `cmd_restore` 單次解壓 (`AUD-U01-05`, `CORE-AUD-10`)**：於 `core/pip_manager.py:_bootstrap_pip` 新增 `_try_copy_host_pip_to_site_packages()`，解決無 `ensurepip` wheel 之離線容器虛擬環境初始化失敗問題；於 `Installer.cmd_restore` 搭配 `AtomicEngine.act_reload(skip_materialize_modules=...)` 消除重複解壓。
     - **空間引擎負時間戳記夾限與批次走訪記憶化 (`CORE-AUD-07`, `AUD-U02-08`)**：於 `core/space/registry.py` 與 `scanner.py` 將 `mtime_ns` / `ctime_ns` 統一夾限為 `max(0, ...)`，在 `_load_snapshot_state` 將快照尾部 16-byte Blake2b 校驗碼納入記憶體快取鍵，並透過 `SpaceRegistry.batch_walk_session()` 與 `CompiledRuleSet._fallback_compiled` 大幅消除跨空間別名重複 `os.scandir` 走訪。

---

## 2. 效能基準實測與結構量化對照 (Performance Benchmark & Structural Delta)

### 2.1 效能基準實測對照表 (`perf_counter_ns()`)

於獨立沙盒工作區（`/working_dir/c_3fdac06fe2853f20/track_workspaces/sub_01`，涵蓋 12 個註冊與合成檔案空間、共 2,543 個追蹤檔案）使用 `time.perf_counter_ns()` 實測 `SpaceScanner.scan(force=True)` 全空間強制掃描延遲：

| 測試項目 | 修改前 (Baseline) | 修改後 (After) | 變化幅度 (Delta) | 優化根因說明 |
| :--- | :---: | :---: | :---: | :--- |
| **`SpaceScanner.scan(force=True)`** (12 空間 / 2,543 檔案全量掃描) | `2,253,410,000 ns` (`2,253.41 ms`) | `534,959,309 ns` (`534.96 ms`) | **-76.26%** (`4.21x` 加速) | `SpaceRegistry.batch_walk_session()` 在批次內共享子空間走訪結果 (`_walk_memo`) 與目錄 `os.scandir`/`stat` 結果 (`_scandir_memo`)，並以 `CompiledRuleSet._fallback_compiled` 消除已由 $O(1)$ 集合涵蓋規則之線性重掃 |
| **`Installer.cmd_restore`** (單模組還原 + `act_reload` 物化) | `2x` ZIP 完整解壓 | `1x` ZIP 完整解壓 | **-50.0% 解壓 I/O** | `cmd_restore` 完成模組解壓與組態部署後，透過 `skip_materialize_modules` 通知 `act_reload` 跳過重複解壓 |
| **`ContributesAggregator._deep_merge`** (`extend` 列表合併去重) | $O(N^2)$ 線性查找 | $O(N)$ 雜湊集合查找 | **消除二次方退化** | `_extend_list_dedup` 對可雜湊純量維護 `seen_hashable: set` 實現 $O(1)$ 查重 |

### 2.2 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 強化 `_safe_extract_zip` Zip Slip 攔截、`_atomic_swap_dir` `.old` 失敗回滾、`cmd_self_update` PID 暫存檔與 `cmd_restore` 轉發收斂 |
| `ys_codebase/source/core/core/service_contract.py` | New | 新建 `BaseServiceWorkerContract`、`BaseServiceWorker` 與 `touch_activity` 常駐服務基底契約 |
| `ys_codebase/source/core/core/__init__.py` | Modify | 匯出 `BaseServiceWorkerContract`、`BaseServiceWorker`、`touch_activity` 與狀態常數 |
| `ys_codebase/source/core/core/context.py` | Modify | 新增 `sys_path_lock`、`invalidate_host_caches` 與 `update_current_scope_roots` |
| `ys_codebase/source/core/core/uri.py` | Modify | 同步 `set_host_dir`/`set_yscb_root`/`set_module_context` 及 `host_scope`/`yscb_scope`/`module_scope` 與活躍 `RuntimeScope`，移除未引用互動函式 |
| `ys_codebase/source/core/core/symbols.py` | Modify | 支援套件 `__init__.py` 定位並於磁碟 `(mtime_ns, size)` 更新時切換至 `core.loader` 重新載入 |
| `ys_codebase/source/core/core/contributes.py` | Modify | `_extend_list_dedup` $O(1)$ 去重、`atomic=True` 寫入、頂層 `contributes.json` 命令支援與 `get_merged_contributes()` |
| `ys_codebase/source/core/core/events.py` | Modify | `broadcast()` 透過 `sys_path_lock` 與 `remove_inserted_sys_paths()` 執行非破壞性路徑清理 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `_load_registry` 納管單檔 `contributes.json` 與 `(mtime_ns, size)` 指紋快取，並以 `sys_path_lock` 保護 `sys.argv` |
| `ys_codebase/source/core/core/platform/venv.py` | Modify | 以 `sys_path_lock` 保護 `sys.path` 注入並提供 `remove_inserted_sys_paths()` |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | 確保鎖檔案句柄確定性關閉並新增 `is_transaction_locked()` |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 確保子進程管道與 `os.scandir` 迭代器於 `finally` 確定性關閉 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出 `is_transaction_locked` 與 `remove_inserted_sys_paths` |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 新增 `_try_copy_host_pip_to_site_packages()` 支援無 `ensurepip` wheel 之離線容器自舉 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | 新增帶 `.old` 回滾之 `atomic_swap_directory` 並修復 `_safe_copytree` 大小寫敏感度判定 |
| `ys_codebase/source/core/core/vfs/__init__.py` | Modify | 匯出 `atomic_swap_directory` 與 `robust_replace` |
| `ys_codebase/source/core/core/engine.py` | Modify | 跨操作可重入共用鎖、Zip Slip 守門、`act_reload` 支援 `skip_materialize_modules` 與 `invalidate_host_caches` |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_restore` 透過 `skip_materialize_modules` 避免二次解壓 |
| `ys_codebase/source/core/core/log.py` | Modify | `_rotate_lines_file` 保留原始副檔名並新增 `create_managed_thread` |
| `ys_codebase/source/core/core/space/schema.py` | Modify | `CompiledRuleSet` 新增 `_fallback_compiled` 短路加速 |
| `ys_codebase/source/core/core/space/registry.py` | Modify | 新增 `batch_walk_session()` 批次走訪與 `os.scandir` 記憶化，並夾限負值 `mtime_ns` |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `scan()` 啟用 `batch_walk_session()`、`_load_snapshot_state` 納入尾部校驗碼快取鍵、`patch_files` 夾限負值 `mtime_ns` |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 以 PEP 562 `__getattr__` 動態解析 16 個空間子命令別名 |
| `ys_codebase/source/core/scripts/migrations/1.2.8.x.py` | Modify | 新增 `_cleanup_legacy_file_space_residuals` 清理舊 `file-space` 殘留 |
| `ys_codebase/source/core/tests/test_runtime_context.py` | Modify | 新增 `test_ft05` 覆蓋 `RuntimeScope` 同步、`invalidate_host_caches`、`symbols` 熱重載與 `BaseServiceWorkerContract` |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 新增負值 `mtime_ns` 夾限、`batch_walk_session` 去重與 `1.2.8.x.py` 殘留清理測試 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 新增跨操作鎖重入、`is_transaction_locked`、Zip Slip 攔截、`atomic_swap_directory` 回滾、日誌輪替與離線 `pip` 複製測試 |

---

## 3. 測試驗證與合規檢核結果 (Test & Verification Results)

### 3.1 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：於隔離沙盒執行 `python3 yscb.py dev test --m core`，共 **287 項測試（3 項 Contract 測試 + 284 項 Custom 測試：Logic 80, Env 204）100% 通過（0 Failed, 0 Skipped，耗時 36.98s）**，0 `ResourceWarning`。
- **實機 UX / 人工驗證**：執行 `python3 yscb.py dev check`，全倉 9 大模組 **100% Passed（0 Warnings, 0 Failed）**，且正規表達式掃描確認源碼與測試註解中 0 審計單號殘留。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `changelog.md` | 已完成 | 同步記錄 `sub_01` 實作、基準實測與驗證結案 |
| **中觀 (Meso)** | `ys_codebase/source/core/README.md` | 免更 | 公開 CLI 命令與參數契約維持 100% 向下相容 |
| **中觀 (Meso)** | `P01-05_auto.md` | 已完成 | 完整記錄 `S4` 架構收斂、`BaseServiceWorkerContract` 與批次掃描去重設計 |
| **中觀 (Meso)** | `P00_discuss.md` | 已完成 | 記錄核心設計決策 `DR-01` ~ `DR-03` |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 嚴格維護 Docstring，零審計單號或任務標籤殘留 |

### 4.2 品質與清理檢核

- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack、無審計單號殘留。
- [x] **測試完整覆蓋**：所有 287 項單元測試與環境整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core): unify RuntimeScope with uri_tls, add BaseServiceWorkerContract, and deduplicate batch space scans

- Synchronize uri.set_host_dir/set_yscb_root/set_module_context and scope context managers with active RuntimeScope
- Add RuntimeContext.invalidate_host_caches and mtime/size staleness verification in core.symbols
- Create core.service_contract.BaseServiceWorkerContract and centralize is_transaction_locked in core.platform.lock
- Make AtomicEngine.act_lock reentrant across operations, add Zip Slip and atomic_swap_directory rollback guards, and support offline host pip copy fallback
- Add SpaceRegistry.batch_walk_session and CompiledRuleSet._fallback_compiled, reducing full space scan latency by 76.3% (4.21x speedup)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：實機執行 `PlanVerifier` 驗證 `sub_01_core_bootstrap_and_space_remediation` 100% Passed（`0 Errors, 0 Warnings`）。

### 模擬新環境全 CLI 部署驗收補充紀錄

- **實機驗收結果**：於模擬新環境部署全 CLI 實機測試中，額外收斂 `core/contributes.py` 對 `module://` 暫存目錄（`.staging_*` / `.old_*`）之過濾防護與 `core/pip_manager.py` 離線環境 `--retries=1 --timeout=5` 快速退避，驗證 26 項 Core/Bootstrap 與 13 項 `fs`/`file-space` CLI 指令 100% 通過。
