# 專題調研與分析報告：YS-Codebase 第二輪全專案九維度與三平台深度審計報告 (R03_round2_full_codebase_9d_deep_audit_report.md)

> 調研主題：YS-Codebase 第二輪全量生產模組九維度（C1~C9 含 A1~A5 架構與 D1~D5 演進債）深度審計 (`Group A` ~ `Group L`)  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：於第一輪八維度深度審計（`R01` 共 67 項）與架構演進債審計（`R02` 共 92 項）全量修復並收斂後，針對更新後之全倉源碼進行第二輪九維度（納入第九維度 `C9` 架構整理 `A1`~`A5` 與演進技術債 `D1`~`D5`）單點序列深度審計，發掘第一輪修補後顯現之更深層跨模組狀態耦合、IPC 安全性、SQLite 並發事務與上帝物件職責膨脹問題。
- **調研目標與範疇**：涵蓋 `yscb.py` 與 `core`、`ast`、`knowledge-db`、`server`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 全倉 218+ 個生產源碼與組態檔案（12 個審計分組 `Group A` ~ `Group L`），執行 `C1`~`C9` 九維度與三平台（Linux / Windows / macOS）深度掃描與三步自我反駁（Step 2.5），產出 P0~P3 分級清單與 `S1`~`S6` Mode A 根因重構手術藍圖。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

# 🛡️ YS-Codebase 全專案第二次九維度單點序列深度審計與架構整理報告 (R03_round2_full_codebase_9d_deep_audit_report.md)

> 調研主題：第一輪修復與 S1~S6 手術後之全專案第二次九維度 (C1~C9 / A1~A5 & D1~D5) 零錨定單點序列深度審計報告  
> 建立日期：2026-11-09  
> 所屬主計畫：[2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella](https://drive.google.com/drive/folders/1yk4TPRleZ5fHM73bcAJcXErnQPcFamuH)  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

### 2.1 審計執行摘要與全專案健康度總覽 (Executive Summary & Health Matrix)

- **受審範圍與規模**：[`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 宿主引導器與 [`ys_codebase/source/`](https://drive.google.com/drive/folders/1u2cfAcil4lo693qE0wXU5xAu58fci-WN) 下八大核心模組（`core`、`server`、`knowledge-db`、`ast`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support`），共劃分為 **6 大盲審群組（24 個獨立審查單元、164 個原始碼與契約檔）**，以 100% 零歷史錨定之冷眼視角完成逐檔序列深潛與三步反向查證。
- **目標語言與平台基準**：語言 `Python 3.11+ (100% Stdlib Microkernel)` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS / Win32) + macOS (APFS / Darwin)` ｜ 架構重構尺度 `Mode B 對外公開契約相容 + Mode A 內部演進技術債根因收斂`
- **跨單元去重後診斷統計總覽**：🔴 **P0 (Critical)**：`14` 項 ｜ 🟠 **P1 (High)**：`33` 項 ｜ 🟡 **P2 (Medium)**：`31` 項 ｜ 🔵 **P3 (Optimization)**：`16` 項（共確認 **94 項深層問題與半套重構演進債**，另經三步反向查證排除假陽性 **26 項**）

| 審計群組 (Audit Group) | 涵蓋模組與單元範圍 | 🔴 P0 | 🟠 P1 | 🟡 P2 | 🔵 P3 | 小計 | 已排除假陽性 | 核心深層病灶摘要 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Group A** | [`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) + `core` Part 1 (Context, URI, Config, Loader, Symbols, ServiceContract, VFS, Platform) | 2 | 6 | 5 | 3 | **16** | 5 | `uri.resolve()` 失去 `_reconciling_tokens` 循環保護引發無限遞迴、`service_contract` 將 `virtual_cwd` 優先綁為 `.yscb` 且三套 `BaseServiceWorker` 未真正統一、`ContextVar` 與 `uri_tls` 退出時漏還原。 |
| **Group B** | `core` Part 2 (Engine, Installer, Migrations, Contributes, Gitignore, Dispatcher, Space) | 3 | 4* | 5 | 3 | **15*** | 5 | `gitignore status` 唯讀刪檔與跨進程規則蒸發、`act_migrate` 晚於 `act_reload` 執行且 `act_snapshot` 漏備份 `storage.local://`、`.yscb.lock` 先釋放再 `unlink` 引發 POSIX Inode 競態、動態打包反向覆寫 `release/*.zip` 觸發二次安裝 SHA-256 崩潰。 |
| **Group C** | `server` + `knowledge-db` (Master, WarmWorker, Service, SpaceWatcher, KDB Engine/Pipeline/Hybrid) | 2 | 5 | 7 | 3 | **17** | 5 | `CoreSpaceWatcher` 在 `sync_dependent_snapshots_batch` 前提前廣播事件導致 `ast` 的 `__all__` 游標永遠落後 1 世代、`kdb.sync_incremental_changes` 在 `hot_patch` 前提前退出 `with consume_ctx` 完成 ACK、單空間 `<space>.index.bin.gz` 舊軌未退役、`_idle_ttl_loop` 未檢查任務忙碌狀態即強制關機。 |
| **Group D** | `ast` (Schema, Engine, Bundler, Linker, Resolver, Parsers, TreeSitter, Hooks) | 2 | 4 | 3 | 1 | **10** | 3 | 新舊兩代圖譜與雙 Linker (`TopologyLinker` vs `WorkspaceGraphLinker`) 仍並存導致單檔提取 4 次、單檔 `hot_patch_index` 重跑全倉 4-Pass Linker、C# `partial` 修改未重連未修改姊妹檔之呼叫點、單空間更新誤呼叫 `ack(None)` 抹除其他空間待處理游標。 |
| **Group E** | `dev` + `vscode-support` (Checker, Builder, Releaser, Tester, Sandbox, Projector, SchemaCompiler) | 2 | 6 | 6 | 4 | **18** | 5 | `Releaser.release_git` 執行全倉 `git add -A` 且先寫 `manifest.json` 後跑測試、`_sweep_sandboxes` 在 `max_keep=None` 時漏保護 `YSCB_SANDBOX_DIR` 跨進程誤刪活躍沙盒、`Builder` 被 `index.json` 幽靈版本擠佔滑動窗口誤刪實體 `.zip`、`projector._translate_exclude_to_vscode_glob` 多段相對路徑死路。 |
| **Group F** | `agents-workflow` + `gdrive-support` (Compiler, Publisher, Plans, SyncCoordinator, Transport, Sandbox) | 3 | 8 | 5 | 2 | **18** | 3 | 背景 `GDriveSyncServiceWorker` 在獲取 `sync.lock` 前無鎖呼叫 `_load_local_state()` 重放並刪除前景正在寫入的 WAL Journal、`checkout_branch` 異常時在 `finally` 強制改寫 `active_branch`、Level 1 增量快取提前突變 `branches` 卻未同步推進 `page_token`、4 反引號巢狀 Code Fence 正則提前閉合、`_parse_ts` 將無時區本地時間強轉 UTC 產生 8 小時偏移。 |
| **全專案總計** | **8 大核心模組 + `yscb.py`（共 24 個審查單元）** | **14** | **33** | **31** | **16** | **94** | **26** | *註：Group A `AUD-06` 與 Group B `AUD-B08`（`atomic_swap_directory` 雙軌分裂）於總表跨組去重合併為 1 項 P1。* |

---

### 2.2 全專案跨模組「根因架構整理手術藍圖」總覽 (Master Mode A Architecture Surgery Blueprints: S1 - S6)

為什麼第一輪修復後會浮現這 94 項深層問題？因為第一輪的多項重構屬於**「新軌道已鋪設、但舊軌道未拆除或邊界時序未閉環的半套重構（Half-Way Refactoring）」**（例如：新增了 `core/service_contract.py` 但 `server`/`kdb`/`gdrive` 仍各自保留舊 `BaseServiceWorker`；新增了 `WorkspaceGraphLinker` 但 `TopologyLinker` 與 `convert_legacy_symbols_to_file_graph` 仍在跑；新增了 `sync_dependent_snapshots_batch` 但廣播仍在迴圈內提前觸發；移除了 `uri.py` 的 `input()` 卻忘了把 `scheme_token` 推入 `reconciling` 集合）。

以下 **6 大跨模組 Mode A 根因重構手術（`S1` ~ `S6`）** 從架構源頭一次性收斂全部 14 項 P0 與 33 項 P1：

| 手術編號 | 跨模組根因重構手術名稱 | 涵蓋模組 | 解決之核心問題 | 核心架構改造與半套重構收斂方案 |
| :--- | :--- | :--- | :--- | :--- |
| **`S1`** | **Core 基礎設施閉環：URI 循環防衛、ContextVar/TLS 對齊、單一 `atomic_swap_directory` 與生命週期交易正交化** | `yscb.py`, `core` | `A-AUD-01`, `A-AUD-04`~`08`, `B-AUD-01`~`04`, `B-AUD-08` | 1. **URI 循環保護復原**：於 `_resolve_const_scheme` / `_resolve_config_scheme` 進入遞迴前將 `scheme_token` 推入 `_reconciling_tokens`。<br>2. **交易與鎖安全**：移除 `act_unlock` 解鎖後的 `vfs.remove(".yscb.lock")` 防止 POSIX Inode 競態；在 `act_migrate` 後強制重刷 `scan_and_inject()` 與 `gitignore.sync()`；補齊 `act_snapshot` 對 `storage.local://` 的備份與 `cmd_restore` 快照保護；禁止 Tier 2 本地動態打包反向覆寫 `release/<mod>/<ver>.zip`。<br>3. **CQS 與跨進程 Gitignore**：禁止 `gitignore status` 與 `yscb.py:load_config` 在唯讀查詢中刪檔或寫盤；新進程啟動時自 `project://.gitignore` 現有託管區塊回填動態規則基準；將 `engine._atomic_swap_dir` 與 `os_backend.atomic_swap_directory` 徹底合而為一。 |
| **`S2`** | **Server & Space 批次快照延遲廣播、服務契約三合一與優雅停機閉環** | `core`, `server`, `knowledge-db`, `gdrive-support` | `A-AUD-02`~`03`, `B-AUD-06`~`07`, `C-AUD-01`, `C-AUD-03`, `C-AUD-07` | 1. **統一 `BaseServiceWorkerContract`**：修正 `service_contract.py` 中 `vcwd = host_dir or yscb_dir` 優先序，合入 `"busy"` IPC 欄位、端點快取與 `ProxyHandler({})`，並讓 `server`、`kdb`、`gdrive` 100% 繼承同一基底類別。<br>2. **Batch-Sync-Before-Broadcast**：在 `CoreSpaceWatcher` 與 `SpaceScanner` 中，嚴格先完成全部子空間更新與 `sync_dependent_snapshots_batch()`（對齊 `/short` 與 `__all__`），最後才發出訂閱通知與 `on_file_space_changed` 廣播；並將 `is_transaction_locked()` 移至確認 `_dirty_spaces` 非空後再執行。<br>3. **IPC 保活與 Idle TTL 防誤殺**：打通 `BaseServiceWorker.touch_activity` 的 IPC `"touch_activity"` 封包發送端；在 `_idle_ttl_loop` 關機前強制檢查 `_is_worker_completely_idle()`，並為 `_wait_worker_ready` 增設超時上限。 |
| **`S3`** | **Knowledge-DB 多空間 `ExitStack` 原子游標交易、單空間舊軌退役與快取 SSOT 收斂** | `knowledge-db` | `C-AUD-02`, `C-AUD-04`~`05`, `C-AUD-09`~`11`, `C-AUD-13`, `C-AUD-15`~`17` | 1. **兩階段原子游標 (`ExitStack`)**：在 `sync_incremental_changes` 入口加 `self._index_lock`，並以 `ExitStack` 保持所有 `target_spaces` 的 `consume_ctx` 開啟，直到 `hot_patch_unified_index` 或 `build_unified_index` 成功落盤後才退出並一次性 ACK 游標。<br>2. **單空間舊軌退役**：廢除 `build_index(space=...)` 寫入 `<safe_name>.index.bin.gz` 與 `_index_cache` 的脫節舊軌，統一路由至 `build_unified_index()`。<br>3. **快取與 CQS 純化**：將 `"vector_dirty"` 與 `indices_dir` 納入共享快取 SSOT；移除 `is_available` 的 `[GUARD]` 輸出副作用與 6 處 `suppress_guard_prompt` 塗改；修正 `is_dirty_file_match` 跨模組同名相對路徑（如 `scripts/cli.py`）誤匹配。 |
| **`S4`** | **AST 單軌圖譜收斂、C# `partial` 姊妹檔連帶重連與單空間精準游標 ACK** | `ast` | `D-ARCH-01`~`03`, `D-AUD-02`, `D-AUD-05`~`10` | 1. **單次提取與單軌 Linker**：統一以 `extract_file_graph() -> FileSymbolGraph` 為唯一原生提取入口並直接投影 `UnifiedSymbol`，拔除單檔 4 次解析與 270 行 `convert_legacy_symbols_to_file_graph`；廢除 `TopologyLinker` 雙軌模糊猜測與 `file_graphs` 雙重序列化。<br>2. **增量熱修補完整性**：在 `hot_patch_index` 中將受影響之 C# `partial` 存活姊妹檔納入 call sites 重連範圍，補傳 `known_indexed_files` 防止刪檔殘留，並移除單空間更新時誤抹除全空間游標的 `ack(None)`。<br>3. **CQS 與跨平台路徑**：移除 `get_persisted_meta` 與 `get_workspace_graph(auto_sync=False)` 的暗中寫盤副作用，並移除 `atomic_save_gzip_pickle` 在正常 `finally` 中誤刪併發 `.tmp` 檔的 `glob` 迴圈。 |
| **`S5`** | **Dev & VSCode 發布/建置兩階段原子交易、沙盒隔離保護與 Schema 契約統一** | `dev`, `vscode-support` | `E-DEV-P0-01`~`02`, `E-DEV-P1-01`~`04`, `E-VSC-P1-01`~`02` | 1. **`Releaser` & `Builder` 兩階段提交**：在 `release_git` 中先跑通過測試再改寫 `manifest.json`，以 `try...finally` 保證任何失敗皆回滾 `manifest.json`，並限制 `git add` 範圍（禁止全倉 `git add -A`）；在 `Builder` 中僅對實體存在的 `.zip` 計算滑動窗口，並在寫完新包與 `index.json` 後才清理淘汰舊檔。<br>2. **跨進程沙盒保護**：在 `_sweep_sandboxes` 中無條件保護 `YSCB_SANDBOX_DIR`。<br>3. **VSCode 跨平台與 Schema 對齊**：修復 `_translate_exclude_to_vscode_glob` 多段相對路徑死路與 macOS `/private/var` `realpath` 比對；100% 對齊 `SchemaCompiler` 與 `Checker` 的 `manifest.json` 契約。 |
| **`S6`** | **Workflow 同長反引號分段器、Plans 單一狀態機與 GDrive 跨進程鎖/帳本/連線池閉環** | `agents-workflow`, `gdrive-support` | `F-AUD-01`~`18` | 1. **GDrive 並發與交易安全**：禁止 `GDriveSyncServiceWorker` 在取得 `sync.lock` 前呼叫 `_load_local_state()` 重放/刪除前景 WAL Journal；修正 `_refresh_active_branch` 被舊 `sync_state.json` 反蓋問題；將 `checkout_branch` 改為先下載驗證成功後再刪舊檔與提交 `active_branch`；確保 Level 1 增量快取 `branches` 與 `page_token` 原子同步；於 4 處 `ThreadPoolExecutor` 結束時歸還 TLS `HTTPSConnection`。<br>2. **Workflow 與 Plans 統一**：支援 4+ 反引號巢狀 Code Fence 與雙反引號 Code Span 對稱匹配；修復 `_parse_ts` 本地時間誤轉 UTC 的 8 小時偏移；將 `status.py`、`scanner.py`、`_common.py` 收斂至單一 `plans/state_machine.py`。 |

---


---

## Part I — Group A：`yscb.py` 與 `core` 模組第一部分（基礎設施與執行期核心）

# 🛡️ YS-Codebase (`yscb.py` & `core` Part 1) 第二次九維度單點序列深度審計與架構整理報告

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：`/working_dir/c_3fdac06fe2853f20/repo_workspace` 下之宿主引導器 `yscb.py` 與 `core` 模組第一部分（基礎設施與執行期核心：`context.py`, `uri.py`, `config.py`, `validator.py`, `loader.py`, `symbols.py`, `events.py`, `log.py`, `service_contract.py`, `update_checker.py`, `commands/resolver.py`, `space/exceptions.py`, `vfs/*`, `pip_manager.py`, `platform/*`），共劃分為 **4 個審查單元（21 個原始碼檔案）**，已按順序逐一完成單點序列深潛與跨單元三步反向查證。
- **目標語言與平台基準**：語言 `Python 3 (100% Standard Library)` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS / Win32) + macOS (APFS / Darwin)` ｜ 架構重構尺度 `Mode B 對外契約 100% 相容 + Mode A 內部演進技術債根因收斂`
- **診斷統計總覽**：🔴 **P0**：`2` 項 ｜ 🟠 **P1**：`6` 項 ｜ 🟡 **P2**：`5` 項 ｜ 🔵 **P3**：`3` 項（共 **16** 項確認問題，並已反向查證排除假陽性 **5** 項）

| 審查單元 (Audit Unit) | 涵蓋檔案 (含 Google Drive 連結) | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`**<br>(`yscb.py` 宿主引導器) | [`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) | `AUD-04`, `AUD-08`, `AUD-10`, `AUD-14` | 🟠 具跨平台與雙軌分歧隱患 |
| **`Unit 02`**<br>(`core` 上下文、URI 與配置) | [`core/context.py`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk), [`core/uri.py`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk), [`core/config.py`](https://drive.google.com/file/d/1u6KPwLuOKDZ9DdOX69t_3gisvtL68Et-/view?usp=drivesdk), [`core/validator.py`](https://drive.google.com/file/d/1pdnoxDaEP0KSXdXco4uNszuS9UaPGORA/view?usp=drivesdk), [`core/space/exceptions.py`](https://drive.google.com/file/d/1LbgQTgEk0ikQe5XKKifidgm86OyO6jf6/view?usp=drivesdk) | `AUD-01`, `AUD-05`, `AUD-07`, `AUD-09`, `AUD-11` | 🔴 具循環遞迴崩潰與雙軌分裂 |
| **`Unit 03`**<br>(`core` 載入、符號、事件、日誌與服務契約) | [`core/loader.py`](https://drive.google.com/file/d/1bMcC0wixXQqyBTdtRpJNhqTlWCzU6KTt/view?usp=drivesdk), [`core/symbols.py`](https://drive.google.com/file/d/1je2ZAayvSyYe5oidZoM7u-jP93a7nzYd/view?usp=drivesdk), [`core/events.py`](https://drive.google.com/file/d/191xVRzHXcdirSYuAnRocZ-C48F62pFFX/view?usp=drivesdk), [`core/log.py`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk), [`core/service_contract.py`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk), [`core/commands/resolver.py`](https://drive.google.com/file/d/11fRM6pDlZg772SHp9vfIBpRw4pDQgAV9/view?usp=drivesdk), [`core/update_checker.py`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk) | `AUD-02`, `AUD-03`, `AUD-07`, `AUD-12`, `AUD-15` | 🔴 具執行期目錄錯位與平行分裂 |
| **`Unit 04`**<br>(`core` VFS、Pip 與平台原語) | [`core/vfs/__init__.py`](https://drive.google.com/file/d/1HvK63iZbW_jxTcwjA5D3rn5VmQ35JxOe/view?usp=drivesdk), [`core/vfs/base.py`](https://drive.google.com/file/d/1O9nn80EjstJ9hG3xd17DgOVf_Kxbh5to/view?usp=drivesdk), [`core/vfs/os_backend.py`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk), [`core/vfs/path.py`](https://drive.google.com/file/d/1ng9XCqOIANJE8DKp9hjyL7Zct2q3BKSo/view?usp=drivesdk), [`core/vfs/vfs.py`](https://drive.google.com/file/d/1fPGYENRi-IQMf5qhRO2FLI8ci-Y6AH21/view?usp=drivesdk), [`core/pip_manager.py`](https://drive.google.com/file/d/1aEVbUF-s4PUoUIw1nvvLZuJChppVDNOC/view?usp=drivesdk), [`core/platform/__init__.py`](https://drive.google.com/file/d/1IogdVczUyU-l50cWLj5KrcWlidmz8Wo0/view?usp=drivesdk), [`core/platform/daemon_probe.py`](https://drive.google.com/file/d/1oXnRnmrKi1X1zTmxoNo-XNIA0ys4o8BM/view?usp=drivesdk), [`core/platform/lock.py`](https://drive.google.com/file/d/1JnE7Sp_K0C5pHrifLkgcs3qpj6_ncKrK/view?usp=drivesdk), [`core/platform/process.py`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk), [`core/platform/venv.py`](https://drive.google.com/file/d/1qdXIHmBLZJagGMKJ7jya3Gm_CjgqcaxZ/view?usp=drivesdk) | `AUD-06`, `AUD-07`, `AUD-08`, `AUD-13`, `AUD-16` | 🟠 具目錄交換分歧與非重入鎖陷阱 |

---

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S6)

針對第一輪修復後浮現的「半套重構殘留（Half-Baked Refactoring Remnants）」與跨模組平行實作漂移，彙整以下 6 大 **Mode A 根因重構手術藍圖**：

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **語意 URI 循環依賴防護與 ContextVar 單軌統一手術** | `AUD-01`, `AUD-05` | `C1.1 / C9.3 (A3)` | 1. 在 [`core/uri.py:L500-L639`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) 的 `_resolve_const_scheme` 與 `_resolve_config_scheme` 進入遞迴 `resolve()` 前，將 `scheme_token` 推入 `_reconciling_tokens` 並於 `finally` 彈出，修復第一輪移除 `input()` 後淪為死欄位的循環檢測機制。<br>2. 將 `uri_tls` 全面收斂至 `_ACTIVE_RUNTIME_SCOPE` (`ContextVar`)，消除 `with bind_runtime_context(): uri.set_host_dir(None)` 退出時殘留舊 TLS 狀態的雙軌分裂。 |
| **`S2`** | **背景服務契約 (`service_contract`) 單一真實來源收斂與 `virtual_cwd` 語意修正手術** | `AUD-02`, `AUD-03` | `C9.1 (A1) / C9.2 (A2) / C7.1` | 1. 修正 [`core/service_contract.py:L240-L255`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) 與 [`server/service.py:L293-L308`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) 中 `vcwd = yscb_dir or host_dir` 的優先序顛倒問題，改為 `vcwd = host_dir or yscb_dir`，防止分離式佈局（`.yscb` 子目錄）下背景 Worker 誤將 `.yscb` 當作專案根目錄。<br>2. 將 `server/service.py` 的 `(mtime_ns, port, token)` 端點快取與 `busy` IPC 欄位合入 `core/service_contract.py`，並讓 `server/service.py`、`knowledge_db/service.py`、`gdrive_support/service.py` 100% 繼承 `core.service_contract.BaseServiceWorkerContract`，拔除 3 處重複定義的 170+ 行平行類別。 |
| **`S3`** | **目錄原子交換 (`atomic_swap_directory`) 三軌合一與 Windows 句柄鎖降級統一手術** | `AUD-06`, `AUD-08` | `C2.2 (Win32) / C9.2 (A2)` | 1. 將 [`core/engine.py:L393-L622`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 具備「三階段目錄鎖探針 (`_is_dir_handle_locked_for_rename`) + 全有全無檔案級原地同步 (`_inplace_atomic_sync_dir`) + 殘留 `.old_/.staging_` 掃除」的完整實作下沉至 [`core/vfs/os_backend.py:L150-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 成為 `core` 唯一正統實作，`engine.py` 直接引用 `vfs.atomic_swap_directory`。<br>2. 同步補齊 [`yscb.py:L517-L540`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 與 `os_backend.py` 在回滾及刪除唯讀檔（如 Windows `.git` packfiles）前呼叫 `_force_writable()` 與 `robust_rmtree` 重試。 |
| **`S4`** | **拔除規避靜態護欄之 Metaclass、PEP 562 鏡像與白箱 Mock 嗅探手術** | `AUD-07` | `C9.2 (D5)` | 1. 移除 [`core/update_checker.py:L292-L311`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk) 檢測 `self.__dict__` 與 `getattr(type(self), ...)` 的執行期 Mock 嗅探分支及死方法。<br>2. 移除 [`core/platform/process.py:L38-L49`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) 操作 `globals().pop("_CAN_SPAWN_DAEMON_CACHE")` 的逃逸補丁。<br>3. 將 [`core/contributes.py:L427-L535`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) 與 [`core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 改為呼叫 `get_runtime_context()` 公開屬性，不再透過 PEP 562 `__getattr__` 存取私有底線變數。 |
| **`S5`** | **冷啟動設定檔載入 CQS 純化與相對路徑基準對齊手術** | `AUD-04`, `AUD-10` | `C9.1 (D1) / C1.2` | 1. 將 [`yscb.py:L176-L202`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) `load_config()` 中的磁碟寫入副作用抽離：讀取時僅在記憶體正規化舊版 `LEGACY_PROVIDER_URLS`，僅於 `init` / `restore` / `update` 等顯式寫入命令才持久化回磁碟，消除唯讀查詢觸發 Watchdog 髒事件的副作用。<br>2. 修正 [`yscb.py:L911`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) `_discover_latest_core(provider, base_dir=base_dir)` 傳遞 `base_dir` 並於 [`yscb.py:L1378-L1415`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) `cmd_restore` 支援 `--provider` 參數，對齊 `yscb.py` 與 `core` 行為。 |
| **`S6`** | **跨進程鎖同進程重入防護與非重入鎖升級手術** | `AUD-12`, `AUD-13` | `C4.3 / C2.2 (Win32)` | 1. 將 [`core/service_contract.py:L52-L63`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) 與 [` core/context.py:L233-L245`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) 的 `server_touch_lock` 與 `cell_seq_lock` 統一升級為 `threading.RLock()`，並於 `CellScope` 增設執行緒安全保護。<br>2. 在 [`core/platform/lock.py:L25-L140`](https://drive.google.com/file/d/1JnE7Sp_K0C5pHrifLkgcs3qpj6_ncKrK/view?usp=drivesdk) `InterProcessLock` 中加入進程內路徑級引用計數與 `RLock` 協調表，防止 Windows `msvcrt.locking` 同進程不同實例重入時自我鎖死（`winerror 33`），以及 POSIX `flock` 第二個實例 `close(fd)` 時意外釋放鎖或引發競爭。 |

---

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：循環遞迴崩潰 / 執行期目錄錯位與平行分裂）

- [x] **[AUD-01] [🔴 P0 | C1.1 & C9.2 (A2/D2) | All-OS] [`ys_codebase/source/core/core/uri.py:L430-L450`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) & [`L491-L562`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) - `uri.resolve()` 對自引用或循環 URI Scheme 完全失去 `_reconciling_tokens` 保護，引發 `RecursionError` 崩潰**
  - **問題座標與分類**：[`ys_codebase/source/core/core/uri.py:L430-L450`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) (`reconcile_undefined_uri`)、[`L491-L562`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) (`_resolve_const_scheme`, `_resolve_config_scheme`) ｜ `C1.1` 邏輯契約失步、`C9.2 (A2)` 半套重構殘留 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - 在第一輪重構移除阻塞式 `input()` 互動補齊時，`reconcile_undefined_uri` 被簡化為檢查 `if scheme_token in reconciling: raise CyclicURIDependencyError(...)` 後直接拋出 `UndefinedURIError`。
    - 然而，經全倉反向查證，`core/uri.py` 的生產路徑中**沒有任何一處呼叫 `reconciling.add(scheme_token)`**！`reconciling.add(...)` 僅存在於單元測試 [`tests/test_uri.py:L146`](https://drive.google.com/file/d/1reqXrfDROedHGir9SHWwbzzXPBSKoFas/view?usp=drivesdk) 與 [`tests/test_runtime_context.py:L436`](https://drive.google.com/file/d/1SEr9vGdgCJuS4AFpnAzLxpKtkJYJTpKU/view?usp=drivesdk) 的人工塞值測試中。
    - 當使用者或模組在 `config.project.json` 或 `contribute.json` 中設定了自引用或互相引用的協議（例如 `custom_a://` 指向 `custom_b://sub`，而 `custom_b://` 指向 `custom_a://`；或 `project_root` 誤設為 `"project://"`），`_resolve_config_scheme`（`L556`）與 `_resolve_const_scheme`（`L514`）直接遞迴呼叫 `resolve()`，完全不會觸發 `CyclicURIDependencyError`，而是無窮遞迴直到觸發 Python `RecursionError: maximum recursion depth exceeded` 崩潰。
  - **建議解決方案（Recommended Solution - Mode A 根因修復）**：
    - **修改思路**：在 `_resolve_const_scheme` 與 `_resolve_config_scheme` 解析目標 `scheme_token` 時，先檢查 `scheme_token in reconciling`，若已存在則立即拋出 `CyclicURIDependencyError`；否則將 `scheme_token` 加入 `reconciling`，並在 `try...finally` 區塊中確保 `reconciling.discard(scheme_token)`。
    - **程式碼修改範例**：
      ```python
      def _resolve_const_scheme(
          scheme_token: str,
          raw_uri: str,
          sval: str,
          rel: str,
          yscb_dir: str,
          active_mod: Optional[str],
          context: Optional[ExecutionContext],
          interactive: bool,
      ) -> str:
          """Resolves a 'const' type contributed URI scheme with cycle and path traversal protection."""
          reconciling = _get_reconciling_tokens()
          if scheme_token in reconciling:
              raise CyclicURIDependencyError(
                  f"Cyclic or self-referencing URI dependency detected for '{scheme_token}://'"
              )
          reconciling.add(scheme_token)
          try:
              try:
                  host_dir, _ = _get_host_config()
              except Exception:
                  host_dir = get_host_dir() or os.path.normpath(os.path.dirname(yscb_dir))

              if "{module}" in sval:
                  if not active_mod:
                      raise UndefinedModuleContextError(raw_uri)
                  val_expanded = sval.replace("{module}", active_mod)
              else:
                  val_expanded = sval
              val_expanded = val_expanded.replace("{yscb_root}", yscb_dir).replace("{yscb_host}", host_dir or "")

              target_base = resolve(val_expanded, current_module=active_mod, context=context, interactive=interactive)
              return _ensure_safe_subpath(target_base, rel, raw_uri)
          finally:
              reconciling.discard(scheme_token)
      ```
      （對 `_resolve_config_scheme` 同步套用相同的 `reconciling` 進出守衛）。

- [x] **[AUD-02] [🔴 P0 | C9.1 (A1) & C9.2 (A2) | All-OS] [`ys_codebase/source/core/core/service_contract.py:L199-L256`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) - `BaseServiceWorkerContract.bind_worker_context` 將 `virtual_cwd` 優先綁定為 `yscb_dir` 而非 `host_dir`，且全專案三套 `BaseServiceWorker` 平行實作分裂**
  - **問題座標與分類**：[`ys_codebase/source/core/core/service_contract.py:L199-L256`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) (`_resolve_worker_runtime_dirs`, `bind_worker_context`, `set_state`, `touch_activity`) ｜ `C9.1 (A1)` 執行模型上下文錯位、`C9.2 (A2)` 半套重構平行雙軌 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **分離式佈局下 `virtual_cwd` 錯位 (`A1`)**：在 `bind_worker_context`（`L240-L241`）中寫了 `host_dir, yscb_dir = self._resolve_worker_runtime_dirs(context)` 與 `vcwd = yscb_dir or host_dir`。當宿主工作區採用標準分離式佈局（例如 `host_dir = /workspace/my_proj`，`yscb_dir = /workspace/my_proj/.yscb` 或 `ys_codebase`），且 `WarmWorker.start_all` 傳入 `{"yscb_root": self.yscb_root, "workspace_root": self.host_dir}`（見 [`server/worker.py:L162-L166`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk)）時，背景服務執行緒內的 `get_virtual_cwd()` 會回傳 `/workspace/my_proj/.yscb` 而非專案根目錄 `/workspace/my_proj`！當 `project://` 尚未設定或子模組（如 [`core/gitignore.py:L76`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk)、[`core/space/registry.py:L340`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk)、[`knowledge_db/engine.py:L299`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk)）在背景執行緒呼叫 `get_virtual_cwd()` 推算專案根目錄時，會直接誤指到 `.yscb` 內部目錄。此外，若 `worker.start(context)` 未將 `context` 存入 `self.context`（如 `GDriveSyncServiceWorker`），後續無參數呼叫 `with self.worker.bind_worker_context():` 時 `_resolve_worker_runtime_dirs` 會拿到 `(None, None)`，導致背景回呼漏綁 `host_dir` 與 `yscb_dir`。
    2. **三處平行實作分裂與功能漂移 (`A2`)**：`core/service_contract.py` 雖已建立並宣稱提供 `server`, `knowledge-db`, `gdrive-support` 統一基底，但經反向查證：`server/service.py`、`knowledge_db/service.py`、`gdrive_support/service.py` **完全沒有匯入 `core.service_contract`**！`server/service.py` 複製貼上了整份 `BaseServiceWorker` 與 `touch_activity`，且兩者已發生嚴重漂移：
       - `server/service.py` 的 `set_state` 會計算 `busy = target_state in (self.STATE_STARTING, self.STATE_UPDATING)` 並隨 `service_status` IPC 封包發送 `"busy": busy`，但 [`core/service_contract.py:L190-L195`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) **漏掉了 `"busy": busy` 欄位**！
       - `server/service.py` 的 `touch_activity` 實作了 `_get_daemon_endpoint_cache()` 以 `(mtime_ns, port, token)` 快取免除每次讀取 `daemon.json`，但 [`core/service_contract.py:L94-L102`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) 每次仍執行無快取 `open()` + `json.load()`。
       - `knowledge_db/service.py` 與 `gdrive_support/service.py` 各自手寫了 60 行 fallback `BaseServiceWorker`（甚至用 `ThreadPoolExecutor` 偽造 `_ManagedHandle` 且漏綁 `bind_runtime_context`）。
  - **建議解決方案（Recommended Solution - Mode A 根因手術 `S2`）**：
    - **修改思路**：
      1. 在 [`core/service_contract.py`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) 中：將 `bind_worker_context` 的 `vcwd` 修正為 `vcwd = host_dir or yscb_dir`（若 `context` 顯式提供 `"virtual_cwd"` 則優先使用）；在 `start_managed_thread` 中若 `isinstance(context, dict)` 則自動同步保存至 `self.context`；在 `set_state` 中補齊 `"busy": busy` 欄位；在 `touch_activity` 中合入 `(mtime_ns, port, token)` 端點快取與 `127.0.0.1` `ProxyHandler({})` 直連（見 `AUD-03`）。
      2. 讓 `server/service.py`、`knowledge_db/service.py`、`gdrive_support/service.py` 直接 `from core.service_contract import BaseServiceWorker, touch_activity`，徹底刪除重複的平行實作。
    - **程式碼修改範例**：
      ```python
      # core/service_contract.py
      def _resolve_worker_runtime_dirs(
          self, context: Optional[Dict[str, Any]] = None
      ) -> tuple[Optional[str], Optional[str], Optional[str]]:
          if isinstance(context, dict) and context:
              if not isinstance(getattr(self, "context", None), dict):
                  self.context = dict(context)
              else:
                  self.context.update(context)
          ctx_dict = context if isinstance(context, dict) else getattr(self, "context", None)
          yscb_dir: Optional[str] = None
          host_dir: Optional[str] = None
          explicit_vcwd: Optional[str] = None
          if isinstance(ctx_dict, dict):
              raw_yscb = ctx_dict.get("yscb_root") or ctx_dict.get("yscb_dir")
              if raw_yscb:
                  yscb_dir = os.path.abspath(str(raw_yscb))
              raw_host = (
                  ctx_dict.get("workspace_root")
                  or ctx_dict.get("project_root")
                  or ctx_dict.get("host_dir")
              )
              if raw_host:
                  host_dir = os.path.abspath(str(raw_host))
              raw_vcwd = ctx_dict.get("virtual_cwd") or ctx_dict.get("cwd")
              if raw_vcwd:
                  explicit_vcwd = os.path.abspath(str(raw_vcwd))
          return host_dir, yscb_dir, (explicit_vcwd or host_dir or yscb_dir)
      ```

---

### 🟠 P1 - High（顯著缺陷：跨平台必爆 / 雙軌狀態失步 / 資源與代理陷阱 / 演進補丁殘留）

- [x] **[AUD-03] [🟠 P1 | C2.3 & C5.1 | All-OS] [`ys_codebase/source/core/core/service_contract.py:L103-L120`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) - `touch_activity` 對 `127.0.0.1` 發送保活請求未繞過系統 HTTP Proxy，在企業代理環境下必失敗且每次重讀 `daemon.json`**
  - **問題座標與分類**：[`ys_codebase/source/core/core/service_contract.py:L103-L120`](https://drive.google.com/file/d/1ZzHItfJaBxSWm9c5KaThr-m5NvMfXJmM/view?usp=drivesdk) (`touch_activity`) ｜ `C2.3` 網路環境邊界、`C7.1` 重複磁碟 I/O ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - 對照 [`yscb.py:L376-L379`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 的 `_http_get_bytes` 已明確針對 `127.0.0.1` / `localhost` 使用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))` 繞過系統 `HTTP_PROXY` / `http_proxy`，但 `core/service_contract.py` 的 `touch_activity` 卻直接呼叫 `urllib.request.urlopen(req, timeout=1.5)`。
    - 當開發者主機或容器環境配置了 `HTTP_PROXY`（且未將 `127.0.0.1` 列入 `NO_PROXY`）時，`touch_activity` 打向本機 `http://127.0.0.1:{port}/api/touch` 的請求會被導向外部代理伺服器並遭拒（或逾時卡頓 1.5 秒），導致背景服務保活失效、Daemon 在執行長任務期間被誤判閒置而強行關閉。
    - 同時，當請求失敗時 `touch_map[root_key]` 完全不會更新，導致背景迴圈每次呼叫 `touch_activity()` 都會重複同步讀取 `daemon.json` 並卡頓 1.5 秒。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：使用模組級預先建構的 `_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))` 發送本機 `127.0.0.1` 請求，並合入 `server_touch_daemon_cache` 快取 `(mtime_ns, port, token)`（同時在 [`core/context.py:L234`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) `RuntimeContext.__init__` 與 `reset_all_caches` 中正式註冊 `self.server_touch_daemon_cache: Dict[str, Tuple[int, int, str]] = {}`）。
    - **程式碼修改範例**：
      ```python
      _LOCAL_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

      # Inside touch_activity():
      with _LOCAL_NO_PROXY_OPENER.open(req, timeout=1.5) as resp:
          if resp.status != 200:
              return False
      ```

- [x] **[AUD-04] [🟠 P1 | C9.1 (D1: CQS Violation) & C4.1 | All-OS] [`yscb.py:L176-L202`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - `load_config()` 唯讀查詢夾帶無鎖覆寫 `yscb.config.json` 之副作用，違反 CQS 並觸發 Watchdog 假陽性事件**
  - **問題座標與分類**：[`yscb.py:L176-L202`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`load_config`) ｜ `C9.1 (D1)` 違反命令查詢分離 (CQS)、`C4.1` 無鎖並發覆寫 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - `yscb.py` 的 `main()` 在每次 CLI 啟動時（包含 `--help`、`status`、`list` 等純唯讀查詢）都會呼叫 `load_config()`。
    - `load_config()` 內部若發現 `default_provider` 或任一模組的 `provider` 屬於 `LEGACY_PROVIDER_URLS`，會在**未持有任何跨進程交易鎖**的情況下，直接呼叫 `_write_json_lf(cfg_path, data)` 改寫磁碟上的 `yscb.config.json`。
    - 這不僅違反 CQS 原則（在唯讀工作區或容器掛載目錄下污染檔案 `mtime`），還會觸發常駐 `space-watcher` 與 `os_backend._maybe_invalidate_uri_cache` 的快取失效風暴；若此時另一個進程正在執行 `install` / `update`，無鎖寫入更可能與交易寫入發生競態覆蓋。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S5`）**：
    - **修改思路**：`load_config()` 僅在記憶體字典中將 `LEGACY_PROVIDER_URLS` 正規化為 `DEFAULT_PROVIDER_URL`，不在讀取函式內偷寫磁碟；將持久化寫入留給顯式的寫入命令（`cmd_init`、`_update_config_module_version` 等）。
    - **程式碼修改範例**：
      ```python
      def load_config(start_dir: Optional[str] = None, persist_migration: bool = False) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
          """剛性組態載入：僅探測當前目錄同層之 yscb.config.json，並於記憶體正規化舊版官方 Provider URL。"""
          cfg_path = os.path.join(os.path.abspath(start_dir or os.getcwd()), CONFIG_FILENAME)
          if os.path.isfile(cfg_path):
              data = _read_json_dict(cfg_path)
              if isinstance(data, dict):
                  changed = False
                  dp = data.get("default_provider")
                  if isinstance(dp, str) and dp.strip() in LEGACY_PROVIDER_URLS:
                      data["default_provider"] = DEFAULT_PROVIDER_URL
                      changed = True
                  inst = data.get("installed_modules")
                  if isinstance(inst, dict):
                      for m_info in inst.values():
                          if isinstance(m_info, dict):
                              mp = m_info.get("provider")
                              if isinstance(mp, str) and mp.strip() in LEGACY_PROVIDER_URLS:
                                  m_info["provider"] = DEFAULT_PROVIDER_URL
                                  changed = True
                  if changed and persist_migration:
                      try:
                          _write_json_lf(cfg_path, data)
                      except Exception:
                          pass
              return cfg_path, data
          return None, None
      ```

- [x] **[AUD-05] [🟠 P1 | C9.3 (A3: Split-Brain SSOT) | All-OS] [`ys_codebase/source/core/core/uri.py:L123-L251`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) & [`ys_codebase/source/core/core/context.py:L359-L447`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) - `RuntimeScope` (`ContextVar`) 與 `uri_tls` (`threading.local`) 雙軌並存，在 `bind_runtime_context` 內呼叫 `set_host_dir(None)` 或退出作用域時引發狀態遮蔽與殘留洩漏**
  - **問題座標與分類**：[`ys_codebase/source/core/core/uri.py:L123-L251`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) (`set_module_context`, `get_module_context`, `set_host_dir`, `get_host_dir`, `set_yscb_root`, `get_yscb_root`, `host_scope`) ｜ `C9.3 (A3)` 狀態真相分裂 (Split-Brain SSOT) ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - `core/uri.py` 同時維護了 `_ACTIVE_RUNTIME_SCOPE` (`ContextVar`) 與 `uri_tls` (`threading.local`) 兩套上下文儲存，導致兩個嚴重的狀態分裂漏洞：
      1. **退出 `bind_runtime_context` 後的 TLS 污染洩漏**：`bind_runtime_context`（[`core/context.py:L388-L447`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk)）退出時只會 `reset` `_ACTIVE_RUNTIME_SCOPE`，**不會還原 `uri_tls`**。若程式碼在 `with bind_runtime_context(...):` 區塊內呼叫了 `uri.set_host_dir("/tmp/inner")` 或 `uri.set_module_context("mod_x")`，該呼叫會同時寫入 `RuntimeScope` 與 `uri_tls`。當 `with bind_runtime_context` 結束後，`_ACTIVE_RUNTIME_SCOPE` 恢復為 `None`，但 `uri_tls.active_host_dir` 卻永久殘留 `"/tmp/inner"`，污染該執行緒後續的所有請求！
      2. **傳入 `None` 清除時被父層環境變數反向遮蔽**：在 `get_host_dir()`（`L165-L176`）中，檢查條件為 `if scope is not None and scope.active_host_dir: return scope.active_host_dir`。當呼叫端在 `with bind_runtime_context(host_dir="/tmp/a"):` 內呼叫 `uri.set_host_dir(None)`（或 `with uri.host_scope(None):`）意圖暫時清空 `host_dir` 時，`scope.active_host_dir` 為 `None`，結果 `get_host_dir()` 竟穿透 `RuntimeScope` 往下讀取 `os.environ["YSCB_HOST_DIR"]`，導致顯式的 `host_scope(None)` 無法隔離環境變數（對照 [`tests/test_uri.py:L191`](https://drive.google.com/file/d/1reqXrfDROedHGir9SHWwbzzXPBSKoFas/view?usp=drivesdk) `with uri.yscb_scope(None):` 之所以能讀到 `YSCB_ROOT_DIR` 是依賴此穿透，但卻與 `RuntimeScope` 雙軌衝突）。
      3. **`host_scope(host_dir, yscb_dir=None)` 未保存/還原內層對 `yscb_dir` 的修改**：在 [`core/uri.py:L201-L210`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) 中，若呼叫 `with uri.host_scope(host_dir):`（未傳 `yscb_dir`），且區塊內部呼叫了 `uri.set_yscb_root(...)`，`finally` 區塊因為 `if yscb_dir is not None:` 為 False，不會還原 `tls.active_yscb_dir` 與 `old_scope_yscb`。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S1`）**：
    - **修改思路**：
      1. 在 `bind_runtime_context` 進入時快照 `(tls.active_host_dir, tls.active_yscb_dir, tls.active_module_context)`，並於 `finally` 退出時一併還原 `uri_tls`，確保在 `bind_runtime_context` 內呼叫 `uri.set_*` 絕不洩漏至作用域外。
      2. 在 `host_scope` 的 `finally` 區塊中無條件還原 `tls.active_yscb_dir = old_yscb` 與 `active_yscb_dir=old_scope_yscb`，消除條件分支遺漏。
    - **程式碼修改範例**：
      ```python
      # core/uri.py: host_scope finally block
      finally:
          tls.active_host_dir = old_host
          tls.active_yscb_dir = old_yscb
          if prev_scope is not None:
              update_current_scope_roots(
                  active_host_dir=old_scope_host,
                  active_yscb_dir=old_scope_yscb,
              )
      ```
      並在 [`core/context.py:L442-L446`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) `bind_runtime_context` 中同步保護 `uri_tls`：
      ```python
      tls = get_runtime_context().uri_tls
      prev_tls_state = (
          getattr(tls, "active_host_dir", None),
          getattr(tls, "active_yscb_dir", None),
          getattr(tls, "active_module_context", None),
      )
      token: Token = _ACTIVE_RUNTIME_SCOPE.set(new_scope)
      try:
          yield new_scope
      finally:
          _ACTIVE_RUNTIME_SCOPE.reset(token)
          tls.active_host_dir, tls.active_yscb_dir, tls.active_module_context = prev_tls_state
      ```

- [x] **[AUD-06] [🟠 P1 | C2.2 (Win32) & C9.2 (A2) | Windows / VirtioFS] [`ys_codebase/source/core/core/vfs/os_backend.py:L150-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) & [`yscb.py:L517-L540`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - `atomic_swap_directory` 存在三套分歧實作，`vfs.os_backend` 缺少目錄句柄鎖原地同步降級，且 `yscb.py` 回滾唯讀檔時在 Windows 必敗**
  - **問題座標與分類**：[`ys_codebase/source/core/core/vfs/os_backend.py:L150-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) (`atomic_swap_directory`)、[`yscb.py:L517-L540`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_rollback_dir_from_backup`)、[`yscb.py:L632-L669`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`atomic_swap_directory`) ｜ `C2.2 (Win32)` Windows 檔案與目錄句柄鎖、`C9.2 (A2)` 多處平行複製貼上漂移 ｜ 受影響平台：`Windows / VirtioFS / WSL2`
  - **觸發情境與演進根因分析**：
    1. **三套 `atomic_swap_directory` 行為分裂 (`A2`)**：全專案共有三套目錄原子交換實作：[`yscb.py:L632`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk)、[`core/engine.py:L553`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 與 [`core/vfs/os_backend.py:L150`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk)。當 `yscb.py` 與 `core/engine.py` 演進加入「三階段目錄鎖探針 (`_is_dir_handle_locked_for_rename`) + 檔案級原地同步 (`_inplace_atomic_sync_dir`)」以解決 Windows / VirtioFS / IDE 背景索引器鎖住模組目錄句柄時的 `PermissionError (WinError 5 / 32)` 後，**`core/vfs/os_backend.py` 的 `atomic_swap_directory` 卻未同步升級**！任何透過 `vfs.atomic_swap_directory` 執行的目錄交換在 Windows / VirtioFS 句柄鎖定下仍會直接拋出 `PermissionError` 失敗。
    2. **`yscb.py` 回滾與清理在 Windows 唯讀檔案上必敗 (`C2.2`)**：
       - 在 [`yscb.py:L517-L540`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) `_rollback_dir_from_backup` 中，刪除新增檔案（`os.remove`）與還原舊檔案（`os.replace(tmp_restore, dst_f)`）時，**漏掉了像正向同步 `L563` / `L576` 那樣先呼叫 `_force_writable(dst_f)`**。在 Windows NTFS 上，若目標檔案帶有唯讀屬性，`os.remove` 與 `os.replace` 會直接拋出 `PermissionError (WinError 5)`，且因外層 `except Exception: pass` 被靜默吞掉，導致回滾不完整、目錄處於半新半舊的撕裂狀態！
       - 在 [`yscb.py:L637`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 中，`old_dir` 命名僅為 `.old_{base_name}_{os.getpid()}`（缺少毫秒時間戳），且 `shutil.rmtree(..., ignore_errors=True)` 未掛載 `_force_writable` `onerror` 回呼，在 Windows 下無法清除唯讀檔或延遲釋放的目錄。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S3`）**：
    - **修改思路**：
      1. 將 `_is_dir_handle_locked_for_rename`、`_inplace_atomic_sync_dir` 與 `_cleanup_stale_swap_dirs` 統一收斂至 [`core/vfs/os_backend.py`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 的 `atomic_swap_directory` 中（內部統一使用 `robust_rmtree` 與 `robust_replace`），並讓 `core/engine.py` 直接委派 `_atomic_swap_dir = vfs.atomic_swap_directory`，消除 `core` 內部的兩套重複實作。
      2. 在 [`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 與 `os_backend.py` 的 `_rollback_dir_from_backup` 中，執行 `os.remove` 與 `os.replace` 前一律先呼叫 `_force_writable`，並為 `yscb.py` 的 `shutil.rmtree` 加上唯讀解鎖重試輔助函式。
    - **程式碼修改範例**：
      ```python
      # yscb.py: _rollback_dir_from_backup
      def _rollback_dir_from_backup(target_abs: str, backup_dir: str, existing_rel_files: Set[str]) -> None:
          """當就地同步異常時，刪除新增檔案並自 backup_dir 原子還原原有檔案。"""
          try:
              for root, _, files in os.walk(target_abs):
                  rel_root = "" if root == target_abs else os.path.relpath(root, target_abs)
                  for fname in files:
                      rel_path = os.path.join(rel_root, fname) if rel_root else fname
                      if rel_path.replace("\\", "/") not in existing_rel_files:
                          target_f = os.path.join(root, fname)
                          try:
                              _force_writable(target_f)
                              os.remove(target_f)
                          except Exception:
                              pass
              for norm_rel in existing_rel_files:
                  rel_os = norm_rel.replace("/", os.sep)
                  bak_f = os.path.join(backup_dir, rel_os)
                  dst_f = os.path.join(target_abs, rel_os)
                  if os.path.isfile(bak_f):
                      os.makedirs(os.path.dirname(dst_f), exist_ok=True)
                      tmp_restore = os.path.join(os.path.dirname(dst_f), f".yscb_restore_{os.getpid()}_{os.path.basename(dst_f)}")
                      shutil.copy2(bak_f, tmp_restore)
                      if os.path.exists(dst_f):
                          _force_writable(dst_f)
                      os.replace(tmp_restore, dst_f)
          except Exception:
              pass
      ```

- [x] **[AUD-07] [🟠 P1 | C9.2 (D5: Test Sniffing & Escape Hatches) | All-OS] [`ys_codebase/source/core/core/update_checker.py:L292-L312`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk), [`core/platform/process.py:L38-L49`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk), [`core/config.py:L17-L43`](https://drive.google.com/file/d/1u6KPwLuOKDZ9DdOX69t_3gisvtL68Et-/view?usp=drivesdk), [`core/validator.py:L61-L76`](https://drive.google.com/file/d/1pdnoxDaEP0KSXdXco4uNszuS9UaPGORA/view?usp=drivesdk) - 生產代碼殘留執行期 Mock 嗅探、`globals().pop` 靜態護欄逃逸與跨模組私有 PEP 562 耦合**
  - **問題座標與分類**：
    - [`ys_codebase/source/core/core/update_checker.py:L230-L234`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk), [`L285-L312`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk) (`_check_host_script_update`)
    - [`ys_codebase/source/core/core/platform/process.py:L38-L49`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) (`_get_can_spawn_cache`, `_set_can_spawn_cache`)
    - [`ys_codebase/source/core/core/config.py:L17-L43`](https://drive.google.com/file/d/1u6KPwLuOKDZ9DdOX69t_3gisvtL68Et-/view?usp=drivesdk) (`_ConfigManagerMeta`) & [`core/validator.py:L61-L76`](https://drive.google.com/file/d/1pdnoxDaEP0KSXdXco4uNszuS9UaPGORA/view?usp=drivesdk) (`_ContributesValidatorMeta`)
    - [`ys_codebase/source/core/core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) (`contributes._JSON_FILE_CACHE.pop`)
    ｜ `C9.2 (D5)` 生產代碼混入測試嗅探與逃逸補丁 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **執行期 Mock 嗅探與零引用死方法 (`update_checker.py`)**：在 `_check_host_script_update`（`L292-L312`）中，生產代碼透過 `"_get_local_host_script_version" in self.__dict__ or getattr(type(self), "_get_local_host_script_version", None) is not UpdateChecker._get_local_host_script_version` 嗅探是否有舊白箱測試在實例或類別上 `unittest.mock.patch` 了舊方法 `_get_local_host_script_version` / `_fetch_latest_host_script_version`。經全倉 `grep` 查證，**全專案（含所有測試檔）0 處引用這兩個舊方法**！這段嗅探分支與兩個舊轉發方法純屬無效歷史殘留。
    2. **`globals().pop` 靜態檢查逃逸 (`platform/process.py`)**：在 `_get_can_spawn_cache`（`L39-L48`）中，為了相容舊測試直接執行 `process._CAN_SPAWN_DAEMON_CACHE = True`（繞過模組 `__getattr__` 寫入模組 `globals()`），特意寫了 `if "_CAN_SPAWN_DAEMON_CACHE" in globals(): val = globals().pop(...)`（甚至觸犯了 `dev/checker.py` 的 `[C8]` 規則，只因 `dev/checker.py` 漏檢查或豁免了該處）。經查證全專案無任何地方寫入 `process._CAN_SPAWN_DAEMON_CACHE`。
    3. **生產模組內部仍透過 PEP 562 `__getattr__` 存取私有快取 (`os_backend.py` / `contributes.py`)**：在 [`core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 中，`_maybe_invalidate_uri_cache` 執行了 `contributes._JSON_FILE_CACHE.pop(norm_path, None)`；在 [`core/contributes.py:L427-L535`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) 中執行了 `uri._URI_REENTRANCY.active = True`。這使得本來僅供向下相容白箱測試的 PEP 562 `__getattr__` 被生產代碼自身在熱路徑上頻繁觸發。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S4`）**：
    - **修改思路**：
      1. 刪除 [`core/update_checker.py:L230-L234`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk)、[`L285-L289`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk) 及 [`L292-L312`](https://drive.google.com/file/d/1wSTLZPUGnT7VgNY0zwXfkzDUJ5-PUqT4/view?usp=drivesdk) 的 `__dict__` 嗅探分支，直接呼叫 `self._get_local_host_script_info()` 與 `self._fetch_latest_host_script_info(cfg)`。
      2. 移除 [`core/platform/process.py:L39-L48`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) 的 `globals().pop("_CAN_SPAWN_DAEMON_CACHE")`，直接讀寫 `get_runtime_context().process_can_spawn_daemon_cache`。
      3. 將 [`core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 改為 `get_runtime_context().contributes_json_file_cache.pop(norm_path, None)`，並將 `contributes.py` 改為 `get_runtime_context().uri_reentrancy.active`。
    - **程式碼修改範例**：
      ```python
      # core/update_checker.py
      def _check_host_script_update(self, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
          """比對本機與來源端 yscb.py 版本與內容 SHA-256，若有新版或內容漂移則回傳更新資訊字典。"""
          cur_ver, local_sha256 = self._get_local_host_script_info()
          if not cur_ver or cur_ver == "build" or cur_ver.endswith(".build"):
              return None
          latest_ver, latest_sha256 = self._fetch_latest_host_script_info(cfg)
          if not latest_ver:
              return None
      ```

- [x] **[AUD-08] [🟠 P1 | C2.2 (Win32) & C6.1 | Windows / POSIX] [`yscb.py:L613-L630`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk), [`ys_codebase/source/core/core/log.py:L609-L622`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) & [`ys_codebase/source/core/core/vfs/os_backend.py:L410-L420`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) - 跨掛載點 `EXDEV` 與符號連結複製邊界漏洞：`_safe_copytree` 未檢核 Symlink 指向目標是否越界，且 `_safe_replace_file` 降級時破壞日誌原子性**
  - **問題座標與分類**：
    - [`ys_codebase/source/core/core/vfs/os_backend.py:L410-L420`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) (`_safe_copytree`)
    - [`ys_codebase/source/core/core/log.py:L609-L622`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) (`_safe_replace_file`)
    - [`yscb.py:L613-L630`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_safe_replace_dir`)
    ｜ `C6.1` 符號連結邊界防護、`C3.3` 假陽性驗證邏輯 (`False-Green Guard`)、`C2.2` 跨平台檔案替換 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`_safe_copytree` 的假陽性 Symlink 檢查 (`C3.3 / C6.1`)**：在 [`core/vfs/os_backend.py:L410-L420`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 中，註解宣稱「對 symlink 執行邊界校驗」，但實際程式碼寫的是：
       ```python
       link_target = os.readlink(s)
       dst_root_norm = os.path.normpath(os.path.abspath(dst))
       d_norm = os.path.normpath(os.path.abspath(d))
       if d_norm != dst_root_norm and not d_norm.startswith(dst_root_norm + os.sep):
           raise PermissionError(...)
       ```
       注意 `d` 是 `os.path.join(dst, item)`（其中 `item` 來自 `os.listdir(src)`，不含 `/` 或 `..`），所以 `d_norm` **永遠**是 `dst_root_norm` 的直接子項目，這個 `if` 條件**恆為 False（False-Green Guard）**！它完全沒有檢查 `link_target`（例如 `../../../../etc/passwd` 或絕對路徑 `/etc/shadow`）解析後是否逃逸出 `self.root_dir` 或目標目錄樹！
    2. **`log.py` 的 `_safe_replace_file` 非原子覆寫風險 (`C2.2`)**：在 [`core/log.py:L609-L622`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) 中，當 `_rotate_lines_file`（`L948`）呼叫 `_safe_replace_file(tmp_path, target_path)` 遇到 Windows 暫態鎖定（如另一進程正在執行 `read_log_file_jsonl` 開啟讀取句柄）拋出 `PermissionError` 時，`_safe_replace_file` 沒有重試，而是立即 fallback 到 `shutil.copy2(src, dst)`（以 `open(dst, 'wb')` 原地截斷重寫目標檔）。在 Windows 上若 `dst` 正被開啟，連 `copy2` 也會失敗；而在 POSIX 上若因其他原因走入 `copy2`，則會導致並發讀取端讀到截斷一半的損毀 JSONL。
    3. **`yscb.py` 的 `_safe_replace_dir` 缺少唯讀屬性清除**：在 [`yscb.py:L618-L628`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 處理 `EXDEV` 時，`shutil.rmtree(dst_dir, ignore_errors=True)` 若遇到唯讀檔未能刪乾淨，下一行 `os.replace(stage, dst_dir)` 就會因 `dst_dir` 非空拋出 `OSError(ENOTEMPTY)`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 [`core/vfs/os_backend.py:L410-L420`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) `_safe_copytree` 中，計算符號連結指向的實體目標路徑 `resolved_link = os.path.normpath(os.path.join(os.path.dirname(d_norm), link_target))`（若 `link_target` 為絕對路徑則直接 `normpath`），驗證其未逃逸出 `dst_root_norm`（以及當 `self.root_dir` 存在時呼叫 `self.assert_safe_path(d_norm)`）。
      2. 在 [`core/log.py:L609-L622`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) `_safe_replace_file` 中，對 `PermissionError` / `WinError 5, 32` 執行短退避重試（或直接委派 `core.vfs.os_backend.robust_replace`）。
    - **程式碼修改範例**：
      ```python
      # core/vfs/os_backend.py: inside _safe_copytree
      if os.path.islink(s):
          link_target = os.readlink(s)
          dst_root_norm = os.path.normpath(os.path.abspath(dst))
          d_norm = os.path.normpath(os.path.abspath(d))
          resolved_target = (
              os.path.normpath(link_target)
              if os.path.isabs(link_target)
              else os.path.normpath(os.path.join(os.path.dirname(d_norm), link_target))
          )
          boundary = self._real_root_dir or dst_root_norm
          if resolved_target != boundary and not resolved_target.startswith(boundary + os.sep):
              raise PermissionError(
                  f"Symlink target '{link_target}' at '{d}' escaped boundary '{boundary}'."
              )
          if os.path.lexists(d):
              os.remove(d)
          os.symlink(link_target, d)
      ```

---

### 🟡 P2 - Medium（防禦缺口與結構耦合：路徑邊界不一致 / 鎖重入風險 / 雙軌行為分歧）

- [x] **[AUD-09] [🟡 P2 | C2.2 (macOS) & C6.1 | macOS / Windows] [`ys_codebase/source/core/core/uri.py:L465-L490`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) & [`L649-L690`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) - `uri._ensure_safe_subpath` 未解析符號連結逃逸，且 `uri.to_uri` 在 macOS `/var -> /private/var` 與 Windows 大小寫差異下反推失敗**
  - **問題座標與分類**：[`ys_codebase/source/core/core/uri.py:L465-L490`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) (`_ensure_safe_subpath`)、[`L649-L690`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) (`to_uri`) ｜ `C2.2 (macOS / Win32)` 跨平台路徑正規化、`C6.1` 符號連結防逃逸 ｜ 受影響平台：`macOS / Windows / Linux`
  - **觸發情境與演進根因分析**：
    1. **`to_uri` 的 `realpath` vs `abspath` 及大小寫失配 (`C2.2`)**：在 [`core/uri.py:L649-L690`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) 中，`to_uri(abs_path)` 僅使用 `os.path.normpath(os.path.abspath(abs_path))` 與字串 `norm.startswith(base_norm + os.sep)` 進行比對。
       - 在 **macOS** 上，系統暫存與工作區目錄 `/var/...` 或 `/tmp/...` 實為指向 `/private/var/...` 與 `/private/tmp/...` 的符號連結。當呼叫端傳入 `Path.resolve()` 或 `os.path.realpath()` 產生的路徑（如 `/private/var/folders/.../config/core/config.project.json`），而 `yscb_dir` 由未經 `realpath` 的路徑設定（`/var/folders/...`）時，`norm.startswith(base_norm + os.sep)` 比對失敗，`to_uri()` 無法還原為 `config://...`，直接退回原始絕對路徑。
       - 在 **Windows** 上，若傳入路徑磁碟機代號為小寫 `c:\repo\...`，而 `base_norm` 為 `C:\repo\...`，因未使用 `os.path.normcase` 比對，`to_uri()` 同樣匹配失敗。
    2. **`_ensure_safe_subpath` 與 `OSBackend.assert_safe_path` 契約不一致 (`C6.1`)**：`OSBackend.assert_safe_path`（[`core/vfs/os_backend.py:L234-L250`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk)）使用了 `os.path.realpath` 防禦符號連結跳板逃逸，但預設全域單例 `vfs = VFS(default_backend=OSBackend())` 的 `self.root_dir` 為 `None`（不啟用檢查），全靠 `uri._ensure_safe_subpath` 把關；然而 `_ensure_safe_subpath` 只用 `abspath` 檢查字面 `..`，若工作區子目錄內存在指向外部敏感目錄的 symlink，`uri.resolve("storage://mod/evil_symlink/secret")` 將直接放行。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `uri._ensure_safe_subpath` 中，除了檢查 `abspath` 的 `commonpath` 外，亦成對計算 `real_base = os.path.normcase(os.path.normpath(os.path.realpath(base_norm)))` 與 `real_joined = os.path.normcase(os.path.normpath(os.path.realpath(joined_norm)))`，確認實體路徑未透過符號連結逃逸出 `real_base`。
      2. 在 `uri.to_uri` 中，使用 `os.path.normcase(os.path.normpath(os.path.realpath(...)))` 作為比對鍵，同時支援 `abspath` 與 `realpath` 雙態匹配。
    - **程式碼修改範例**：
      ```python
      # core/uri.py: inside _ensure_safe_subpath
      real_base = os.path.normcase(os.path.normpath(os.path.realpath(base_norm)))
      real_joined = os.path.normcase(os.path.normpath(os.path.realpath(joined_norm)))
      try:
          if os.path.commonpath([real_base, real_joined]) != real_base:
              raise PermissionError(
                  f"Symlink escape detected in URI '{raw_uri}': subpath '{rel}' escaped base '{base_norm}'."
              )
      except ValueError as err:
          raise PermissionError(
              f"Symlink escape or drive reset detected in URI '{raw_uri}': escaped base '{base_norm}'."
          ) from err
      ```

- [x] **[AUD-10] [🟡 P2 | C1.2 & C9.2 (A2) | All-OS] [`yscb.py:L903-L956`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) & [`L1378-L1415`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - `yscb.py` 之 `_discover_latest_core` 漏傳 `base_dir`，且 `cmd_restore` 降級分支忽略 `--provider` 參數並跳過 `.build` 雜湊比對**
  - **問題座標與分類**：[`yscb.py:L903-L956`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_discover_latest_core`)、[`L1061`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`cmd_init`)、[`L1378-L1415`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`cmd_restore`) ｜ `C1.2` 契約漂移、`C9.2 (A2)` 雙軌行為不一致 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`_discover_latest_core` 漏傳 `base_dir`**：在 [`yscb.py:L911`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 中，`_discover_latest_core(provider)` 呼叫 `_normalize_local_path(p)` 時未傳入 `base_dir`（而同檔案的 `_load_provider_index_dict` 與 `_lookup_provider_release_sha256` 皆有傳入 `base_dir`）。若測試或呼叫端在非 `base_dir` 目錄下呼叫，相對路徑 `provider` 會相對於錯誤的工作目錄解析。
    2. **`cmd_restore` 降級路徑忽略 `--provider` / `-p`**：當 `.modules/core` 損毀且 `cmd_restore(argv)` 退回標準庫最小還原迴圈（`L1397-L1414`）時，它只解析了 `ignore_sha256` 與 `force`，**完全忽略了使用者傳入的 `--provider <path>` / `-p <path>`**（而說明訊息 `L1132` 卻明確建議使用者在來源遺失時執行 `python yscb.py restore --force --provider <valid_url_or_path>`！當使用者照做且 `core` 尚未安裝時，`_auto_bootstrap_and_restore_if_needed` 與 `cmd_restore` 仍去讀 `yscb.config.json` 內已經壞掉的舊 `provider`，導致修復指令失效！）。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S5`）**：
    - **修改思路**：
      1. 為 `_discover_latest_core(provider: str, base_dir: Optional[str] = None)` 補上 `base_dir` 參數並傳遞給 `_normalize_local_path(p, base_dir=base_dir)`。
      2. 在 `main()`、`cmd_restore()` 與 `_auto_bootstrap_and_restore_if_needed()` 中使用 `_parse_flag_options(argv)` 提取 `opts["provider"]`，當使用者顯式指定 `--provider` 時優先使用該來源自舉與還原。
    - **程式碼修改範例**：
      ```python
      # yscb.py: inside cmd_restore(argv)
      _, opts = _parse_flag_options(argv)
      ignore_sha256 = bool(opts.get("ignore_sha256", False))
      force = bool(opts.get("force", False)) or ("-f" in argv)
      explicit_prov = opts.get("provider")
      ```

- [x] **[AUD-11] [🟡 P2 | C2.1 & C1.2 | All-OS] [`ys_codebase/source/core/core/validator.py:L167-L188`](https://drive.google.com/file/d/1pdnoxDaEP0KSXdXco4uNszuS9UaPGORA/view?usp=drivesdk) - `ContributesValidator.parse_type_signature` 以無邊界 `rsplit("|", 1)` 與 `split("=", 1)` 切分型別簽名，當預設字串含 `|` 或 `enum(...)` 含 `=` 時解析錯亂**
  - **問題座標與分類**：[`ys_codebase/source/core/core/validator.py:L167-L188`](https://drive.google.com/file/d/1pdnoxDaEP0KSXdXco4uNszuS9UaPGORA/view?usp=drivesdk) (`parse_type_signature`) ｜ `C2.1` 退化與邊界輸入解析 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - `parse_type_signature` 在剝離 `@attr(...)` 後，直接對剩餘字串依序執行：
      ```python
      if "|" in raw:
          raw_part, strat_part = raw.rsplit("|", 1)
      ...
      if "=" in raw:
          parts = raw.split("=", 1)
      ```
    - 若某個欄位的預設字串值包含管道符 `|`（例如 `'str? = "a|b"'`），`rsplit("|", 1)` 會在解析 `=` 之前先把 `"a|b"` 從中間切開，將 `b"` 誤判為 `merge_strategy = 'b"'`，且預設值變成未閉合引號的 `"a`！
    - 同理，若 `enum(...)` 內含 `=`（例如 `enum(a=1, b=2)!`），`split("=", 1)` 會把 `enum(` 切碎。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：切分頂層 `|` 與 `=` 時，應跳過引號（`"..."`, `'...'`）與括號（`(...)`, `[...]`）內部字元，僅在頂層深度（`depth == 0 and not in_quote`）進行切分。
    - **程式碼修改範例**：
      ```python
      @staticmethod
      def _split_top_level_delim(text: str, delim: str, from_right: bool = False) -> Optional[Tuple[str, str]]:
          depth = 0
          in_quote: Optional[str] = None
          match_idx: Optional[int] = None
          for idx, ch in enumerate(text):
              if in_quote:
                  if ch == in_quote and (idx == 0 or text[idx - 1] != "\\"):
                      in_quote = None
                  continue
              if ch in ("'", '"'):
                  in_quote = ch
              elif ch in "([":
                  depth += 1
              elif ch in ")]":
                  depth = max(0, depth - 1)
              elif ch == delim and depth == 0:
                  if not from_right:
                      return text[:idx].strip(), text[idx + 1 :].strip()
                  match_idx = idx
          if match_idx is not None:
              return text[:match_idx].strip(), text[match_idx + 1 :].strip()
          return None
      ```

- [x] **[AUD-12] [🟡 P2 | C4.1 & C4.3 | All-OS] [`ys_codebase/source/core/core/context.py:L104-L154`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) & [`ys_codebase/source/core/core/log.py:L440-L473`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) - `CellScope` 跨執行緒共用時無鎖突變 `cache` / `stages_ms`，且 `DebouncedIOStreamer._flush_locked` 持鎖執行外部 `emit_chunk` I/O 回呼**
  - **問題座標與分類**：
    - [`ys_codebase/source/core/core/context.py:L104-L154`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk), [`L539-L575`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) (`CellScope`, `get_or_compute_cell_state`, `invalidate_cell_state`)
    - [`ys_codebase/source/core/core/log.py:L440-L473`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) (`DebouncedIOStreamer._flush_locked`)
    ｜ `C4.1` 共享字典競態、`C4.3` 持鎖執行外部 I/O ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`CellScope` 並發競態 (`C4.1`)**：當單次 CLI / 任務在 `CellScope` 生命週期內使用 `ThreadPoolExecutor` 或啟動子執行緒並透過 `contextvars.copy_context()` 繼承同一個未關閉的 `CellScope` 時，多個執行緒會同時呼叫 `cell.record_stage_ms()`、`get_or_compute_cell_state()`、`invalidate_cell_state()` 或由主執行緒呼叫 `close_and_clear_cache()`。由於 `CellScope._state` 完全沒有鎖保護，若一個執行緒正在迭代或寫入 `cell.cache`，而主執行緒結束任務呼叫 `close_and_clear_cache()`（或另一執行緒呼叫 `invalidate_cell_state()`），可能引發競態覆寫或讀寫不一致。
    2. **`DebouncedIOStreamer` 持鎖執行慢速 IPC 回呼 (`C4.3`)**：在 [`core/log.py:L440-L473`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) 中，`_flush_locked()` 雖然已先清空 `self._buffer`，但仍在持有 `self._lock` 的狀態下呼叫 `self.emit_chunk(packet)`（底層寫入跨進程 IPC 管道或 Socket）。當背景 `threading.Timer` 執行緒觸發 `_on_timer` 持鎖執行 `emit_chunk` 且 IPC 管道短暫背壓阻塞時，前景業務執行緒的所有 `print()` / `log()` 呼叫都會卡在 `with self._lock:` 等待。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S6`）**：
    - **修改思路**：
      1. 在 `RuntimeContext.__init__` 中將 `server_touch_lock` 與 `cell_seq_lock` 統一改為 `threading.RLock()`，並於 `CellScope` 內部狀態字典加入 `"lock": threading.RLock()`，保護 `record_stage_ms`、`close_and_clear_cache` 與 `invalidate_cell_state`。
      2. 在 `DebouncedIOStreamer` 中新增一把獨立的 `self._emit_lock = threading.RLock()`，讓 `_flush_locked()` 在 `self._lock` 內取出並清空 `consolidated` 緩衝區後即可釋放 `self._lock`，改以 `self._emit_lock` 依序發送 `emit_chunk(packet)`（確保文字流順序不亂且不阻塞緩衝區寫入）。

- [x] **[AUD-13] [🟡 P2 | C2.2 (Win32) & C4.3 | Windows / POSIX] [`ys_codebase/source/core/core/platform/lock.py:L25-L140`](https://drive.google.com/file/d/1JnE7Sp_K0C5pHrifLkgcs3qpj6_ncKrK/view?usp=drivesdk) - `InterProcessLock` 僅在同一實例內可重入，若同進程建立第二個指向同一鎖檔的實例，在 Windows 下自我鎖死 (`winerror 33`)，在 POSIX 下則破壞互斥**
  - **問題座標與分類**：[`ys_codebase/source/core/core/platform/lock.py:L25-L140`](https://drive.google.com/file/d/1JnE7Sp_K0C5pHrifLkgcs3qpj6_ncKrK/view?usp=drivesdk) (`InterProcessLock`) ｜ `C2.2 (Win32)` Windows `msvcrt.locking` 與 POSIX `flock` 語意差異、`C4.3` 同進程鎖重入 ｜ 受影響平台：`Windows / Linux / macOS`
  - **觸發情境與演進根因分析**：
    - `InterProcessLock` 的模組註解宣稱 `"Provides a robust, reentrant-safe, non-blocking file-based mutex"`，但其重入檢查僅為實例屬性 `if self._is_locked: return True`（`L54`）。
    - 當同一進程內的上游已持有 `lock1 = InterProcessLock(path)`，而下游（或同進程內的狀態探針如 `is_transaction_locked`、`is_daemon_lock_held`）建立了第二個實例 `lock2 = InterProcessLock(path)` 並呼叫 `acquire()` 時，三個平台會表現出完全矛盾的行為：
      - 在 **Windows** 上，`lock2._open_lock_fd()` 會打開第二個 OS file descriptor，呼叫 `msvcrt.locking(fd2, LK_NBLCK, 1)` 時會被同進程同執行緒的 `fd1` 阻擋（返回 `False` 或在 `blocking=True` 時**同執行緒自我死鎖直到 timeout**）！這也是為什麼 `PipManager` 被迫自己在外層手寫 `self._held_lock`（[`core/pip_manager.py:L246`](https://drive.google.com/file/d/1aEVbUF-s4PUoUIw1nvvLZuJChppVDNOC/view?usp=drivesdk)），但若跨兩個 `PipManager()` 實例仍會死鎖。
      - 在 **POSIX** 上，`os.open()` 產生獨立的 open file description，`fcntl.flock(fd2, LOCK_EX | LOCK_NB)` 也會與同進程的 `fd1` 互斥！這導致在同進程同執行緒內嵌套呼叫時，即使在 Linux/macOS 上也會自我死鎖！
      - 反之，這也意味著在同進程內呼叫 `is_transaction_locked()` 探測時，`is_transaction_locked()` 會將**自己這個執行緒**正在持有的交易鎖也視為「被鎖定」而回傳 `True`（若在交易鎖內部觸發需要檢查鎖的邏輯就會誤判）。
  - **建議解決方案（Recommended Solution - Mode A 手術 `S6`）**：
    - **修改思路**：若呼叫方需要同執行緒可重入語意（或區分「是否被其他執行緒/其他進程鎖定」），可在 `RuntimeContext` 維護一個進程級 `_held_interprocess_locks: Dict[str, Tuple[int, int]]`（記錄 `normcase(realpath(lock_file)) -> (owner_thread_ident, ref_count)`），或提供顯式的 `reentrant: bool = False` 參數，讓同執行緒嵌套獲取同一鎖檔時在三平台表現一致。

---

### 🔵 P3 - Optimization（效能加速與無損結構打磨）

- [x] **[AUD-14] [🔵 P3 | C7.1 & C8.3 (S3) | All-OS] [`yscb.py:L937-L940`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) & [`L431-L441`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - `_discover_latest_core` 與 `_resolve_same_triplet_fallback_version` 串列推導式內重複解析 SemVer，且 `yscb.py` 與 `core/engine.py` 存在重複打包樣板**
  - **問題座標與分類**：[`yscb.py:L431-L441`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_resolve_same_triplet_fallback_version`)、[`L937-L940`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_discover_latest_core`) ｜ `C7.1` 重複解析開銷、`C8.3 (S3)` 重複樣板 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - 在 [`yscb.py:L431-L437`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 中，對每個候選版本字串 `v` 連續呼叫了 3 次 `_parse_simple_semver(v)`：
      ```python
      same_triplet_cands = [
          (_parse_simple_semver(v), v)
          for v in active_vers
          if isinstance(v, str)
          and not _parse_simple_semver(v)[4]
          and _parse_simple_semver(v)[:3] == req_triplet
      ]
      ```
    - 在 [`yscb.py:L937-L938`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 中，同樣對每個 `v` 重複呼叫 `_parse_simple_semver(v)`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：使用海象運算子 `:=` 或單次預解析，使每個版本字串僅解析一次。
    - **程式碼修改範例**：
      ```python
      same_triplet_cands = [
          (parsed, v)
          for v in active_vers
          if isinstance(v, str)
          and not (parsed := _parse_simple_semver(v))[4]
          and parsed[:3] == req_triplet
      ]
      ```

- [x] **[AUD-15] [🔵 P3 | C7.1 & C7.2 | All-OS] [`ys_codebase/source/core/core/log.py:L1034-L1045`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) & [`ys_codebase/source/core/core/events.py:L108-L126`](https://drive.google.com/file/d/191xVRzHXcdirSYuAnRocZ-C48F62pFFX/view?usp=drivesdk) - `read_log_file_jsonl` 讀取尾部 `limit` 筆記錄時一次性 `readlines()` 全量載入記憶體，且 `events.broadcast` 在 Hook 迴圈內重複掃描 `.modules` 目錄**
  - **問題座標與分類**：
    - [`ys_codebase/source/core/core/log.py:L1034-L1045`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) (`read_log_file_jsonl`)
    - [`ys_codebase/source/core/core/events.py:L108-L126`](https://drive.google.com/file/d/191xVRzHXcdirSYuAnRocZ-C48F62pFFX/view?usp=drivesdk) (`broadcast`)
    ｜ `C7.1` 迴圈內重複 `os.listdir` / `realpath`、`C7.2` 全量讀檔記憶體分配 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`events.broadcast` 迴圈內重複呼叫 `ensure_installed_modules_path` (`C7.1`)**：在 [`core/events.py:L109`](https://drive.google.com/file/d/191xVRzHXcdirSYuAnRocZ-C48F62pFFX/view?usp=drivesdk) 先呼叫了一次 `ensure_installed_modules_path(priority_module="core")`，接著在 `for mod_name, hook_real_path in targets:` 迴圈內（`L122-L125`）又對每個模組呼叫一次 `ensure_installed_modules_path(priority_module=mod_name, extra_paths=extra_list)`，之後 `load_module_from_path` 若傳入參數又可能觸發。每次呼叫 `ensure_installed_modules_path` 都會執行 `os.listdir(modules_dir)` 並對 `sys.path` 內所有路徑與所有模組執行 `os.path.realpath`（[`core/platform/venv.py:L20-L21`, `L169`, `L317`, `L323`](https://drive.google.com/file/d/1qdXIHmBLZJagGMKJ7jya3Gm_CjgqcaxZ/view?usp=drivesdk)）。當安裝 6 個模組時，單次 `broadcast` 就會觸發 7 次 `.modules/` 目錄掃描與上百次 `realpath` 系統呼叫！
    2. **`read_log_file_jsonl` 全量 `readlines()` (`C7.2`)**：在 [`core/log.py:L1034-L1045`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) 中，當 `filter_fn is None and limit is not None and limit > 0`（例如只取最後 10 筆遙測日誌）時，使用了 `raw_lines = f.readlines()` 將整個檔案載入為字串串列，而非使用 `collections.deque(f, maxlen=...)` 或自檔案尾部塊狀倒讀。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `events.broadcast` 中，若 `hook_mod` 命中 `get_cached_module(mod_key)` 且檔案 `(mtime_ns, size)` 未變（熱路徑 99% 情況），無須在每次執行 Hook 前重跑完整的 `list_installed_module_roots` 掃描；或讓 `ensure_installed_modules_path` 快取已掛載的模組根集合。
      2. 在 `read_log_file_jsonl` 中，當 `filter_fn is None` 且檔案較大時，自檔案末端按 64KB 區塊倒序讀取直到湊滿 `limit` 筆有效 JSONL，避免配置整個檔案的串列記憶體。

- [x] **[AUD-16] [🔵 P3 | C7.1 & C8.1 | Linux / POSIX] [`ys_codebase/source/core/core/platform/process.py:L373-L469`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) & [`L510-L560`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) - `kill_process_tree` 與 `terminate_popen_tree` 在單次終止流程中重複全量掃描 `/proc` 達 3~4 次**
  - **問題座標與分類**：[`ys_codebase/source/core/core/platform/process.py:L373-L469`](https://drive.google.com/file/d/1HOcolwpVXiNf58vHvEbK6czSRpCxMi3r/view?usp=drivesdk) (`_collect_posix_descendants`, `_signal_posix_tree`, `kill_process_tree`, `terminate_popen_tree`) ｜ `C7.1` 重複全量 `/proc` 掃描 ｜ 受影響平台：`Linux / POSIX`
  - **觸發情境與演進根因分析**：
    - 在 `kill_process_tree(pid)`（`L539-L540`）與 `terminate_popen_tree(proc)`（`L600-L601`）中，呼叫端先執行了一次 `descendants, pgids = _collect_posix_descendants(pid)`（掃描整個 `/proc/*/stat` 與 `/proc/<pid>/task/*/children`），接著馬上呼叫 `_signal_posix_tree(pid, signal.SIGTERM, descendants=descendants, pgids=pgids)`。
    - 然而，`_signal_posix_tree` 的第一行（`L478`）**又無條件呼叫了一次 `curr_desc, curr_pgids = _collect_posix_descendants(root_pid)`**！
    - 加上若升級到 `SIGKILL` 時再呼叫一次，單次 `kill_process_tree` 會對整個系統的 `/proc` 所有進程執行 **2 到 3 次重複的全量掃描**；而在 `reap_sandbox_processes`（`L882-L885`）中若匹配到 $K$ 個沙盒進程，更會觸發 $2K + 1$ 次全系統 `/proc` 掃描。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `_signal_posix_tree` 中，當呼叫端已經傳入非 `None` 的 `descendants` 與 `pgids` 時，直接使用傳入集合（僅在 `descendants is None` 時才呼叫 `_collect_posix_descendants(root_pid)`）。
    - **程式碼修改範例**：
      ```python
      def _signal_posix_tree(
          root_pid: int,
          sig: int,
          descendants: Optional[Set[int]] = None,
          pgids: Optional[Set[int]] = None,
      ) -> None:
          """Send ``sig`` to ``root_pid``, its process group (if leader), and all discovered descendants/PGIDs."""
          if descendants is None or pgids is None:
              curr_desc, curr_pgids = _collect_posix_descendants(root_pid)
              all_desc = (descendants or set()) | curr_desc
              all_pgids = (pgids or set()) | curr_pgids
          else:
              all_desc = set(descendants)
              all_pgids = set(pgids)
      ```

---

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

為確保 100% 精確度與零湊數，以下初看疑似風險之處經三步反向查證後確認為安全設計（By Design），已排除於問題清單外：

- **[RFP-01] [`ys_codebase/source/core/core/context.py:L496-L506`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) (`CellScope` 透過 `contextvars.copy_context()` 洩漏至背景常駐執行緒之風險)**：
  - **查證結論**：安全（已防護）。`CellScope` 設有 `is_closed` 狀態旗標，當外層 `bind_cell_context` 退出時會在 `finally` 呼叫 `new_cell.close_and_clear_cache()` 將 `closed` 設為 `True` 並清空快取字典；任何透過 `copy_context()` 繼承了該 `CellScope` 的長命背景執行緒在呼叫 `get_current_cell()` 時都會因 `cell.is_closed` 為 `True` 而安全拿到 `None`，不會發生跨請求快取污染或記憶體洩漏。
- **[RFP-02] [`ys_codebase/source/core/core/context.py:L577-L598`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk) (`get_or_compute_epoch_state` 在鎖外執行 `builder_fn()` 之並發安全性)**：
  - **查證結論**：安全（刻意設計）。`get_or_compute_epoch_state` 刻意在 `epoch_states_lock` 鎖外計算 `epoch_fn()` 與 `builder_fn()`，以避免耗時的建構阻塞其他執行緒讀取其他鍵值；最後寫回時以 `(current_epoch, new_val)` 原子更新，具備冪等安全性。
- **[RFP-03] [`ys_codebase/source/core/core/loader.py:L107-L144`](https://drive.google.com/file/d/1bMcC0wixXQqyBTdtRpJNhqTlWCzU6KTt/view?usp=drivesdk) (`load_module_from_path` 於 `exec_module` 拋出異常時的殭屍模組殘留風險)**：
  - **查證結論**：安全（已防護）。`load_module_from_path` 在執行 `spec.loader.exec_module(mod_obj)` 前已完整快照 `prev_entries = {k: sys.modules.get(k) for k in all_keys}`，並在 `except Exception:` 區塊中逐一還原 `sys.modules` 與 `loaded_modules_cache`，徹底防止半初始化模組殘留。
- **[RFP-04] [`yscb.py:L444-L455`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) (`_extract_safe_zip` 的 Zip Slip 目錄穿越防護)**：
  - **查證結論**：安全（已防護）。在呼叫 `zf.extractall(dest_dir)` 前已逐一走訪 `zf.infolist()`，同時檢查了絕對路徑前綴 `/`、Windows 磁碟機代號 `:`、`..` 路徑段，以及 `os.path.abspath(os.path.join(dest_abs, m.filename))` 是否嚴格以 `dest_abs + os.sep` 開頭。
- **[RFP-05] [`ys_codebase/source/core/core/pip_manager.py:L320-L365`](https://drive.google.com/file/d/1aEVbUF-s4PUoUIw1nvvLZuJChppVDNOC/view?usp=drivesdk) (`install_packages` 的命令注入與任意套件安裝編譯風險)**：
  - **查證結論**：安全（已防護）。全程使用參數陣列 `[py_exec, "-m", "pip", "install", "--only-binary=:all:", ..., *specs]` 呼叫 `subprocess.run(..., stdin=subprocess.DEVNULL, timeout=300)`，無 Shell 拼接注入風險，且強制 `--only-binary=:all:` 阻斷惡意 `setup.py` 執行期任意代碼執行。


---

## Part II — Group B：`core` 模組第二部分（打包安裝引擎、Contributes、CLI 派發器、Space 與 Gitignore）

# 🛡️ YS-Codebase `core` 模組（Group B）第二次九維度單點序列深度審計與架構整理報告

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：`/working_dir/c_3fdac06fe2853f20/repo_workspace/ys_codebase/source/core/` 第二部分（打包安裝引擎、Contributes 聚合器、CLI 派發器、Space 空間引擎與 Gitignore，共劃分為 **4 個審查單元、23 個核心檔案**，已完成 100% 逐檔逐行細讀、跨呼叫端三步反向查證與跨單元架構收斂）。
- **目標語言與平台基準**：語言 `Python 3.11 (100% Stdlib)` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS/Win32) + macOS (APFS/Darwin)` ｜ 架構重構尺度 `Mode B 外圍 CLI/SDK 契約相容 + Mode A 內部演進技術債根因收斂`
- **診斷統計總覽**：🔴 **P0**：`3` 項 ｜ 🟠 **P1**：`5` 項 ｜ 🟡 **P2**：`5` 項 ｜ 🔵 **P3**：`3` 項（共 **16 項確認問題**；已透過三步反向查證排除假陽性 `5` 項）

| 審查單元 (Audit Unit) | 涵蓋檔案（附 Google Drive 連結） | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`**<br>(`core` 引擎、安裝器與遷移) | [`core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk), [`core/installer.py`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk), [`scripts/migrations/1.2.7.x.py`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk), [`scripts/migrations/1.2.8.x.py`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) | `AUD-B02`, `AUD-B03`, `AUD-B04`, `AUD-B08`, `AUD-B12`, `AUD-B15`, `AUD-B16` | 🔴 建議優先修復 |
| **`Unit 02`**<br>(`core` Contributes 與 Gitignore) | [`core/contributes.py`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk), [`core/gitignore.py`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) | `AUD-B01`, `AUD-B10`, `AUD-B13`, `AUD-B14` | 🔴 建議優先修復 |
| **`Unit 03`**<br>(`core` 指令派發器與內建指令) | [`core/commands/__init__.py`](https://drive.google.com/file/d/19hdo3UypSVZDPtkgHDM7LLixlJge9Yr_/view?usp=drivesdk), [`core/commands/bags.py`](https://drive.google.com/file/d/1efWecIoB5hYnz-idyds0vcfiRhBjm2fJ/view?usp=drivesdk), [`core/commands/contributes_cmd.py`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk), [`core/commands/dispatcher.py`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk), [`core/commands/help.py`](https://drive.google.com/file/d/1RiVqcmcmso-b4TLkJ2cqTYwSfJpzT4ZI/view?usp=drivesdk), [`core/commands/registry.py`](https://drive.google.com/file/d/1vhtdAbIgmF2kLEOOJMbJdpkhZSrEPX3_/view?usp=drivesdk), [`core/commands/resolver.py`](https://drive.google.com/file/d/11fRM6pDlZg772SHp9vfIBpRw4pDQgAV9/view?usp=drivesdk), [`scripts/cli.py`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk), [`scripts/hook.dev.py`](https://drive.google.com/file/d/1NXoSOo8maLpZeejH5uLH14tajfgX_Bho/view?usp=drivesdk) | `AUD-B03`, `AUD-B05`, `AUD-B06`, `AUD-B10`, `AUD-B11`, `AUD-B12`, `AUD-B13`, `AUD-B16` | 🔴 建議優先修復 |
| **`Unit 04`**<br>(`core` Space 空間註冊、掃描與二進位快照) | [`core/space/__init__.py`](https://drive.google.com/file/d/1OA7c-4SmXVVAcyoxo3XiyCAkTcMVnz5t/view?usp=drivesdk), [`core/space/exceptions.py`](https://drive.google.com/file/d/1LbgQTgEk0ikQe5XKKifidgm86OyO6jf6/view?usp=drivesdk), [`core/space/hasher.py`](https://drive.google.com/file/d/11merQpRcW08-8yF8R9uHDrX7lrdwVdfZ/view?usp=drivesdk), [`core/space/providers.py`](https://drive.google.com/file/d/1NgCbtJzIaWPq8p0GBMBhNp4MfkbIuefK/view?usp=drivesdk), [`core/space/registry.py`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk), [`core/space/scanner.py`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/schema.py`](https://drive.google.com/file/d/1zWqWz9MBcUvW65EZhqKCYxaRPGhU0Ch0/view?usp=drivesdk), [`core/space/watcher.py`](https://drive.google.com/file/d/1WtGYEtK5BMLkT-0BLd_hx3UhEwRrD-oX/view?usp=drivesdk) | `AUD-B06`, `AUD-B07`, `AUD-B09`, `AUD-B13` | 🟠 建議修復 |

---

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S6)

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **安裝與重載交易管線時序正交化 (`Materialize -> Migrate -> Deploy & Inject`) 與全量快照閉環** | `AUD-B02`, `AUD-B04`, `AUD-B12` | `C9.1 (A1/D2)`<br>`C1.1 / C3.2` | 1. 將 [`core/engine.py:L2061-L2183`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 的 `act_reload` 拆分為「Stage 1~2 鏡像自癒與模組解壓物化」與「Stage 3~4 組態模板部署、快取失效、Contributes 聚合、`gitignore.sync` 與 `on_reload` 廣播」兩階段，或於 `act_migrate` 完成後強制執行 Stage 3~4 收斂。<br>2. 在 [`core/engine.py:L2184-L2280`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 的 `act_snapshot` / `act_restore_snapshot` 補齊 `storage.local://` 備份與 `config://`、`storage://` 初始空狀態之 `else: vfs.rmtree(...)` 清理分支。<br>3. 為 [`core/installer.py:L889-L955`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) 的 `cmd_restore` 加上 `act_snapshot("pre_restore")` 與異常自動回滾。 |
| **`S2`** | **退役 `Installer._restore_module_package` 平行拉取軌道，收斂至單一 `AtomicEngine.act_download` 並禁止動態打包污染 `release/`** | `AUD-B04`, `AUD-B08` | `C9.2 (A2)`<br>`C1.1 / C6.1` | 1. 拔除 [`core/installer.py:L969-L1157`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) 手寫的 190 行五階段 `_restore_module_package`，統一委派予 [`core/engine.py:L1306-L1340`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 的 `act_download` + `_reload_materialize_single_module`，並回傳實際解析之 `(ok, effective_ver)`。<br>2. 在 [`core/engine.py:L1048`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 與 [`core/installer.py:L1096`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) 呼叫 `package_local_source_if_exact_match` 時移除 `release_zip_path=...` 參數（僅寫入 `module.mirror://`，絕不反向覆寫受 Git 與 `index.json` 管控的 `release/`），並統一 [`core/engine.py:L553-L622`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 與 [`core/vfs/os_backend.py:L150-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 的 `atomic_swap_directory`。 |
| **`S3`** | **`core.gitignore` 與 `core.space` 單一真相來源 (SSOT) 收斂與 CQS 純化** | `AUD-B01`, `AUD-B07`, `AUD-B14` | `C9.1 (D1)`<br>`C9.2 (A2)`<br>`C9.3 (A3)` | 1. 嚴格執行命令查詢分離（CQS）：在 [`core/gitignore.py:L200-L211`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) 與 [`core/gitignore.py:L820-L862`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) 中，唯讀 `status()` / `_load_dynamic_registry()` 僅讀取而不刪除磁碟檔案；且若保留跨 CLI 進程之 `register_dynamic` 契約，應以 `SpaceRegistry` Stage 3 (`on_register_file_spaces`) + 持久化或受託管區塊解析作為 SSOT。<br>2. 刪除 [`core/gitignore.py:L274-L352`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) 的 `_collect_static_contributes_by_module` 重複掃描器，統一由 `SpaceRegistry` 的 `<owner>/gitignore` 空間提供規則（並修正 [`core/space/registry.py:L115-L118`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) 對 `gitignore` 空間的 `"*"` 吞噬問題）。 |
| **`S4`** | **`core.space` 預設實例共享、相依快照聯動同步與墓碑 GC 閉環** | `AUD-B06`, `AUD-B07`, `AUD-B09` | `C9.3 (A3)`<br>`C1.1 / C7.2` | 1. 將 [`scripts/cli.py:L650-L966`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) 所有 `_handle_space_*` 改為呼叫 `get_default_registry()` 與 `get_default_scanner()`。<br>2. 在 [`core/space/scanner.py:L812-L814`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) 與 [`core/space/scanner.py:L1217`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) 完成單一空間變更後自動呼叫 `sync_dependent_snapshots`，並修正 `status()` (`L1737-L1755`) 誤套用合成空間 `/<short>` 快照的問題。<br>3. 為 `YFP2` 墓碑加入基於最低 Consumer 水位線或 `force=True` 的自動 GC 淘汰。 |
| **`S5`** | **CLI 派發器 (`dispatcher.py`) 執行緒安全化、Contributes 契約對齊與命令級別名 (`alias`) 擴充** | `AUD-B03`, `AUD-B05`, `AUD-B10`, `AUD-B11`, `AUD-B16` | `C9.3 (A4)`<br>`C9.2 (A2)`<br>`C4.1 / C3.3` | 1. 移除 [`core/commands/dispatcher.py:L754-L796`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) 在 `dispatch_local` 對全域 `sys.argv` 的非原子覆寫（所有內建模組已透過 `CmdBags` 接收參數）。<br>2. 在 [`core/commands/dispatcher.py:L965-L980`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) 對純分支群組指令（`cmd_spec.cmd and not cmd_spec.args and not sub_args`）直接於路由層渲染 Help 返回 `0`，不進入熱派發或背景拉起 Server。<br>3. 在 [`core/commands/contributes_cmd.py:L100, L156`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk) 補齊 `commands -> core` 映射與單檔 `contributes.json` 檢查；在 `CommandSpec` 支援命令級 `alias` 以消除 [`contributes/core.json:L711-L1413`](https://drive.google.com/file/d/1DhkxfgO8mjjbnCLqJF43k1orDNTirXYw/view?usp=drivesdk) 的 700 行重複宣告。 |
| **`S6`** | **全面清理 PEP 562 `__getattr__` 私有鏡像、`globals().pop` 逃逸補丁與 Mock 嗅探 (`D5`)** | `AUD-B13`, `AUD-B15` | `C9.2 (D5)`<br>`C8.2 / C8.3` | 1. 將 [`core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 改用 `get_runtime_context().contributes_json_file_cache` 或公開 API。<br>2. 清理 6 個核心模組底部的 PEP 562 `__getattr__` 私有狀態轉發與 [`scripts/cli.py:L1001-L1008`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) 的動態函式名解析，改為顯式函式綁定並同步升級白箱測試至 `get_runtime_context()`。 |

---

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：資料遺失 / 交易回滾缺口 / 並發鎖與全域狀態競態）

- [x] **[AUD-B01 / ARCH-B01] [🔴 P0 | C9.1 (D1) & C9.3 (A3) & C1.3 | All-OS] [`core/gitignore.py:L179-L227`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk), [`core/gitignore.py:L820-L862`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk), [`scripts/migrations/1.2.7.x.py:L106-L140`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk) - `gitignore` 動態規則純記憶體化導致跨進程狀態蒸發，且唯讀 `status()` 夾帶破壞性刪檔副作用**
  - **問題座標與分類**：[`core/gitignore.py:L179-L227`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) (`_migrate_legacy_dynamic_cache_if_needed`, `_load_dynamic_registry`, `_save_dynamic_registry`)、[`core/gitignore.py:L820-L862`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) (`status`)、[`core/engine.py:L2005-L2009`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`act_delete`) ｜ `C9.1 (D1)`、`C9.3 (A3)`、`C1.3` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **唯讀 `status()` 摧毀磁碟遷移產物（違反 `D1` CQS）**：[`scripts/migrations/1.2.7.x.py:L106-L140`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk) 將 `.cache/core/gitignore_dynamic.json` 搬移至 `storage.local://core/gitignore_dynamic.json` (`DYNAMIC_CACHE_URI`)。然而 [`core/gitignore.py:L188-L194`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) 在 `_migrate_legacy_dynamic_cache_if_needed` 讀取該檔案後，立即執行 `vfs.remove(DYNAMIC_CACHE_URI, missing_ok=True)` 將其從磁碟刪除，且僅存入當前進程的 `RuntimeContext.gitignore_custom_root_store`。當使用者執行唯讀指令 `python yscb.py gitignore status` 時，`status()` 呼叫 `collect_grouped_patterns()` (`L830`) -> `_load_dynamic_registry()` (`L418`)，在未重寫 `.gitignore` 的情況下把 `gitignore_dynamic.json` 刪除，隨即進程結束、記憶體釋放，所有遷移過來的動態規則永久遺失。
    2. **跨進程動態規則分裂與抹除 (`A3`)**：若任何模組在 CLI 進程 A 呼叫 `gitignore.register_dynamic("my-mod", ["/my_dir/"], sync_now=True)`，規則雖寫入 `.gitignore`，但註冊表僅存於進程 A 記憶體。當進程 B 隨後執行 `python yscb.py gitignore sync` 或 `python yscb.py reload` 時，進程 B 的 `gitignore_custom_root_store` 為空，會直接覆寫 `.gitignore` 並把 `# [my-mod]` 區塊抹除。反之，[`core/engine.py:L2007`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 在 `yscb remove <mod>` 呼叫 `gi_mod.clear_dynamic(module_name, sync_now=False)` 也只清空了當前進程原本就是空的記憶體字典。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路（Mode A 根因收斂 + Mode B 契約保護）**：
      1. 在 `_load_dynamic_registry`（由唯讀 `status` / `collect_grouped_patterns` 呼叫）中，對 `DYNAMIC_CACHE_URI` 僅做唯讀載入，**絕不在讀取路徑執行 `vfs.remove(DYNAMIC_CACHE_URI)`**；僅在 `sync()` 實際將規則成功寫入 `project://.gitignore` 後才清理遺留快取檔。
      2. 為使 `register_dynamic` / `clear_dynamic` 在不產生額外 `gitignore_dynamic.json` 檔案的前提下具備跨進程持久性，於 `_load_dynamic_registry` 啟動且記憶體 store 為空時，可自現有 `project://.gitignore` 的 `GITIGNORE_BEGIN_MARKER ... GITIGNORE_END_MARKER` 託管區塊內解析既有的 `# [<mod>]` 規則，將不屬於當前靜態 `contributes` 與 `SpaceRegistry` 的已安裝模組規則回填為初始基準（並過濾已不在 `installed_modules` 的被移除模組），如此既滿足 `test_runtime_register_unregister_and_no_dynamic_cache_file`（0 額外磁碟檔），又徹底消滅跨進程規則蒸發與 `status()` 刪檔副作用。
    - **程式碼修改範例**：
      ```python
      # core/gitignore.py
      def _migrate_legacy_dynamic_cache_if_needed(
          is_custom_root: bool, *, remove_file: bool = False
      ) -> Dict[str, List[str]]:
          if is_custom_root:
              return {}
          migrated: Dict[str, List[str]] = {}
          try:
              if vfs.exists(DYNAMIC_CACHE_URI):
                  data = vfs.read_json(DYNAMIC_CACHE_URI)
                  if isinstance(data, dict):
                      for k, v in data.items():
                          if isinstance(k, str) and k.strip() and isinstance(v, list):
                              migrated[k.strip()] = [str(x) for x in v if isinstance(x, str) and x.strip()]
                  if remove_file:
                      vfs.remove(DYNAMIC_CACHE_URI, missing_ok=True)
          except Exception:
              pass
          return migrated
      ```

- [x] **[AUD-B02 / ARCH-B02] [🔴 P0 | C1.1 & C3.2 & C9.1 (D2) | All-OS] [`core/engine.py:L2061-L2280`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk), [`core/installer.py:L514-L537`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk), [`core/installer.py:L635-L654`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk), [`core/installer.py:L889-L955`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) - 模組生命週期交易三大斷裂：(1) `act_migrate` 在 `act_reload` 之後執行導致遷移產物未注入快取；(2) `act_snapshot`/`act_restore_snapshot` 漏備份 `storage.local://` 且漏清理新增之 `config/` 與 `storage/`；(3) `cmd_restore` 無快照回滾保護**
  - **問題座標與分類**：[`core/installer.py:L514-L537`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`cmd_install`)、[`core/installer.py:L635-L654`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`cmd_update`)、[`core/installer.py:L889-L955`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`cmd_restore`)、[`core/engine.py:L2184-L2280`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`act_snapshot`, `act_restore_snapshot`) ｜ `C1.1`、`C3.2`、`C9.1 (D2)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **`act_reload` 早於 `act_migrate` 執行**：在 `cmd_install` (`L514-L520`)、`cmd_update` (`L635-L637`) 與 `cmd_restore` (`L941-L948`) 中，皆先呼叫 `self.engine.act_reload(clean_stage=True, inject_stage=True)`，隨後才執行 `self.engine.act_migrate(mod, old_ver, new_ver)`。這造成：
       - `act_reload` Stage 3 (`_deploy_and_strip_single_module_config`, [`core/engine.py:L1958-L1965`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk)) 在 [`scripts/migrations/1.2.7.x.py`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk) 搬移舊版 `config/core/config.local.json` 之前，就先建立了全新的 `.config.local/core/config.local.json`；
       - `act_reload` Stage 4 (`contributes_aggregator.scan_and_inject()`, `gitignore.sync()`, `on_reload`) 在 `1.2.7.x.py` / `1.2.8.x.py` 將 `config/file-space/contribute.json` 遷移至 `config/core/contribute.json` 之前就已執行完畢；而 `act_migrate` 改寫 `config/core/contribute.json` 與 `yscb.config.json` 後，卻未再執行 `invalidate_host_caches("all")`、`scan_and_inject()` 與 `gitignore.sync()`，導致升級完成後 `.cache/core/contributes.merged.json` 與 `SpaceRegistry` 缺少遷移進來的 `spaces` 定義！
    2. **快照與還原漏項 (`engine.py:L2184-L2280`)**：
       - `act_snapshot` 未備份 `storage.local://`（或其中的輕量 JSON 帳本），當 `cmd_remove(..., purge=True)` (`engine.py:L2017`) 刪除 `storage.local://<mod>` 或遷移腳本修改 `.storage.local/` 後發生異常觸發 `act_restore_snapshot` 時，`.storage.local/` 無法還原。
       - `act_restore_snapshot` (`engine.py:L2240-L2261`) 對 `snap_config_dir` 與 `snap_storage_dir` 缺少 `else:` 分支（對比 `snap_config_local_dir` 在 `L2251-L2254` 有 `else: vfs.rmtree("config.local://")`）；若快照時 `config://` 或 `storage://` 尚不存在，安裝失敗中途產生的設定檔在回滾後不會被清除。
    3. **`cmd_restore` 無快照回滾 (`installer.py:L889-L955`)**：`cmd_restore` 全程未呼叫 `act_snapshot`，若 `act_reload`（含 `reconcile_installed_dependencies`）或 `act_migrate` 拋出異常，將直接中斷並留下半成品環境。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `cmd_install`、`cmd_update`、`cmd_restore` 中，若有任何模組執行了 `act_migrate`，於遷移階梯完成後呼叫 `self.engine.act_post_migrate_reconcile()`（執行 `invalidate_host_caches("all")`、`self.contributes_aggregator.scan_and_inject()` 與 `gitignore.sync(emit_event=False)`）。
      2. 在 `act_restore_snapshot` 為 `snap_config_dir` 與 `snap_storage_dir` 補齊 `else: if vfs.exists(...): vfs.rmtree(..., ignore_errors=True)`，並在 `act_snapshot` / `act_restore_snapshot` 納入 `storage.local://`（排除大型二進位快取或完整備份配置帳本）。
      3. 在 `cmd_restore` 進入鎖定區後建立 `snap_id = self.engine.act_snapshot("pre_restore")`，於 `except Exception:` 區塊呼叫 `self.engine.act_restore_snapshot(snap_id)`。
    - **程式碼修改範例**：
      ```python
      # core/engine.py (於 act_restore_snapshot 補齊 else 清理分支，並新增遷移後重聚輔助方法)
      snap_config_dir = f"{snap_dir}/config"
      if vfs.exists(snap_config_dir):
          if vfs.exists("config://"):
              vfs.rmtree("config://", ignore_errors=True)
          vfs.copy(snap_config_dir, "config://")
      elif vfs.exists("config://"):
          vfs.rmtree("config://", ignore_errors=True)

      snap_storage_dir = f"{snap_dir}/storage"
      if vfs.exists(snap_storage_dir):
          if vfs.exists("storage://"):
              vfs.rmtree("storage://", ignore_errors=True)
          vfs.copy(snap_storage_dir, "storage://")
      elif vfs.exists("storage://"):
          vfs.rmtree("storage://", ignore_errors=True)
      ```

- [x] **[AUD-B03] [🔴 P0 | C4.1 & C4.3 & C9.3 (A4) | All-OS] [`core/engine.py:L768-L846`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk), [`core/commands/dispatcher.py:L753-L796`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) - `.yscb.lock` 跨進程鎖「先釋放再 unlink」引發 POSIX Inode 鎖失效競態，且 `dispatch_local` 執行期間無鎖覆寫全域 `sys.argv`**
  - **問題座標與分類**：[`core/engine.py:L792-L846`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`act_lock`, `act_unlock`)、[`core/commands/dispatcher.py:L753-L796`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) (`dispatch_local`) ｜ `C4.1`、`C4.3`、`C9.3 (A4)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **POSIX `flock`/`fcntl` 先釋放後刪除競態 (`engine.py:L831-L844`)**：`act_unlock` 先呼叫 `lock.release()` (`L831`)，再呼叫 `vfs.remove("cache://.yscb.lock")` (`L834`)。當進程 B 正在 `act_lock` (`L808`) 等待鎖時，進程 A 釋放鎖的瞬間進程 B 立即在舊 Inode 上獲得鎖；緊接著進程 A 執行 `vfs.remove(lock_uri)` 將該路徑 unlink。此時進程 C 呼叫 `act_lock` 會創建全新的 `.yscb.lock` Inode 並立即獲鎖，造成進程 B 與進程 C 同時持鎖執行安裝/重載！此外，`act_lock` (`L792-L805`) 當 `time.time() - mtime > timeout`（預設 10 秒）時會嘗試 `probe.acquire(blocking=False)` 並刪除鎖檔，而 `act_lock` 在同進程重入前竟然在 `L796-L799` 寫了釋放 `self._active_locks` 的死分支。
    2. **`sys.argv` 跨執行緒覆寫競態 (`dispatcher.py:L753-L796`)**：`dispatch_local` 在 `with rt_ctx.sys_path_lock:` 內僅執行 `orig_argv = list(sys.argv); sys.argv = [target_cli] + raw_args` (`L754-L756`) 即釋放鎖，隨後在無鎖狀態下執行 `fn(cmd_bags)` (`L770`)。在常駐 Server Worker 或事件 Hook 巢狀執行 `dispatch_local` 時，交錯的執行緒會把對方的臨時 `sys.argv` 備份為 `orig_argv`，或是 `_ensure_hooks` (`L633`: `"--verbose" in sys.argv`) 讀到其他執行緒的參數。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `act_lock` / `act_unlock` 中，遵循 `core/platform/lock.py` (`InterProcessLock`) 的設計：**保留鎖檔案 Inode 於 `.cache/.yscb.lock` 不執行 unlink**（或僅在持有鎖期間處理，且依賴 OS 級 `flock`/`msvcrt.locking` 判斷鎖活性而非刪除鎖檔），從根源杜絕 POSIX Inode 替換競態。
      2. 在 `dispatch_local` 中，若為相容極少數讀取 `sys.argv` 的外部腳本而需暫時替換 `sys.argv`，應使用堆疊計數器（僅在最後一個活躍呼叫退出時還原最外層 `orig_argv`）或將 `sys.argv` 替換限制於單執行緒冷啟動模式（當 `get_env("YSCB_IN_SERVER_WORKER") == "1"` 時不覆寫進程全域 `sys.argv`），並將 `_ensure_hooks` 的 `--verbose` 判斷改為讀取顯式傳入參數。
    - **程式碼修改範例**：
      ```python
      # core/engine.py
      def act_unlock(self, operation: str = "global") -> bool:
          count = self._lock_counts.get(operation, 0)
          if count > 1:
              self._lock_counts[operation] = count - 1
              return True

          self._lock_counts.pop(operation, None)
          lock = self._active_locks.pop(operation, None)
          remaining_active = sum(self._lock_counts.values()) > 0 or bool(self._active_locks)
          if lock is not None and not remaining_active:
              lock.release()
          return True
      ```

---

### 🟠 P1 - High（顯著缺陷：雙軌實作分歧 / 假陽性驗證守門 / 狀態分裂 / 匹配邏輯錯誤）

- [x] **[AUD-B04 / ARCH-B03] [🟠 P1 | C9.2 (A2) & C1.1 & C6.1 | All-OS] [`core/installer.py:L893-L1157`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk), [`core/engine.py:L1017-L1050`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) - `Installer._restore_module_package` 與 `AtomicEngine.act_download` 雙軌分歧：Fallback 版號丟失、失敗預建空目錄污染 `list`、動態打包反向污染 `release/` 導致後續 SHA-256 校驗崩潰**
  - **問題座標與分類**：[`core/installer.py:L893-L1157`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`cmd_restore`, `_restore_module_package`)、[`core/engine.py:L1017-L1050`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`_download_from_release_tier`) ｜ `C9.2 (A2)`、`C1.1`、`C6.1` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **Fallback 遞補版號未傳回 `cmd_restore` (`installer.py:L920-L930` vs `L1118-L1155`)**：當 `_restore_module_package` 第 5 階因原版號 `ver` 被上游滑動視窗淘汰而遞補安裝了 `fallback_ver` 時，雖然更新了 `yscb.config.json` (`L1146`)，但僅回傳 `True`；`cmd_restore` (`L921`, `L927-L928`) 仍拿舊的 `ver` 執行 `_apply_release_index_override_to_staging(mod_name, ver, dest)` 與 `migrations_to_run.append((mod_name, installed_ver, ver))`！
    2. **失敗前預建 `.modules/<mod>` 空目錄 (`installer.py:L984` vs `L750`)**：`_restore_module_package` 開頭即執行 `os.makedirs(dest_dir, exist_ok=True)` (`L984`)；若拉取失敗回傳 `False`，殘留的 `.modules/<mod>` 空目錄會讓 `cmd_list` (`L750`: `vfs.exists(f"module://{mod}")`) 誤報為 `"Installed"`。
    3. **動態打包反向寫入 `release/<mod>/<ver>.zip` 引發二次安裝 SHA-256 失敗 (`engine.py:L1048`, `installer.py:L1096-L1097`)**：當 `act_download` 或 `_restore_module_package` 退回本地 `source/<mod>` 呼叫 `package_local_source_if_exact_match` 時，傳入了 `release_zip_path=rel_zip_real`（即 `release/<mod>/<ver>.zip`）。這會用未簽署的本地源碼打包覆寫 `release/<mod>/<ver>.zip`；當下次執行 `install --force` 或 `reload` 時，`engine.py:L1000-L1002` 優先命中該 `release/<mod>/<ver>.zip` 並與 `release/<mod>/index.json` 比對 SHA-256，若本地源碼曾有修改即立刻拋出 `RuntimeError: SHA-256 checksum mismatch`！此外 `engine.py:L1021-L1038` 對目錄來源打包時未使用 `_RELEASE_PACKAGE_IGNORES` 且漏呼叫 `_verify_zip_sha256`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `_restore_module_package` 中移除開頭的 `os.makedirs(dest_dir, exist_ok=True)`（交由 `fetch_and_extract_zip` 內的 `_atomic_swap_dir` 原子建立），並將回傳型別或狀態改為回傳實際安裝之版本號（或於 `cmd_restore` 重新讀取 `yscb.config.json` 取得 `effective_ver`）。
      2. 在 `engine.py:L1048` 與 `installer.py:L1096` 呼叫 `package_local_source_if_exact_match` 時，將 `release_zip_path=None`（僅輸出至 `.mirror/<mod>/<ver>.zip`，絕不污染 `release/` 目錄）。
    - **程式碼修改範例**：
      ```python
      # core/engine.py:L1040-L1050
      src_dir = find_matching_local_source_dir(module_name, [p_abs] if p_abs else [])
      if src_dir:
          if package_local_source_if_exact_match(src_dir, version, dest_zip_real, release_zip_path=None):
              return dest_zip_uri
      ```

- [x] **[AUD-B05] [🟠 P1 | C1.2 & C3.3 (False-Green Guard) | All-OS] [`core/commands/contributes_cmd.py:L96-L110`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk), [`core/commands/contributes_cmd.py:L145-L204`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk) - `yscb contributes check` 漏映射 `commands.json -> core` 且漏檢單檔 `module://<donor>/contributes.json`，導致錯誤配置恆通過驗證 (False-Green)**
  - **問題座標與分類**：[`core/commands/contributes_cmd.py:L96-L110`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk) (`_check_single_file_mode`)、[`core/commands/contributes_cmd.py:L145-L204`](https://drive.google.com/file/d/1XLF8qHzliceKhLHIE1VlyhLVeojDZS7U/view?usp=drivesdk) (`_check_modules_mode`) ｜ `C1.2`、`C3.3` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. 在 [`core/contributes.py:L690-L692`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) 中，`contributes/commands.json` 的目標模組被正規化為 `"core"`（因其 Schema 定義於 `core/contributes/_format.json` 的 `commands` 擴充點）。但 `contributes_cmd.py` 在 `_check_single_file_mode` (`L100`) 與 `_check_modules_mode` (`L156`) 取 `target_mod = f[:-5]` 得到 `"commands"`，查無 `commands` 模組的 `_format.json` 後直接略過驗證並回傳 `0`！
    2. `_check_modules_mode` (`L145-L180`) 僅檢查 `module://<donor>/contributes/*.json`，完全漏檢 `module://<donor>/contributes.json` 統一檔案格式。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `_check_single_file_mode` 與 `_check_modules_mode` 將 `target_mod == "commands"` 統一映射為 `"core"`，並在 `_check_modules_mode` 補齊對 `module://<donor>/contributes.json` 的驗證。
    - **程式碼修改範例**：
      ```python
      # core/commands/contributes_cmd.py
      target_mod = "core" if fname[:-5] == "commands" else fname[:-5]
      ```

- [x] **[AUD-B06 / ARCH-B04] [🟠 P1 | C9.3 (A3) & C1.1 & C1.3 | All-OS] [`scripts/cli.py:L650-L966`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk), [`core/space/scanner.py:L789-L814`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/scanner.py:L1013-L1218`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/scanner.py:L1734-L1756`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) - `core.space` 狀態分裂：(1) CLI 處理器繞過預設共享實例；(2) 單一空間 `scan`/`patch_files` 未同步相依合成空間與 `__all__`；(3) `status()` 誤將合成空間 `/<short>` 快照套用至未掃描之子空間**
  - **問題座標與分類**：[`scripts/cli.py:L650-L966`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) (`_handle_space_*`)、[`core/space/scanner.py:L789-L814`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`scan`)、[`core/space/scanner.py:L1013-L1218`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`patch_files`)、[`core/space/scanner.py:L1734-L1756`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`status`) ｜ `C9.3 (A3)`、`C1.1`、`C1.3` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **CLI 與常駐 Worker 實例分裂 (`scripts/cli.py:L660-L951`)**：`_handle_space_spaces`、`match`、`ls`、`hash`、`status`、`scan`、`diff`、`clean` 全部直接呼叫 `SpaceRegistry()` / `SpaceScanner()` 建立拋棄式實例，而非呼叫 `get_default_registry()` / `get_default_scanner()`。在常駐 Server Worker 中，透過 `register_space` / `define_ephemeral_space` 注入的動態空間對 CLI 查詢完全隱形，且 CLI 執行 `file-space clean` 後常駐 Worker 的 `get_default_scanner()._snapshot_mem_cache` 仍殘留舊快照。
    2. **單一空間 `scan(space_query)` 與 `patch_files(space_query)` 未連動更新相依快照 (`scanner.py:L812-L814`, `L1217`)**：當呼叫 `scanner.scan("core/source")` 時，僅更新 `core__source.yfp2.bin`，未呼叫 `sync_dependent_snapshots`，導致已存在之 `/source` (`synthetic__source.yfp2.bin`)、複合父空間與 `__all__.yfp2.bin` 世代與內容失步。
    3. **`status()` 張冠李戴 (`scanner.py:L1737-L1742`)**：在 `status()` 中，若 `s_cfg` 為 `dev/source`（尚未獨立掃描，`head_generation == 0`），而 `/source` 合成空間曾被掃描過，`L1737-L1742` 會把 `/source` 的 `SnapshotState` 直接當成 `dev/source` 的狀態輸出，導致 `dev/source` 顯示的檔案數與 Merkle Root 實際上是全專案所有模組 `source` 的聯集！
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 將 `scripts/cli.py` 所有 `_handle_space_*` 改為使用 `get_default_registry()` 與 `get_default_scanner()`。
      2. 在 `SpaceScanner.scan(space_query)`（當 `space_query` 非空且發生變更時）自動呼叫 `self.sync_dependent_snapshots(res.space_name)`。
      3. 在 `SpaceScanner.status()` 中移除將 `/<short_name>` 合成快照套用至個別 `<owner>/<short_name>` 子空間的錯誤 fallback（僅當 `s_cfg.owner == ""` 即合成空間本身時才讀取 `synthetic__<short_name>`）。
    - **程式碼修改範例**：
      ```python
      # scripts/cli.py
      from core.space import SpaceError, get_default_registry, get_default_scanner
      # 於 _handle_space_spaces / match / ls / hash 使用 reg = get_default_registry()
      # 於 _handle_space_status / scan / diff / clean 使用 scanner = get_default_scanner()
      ```

- [x] **[AUD-B07] [🟠 P1 | C1.1 & C2.1 | All-OS] [`core/space/schema.py:L374-L382`](https://drive.google.com/file/d/1zWqWz9MBcUvW65EZhqKCYxaRPGhU0Ch0/view?usp=drivesdk), [`core/space/schema.py:L489-L534`](https://drive.google.com/file/d/1zWqWz9MBcUvW65EZhqKCYxaRPGhU0Ch0/view?usp=drivesdk), [`core/space/registry.py:L110-L118`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) - `CompiledRuleSet` 對正向 `include` 的純檔名/副檔名規則誤匹配父目錄名稱片段，且 `_merge_raw_space_dict` 萬用字元吸收規則吞噬 `gitignore` 空間規則**
  - **問題座標與分類**：[`core/space/schema.py:L374-L382`](https://drive.google.com/file/d/1zWqWz9MBcUvW65EZhqKCYxaRPGhU0Ch0/view?usp=drivesdk) (`_entry_matches_candidate`)、[`core/space/schema.py:L489-L534`](https://drive.google.com/file/d/1zWqWz9MBcUvW65EZhqKCYxaRPGhU0Ch0/view?usp=drivesdk) (`CompiledRuleSet.matches_fast`)、[`core/space/registry.py:L110-L118`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) (`_merge_raw_space_dict`) ｜ `C1.1`、`C2.1` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **父目錄名稱觸發正向檔案副檔名匹配 (`schema.py:L502-L505`, `L375`)**：在 `CompiledRuleSet.matches_fast` 與 `find_matching_rule` 中，對 `self._ext_suffixes`（如 `"include": ["*.py"]`）與 `self._exact_names` 一律檢查 `any(p.endswith(self._ext_suffixes) for p in parts)`。當 `self.is_exclude=False` 且測試目標為檔案 (`is_dir=False`) 時，若某個父目錄名稱含有 `.py`（例如 `test.py.d/README.txt` 或 `foo.py/data.bin`），其父目錄片段 `foo.py` 會命中 `*.py`，導致其下所有非 `.py` 檔案被誤判為匹配 `*.py`！
    2. **`_merge_raw_space_dict` 將含 `"*"` 的 `include` 強制壓為 `["*"]` (`registry.py:L115-L118`)**：當空間定義為 `gitignore` 空間時，`include` 存放的是欲寫入 `.gitignore` 的忽略規則清單；若其中包含 `"*"` 或 `"**"`，`_merge_raw_space_dict` 會把整個 `include` 清單替換為 `["*"]`，接著 [`core/gitignore.py:L395`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk) 的 `if s and s != "*"` 又將 `"*"` 濾除，導致該模組的所有 `gitignore` 規則全部消失。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `CompiledRuleSet` 中，對 `ext_suffix`（如 `*.py`）當 `not self.is_exclude and not is_dir` 時，僅比對 `filename` 而非所有父目錄 `parts`。
      2. 在 `_merge_raw_space_dict` 中，提供 `collapse_wildcard: bool = True` 參數（對 `short_name == "gitignore"` 設為 `False`，保留原始規則不壓縮為 `["*"]`）。
    - **程式碼修改範例**：
      ```python
      # core/space/schema.py (於 matches_fast 中區分 exclude 與檔案副檔名匹配)
      if self._exact_names:
          pool = parts if self.is_exclude else (parts if is_dir else (filename,))
          if any(p in self._exact_names for p in pool):
              return True
      if self._ext_suffixes:
          ext_pool = parts if self.is_exclude else (filename,)
          if any(p.endswith(self._ext_suffixes) for p in ext_pool):
              return True
      ```

- [x] **[AUD-B08 / ARCH-B05] [🟠 P1 | C9.2 (A2) & C1.1 & C2.2 | All-OS] [`core/engine.py:L393-L622`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) vs [`core/vfs/os_backend.py:L95-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) - `core` 內部維護兩套能力分裂的 `atomic_swap_directory` 實作**
  - **問題座標與分類**：[`core/engine.py:L393-L622`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`_atomic_swap_dir`) vs [`core/vfs/os_backend.py:L95-L197`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) (`atomic_swap_directory`) ｜ `C9.2 (A2)`、`C1.1`、`C2.2` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - `core.engine._atomic_swap_dir` 與 `core.vfs.os_backend.atomic_swap_directory` 為同一套件內部的兩套平行實作：
      - `engine.py` 版支援 Windows/virtiofs 目錄句柄鎖定時的三階段探針 (`_is_dir_handle_locked_for_rename`) 與檔案級全有全無同步 (`_inplace_atomic_sync_dir`) 及殘留 `.old_*`/`.staging_*` 清掃，但缺少跨掛載點 `EXDEV` 處理與 `_maybe_invalidate_uri_cache`；
      - `os_backend.py` 版支援 `robust_replace` (`EXDEV` 跨檔案系統回退與唯讀 `chmod`) 及 `_maybe_invalidate_uri_cache`，但缺少目錄句柄鎖定時的 `_inplace_atomic_sync_dir` 回退與殘留目錄清掃。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：將三階段句柄鎖探針、`_inplace_atomic_sync_dir`、`robust_replace` (`EXDEV` 回退) 與 `_maybe_invalidate_uri_cache` 統一收斂至 `core/vfs/os_backend.py` 的 `atomic_swap_directory`，並讓 `core/engine.py` 直接匯入委派，消除套件內雙軌分歧。

---

### 🟡 P2 - Medium（防禦缺口、資源增長與演進技術債）

- [x] **[AUD-B09] [🟡 P2 | C7.2 & C2.1 | All-OS] [`core/space/scanner.py:L248-L261`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/scanner.py:L953-L972`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/scanner.py:L1153-L1171`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) - `YFP2` 快照之刪除墓碑 (`is_deleted=True`) 永不淘汰導致二進位快照無限膨脹**
  - **問題座標與分類**：[`core/space/scanner.py:L953-L972`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`_scan_single_query`)、[`core/space/scanner.py:L1153-L1171`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`patch_files`) ｜ `C7.2`、`C2.1` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - `_scan_single_query` (`L971`) 將所有歷史 `is_deleted=True` 的 `FileFingerprint` 無條件複製至 `new_entries`，即使所有已註冊 Consumer 游標皆已確認過該刪除世代（或完全無 Consumer 游標且世代差距超過上限），墓碑也永不清除，導致頻繁增刪暫存檔的工作區 `.yfp2.bin` 隨時間單調膨脹。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：計算當前所有已持久化 Consumer 游標對該 `space_key` 的最小 `acked_generation`（若無任何 Consumer 則保留最近 `MAX_TOMBSTONE_GEN_WINDOW = 64` 世代內的墓碑），當 `old_fp.is_deleted` 且 `old_fp.updated_gen <= min_acked_gen` 時自動淘汰墓碑。

- [x] **[AUD-B10] [🟡 P2 | C9.2 (A2) & C1.2 | All-OS] [`core/commands/dispatcher.py:L158-L216`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) vs [`core/contributes.py:L684-L785`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) - `dispatcher._load_registry` 繞過 `contributes` 自行掃描 `.modules/`，同模組並存 `core.json` 與 `commands.json` 時提前 `break` 且忽略 `config://core/contribute.json`**
  - **問題座標與分類**：[`core/commands/dispatcher.py:L158-L216`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) (`_load_registry`)、[`core/contributes.py:L766-L777`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) (`_apply_project_overrides_and_persist`) ｜ `C9.2 (A2)`、`C1.2` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - `dispatcher._load_registry` 在 [`core/commands/dispatcher.py:L185-L194`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) 迴圈讀取 `("core.json", "commands.json")` 時，一旦 `core.json` 內有 `"commands"` 即 `break`，忽略同目錄下的 `commands.json`；同時 `CommandsRegistry.register_module` ([`core/commands/registry.py:L155`](https://drive.google.com/file/d/1vhtdAbIgmF2kLEOOJMbJdpkhZSrEPX3_/view?usp=drivesdk)) 直接覆寫 `self._modules[module_name] = mod_spec` 而非合併。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：移除 `dispatcher._load_registry` 內的 `break`，將同模組多個 contributes 檔案中的 `commands` 字典先合併後再呼叫 `registry.register_module(mod_name, merged_cmds)`。

- [x] **[AUD-B11] [🟡 P2 | C1.1 & C7.1 & C9.1 (A1) | All-OS] [`core/commands/dispatcher.py:L965-L980`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk), [`core/commands/dispatcher.py:L1004-L1032`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) - `_dispatch_inner` 以字串搜尋 `"def {func_name}("` 判斷純分支指令，導致群組指令無參數查看 Help 時誤觸發 Server 熱派發與背景 Auto-Spawn**
  - **問題座標與分類**：[`core/commands/dispatcher.py:L965-L980`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) (`_dispatch_inner`) ｜ `C1.1`、`C7.1`、`C9.1 (A1)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - 當 `cmd_spec.cmd` 存在（代表該指令擁有子指令樹）且使用者未傳入任何 `sub_args` 與選項（例如執行 `python yscb.py config` 或 `python yscb.py file-space`）且 `not cmd_spec.args` 時，`dispatcher.py:L965-L980` 讀取 `scripts/cli.py` 全文搜尋 `f"def {func_name}("`。因 `scripts/cli.py` 定義了同名群組轉發函式（其內部無參數時也只是呼叫 `_render_subcommand_group_help`），導致路由層不攔截，反而進入 Step 9 嘗試熱派發至常駐 Server（在 `strict_hot_dispatch=True` 且無 Server 時甚至直接報錯 `[BLOCKER]` 拒絕印出 Help！）並在 Step 9.5 自動拉起背景 Server 守護進程。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：當 `cmd_spec and cmd_spec.cmd and not cmd_spec.args and not sub_args` 時（純子指令群組且未帶任何子指令或旗標），直接於路由層 Step 7 渲染 `HelpRenderer.render_cmd_help(module_name, cmd_disp_name, cmd_spec)` 並回傳 `0`，既免除整檔讀取 I/O，亦避免無參數查看 Help 時誤觸發 Server 熱派發與守護進程拉起。

- [x] **[AUD-B12] [🟡 P2 | C1.2 | All-OS] [`core/installer.py:L622-L643`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk), [`scripts/cli.py:L373-L395`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) - `cmd_update` 自癒補裝新相依模組時漏廣播 `on_installed` 且 `on_update` 載荷不準確；`cli.install` 單參數拆分冗余**
  - **問題座標與分類**：[`core/installer.py:L622-L643`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`cmd_update`)、[`scripts/cli.py:L373-L395`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) (`install`) ｜ `C1.2` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - `cmd_update` 在 `reconcile_installed_dependencies` 補裝全新相依模組 (`newly_installed_deps`) 時未廣播 `on_installed` 事件，且 `on_update` 傳入未過濾的 `targets` 而非實際更新的模組清單。
    - `scripts/cli.py:L379-L387` 在 `len(specs) == 1` 時手動 `split("@", 1)` 覆蓋 `version`，但 `Installer._parse_install_requests` 本就支援完整序列與 `@` 解析。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `cmd_update` 中針對 `newly_installed_deps` 廣播 `on_installed`，並將實際發生版本升級的模組清單傳予 `on_update`；簡化 `scripts/cli.py:install` 直接傳遞 `cmd_bags.args` 予 `installer.cmd_install`。

- [x] **[AUD-B13 / ARCH-B06] [🟡 P2 | C9.2 (D5) & C8.2 | All-OS] [`core/contributes.py:L829-L838`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk), [`core/gitignore.py:L865-L869`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk), [`core/commands/dispatcher.py:L238-L246`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk), [`core/commands/dispatcher.py:L507-L518`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk), [`core/commands/dispatcher.py:L1055-L1066`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk), [`core/space/registry.py:L2033-L2040`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk), [`core/space/scanner.py:L2129-L2136`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk), [`core/space/watcher.py:L388-L399`](https://drive.google.com/file/d/1WtGYEtK5BMLkT-0BLd_hx3UhEwRrD-oX/view?usp=drivesdk), [`scripts/cli.py:L1001-L1008`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) - 7 處模組殘留 PEP 562 `__getattr__` 轉發、`globals().pop` 逃逸補丁與 Mock 嗅探 (`D5`)**
  - **問題座標與分類**：上述 7 個檔案之 `__getattr__` 與 `dispatcher.py:L73-L74, L238-L246, L507-L518` ｜ `C9.2 (D5)`、`C8.2` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    - 生產代碼在 [`core/vfs/os_backend.py:L37`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 透過 PEP 562 `__getattr__` 存取 `contributes._JSON_FILE_CACHE`；`space/registry.py`、`space/scanner.py`、`space/watcher.py` 中的 `_*_LOCK` 與 `_ACTIVE_WATCHER_WORKER` 更是全專案（含測試）零引用之死分支；`scripts/cli.py:L1001-L1008` 則用 `__getattr__` 動態轉發 `file_space_<subcmd>` 與 `fs_<subcmd>`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `scripts/cli.py` 以顯式字典迴圈或明確具名函式綁定 `file_space_<subcmd>` 與 `fs_<subcmd>`，移除 `scripts/cli.py` 的 `__getattr__`。
      2. 將 `core/vfs/os_backend.py:L37` 改為呼叫 `get_runtime_context().contributes_json_file_cache.pop(norm_path, None)`，並移除零引用的 PEP 562 轉發項目（或於測試同步遷移至 `get_runtime_context()` 後全面拔除 `__getattr__` 與 `globals().pop` 補丁）。

---

### 🔵 P3 - Optimization（效能加速與重複樣板收斂）

- [x] **[AUD-B14] [🔵 P3 | C7.1 & C9.2 (A2/D4) | All-OS] [`core/gitignore.py:L274-L433`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk), [`core/contributes.py:L272-L295`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk), [`core/contributes.py:L507-L547`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk), [`core/contributes.py:L791-L826`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) - `gitignore` 雙重讀取 `contributes/core.json` 與 `ContributesAggregator` 重複 `_scan_contributes_inputs()` 掃描**
  - **問題座標與分類**：[`core/gitignore.py:L415-L418`](https://drive.google.com/file/d/1oVKaEd9d7qDCksmJHvxxmE0w0NdP86yh/view?usp=drivesdk)、[`core/contributes.py:L447, L507, L539, L793, L825`](https://drive.google.com/file/d/1nPSWtThy9xGHT2yvsUCBTUbQk4R6LFUH/view?usp=drivesdk) ｜ `C7.1`、`C9.2 (A2/D4)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. `gitignore.collect_grouped_patterns` 依序呼叫 `_collect_static_contributes_by_module` 與 `_collect_space_registry_gitignore_groups`，使所有 `.modules/*/contributes/core.json` 與 `config/core/contribute.json` 被重複讀取與解析兩次。
    2. `contributes.get()` 在快取失效時先呼叫 `_is_contributes_dirty()` 執行一次 `_scan_contributes_inputs()` (`L447`)，緊接著呼叫 `scan_and_inject()` 時又在 `_apply_project_overrides_and_persist()` (`L793`) 重複執行第二次 `_scan_contributes_inputs()`，最後 `L825` 呼叫 `invalidate_cache()` 把剛填滿的 `_JSON_FILE_CACHE` 清空。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：將 `_is_contributes_dirty()` 取得的 `current_snapshot` 傳入 `scan_and_inject(input_snapshot=...)` 免除二次掃描，且在 `scan_and_inject()` 完成時僅清除 `_MERGED_MEMORY_CACHE` 與 `_LAST_CLEAN_SCAN_TS` 而保留已驗證 `mtime_ns` 的 `_JSON_FILE_CACHE`。

- [x] **[AUD-B15] [🔵 P3 | C8.3 & C9.2 (A2) | All-OS] [`scripts/migrations/1.2.7.x.py:L25-L51`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk), [`scripts/migrations/1.2.7.x.py:L143-L230`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk) vs [`scripts/migrations/1.2.8.x.py:L14-L84`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk), [`scripts/migrations/1.2.8.x.py:L124-L156`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) - `1.2.7.x.py` 與 `1.2.8.x.py` 遷移腳本 90% 樣板代碼重複**
  - **問題座標與分類**：[`scripts/migrations/1.2.7.x.py`](https://drive.google.com/file/d/10vvmzpCwLSnyCr6kxZPLEF8O91z65Zms/view?usp=drivesdk) 與 [`scripts/migrations/1.2.8.x.py`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) ｜ `C8.3`、`C9.2 (A2)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：兩支遷移腳本各自複製貼上了 `_read_json_dict_or_none`、`_atomic_write_json_file`、`_convert_legacy_space_entry` 與 `config/file-space/contribute.json -> config/core/contribute.json` 搬移邏輯。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：將共用遷移轉換與 VFS 原子 JSON 讀寫收斂為共用輔助函式（或於 `1.2.8.x.py` 複用 `1.2.7.x.py` 的 `_migrate_legacy_file_space_config`），並在 `1.2.8.x.py` 結尾補齊 `config.reload()` 與 `contributes.invalidate_cache()`。

- [x] **[AUD-B16] [🔵 P3 | C8.2 & C8.3 & C9.2 (A2) | All-OS] [`contributes/core.json:L711-L1413`](https://drive.google.com/file/d/1DhkxfgO8mjjbnCLqJF43k1orDNTirXYw/view?usp=drivesdk), [`core/commands/registry.py:L33-L46`](https://drive.google.com/file/d/1vhtdAbIgmF2kLEOOJMbJdpkhZSrEPX3_/view?usp=drivesdk), [`core/installer.py:L28-L45`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) - `contributes/core.json` 中 `file-space` 與 `fs` 700 行指令規格重複，且 `installer.py` 殘留未使用之 `INTERNAL_IGNORE_*` 常數**
  - **問題座標與分類**：[`contributes/core.json:L711-L1413`](https://drive.google.com/file/d/1DhkxfgO8mjjbnCLqJF43k1orDNTirXYw/view?usp=drivesdk)、[`core/commands/registry.py:L33-L46, L149-L154`](https://drive.google.com/file/d/1vhtdAbIgmF2kLEOOJMbJdpkhZSrEPX3_/view?usp=drivesdk)、[`core/installer.py:L28-L45`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) ｜ `C8.2`、`C8.3`、`C9.2 (A2)` ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. `CommandSpec` 不支援頂層或子指令 `alias` 欄位，導致 `contributes/core.json` 為了提供 `fs` 縮寫而將 350 行的 `file-space` 完整複製了一份。
    2. `core/installer.py:L28-L45` 的 `INTERNAL_IGNORE_BEGIN`、`INTERNAL_IGNORE_END`、`INTERNAL_IGNORE_PATTERNS` 在 `generate_internal_gitignore` 改為委派 `core.gitignore.sync()` 後已無任何引用。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `CommandSpec` 新增 `alias: List[str]` 欄位並於 `CommandsRegistry.register_module` 將別名映射至同一 `CommandSpec`，即可將 `contributes/core.json` 的 `fs` 收斂為 `file-space` 的 `"alias": ["fs"]`（減少 350 行重複 JSON）；並清理 `core/installer.py:L28-L45` 死常數（若外部無引用）。

---

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

- **[RFP-01] [`core/engine.py:L635-L658`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) (`_extract_zip_safely`) 與 [`core/installer.py:L79-L132`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) (`fetch_and_extract_zip`) 之 Zip Slip 防護**：
  - 初看 `zf.extractall(dest_dir)` 疑似存在路徑穿越風險，但經核對 `L644-L656`，在 `extractall` 前已逐一對 `zf.infolist()` 檢查 `norm_member.startswith("/")`、磁碟機代號 `:`、`".." in norm_member.split("/")` 與 `os.path.abspath(os.path.join(dest_abs, member.filename)).startswith(dest_abs + os.sep)`，且解壓至同父目錄 `.staging_*` 後再原子替換，防護完整。
- **[RFP-02] [`core/commands/dispatcher.py:L249-L380`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) (`_hot_dispatch_attempt` / `_try_hot_dispatch`) 之請求重試冪等性防護**：
  - 初看熱派發失敗回退冷派發可能導致非冪等指令重複執行，但經核對 `_HotDispatchResult(exit_code, accepted)` 設計：僅在連線建立前拒絕（`ECONNREFUSED`、過期 `daemon.json`、HTTP 前置鑑權錯誤，`accepted=False`）時才回退冷派發；一旦連線已建立或開始串流（`accepted=True`）卻發生讀取逾時或斷線，均直接回傳 exit code `1` 並拒絕冷派發重試，設計嚴謹。
- **[RFP-03] [`core/space/scanner.py:L861-L883`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) (`RACY_CLEAN_WINDOW_NS`) 之同時間戳記極速修改防護**：
  - 初看二階段增量掃描依賴 `(mtime_ns, size)` 快篩可能漏檢同一毫秒內的修改，但經核對 `L862` 已實作 Git Index 同款 `is_racy = (now_ns - wf.mtime_ns) < RACY_CLEAN_WINDOW_NS`（10ms 視窗內強制重算 Blake2b 內容雜湊），且内容雜湊未變時僅更新 `mtime_ns` 而不推進 generation (`L938-L950`)，設計正確。
- **[RFP-04] [`core/space/registry.py:L1767-L1782`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) (`_scandir_walk_recursive`) 之符號連結迴圈防護**：
  - 初看 `follow_symlinks=True` 遞迴 `os.scandir` 可能因符號連結形成無限迴圈，但經核對 `L1767-L1782` 已維護 `visited_inodes` `(st_dev, st_ino)` 與 Windows `st_ino == 0` 時的 `visited_dirs_norm` `resolve()` 雙軌去重集合，不會發生無窮遞迴。
- **[RFP-05] [`yscb.py:L204-L706`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 與 [`core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 之間的獨立工具函式副本**：
  - 初看 `yscb.py` 內含獨立的 `_extract_safe_zip`、`atomic_swap_directory` 與 `_package_source_to_zip_if_exact_version`，但因 `yscb.py` 為尚未安裝 `.modules/core` 前負責 `init` / `self-update` 的單檔零依賴宿主自舉器（Host Bootstrapper），無法在自舉前 `import core`，故宿主檔與 `core` 之間的最小自舉副本屬於刻意架構隔離（By Design），僅 `core` 套件內部的重複（如 `engine.py` vs `installer.py` vs `os_backend.py`）列為 `A2` 重構目標。


---

## Part III — Group C：`server` 與 `knowledge-db` 模組（主從監督、熱進程、雙階段索引與混合檢索）

# 🛡️ `server` 與 `knowledge-db` 模組第二次九維度單點序列深度審計與架構整理診斷報告 (Round 2 Codebase Deep Audit: C1~C9 / A1~A5 & D1~D5)

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：`ys_codebase/source/server` 與 `ys_codebase/source/knowledge-db` 全模組原始碼（共劃分為 `4` 個獨立審查單元，並向上游核對 `core` 與 `ast` 跨模組呼叫鏈；100% 獨立黑盒視角完成逐檔序列深潛與三步反向查證）
- **目標語言與平台基準**：語言 `Python 3` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS/Win32) + macOS (APFS/Darwin)` ｜ 架構重構尺度 `Mode B 對外 CLI/SDK 契約相容 + Mode A 內部演進技術債根因收斂`
- **診斷統計總覽**：🔴 **P0**：`2` 項 ｜ 🟠 **P1**：`5` 項 ｜ 🟡 **P2**：`7` 項 ｜ 🔵 **P3**：`3` 項（共確認 `17` 項問題，並反向查證排除假陽性 `5` 項）

| 審查單元 (Audit Unit) | 涵蓋檔案（附 Google Drive 連結） | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`**<br>(`server` 主從監督與熱執行器) | • [`server/server/master.py`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)<br>• [`server/server/worker.py`](https://drive.google.com/file/d/1YDMnio1KHGj52Tiro48e18u6i4NNYN9p/view?usp=drivesdk)<br>• [`server/server/config.py`](https://drive.google.com/file/d/1klmD9x_NQsjuXlmAevyGFHPovLN9XiUy/view?usp=drivesdk)<br>• [`server/server/__init__.py`](https://drive.google.com/file/d/1emCTamzXw_CGIaRbcpij-s-PD6L9_ZpW/view?usp=drivesdk)<br>*(註：`protocol.py` 與 `client.py` 實體已併入 [`master.py`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) 與 [`core/commands/dispatcher.py`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk))* | `AUD-03`, `AUD-07`, `AUD-08`, `AUD-14` | 🟠 建議優先修復 |
| **`Unit 02`**<br>(`server` 背景服務、Watcher 與 CLI) | • [`server/server/service.py`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk)<br>• [`server/server/space_watcher.py`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)<br>• [`server/server/watcher.py`](https://drive.google.com/file/d/1HPg_sG_c-i2OI1Z7U1MDC4M8-mIi9dba/view?usp=drivesdk)<br>• [`server/server/logger.py`](https://drive.google.com/file/d/1tpy7XYyfoUAhI0EtXSeQHj1BVaeQO8t1/view?usp=drivesdk)<br>• [`server/server/streamer.py`](https://drive.google.com/file/d/1UkuxGO5yW1_Rm4zw9roQPXHspRIZuQ8O/view?usp=drivesdk)<br>• [`server/scripts/cli.py`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) | `AUD-01`, `AUD-03`, `AUD-06`, `AUD-08`, `AUD-10`, `AUD-12`, `AUD-14`, `AUD-17` | 🔴 建議立即修復 |
| **`Unit 03`**<br>(`knowledge-db` 引擎與雙階段管線) | • [`knowledge-db/knowledge_db/engine.py`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/schema.py`](https://drive.google.com/file/d/1NQhH7d0ndfViI-pk6oj-wbJw7wzXQ-uK/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/tokenizer.py`](https://drive.google.com/file/d/1ibgVre87bT0G4fd0unMXqUE4J-APUusn/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/config.py`](https://drive.google.com/file/d/111Qj35vYsej9Zd0JrLkEgdkfG6QmmLAX/view?usp=drivesdk)<br>*(註：`chunker.py` 職責已由 `module:ast` 符號共享取代)* | `AUD-02`, `AUD-04`, `AUD-05`, `AUD-06`, `AUD-08`, `AUD-09`, `AUD-11`, `AUD-13`, `AUD-15`, `AUD-16`, `AUD-17` | 🔴 建議立即修復 |
| **`Unit 04`**<br>(`knowledge-db` 混合檢索、嵌入、常駐服務與 CLI) | • [`knowledge-db/knowledge_db/retrieval.py`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/hybrid.py`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/formatter.py`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/embedding.py`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/service.py`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/selector.py`](https://drive.google.com/file/d/148p_sUneWNWzkpkr51aNwwS7POjYe45Y/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/io_utils.py`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk)<br>• [`knowledge-db/knowledge_db/providers.py`](https://drive.google.com/file/d/1r1IaGLRJKJgVgl4PmRKW2TPGTFFC6cUZ/view?usp=drivesdk)<br>• [`knowledge-db/scripts/cli.py`](https://drive.google.com/file/d/1_M7CkzQdhh_gAqoqaHjqqZAv2FSizRCi/view?usp=drivesdk)<br>• [`knowledge-db/scripts/hook.ast.py`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk)<br>• [`knowledge-db/scripts/hook.core.py`](https://drive.google.com/file/d/1PT-vJgdvysyoMfW7f_PXssnUaI3PELqb/view?usp=drivesdk)<br>• [`knowledge-db/scripts/hook.dev.py`](https://drive.google.com/file/d/12ruUWrND3kD7C6gM-8yngP14GSHk2QfD/view?usp=drivesdk) | `AUD-01`, `AUD-05`, `AUD-08`, `AUD-09`, `AUD-10`, `AUD-11`, `AUD-13`, `AUD-15`, `AUD-16` | 🟠 建議優先修復 |

---

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S6)

> 第一輪重構雖引入了 `MasterSupervisor` stdout demuxer、兩階段索引 (`Stage 1` + `Stage 2`) 與 `sync_incremental_changes` 輔助函式，但在邊界處留下了**「半套重構（Half-Way Refactoring）」**與**「新舊雙軌並存」**。以下 6 項跨檔案根因架構手術將 17 個局部問題收斂為一次性結構根治：

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **批次快照同步與延遲廣播閉環 (`SpaceWatcher` Batch-Sync-Before-Broadcast)** | `AUD-01`, `AUD-12`, `AUD-17` | `C9.1 (A1/D3)`, `C4.2`, `C8.3` | 1. 合併 [`space_watcher.py`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) 中 `flush_space_now` 與 `flush_dirty_spaces` 重複的 50 行批次迴圈為單一 `_flush_target_qnames_batch()`。<br>2. **嚴格先完成全部子空間更新與 `sync_dependent_snapshots_batch()`（確保合成空間與 `__all__` 快照已落盤對齊），最後才對有變更的空間發出訂閱通知與單次批次 `on_file_space_changed` 廣播**。<br>3. 將 `is_transaction_locked()` 移至確認 `self._dirty_spaces` 非空且過防抖視窗之後再執行，消除閒置期每秒 10 次的無效鎖探測。 |
| **`S2`** | **多空間原子游標交易與單一增量入口收斂 (`Transactional Multi-Space Cursor Commit`)** | `AUD-02`, `AUD-16`, `AUD-17` | `C9.2 (A2/D2)`, `C4.1`, `C7.1` | 1. 在 [`pipeline.py:sync_incremental_changes`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 入口強制獲取 `self._index_lock`。<br>2. 廢除 `for q_sp in target_spaces: with consume_ctx(...)` 的「逐空間提前 ACK 游標（先寫後檢 `D2`）」反模式；改為**階段一僅呼叫 `scanner.diff()` 收集所有空間差異，階段二完成 `hot_patch_unified_index()` 或 `build_unified_index()` 並成功落盤後，階段三才統一對 `target_spaces` 與 `None` 執行 `scanner.ack()`**。<br>3. 合併 `target_spaces` 與 `space_name` 兩套 90% 重複的 90 行分支，並消除 `_evict_dirty_file_artifacts` 與 `patch_incremental` 的雙重全表掃描。 |
| **`S3`** | **常駐服務 IPC 保活收斂與優雅停機預算對齊 (`Service IPC Keepalive & Graceful Drain`)** | `AUD-03`, `AUD-07`, `AUD-14` | `C9.1 (A1/A4)`, `C5.1`, `C3.2` | 1. 在 [`server/service.py:BaseServiceWorker.touch_activity`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk) 優先透過 `_log_sink.emit_packet_fn({"type": "touch_activity", "source": self.name})` 走既有 IPC 管道保活（僅外部無管道 SDK 呼叫才讀 `daemon.json` 打 HTTP `/api/touch`），徹底打通 [`master.py:L515`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) 的懸空分支。<br>2. 在 [`master.py:_idle_ttl_loop`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) 觸發自動關機前強制檢查 `self._is_worker_completely_idle()`，並為 `_wait_worker_ready()` 補上明確超時上限，防止長任務被誤殺或 `pre_warm` 死鎖永久卡死 `_dispatch_lock`。 |
| **`S4`** | **退役單空間索引舊軌 (`<space>.index.bin.gz`) 與統一索引快取 SSOT (`Legacy Per-Space Index Retirement & Cache SSOT`)** | `AUD-04`, `AUD-05`, `AUD-13` | `C9.2 (A2)`, `C9.3 (A3)` | 1. 退役 [`pipeline.py:build_index(space=...)`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 寫入 `<safe_name>.index.bin.gz` 與 `self._index_cache` 的孤兒舊軌，統一委派至 `build_unified_index()` 並按空間回傳視圖。<br>2. 將 `_get_index_cache()` 與 `_get_worker_mem_state()` 改為以 `os.path.normcase(str(storage_dir))` / `indices_dir` 為鍵的分倉映射，並在 `read_worker_state` 優先讀取同進程活躍 Worker 記憶體狀態。<br>3. 收斂 [`engine.py`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) 與 [`scripts/hook.ast.py`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) 的空間權重解析為單一 SSOT 函式，並以 `qualified_name` 作為空間註冊表主鍵防止同名 `short_name` 互相覆蓋。 |
| **`S5`** | **嚴格命令查詢分離 (`CQS`) 與生產代碼純化 (`Purify Production Code & CQS Enforcement`)** | `AUD-08`, `AUD-09`, `AUD-10` | `C9.1 (D1)`, `C9.2 (D5)`, `C9.3 (A5)` | 1. 將 [`EmbeddingService.is_available`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk) 拆分為純唯讀無副作用探針與顯式載入/提示方法，消除散落 6 處的 `suppress_guard_prompt` 狀態塗改；讓 `KnowledgeEngine.status()` 優先讀取輕量檔頭或已載入快取而不強制觸發重型反序列化與 `trim_process_memory()`。<br>2. 移除 [`master.py:L1136`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) 的 `unittest.mock` 執行期嗅探與雙軌讀取分支，清理 4 處 PEP 562 `__getattr__` 全局變數橋接補丁。<br>3. 讓 [`knowledge_db/io_utils.py`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) 直接復用 `ast_engine.io_utils.atomic_save_gzip_pickle`（底層走 `core.vfs.write_bytes(..., atomic=True)` 含 Windows 退避重試）。 |
| **`S6`** | **三平台規範化路徑比對與混合檢索候選預過濾 (`Canonical Path Matching & Vector Masking`)** | `AUD-06`, `AUD-11`, `AUD-15` | `C2.2`, `C6.1`, `C7.1` | 1. 在 [`space_watcher.py`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) 與 [`formatter.py`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) 統一使用 `os.path.normcase(os.path.realpath(...))` 對齊 macOS `/private/var` 符號連結與 Windows 大小寫。<br>2. 修正 `is_dirty_file_match` 禁止跨模組相對路徑尾綴誤匹配。<br>3. 在 [`hybrid.py`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk) 將過濾條件轉為 `allowed_doc_ids` 傳入 `VectorIndex.search`，並補齊 Hybrid RRF 模式的 `min_score` 過濾契約。 |

---

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：並發時序顛倒 / 交易原子性違背 / 資料與游標永久失步）

- [x] **[AUD-01 / ARCH-01] [🔴 P0 | C9.1 (A1/D3) & C4.2 | All-OS] [`server/server/space_watcher.py:L512-L529`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk), [`L596-L639`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk), [`L681-L717`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) - `CoreSpaceWatcher` 在更新依賴快照（`__all__` / 合成空間）前即於迴圈內提前廣播 `on_file_space_changed`，引發下游 `ast` 與 `knowledge-db` 游標錯位與併發競態**
  - **問題座標與分類**：[`server/server/space_watcher.py`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)（`_refresh_or_patch_space` `L512-L529`、`flush_space_now` `L596-L639`、`flush_dirty_spaces` `L681-L717`）｜ 連動影響 [`ast/scripts/hook.core.py:L54-L64`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk) 與 [`knowledge-db/scripts/hook.core.py:L96-L105`](https://drive.google.com/file/d/1PT-vJgdvysyoMfW7f_PXssnUaI3PELqb/view?usp=drivesdk) ｜ `C4.2` 時序違背、`C9.1 (A1/D3)`
  - **觸發情境與演進根因分析**：
    1. 在 `flush_dirty_spaces()`（`L686-L692`）與 `flush_space_now()`（`L608-L614`）的 `for q_name in target_spaces:` 迴圈中，呼叫 `_refresh_or_patch_space(..., sync_dependents=False)` 將 `sync_dependent_snapshots_batch` 延後至迴圈結束後（`L634`、`L712`）才批次執行。
    2. 然而 `_refresh_or_patch_space` 在 `L526-L527` **並未等待 `sync_dependent_snapshots_batch` 完成**，而是在單一子空間剛寫完快照、但合成短名空間（如 `/docs`）、組合空間（`compose`）與全域 `__all__` 快照**仍處於舊世代**時，就立即同步呼叫 `notify_subscribers(q_name, diff_res)` 與 `broadcast_file_space_changed(q_name, diff_res)`。
    3. 這導致兩個嚴重後果：
       - `broadcast_file_space_changed` 同步觸發 [`ast/scripts/hook.core.py:L54-L63`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk)，其內部的 `scanner.ack(None, consumer_id="ast")` 會讀取尚未更新的 `__all__` 快照世代進行 ACK；待迴圈結束後 `sync_dependent_snapshots_batch` 才將 `__all__` 推進至新世代，導致 `"ast"` 的 `__all__` 游標永遠落後 1 個世代！
       - 當單次防抖視窗內有多個空間同時變更時，第一個空間在迴圈中廣播 `on_file_space_changed` 就會透過 [`knowledge-db/scripts/hook.core.py:L99`](https://drive.google.com/file/d/1PT-vJgdvysyoMfW7f_PXssnUaI3PELqb/view?usp=drivesdk) 喚醒背景執行緒 `KnowledgeDBServiceWorker`（`self._wake_event.set()`），使 `KnowledgeDBServiceWorker` 與仍在掃描後續空間並執行 `ast` 同步 Hook 的 `CoreSpaceWatcher` 執行緒發生正面鎖與游標競態！
  - **建議解決方案（Mode A 根因重構 — 手術 `S1`）**：
    - **修改思路**：在 `_refresh_or_patch_space` 中當 `sync_dependents=False` 時禁止提前觸發 `notify_subscribers` 與 `broadcast_file_space_changed`；統一於 `_flush_target_qnames_batch` 完成所有目標空間修補及 `self.scanner.sync_dependent_snapshots_batch(...)` 後，再依序執行 `touch_activity()`、`notify_subscribers` 與 `broadcast_file_space_changed`。
    - **程式碼修改範例**：
      ```python
      # server/server/space_watcher.py
      def _refresh_or_patch_space(
          self,
          q_name: str,
          dirty_paths: Set[Path],
          full_rescan: bool,
          *,
          batch_qnames: Optional[Set[str]] = None,
          sync_dependents: bool = True,
      ) -> Tuple[ScanDiffResult, bool]:
          has_snap = self.scanner._has_existing_snapshot(q_name)
          use_patch = (
              not full_rescan
              and 0 < len(dirty_paths) <= self.MAX_PATCH_PATHS_THRESHOLD
              and has_snap
          )
          if use_patch:
              state = self.scanner.patch_files(q_name, dirty_paths)
              diff_res = state.last_diff
              if diff_res is None:
                  diff_res = self.scanner._scan_single_query(q_name)
                  use_patch = False
          else:
              diff_res = self.scanner._scan_single_query(q_name)

          if diff_res.has_changes:
              with self._lock:
                  self._refresh_count += 1
                  self._last_refresh_at = time.time()
              if sync_dependents:
                  self.scanner.sync_dependent_snapshots(
                      q_name,
                      dirty_paths if use_patch else None,
                      exclude_keys=batch_qnames,
                  )
                  try:
                      self.touch_activity()
                  except Exception:
                      pass
                  notify_subscribers(q_name, diff_res)
                  broadcast_file_space_changed(q_name, diff_res)

          return diff_res, use_patch
      ```
      並在批次匯流處先執行 `self.scanner.sync_dependent_snapshots_batch(...)`，完成後再遍歷本次 `changed_diffs: List[Tuple[str, ScanDiffResult]]` 發出 `notify_subscribers` 與 `broadcast_file_space_changed`。

- [x] **[AUD-02 / ARCH-02] [🔴 P0 | C4.1 & C9.2 (D2) | All-OS] [`knowledge-db/knowledge_db/pipeline.py:L690-L914`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `sync_incremental_changes` 違反兩階段原子提交（`D2` 先寫後檢）：在執行 `hot_patch_unified_index` 前即於迴圈中提前 ACK 所有空間游標，且入口缺少 `_index_lock` 保護**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)（`sync_incremental_changes` `L690-L914`）｜ `C4.1` 原子性違背、`C1.1` 雙軌狀態失步、`C9.2 (D2)` 先寫後檢
  - **觸發情境與演進根因分析**：
    1. 當 `sync_incremental_changes` 以 `target_spaces` 模式執行時（此為 [`service.py:L772`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk) `KnowledgeDBServiceWorker` 與 [`pipeline.py:L1704`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 前景 JIT 的預設路徑），`L730-L741` 寫為：
       ```python
       for q_sp in target_spaces:
           with consume_ctx(
               space_name=q_sp, consumer_id="knowledge-db", auto_refresh=auto_refresh
           ) as diff_res:
               ...
       ```
       由於 [`SpaceScanner.consume_diff`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk)（`scanner.py:L1702-L1726`）在退出 `with` 區塊時就會立即呼叫 `self.ack(...)` 將游標寫入磁碟，這導致**在 `L741` 迴圈結束的瞬間（尚未執行 `L794` 的 `hot_patch_unified_index` 或 `L802` 的 `_invoke_rebuild`），所有受索引空間的 `"knowledge-db"` 游標就已經全部被提前 ACK 到最新世代**！
    2. 一旦後續 `hot_patch_unified_index` 或 `build_unified_index` 因 I/O 異常、鎖超時、或 `WarmWorker` 被 `restart_worker` 搶占終止而中斷，磁碟上的 `"knowledge-db"` 游標已處於最新世代，但 `unified.index.bin.gz` 卻未更新，造成永久性漏索引（Dirty Read / Lost Update）。
    3. 此外，`sync_incremental_changes` 入口未加 `with self._index_lock:`，當 `KnowledgeDBServiceWorker` 背景呼叫 `sync_incremental_changes` 時，直到進入 `hot_patch_unified_index` 才拿鎖，期間與前景執行緒存在無鎖競態視窗。
  - **建議解決方案（Mode A 根因重構 — 手術 `S2`）**：
    - **修改思路**：使用 `ExitStack` 將所有 `target_spaces`（或單一 `space_name`）的 `consume_ctx` 交易上下文保持開啟，直到 `hot_patch_unified_index` 或 `_invoke_rebuild` 成功完成後，才讓 `ExitStack` 正常退出並一次性提交所有空間游標；若中途拋出任何異常，`ExitStack` 自動將異常傳播給各個 `consume_ctx`，保證 0 游標提前推進；同時將兩個重複的 90 行分支收斂為單一實作並置於 `with self._index_lock:` 保護下。
    - **程式碼修改範例**：
      ```python
      # knowledge-db/knowledge_db/pipeline.py
      from contextlib import ExitStack

      def sync_incremental_changes(
          self,
          *,
          space_name: Optional[str] = None,
          target_spaces: Optional[List[str]] = None,
          auto_refresh: Optional[bool] = None,
          skip_vectors: bool = False,
          allow_parallel: bool = True,
          require_vectors: bool = False,
          verbose: bool = False,
          consume_fn: Optional[Callable[..., Any]] = None,
      ) -> Dict[str, Any]:
          with self._index_lock:
              indices_dir = self.get_indices_dir()
              bin_file = indices_dir / "unified.index.bin.gz"
              self._ensure_indices_loaded(load_vectors=require_vectors)
              consume_ctx = consume_fn or self._consume_space_diff
              spaces_to_consume = list(target_spaces) if target_spaces else [space_name]

              def _invoke_rebuild() -> None:
                  self.build_unified_index(
                      force=True,
                      allow_parallel=allow_parallel,
                      skip_vectors=skip_vectors,
                  )

              with ExitStack() as stack:
                  merged_added: Set[str] = set()
                  merged_modified: Set[str] = set()
                  merged_deleted: Set[str] = set()
                  unchanged_total = 0
                  last_to_gen = 0
                  for q_sp in spaces_to_consume:
                      diff_res = stack.enter_context(
                          consume_ctx(
                              space_name=q_sp,
                              consumer_id="knowledge-db",
                              auto_refresh=auto_refresh,
                          )
                      )
                      if diff_res:
                          last_to_gen = max(last_to_gen, int(getattr(diff_res, "to_generation", 0) or 0))
                          unchanged_total += int(getattr(diff_res, "unchanged_count", 0) or 0)
                          if diff_res.has_changes:
                              merged_added.update(diff_res.detail.added)
                              merged_modified.update(diff_res.detail.modified)
                              merged_deleted.update(diff_res.detail.deleted)
                  # 於同一個 ExitStack 交易內執行熱修補或重建，成功返回時才批次 ACK 所有空間游標
                  ...
      ```

---

### 🟠 P1 - High（顯著缺陷：三態耦合與盲管繞道 / 雙軌索引未退役 / SSOT 狀態分裂 / 三平台路徑斷裂 / 缺少超時）

- [x] **[AUD-03 / ARCH-03] [🟠 P1 | C9.1 (A1/A4) & C3.2 | All-OS] [`server/server/service.py:L71-L143`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk), [`L377-L379`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk) & [`server/server/master.py:L515-L517`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk), [`L750-L760`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) - 背景服務保活仍繞道讀磁碟打 HTTP `/api/touch`（IPC `"touch_activity"` 發送端懸空），且 `WarmWorker` 1.5s 強制退出上限截斷 `KnowledgeDBServiceWorker` 5.0s 優雅落盤**
  - **問題座標與分類**：[`server/server/service.py:L71-L143, L377-L379`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk)、[`server/server/master.py:L515-L517, L750-L760`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) ｜ `C9.1 (A1/A4)`、`C3.2`
  - **觸發情境與演進根因分析**：
    1. **半套重構之保活通道分裂（`A4`）**：[`MasterSupervisor._handle_worker_control_packet`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（`master.py:L515-L517`）雖新增了 `if pkt_type == "touch_activity":` 接收邏輯，但 [`WarmWorker`](https://drive.google.com/file/d/1YDMnio1KHGj52Tiro48e18u6i4NNYN9p/view?usp=drivesdk) 與 [`BaseServiceWorker.touch_activity()`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk)（`service.py:L377-L379`）從未發送該 IPC 封包！所有執行於 `WarmWorker` 內的背景服務（`CoreSpaceWatcher`、`KnowledgeDBServiceWorker`）呼叫 `self.touch_activity()` 時，仍走舊軌讀取磁碟 `.cache/server/daemon.json` 並發起 TCP Loopback `POST http://127.0.0.1:{port}/api/touch`（`service.py:L98-L137`）。
    2. **寄生生命週期與停機時限衝突（`A1 / C3.2`）**：[`KnowledgeDBServiceWorker.stop()`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk)（`knowledge-db/service.py:L441`）宣告 `timeout: float = 5.0` 以確保正在執行的 ONNX 批次推論與 `flush_vector_index()` 能安全落盤。但宿主 [`MasterSupervisor._kill_worker_locked`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（`master.py:L753`）卻寫死 `proc.wait(timeout=min(timeout_sec, 1.5))`（且 `restart_worker` 傳入 `timeout_sec=1.5`、` _spawn_worker_locked` 傳入 `1.0`），只要背景服務關閉與索引落盤總耗時超過 1.5 秒，子進程樹即被 `terminate_popen_tree` 強制擊殺。
  - **建議解決方案（Mode A 根因重構 — 手術 `S3`）**：
    - **修改思路**：
      1. 在 `BaseServiceWorker.touch_activity()` 中，若 `self._log_sink` 具備 `emit_packet_fn`，直接透過記憶體節流（1.0s）發送 `{"type": "touch_activity", "source": self.name}` IPC 封包，零磁碟 `stat`、零 HTTP 連線開銷；僅在外部獨立進程呼叫 `server.service.touch_activity()` 時才使用 HTTP `/api/touch`。
      2. 將 `MasterSupervisor._kill_worker_locked` 的預設優雅握手等待時限提升至 `max(timeout_sec, 5.0)`（當背景服務處於活躍或 `busy` 狀態時給予充足的 `flush_vector_index` 時間）。
    - **程式碼修改範例**：
      ```python
      # server/server/service.py (BaseServiceWorker.touch_activity)
      def touch_activity(self) -> bool:
          """Notify the server supervisor that this background worker is actively processing work."""
          sink = getattr(self, "_log_sink", None)
          emit_fn = getattr(sink, "emit_packet_fn", None) if sink is not None else None
          if callable(emit_fn):
              now = time.monotonic()
              last_ts = getattr(self, "_last_ipc_touch_ts", 0.0)
              if (now - last_ts) >= _TOUCH_MIN_INTERVAL_SEC:
                  self._last_ipc_touch_ts = now
                  try:
                      emit_fn({"type": "touch_activity", "source": self.name})
                      return True
                  except Exception:
                      pass
              else:
                  return True
          return touch_activity(source=self.name)
      ```

- [x] **[AUD-04 / ARCH-04] [🟠 P1 | C9.2 (A2) & C1.1 | All-OS] [`knowledge-db/knowledge_db/pipeline.py:L1481-L1538`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) & [`knowledge-db/knowledge_db/engine.py:L677-L678`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) - 單空間獨立索引 (`<space>.index.bin.gz` / `_index_cache`) 舊軌未退役：導致 `yscb kdb index <space>` 與檢索使用的 `unified.index.bin.gz` 徹底脫節**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/pipeline.py:L213, L1481-L1538, L1560-L1569`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)、[`knowledge-db/knowledge_db/engine.py:L677-L678`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) ｜ `C9.2 (A2)` 新舊雙軌並存、`C1.1` 雙軌狀態失步
  - **觸發情境與演進根因分析**：
    1. 檢索管線 `IndexingPipeline.search()`（`pipeline.py:L1890`）與背景服務 `KnowledgeDBServiceWorker` 100% 僅讀取與維護全域統一索引 `unified.index.bin.gz`（`self._unified_index`）與 `unified.vectors.bin.gz`。
    2. 然而當呼叫 `engine.build_index(space="...")`（或執行 CLI `python yscb.py kdb index <space>`）時，`pipeline.py:L1492-L1537` 卻仍走舊軌：單獨建置並寫入 `indices/{safe_name}.index.bin.gz` 與只寫不讀的孤兒字典 `self._index_cache[sp_name]`，**完全不更新 `unified.index.bin.gz`、不建置向量索引、也不推進 `"knowledge-db"` 空間游標**！使用者執行 `yscb kdb index <space> --force` 後，緊接著執行 `yscb kdb search <query> --space <space>` 卻仍然讀到舊的 `unified.index.bin.gz`。
    3. 此外，[`engine.py:L677`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) 檢查 `bin_idx = indices_dir / f"{sp_name}.index.bin.gz"` 時未將 `sp_name` 中的 `"/"` 替換為 `"_"`，與 `pipeline.py:L1504` 的 `safe_name = sp_name.replace("/", "_")` 檔名不一致。
  - **建議解決方案（Mode A 根因重構 — 手術 `S4`）**：
    - **修改思路**：徹底退役 `<safe_name>.index.bin.gz` 磁碟檔案與 `self._index_cache` 屬性；在 `build_index(space=...)` 中統一呼叫 `self.build_unified_index(force=force, interactive=interactive)` 確保全域 BM25 與向量索引真正更新，再從 `unified_idx` 篩選或投影出 `{sp_name: sp_idx}` 回傳以保持 Mode B 對外回傳結構相容，並在 `engine.py:L678` 直接以 `has_index = has_unified_index` 為準。
    - **程式碼修改範例**：
      ```python
      # knowledge-db/knowledge_db/pipeline.py
      def build_index(
          self,
          space: Optional[str] = None,
          force: bool = False,
          interactive: bool = False,
      ) -> Dict[str, InvertedIndex]:
          """建置統一倒排與向量索引；若指定 space 則回傳該空間之符號索引視圖（保持對外契約相容）。"""
          unified_idx = self.build_unified_index(force=force, interactive=interactive)
          if space is None:
              return {"unified": unified_idx}

          resolved_list = self.space_manager.resolve_spaces(space)
          sp = resolved_list[0]
          weights = self._resolve_space_weights()
          if space in weights:
              sp_name = space
          elif sp.short_name in weights:
              sp_name = sp.short_name
          elif sp.qualified_name in weights:
              sp_name = sp.qualified_name
          else:
              sp_name = sp.short_name or sp.qualified_name

          match_keys = {space, sp_name, sp.short_name, sp.qualified_name}
          space_symbols = [
              sym for sym in unified_idx.symbols.values()
              if not sym.spaces or any(s in match_keys for s in sym.spaces)
          ]
          sp_idx = InvertedIndex(space_name=sp_name)
          sp_idx.build(space_symbols, tokenizer=self.tokenizer, space=sp_name, pre_aggregated=True)
          sp_idx.acked_ast_generation = unified_idx.acked_ast_generation
          return {sp_name: sp_idx}
      ```

- [x] **[AUD-05 / ARCH-05] [🟠 P1 | C9.3 (A3) & C1.3 | All-OS] [`knowledge-db/knowledge_db/service.py:L118-L132, L255-L328`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk) & [`knowledge-db/knowledge_db/pipeline.py:L328-L405, L1711-L1725`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `worker_state` 與 `_GLOBAL_INDEX_CACHE` 跨記憶體與磁碟真相分裂 (Split-Brain SSOT)**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/service.py:L118-L132, L255-L328`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk)、[`knowledge-db/knowledge_db/pipeline.py:L328-L405, L1711-L1725`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) ｜ `C9.3 (A3)`、`C1.3`
  - **觸發情境與演進根因分析**：
    1. **同進程記憶體狀態未按 `indices_dir` 隔離且讀取優先序顛倒**：在 `service.py:L118-L131` 中，`_get_worker_mem_state()` 是全進程唯一的單一字典（無 `indices_dir` 鍵隔離）。而在 `read_worker_state(indices_dir)`（`L255-L328`）中，當磁碟檔案不存在時（例如剛執行完 `clean()` 或在測試中傳入另一個新建的 `indices_dir`），竟直接退回讀取全進程共用的 `_get_worker_mem_state()`，導致讀取無關目錄時誤報當前進程其他 Worker 的 `busy` 狀態！反之，當同進程 Worker 正在運行時，卻優先去 `stat` 與讀取磁碟 JSON（透過 `CellScope` 快取），若在同一 `CellScope` 內背景執行緒改變了狀態，前景因 `CellScope` 快取或檔案寫入延遲而讀到過期狀態。
    2. **未持久化微批次向量被新實例覆寫**：在 `pipeline.py:L1469-L1473` 中，當 `sync_vector_deficit_step(persist=False)` 更新了記憶體中的 `cache["vector_index"]` 時，僅在當前 `IndexingPipeline` 實例上設定 `self._vector_index_dirty = True`，而未將 `"vector_dirty": True` 記錄於共享的 `_get_index_cache()` 中。若另一個 `IndexingPipeline` 實例呼叫 `_ensure_indices_loaded()`，因其 `self._vector_index_dirty` 為 `False`，在 `L380-L394` 會直接從磁碟載入舊的 `unified.vectors.bin.gz` 並覆寫 `cache["vector_index"]`，抹除背景已計算完畢但尚未滿 8 批次落盤的記憶體向量！
    3. 此外，`pipeline.py:L1711-L1720` 在 `self._unified_index is None` 時直接呼叫 `InvertedIndex.load_binary(bin_file)`，繞過了 `_ensure_indices_loaded()` 的 `_CACHE_LOCK`、`_align_index_symbols_with_ast_snapshot()` 與 `cache` 更新。
  - **建議解決方案（Mode A 根因重構 — 手術 `S4`）**：
    - **修改思路**：
      1. 在 `_get_worker_mem_state()` 中記錄 `"indices_dir": os.path.normcase(str(Path(indices_dir).resolve()))`；在 `read_worker_state(indices_dir)` 中，若同進程 `active_worker` 存活且其 `indices_dir` 與目標吻合，直接以 O(1) 讀取記憶體 `_get_worker_mem_state()` 為唯一真實來源（SSOT）；若 `indices_dir` 不吻合則絕不回退讀取該記憶體狀態。
      2. 將 `"vector_dirty"` 納入 `_get_index_cache()` 字典中統一管理，並刪除 `pipeline.py:L1711-L1720` 繞過 `_ensure_indices_loaded` 的重複讀檔分支。

- [x] **[AUD-06 / ARCH-06] [🟠 P1 | C2.2 & C6.1 | macOS / Windows] [`server/server/space_watcher.py:L380-L401, L440-L445`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) & [`knowledge-db/knowledge_db/formatter.py:L288-L299`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) - macOS `/var -> /private/var` 符號連結與大小寫不敏感檔案系統下之 `relative_to` 崩潰與目錄事件漏接**
  - **問題座標與分類**：[`server/server/space_watcher.py:L380-L401, L440-L445`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)、[`knowledge-db/knowledge_db/formatter.py:L288-L299`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) ｜ `C2.2` 三平台差異（macOS / Windows）
  - **觸發情境與演進根因分析**：
    1. 在 macOS 上，`watchdog` 的 FSEvents 後端回報之事件路徑恆為解析符號連結後的實體路徑（如 `/private/var/folders/.../sub_dir`），而 `SpaceRegistry` 中的 `entry_p` 則由 `os.path.abspath` 建立（如 `/var/folders/.../sub_dir`）。
    2. 在 `CoreSpaceWatcherServiceWorker.notify_file_event`（`space_watcher.py:L440-L445`）中，`abs_p` 僅使用 `os.path.normpath` 而未執行 `os.path.realpath`。當發生目錄新增/移動/刪除事件時，`_dir_belongs_to_space(abs_p, s_cfg)`（`L380-L401`）直接呼叫 `dir_abs.relative_to(entry_p)` 與 `entry_p.relative_to(dir_abs)`。因為 `/private/var/...` 與 `/var/...` 前綴不同（或在 Windows / macOS APFS 上磁碟機代號/資料夾大小寫不同），`Path.relative_to()` 直接拋出 `ValueError`，導致 macOS 臨時工作區或符號連結目錄下的所有目錄級別事件被 100% 靜默丟棄！
    3. 同樣地，[`ResultFormatter.normalize_workspace_path`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk)（`formatter.py:L294`）使用 `p.resolve().relative_to(ws)`，在 Windows 大小寫不一致或專案內含軟連結時亦會因 `ValueError` 退回輸出完整絕對路徑。
  - **建議解決方案（Mode A 根因重構 — 手術 `S6`）**：
    - **修改思路**：在 `_dir_belongs_to_space` 與 `normalize_workspace_path` 中統一對兩端路徑執行 `os.path.realpath`（並於大小寫不敏感系統配合 `os.path.normcase` 比對前綴），廢除局部拼湊的 `_strip_macos_private_prefix` 補丁。
    - **程式碼修改範例**：
      ```python
      # server/server/space_watcher.py
      def _canonical_dir_path(p: Path) -> Path:
          try:
              return Path(os.path.normcase(os.path.realpath(str(p))))
          except OSError:
              return Path(os.path.normcase(os.path.abspath(str(p))))

      def _dir_belongs_to_space(self, dir_abs: Path, s_cfg: SpaceConfig) -> bool:
          canon_dir = _canonical_dir_path(dir_abs)
          all_entries = self.registry.collect_all_entry_paths(s_cfg.qualified_name)
          for entry_p in all_entries:
              if entry_p.is_file():
                  continue
              canon_entry = _canonical_dir_path(entry_p)
              if canon_dir == canon_entry:
                  return True
              try:
                  rel = canon_dir.relative_to(canon_entry)
                  if str(rel) != "." and not str(rel).startswith(".."):
                      if not s_cfg.is_dir_excluded_fast(
                          dir_abs, entry_p, self.registry.project_root
                      ):
                          return True
              except ValueError:
                  try:
                      rel_rev = canon_entry.relative_to(canon_dir)
                      if not str(rel_rev).startswith(".."):
                          return True
                  except ValueError:
                      continue
          return False
      ```

- [x] **[AUD-07 / ARCH-07] [🟠 P1 | C5.1 & C4.2 | All-OS] [`server/server/master.py:L946-L966, L1085, L1322-L1336`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) - `_idle_ttl_loop` 未檢查前景任務與背景服務忙碌狀態即強制關機，且 `dispatch_task` 中 `_wait_worker_ready()` 缺少超時上限可永久鎖死 `_dispatch_lock`**
  - **問題座標與分類**：[`server/server/master.py:L946-L966, L1085, L1322-L1336`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) ｜ `C5.1` 缺少超時與無限阻塞、`C4.2` 時序競態
  - **觸發情境與演進根因分析**：
    1. **前景任務執行期間被 Idle TTL 誤殺**：在 [`MasterSupervisor._idle_ttl_loop`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（`master.py:L1322-L1336`）中，每 2 秒僅檢查 `idle_seconds = time.time() - last_active >= self.idle_timeout_sec`，**完全沒有檢查 `self._is_worker_completely_idle()`（即 `self._current_task is not None` 或 `self.is_any_worker_service_busy()`）**！由於 `dispatch_task` 僅在任務開始（`L1068`）與結束（`L1049`）時更新 `self._last_active_time`，當執行任何耗時超過 `idle_timeout_sec` 的前景任務（例如使用者設定短 TTL `--ttl 15` 或執行大型全量建置/測試任務）時，`_idle_ttl_loop` 會在前景任務仍在執行中時直接呼叫 `self.stop()` 殺死 Worker 與 Server！
    2. **`_wait_worker_ready()` 無超時永久死鎖**：在 `dispatch_task`（`L1076-L1086`）中，執行緒在持有 `self._dispatch_lock` 的狀態下呼叫 `self._wait_worker_ready()`（預設 `timeout_sec=None`）。若 `WarmWorker` 送出第一階段 `worker_alive` 後，在 `pre_warm()` 階段（如某個模組的 `server_worker_warming` 事件 Hook 或 `service_manager.start_all`）發生無限阻塞，且進程未退出（`proc.poll() is None`），則 `_wait_worker_ready()` 將永遠迴圈等待，永久鎖死 `_dispatch_lock`，導致所有後續請求全部卡死！
  - **建議解決方案（Mode A 根因重構 — 手術 `S3`）**：
    - **修改思路**：
      1. 在 `_idle_ttl_loop` 中，若 `not self._is_worker_completely_idle()`，自動刷新 `self.touch_activity(source="active_task")` 並跳過關機與記憶體回收評估。
      2. 為 `_wait_worker_ready` 設定預設超時上限（例如 `max(30.0, self._worker_alive_timeout_sec * 6.0)`），超時後自動在 `_worker_lock` 下終止卡住的 Worker 並返回失敗，釋放 `_dispatch_lock`。
    - **程式碼修改範例**：
      ```python
      # server/server/master.py
      def _idle_ttl_loop(self) -> None:
          while self._is_running:
              time.sleep(2.0)
              if not self._is_running:
                  break
              if not self._is_worker_completely_idle():
                  self.touch_activity(source="busy_guard")
                  continue
              with self._activity_lock:
                  last_active = self._last_active_time
              idle_seconds = time.time() - last_active
              if self.idle_timeout_sec > 0 and idle_seconds >= self.idle_timeout_sec:
                  self.logger.info(f"Idle TTL ({self.idle_timeout_sec}s) reached. Initiating automatic shutdown...")
                  threading.Thread(target=self.stop, daemon=True).start()
                  break
              if idle_seconds >= 2.0:
                  self._evaluate_worker_memory_health()
      ```

---

### 🟡 P2 - Medium（防禦缺口與結構技術債：測試嗅探補丁 / 違反 CQS / 空殼抽象層 / 路徑尾綴誤匹配 / 10Hz 鎖探針）

- [x] **[AUD-08 / ARCH-08] [🟡 P2 | C9.2 (D5) | All-OS] [`server/server/master.py:L976-L989, L1136-L1139, L1178-L1179`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) & [`server/server/service.py:L628-L635`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk) & [`knowledge-db/knowledge_db/engine.py:L933-L936, L968-L971`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) - 生產代碼混入 `unittest.mock` 執行期嗅探與多處 PEP 562 `__getattr__` 白箱測試補丁 (`D5`)**
  - **問題座標與分類**：[`server/server/master.py:L976-L989, L1136-L1139, L1178-L1179`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)、[`server/server/service.py:L628-L635`](https://drive.google.com/file/d/1vKzjGXS091p73fPX9u4dRxaz81GSJ_fl/view?usp=drivesdk)、[`knowledge-db/knowledge_db/engine.py:L933-L936, L968-L971`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk)、[`knowledge-db/knowledge_db/pipeline.py:L94-L97, L111-L114`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)、[`knowledge-db/knowledge_db/service.py:L129-L143`](https://drive.google.com/file/d/1QMliIWw0Np-Fdugw7p8kZphoJThZf8yU/view?usp=drivesdk) ｜ `C9.2 (D5)` 生產代碼混入測試嗅探與逃逸補丁
  - **觸發情境與演進根因分析**：
    1. `MasterSupervisor._read_worker_handshake`（`master.py:L1136-L1139`）在生產代碼中直接檢查 `type(proc).__module__.startswith("unittest.mock")`，並在收到 `worker_ready` 後直接 `break` 退出讀取執行緒（`L1178-L1179`）。這迫使 `_stream_task_over_worker_pipe`（`L976-L1021`）必須同時維護兩套 stdout 讀取邏輯（`if use_demux:` 從 `task_q.get()` 讀取 vs `else:` 直接呼叫 `proc.stdout.readline()`），甚至還要在 `L980-L988` 寫一段專門清理 `is_mock_proc` 退出時塞入 `task_q` 之 `None` 哨兵的修補迴圈！
    2. `server/service.py`、`knowledge_db/engine.py`、`pipeline.py`、`service.py` 共 4 個檔案底部皆塞入了 PEP 562 `__getattr__` 與 `globals().pop("_GLOBAL_...")` 補丁以迎合舊白箱測試對私有全域變數的直接讀寫。而在 `server/service.py:L632` 中，當測試執行 `server_service._LAST_TOUCH_TS = 0.0` 後，該屬性即被寫入模組 `__dict__`，導致後續讀取 `server_service._LAST_TOUCH_TS` 永遠不會再觸發 `__getattr__`，形成雙軌遮蔽 Bug！
  - **建議解決方案（Mode A 根因重構 — 手術 `S5`）**：
    - **修改思路**：移除 `master.py` 中的 `is_mock_proc` 嗅探與 `_stream_task_over_worker_pipe` 的 `else: proc.stdout.readline()` 舊軌，讓 `worker-stdout-demux` 成為唯一的單一擁有者讀取通道（測試中 Mock `Popen.stdout.readline` 只需在序列末尾返回 `b""` 即自然結束執行緒）；提供顯式的 `set_engine_for_testing()` / `reset_touch_state()` 輔助函式並移除 PEP 562 `__getattr__` 私有變數鏡像。

- [x] **[AUD-09 / ARCH-09] [🟡 P2 | C9.1 (D1) | All-OS] [`knowledge-db/knowledge_db/embedding.py:L249-L286, L326-L341`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk) & [`knowledge-db/knowledge_db/engine.py:L538-L585`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) - 違反命令查詢分離 (CQS)：唯讀屬性 `EmbeddingService.is_available` 與 `KnowledgeEngine.status()` 觸發重型載入、目錄建立、實例狀態塗改與 `[GUARD]` 阻斷輸出**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/embedding.py:L249-L286, L326-L341`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk)、[`knowledge-db/knowledge_db/engine.py:L538-L585`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) ｜ `C9.1 (D1)` 違反 CQS 與隱藏副作用
  - **觸發情境與演進根因分析**：
    1. 讀取布林屬性 `embedding_service.is_available`（`embedding.py:L327`）會觸發 `_ensure_model()` -> `_init_model()`，不僅在磁碟建立目錄並載入數百 MB 的 ONNX Runtime 模型，且當本地無模型時會向 `stderr` 印出 `[GUARD] 如果你是 AI Agent，必須立即暫停當前作業...`（`L266`）。為了壓制這個副作用，`engine.py:L583`、`engine.py:L918`、`pipeline.py:L1813`、`pipeline.py:L1886`、`service.py:L476`、`service.py:L574` 在 6 個地方反覆塗改 `self.embedding_service.suppress_guard_prompt` 實例屬性。
    2. 呼叫唯讀查詢 `KnowledgeEngine.status()`（`engine.py:L560-L563`）時，若記憶體尚未載入索引，會無條件呼叫 `_ensure_indices_loaded(load_vectors=has_vector_index)` 將整個 `unified.index.bin.gz` 與 `unified.vectors.bin.gz` 反序列化進記憶體（並觸發 `trim_process_memory()`），使單純查看狀態的指令承擔全量索引載入開銷。
  - **建議解決方案（Mode A 根因重構 — 手術 `S5`）**：
    - **修改思路**：將 `[GUARD]` 提示移至顯式的 `emit_missing_model_guard_if_needed()` 方法（僅於前台 `search` 且無背景 Worker 時呼叫一次），讓 `is_available` 與 `_init_model()` 不再產生終端 `[GUARD]` 副作用，並移除 `suppress_guard_prompt` 狀態欄位。

- [x] **[AUD-10 / ARCH-10] [🟡 P2 | C9.3 (A5) & C2.2 | All-OS / Windows] [`server/server/logger.py:L1-L31`](https://drive.google.com/file/d/1tpy7XYyfoUAhI0EtXSeQHj1BVaeQO8t1/view?usp=drivesdk), [`server/server/streamer.py:L1-L13`](https://drive.google.com/file/d/1UkuxGO5yW1_Rm4zw9roQPXHspRIZuQ8O/view?usp=drivesdk), [`knowledge-db/knowledge_db/providers.py:L1-L20`](https://drive.google.com/file/d/1r1IaGLRJKJgVgl4PmRKW2TPGTFFC6cUZ/view?usp=drivesdk), [`knowledge-db/knowledge_db/io_utils.py:L19-L49`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) - 3 個空殼轉發檔案與繞過 `core.vfs` 的重複 `atomic_save_gzip_pickle`（Windows 下無 `WinError 5/32` 退避重試）**
  - **問題座標與分類**：[`server/server/logger.py`](https://drive.google.com/file/d/1tpy7XYyfoUAhI0EtXSeQHj1BVaeQO8t1/view?usp=drivesdk)、[`server/server/streamer.py`](https://drive.google.com/file/d/1UkuxGO5yW1_Rm4zw9roQPXHspRIZuQ8O/view?usp=drivesdk)、[`knowledge-db/knowledge_db/providers.py`](https://drive.google.com/file/d/1r1IaGLRJKJgVgl4PmRKW2TPGTFFC6cUZ/view?usp=drivesdk)、[`knowledge-db/knowledge_db/io_utils.py:L19-L49`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) ｜ `C9.3 (A5)` 空殼抽象層、`C2.2` Windows 檔案替換鎖定
  - **觸發情境與演進根因分析**：
    1. [`knowledge_db/io_utils.py`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) 已從 [`ast_engine.io_utils`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk) 匯入 `load_gzip_pickle`、`normalize_dirty_paths` 與 `is_dirty_file_match`，卻在 `L19-L49` 重新手寫了一份不經過 `core.vfs.write_bytes(..., atomic=True)` 的 `atomic_save_gzip_pickle`，直接呼叫裸 `os.replace(str(tmp_path), str(p))`。在 Windows NTFS 下，當防毒軟體或無鎖讀取端（如 `_ensure_indices_loaded`）正開啟 `unified.index.bin.gz` 時，單次裸 `os.replace` 會立即拋出 `PermissionError: [WinError 5 / 32]` 導致索引建置或熱修補失敗！
    2. `server/logger.py`、`server/streamer.py` 與 `knowledge_db/providers.py` 皆為無任何自訂邏輯的 1:1 轉發空殼。
  - **建議解決方案（Mode A 根因重構 — 手術 `S5`）**：
    - **修改思路**：在 `knowledge_db/io_utils.py` 中直接重導出 `from ast_engine.io_utils import atomic_save_gzip_pickle`（或統一委派 `core.vfs.write_bytes(str(p), compressed, atomic=True)`），消除重複且缺乏 Windows 重試的實作；內部模組（如 `master.py`、`worker.py`、`cli.py`）直接匯入 `core.log.RollingFileLogger`、`core.log.DebouncedIOStreamer` 與 `core.space.providers.get_knowledge_db_spaces`。

- [x] **[AUD-11] [🟡 P2 | C1.2 & C2.1 | All-OS] [`knowledge-db/knowledge_db/io_utils.py:L12-L16`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) -> [`ast/ast_engine/io_utils.py:L128-L148`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk) - `is_dirty_file_match` 雙向尾綴比對 (`p.endswith("/" + sym_path_norm)`) 過寬，導致不同模組下的同名相對路徑（如 `scripts/cli.py`）在熱修補時被誤刪**
  - **問題座標與分類**：[`ast/ast_engine/io_utils.py:L128-L148`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk)（由 [`knowledge-db/knowledge_db/pipeline.py:L1021, L1040, L1059, L1078`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 與 [`retrieval.py:L895`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk) 呼叫）｜ `C1.2`、`C2.1`
  - **觸發情境與演進根因分析**：
    1. `is_dirty_file_match` 在 `L144-L146` 執行：
       ```python
       for p in dirty_paths_norm:
           if "/" in p and (p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p)):
               return True
       ```
    2. 在多模組專案中，每個模組皆有 `scripts/cli.py`、`scripts/hook.core.py`、`tests/__init__.py`。若某單一模組空間回報空間內相對變更路徑 `p = "scripts/cli.py"`，則全專案所有模組中 `sym_path_norm = "ys_codebase/source/<mod>/scripts/cli.py"` 都會因 `sym_path_norm.endswith("/scripts/cli.py")` 為 `True` 而被匹配！在 `InvertedIndex.patch_incremental` 中，這會將其他未修改模組的 `scripts/cli.py` 符號從倒排索引中剔除。
  - **建議解決方案（Mode A 根因重構 — 手術 `S6`）**：
    - **修改思路**：僅當 `p` 為絕對路徑（`p.startswith("/")` 或含磁碟機代號 `c:/`）時才允許 `p.endswith("/" + sym_path_norm)`（對應 workspace root 絕對路徑匹配專案相對路徑）；當兩者皆為相對路徑時，必須完全相等（`p == sym_path_norm`），禁止以短相對路徑尾綴匹配長相對路徑。
    - **程式碼修改範例**：
      ```python
      # ast/ast_engine/io_utils.py
      def _is_abs_norm(path_str: str) -> bool:
          return path_str.startswith("/") or (len(path_str) > 2 and path_str[1] == ":" and path_str[2] == "/")

      def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool:
          if not dirty_paths_norm:
              return False
          sym_raw = str(doc_file_path).replace("\\", "/").lower()
          sym_is_abs = _is_abs_norm(sym_raw)
          sym_path_norm = sym_raw.strip("/")
          if not sym_path_norm:
              return False
          if sym_raw in dirty_paths_norm or sym_path_norm in dirty_paths_norm or ("/" + sym_path_norm) in dirty_paths_norm:
              return True
          for p in dirty_paths_norm:
              p_is_abs = _is_abs_norm(p)
              if p_is_abs and not sym_is_abs and p.endswith("/" + sym_path_norm):
                  return True
              if sym_is_abs and not p_is_abs and sym_raw.endswith("/" + p.strip("/")):
                  return True
          return False
      ```

- [x] **[AUD-12] [🟡 P2 | C4.3 & C7.1 | All-OS] [`server/server/space_watcher.py:L154-L174, L651-L660`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) & [`server/server/watcher.py:L17-L34`](https://drive.google.com/file/d/1HPg_sG_c-i2OI1Z7U1MDC4M8-mIi9dba/view?usp=drivesdk) - `flush_dirty_spaces` 在檢查 `_dirty_spaces` 為空前即每 100ms 執行 `is_transaction_locked()` 搶鎖探測，且兩處鎖探測函式重複實作**
  - **問題座標與分類**：[`server/server/space_watcher.py:L154-L174, L651-L660`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)、[`server/server/watcher.py:L17-L34`](https://drive.google.com/file/d/1HPg_sG_c-i2OI1Z7U1MDC4M8-mIi9dba/view?usp=drivesdk) ｜ `C4.3`、`C7.1`、`C8.3`
  - **觸發情境與演進根因分析**：
    1. 在 [`CoreSpaceWatcherServiceWorker.flush_dirty_spaces`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)（`space_watcher.py:L651-L660`）中，第一行就是 `if self.is_transaction_locked():`，直到 `L659` 才檢查 `if not self._dirty_spaces: return {}`。
    2. 因為 `CoreSpaceWatcher.run()` 主迴圈每 `0.1s`（100ms）呼叫一次 `flush_dirty_spaces()`（`L866-L870`），這導致**即使工作區完全沒有任何檔案變更（100% 閒置），背景執行緒仍然每秒執行 10 次 `uri.resolve("cache://.yscb.lock")` 並對 4 個 `.yscb.lock` 候選路徑呼叫 `InterProcessLock.acquire(blocking=False)` + `release()`**！
    3. 由於 `.yscb.lock` 在交易結束後檔案仍保留於磁碟上，每秒 10 次的 `acquire(blocking=False)` + `release()` 不僅造成持續的背景系統呼叫開銷，更會在那數微秒的鎖持有瞬間阻塞或干擾正要取得 `.yscb.lock` 的前景交易！
  - **建議解決方案（Mode A 根因重構 — 手術 `S1`）**：
    - **修改思路**：在 `flush_dirty_spaces` 與 `flush_space_now` 中，**先在 `self._lock` 下確認 `self._dirty_spaces` 非空且已達 `debounce_seconds` 視窗，只有當真正需要寫入快照時才呼叫 `self.is_transaction_locked()`**；並將 `_is_lock_path_active` 與 `_is_lock_file_active` 收斂為單一共用函式。
    - **程式碼修改範例**：
      ```python
      # server/server/space_watcher.py
      def flush_dirty_spaces(self, *, force: bool = False) -> Dict[str, ScanDiffResult]:
          now_mono = time.monotonic()
          with self._lock:
              if not self._dirty_spaces:
                  return {}
              if not force and (now_mono - self._last_event_time) < self.debounce_seconds:
                  return {}
          if self.is_transaction_locked():
              with self._lock:
                  if self._dirty_spaces:
                      self._deferred_by_lock_count += 1
              return {}
          ...
      ```

- [x] **[AUD-13] [🟡 P2 | C1.2 & C9.2 (A2) | All-OS] [`knowledge-db/knowledge_db/engine.py:L115-L158, L327-L419`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) & [`knowledge-db/scripts/hook.ast.py:L12-L69`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) - `_collect_raw_spaces_for_registry` 以 `short_name` 為鍵導致跨模組同名空間被覆蓋，且 `engine.py` 與 `hook.ast.py` 空間權重收集邏輯分歧**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/engine.py:L115-L158, L327-L419`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk)、[`knowledge-db/scripts/hook.ast.py:L12-L69`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) ｜ `C1.2` 契約漂移、`C9.2 (A2)` 平行實作
  - **觸發情境與演進根因分析**：
    1. 在 `_collect_raw_spaces_for_registry`（`engine.py:L121-L157`）中，使用 `by_short_name[s_short] = (owner, norm_d)` 暫存空間定義。若兩個不同 owner 的空間擁有相同 `short_name`（例如 `core/docs` 與 `project/docs`），後者會直接覆蓋前者，導致前者從 `SpaceRegistry` 中消失！
    2. 在 `engine.py:L382-L389` 中，讀取 `contribute.json` 時使用了互斥的 `if "space_weights" in file_data: ... elif isinstance(file_data.get("spaces"), dict):`，導致同一檔案內若同時定義 `"space_weights"` 與帶有 `"weight"` 的 `"spaces"`，`"spaces"` 中的權重會被靜默忽略；而 `scripts/hook.ast.py:L12-L29` 卻同時收集兩者，造成 `ASTEngine` 註冊的目標空間與 `KnowledgeEngine` 實際索引的空間不一致。
  - **建議解決方案（Mode A 根因重構 — 手術 `S4`）**：
    - **修改思路**：將 `_collect_raw_spaces_for_registry` 改為以 `f"{owner}/{s_short}"`（當顯式指定 owner 時）或 `s_short` 作為鍵，避免不同 owner 的同名空間互相覆蓋；將 `engine.py:L385` 的 `elif` 改為獨立的 `if`（先讀 `spaces` 內嵌 `weight`，再以 `space_weights` 覆寫），並讓 `scripts/hook.ast.py` 直接呼叫 `engine.py` 的共用解析函式。

- [x] **[AUD-14] [🟡 P2 | C3.2 & C1.2 | All-OS] [`server/scripts/cli.py:L198-L208`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) & [`server/server/master.py:L808, L833, L897-L901`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) - `cli.py:stop()` 在獲取 `daemon.lock` 失敗時仍無鎖強行歸檔日誌，且 `restart_worker` 覆蓋 CLI `--ttl` 啟動參數**
  - **問題座標與分類**：[`server/scripts/cli.py:L198-L208`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk)、[`server/server/master.py:L808, L833, L897-L901`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) ｜ `C3.2`、`C1.2`
  - **觸發情境與演進根因分析**：
    1. 在 [`server/scripts/cli.py:L200-L206`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) 中：
       ```python
       if archive_lock.acquire(blocking=True, timeout_sec=0.5):
           try:
               archived_log = ServerLogger(yscb_root=state.root).archive_and_close() or ""
           finally:
               archive_lock.release()
       else:
           archived_log = ServerLogger(yscb_root=state.root).archive_and_close() or ""
       ```
       當 `archive_lock.acquire` 返回 `False`（代表已有另一個活躍的 MasterSupervisor 持有 `daemon.lock`）時，`else:` 分支竟照常無鎖執行 `archive_and_close()`，直接把正在運行的 Server 日誌檔重命名移走！
    2. 在 `MasterSupervisor` 中，若使用者透過 CLI `yscb server start --ttl 60` 指定了自訂 TTL，一旦觸發 `restart_worker()`（`master.py:L808, L833`），`self.idle_timeout_sec = float(cfg.idle_timeout_sec)` 會無條件用組態檔預設值（1800s）覆蓋掉 CLI 傳入的 `60s`。
  - **建議解決方案（Mode A 根因重構 — 手術 `S3`）**：
    - **修改思路**：刪除 `server/scripts/cli.py:L205-L206` 的無鎖 `else:` 分支（拿不到鎖時不應觸碰活躍進程的日誌檔）；在 `MasterSupervisor.__init__` 記錄 `self._explicit_idle_timeout: Optional[float]`，僅在未透過 CLI 顯式指定時才由 `ServerConfig.load()` 動態同步。

---

### 🔵 P3 - Optimization（效能加速與局部結構打磨：重複過濾、熱補丁 $3 \times O(N)$ 全表掃描與樣板收斂）

- [x] **[AUD-15] [🔵 P3 | C7.1 & C1.1 | All-OS] [`knowledge-db/knowledge_db/hybrid.py:L157-L194`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk) & [`knowledge-db/knowledge_db/pipeline.py:L1927-L1981`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `HybridSearchEngine.search` 未利用 `VectorIndex.search(allowed_doc_ids=...)` 造成全量 $O(N \log N)$ 排序與 Tuple 分配，且 Hybrid 模式漏套用 `min_score` 並重複執行 `_symbol_matches_filters`**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/hybrid.py:L157-L194`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk)、[`knowledge-db/knowledge_db/pipeline.py:L1927-L1981`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) ｜ `C7.1` 效能熱點、`C1.1` 過濾契約不一致
  - **觸發情境與演進根因分析**：
    1. 當帶有 `spaces`、`kinds`、`languages` 或 `file_types` 過濾條件時，`HybridSearchEngine.search`（`hybrid.py:L158-L161`）將 `top_k` 設為 `len(self.vector_index.doc_ids)`，導致 `VectorIndex.search` 對全部 $N$ 個向量執行完整 `np.argsort(-sims)` 並建立 $N$ 個 Python Tuple，再於 `L174-L193` 逐一過濾；事實上 `VectorIndex.search`（`embedding.py:L534`）已內建 `allowed_doc_ids` 參數，或可在 NumPy 內先篩出 `sims >= min_vector_similarity` 的索引再過濾。
    2. `HybridSearchEngine.search` 已完整過濾所有候選符號，但 `pipeline.py:L1943, L1977` 又對結果重複執行一次 `_symbol_matches_filters`；同時在 Hybrid 模式下完全漏掉了 `flt.min_score` 門檻檢查（純 BM25 模式在 `retrieval.py:L1151` 則有檢查 `score < flt.min_score`）。
  - **建議解決方案（Mode A 根因重構 — 手術 `S6`）**：
    - **修改思路**：在 `HybridSearchEngine.search` 中支援 `min_score` 參數，並在 `VectorIndex.search` 中對無 `allowed_doc_ids` 但有相似度門檻的查詢先以 `np.flatnonzero(sims >= min_sim)` 縮減候選集，再執行 `argpartition`；移除 `pipeline.py` 中冗餘的二次 `_symbol_matches_filters` 呼叫（僅保留 `score >= min_score` 檢查）。

- [x] **[AUD-16] [🔵 P3 | C7.1 & C9.2 (D4) | All-OS] [`knowledge-db/knowledge_db/pipeline.py:L1018-L1080, L1221-L1228`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) & [`knowledge-db/knowledge_db/retrieval.py:L890-L898`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk) - `hot_patch_unified_index` 單檔增量更新重複掃描全量 `symbols` 字典達 5 次，且 `_evict_dirty_file_artifacts` 與 `patch_incremental` 重複計算 `old_doc_ids`**
  - **問題座標與分類**：[`knowledge-db/knowledge_db/pipeline.py:L1018-L1080, L1221-L1228`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)、[`knowledge-db/knowledge_db/retrieval.py:L890-L898`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk) ｜ `C7.1`、`C9.2 (D4)` 假增量掃描
  - **觸發情境與演進根因分析**：
    1. 在 `_hot_patch_unified_index_locked`（`pipeline.py:L1222-L1228`）中，先呼叫 `old_doc_ids = self._evict_dirty_file_artifacts(dirty_keys)` 全表掃描 `self._unified_index.symbols` 找出待刪 `old_doc_ids`，緊接著下一行呼叫 `self._unified_index.patch_incremental(dirty_file_paths=dirty_keys, ...)`，在 `retrieval.py:L892-L896` **又對 `self.symbols` 執行完全相同的全表掃描與 `normalize_dirty_paths(dirty_file_paths)`**！
    2. 在 `_collect_all_dirty_files` 中，即使變更的檔案不是 C# 檔案（無 `partial class`），仍無條件對 `self._unified_index.symbols` 與 `snapshot.symbols` 執行兩輪 C# partial closure 掃描（`L1018-L1049`）。
  - **建議解決方案（Mode A 根因重構 — 手術 `S2`）**：
    - **修改思路**：讓 `InvertedIndex.patch_incremental` 接受選填的 `removed_doc_ids: Optional[Set[str]] = None`（或由 `patch_incremental` 直接回傳 `removed_doc_ids: Set[str]` 供後續向量索引刪除使用），徹底刪除 `_evict_dirty_file_artifacts()` 這一輪多餘的全表掃描；並在 `_collect_all_dirty_files` 中當 `dirty_keys` 不含 `.cs` 檔案且無跨世代落差時跳過 C# partial closure 雙重全表掃描。

- [x] **[AUD-17] [🔵 P3 | C8.3 (S3) | All-OS] [`server/server/space_watcher.py:L571-L723`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) & [`knowledge-db/knowledge_db/pipeline.py:L724-L915`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `flush_space_now` / `flush_dirty_spaces` 與 `sync_incremental_changes` 存在大面積同構樣板重複**
  - **問題座標與分類**：[`server/server/space_watcher.py:L571-L723`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)、[`knowledge-db/knowledge_db/pipeline.py:L724-L915`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) ｜ `C8.3 (S3)` 同構樣板收斂
  - **觸發情境與演進根因分析**：
    1. `space_watcher.py` 中 `flush_space_now` 與 `flush_dirty_spaces` 兩方法的批次更新、回滾、`sync_dependent_snapshots_batch` 與狀態切換邏輯高達 85% 相同（僅差在髒空間集合的提取方式與回傳型別）。
    2. `pipeline.py` 中 `sync_incremental_changes` 的 `if target_spaces:` 分支（`L724-L821`）與單一 `space_name` 分支（`L823-L914`）高達 90% 相同。
  - **建議解決方案（Mode A 根因重構 — 手術 `S1` & `S2`）**：
    - **修改思路**：如手術 `S1` 與 `S2` 所述，將 `space_watcher.py` 提取共用 `_execute_space_flush_batch(dirty_batch, full_rescan_batch)`，並將 `pipeline.py:sync_incremental_changes` 統一為 `spaces_to_consume = list(target_spaces) if target_spaces else [space_name]` 單一管線（保留 20% 差異分支不變量）。

---

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

- **[RFP-01] [`server/server/master.py:L1390-L1397, L1549`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（HTTP 端點鑑權與綁定介面）**：初看 HTTP Server 暴露 `/api/dispatch` 執行指令疑似存在本機權限提升風險；經查驗其嚴格綁定 `127.0.0.1:0`、使用 `secrets.token_hex(16)` 產生隨機 Token、將 `daemon.json` 權限設為 `0o600`，並以常數時間 `secrets.compare_digest` 驗證 `Authorization: Bearer <token>` 與校驗 `yscb_root` 路徑一致，符合本機 IPC 安全邊界（`C6.3`）。
- **[RFP-02] [`server/server/worker.py:L271-L285`](https://drive.google.com/file/d/1YDMnio1KHGj52Tiro48e18u6i4NNYN9p/view?usp=drivesdk)（`WarmWorker` 執行環境隔離）**：初看常駐熱進程執行不同目錄下之 CLI 任務疑似有 `os.chdir` 或 `os.environ` 污染；經核對 [`core/core/context.py:L388-L447`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk)，`WarmWorker` 已全面透過 `ContextVar` 綁定 `RuntimeScope`（`virtual_cwd` 與 `env_overrides`）與 `CellScope`，零全域 `os.chdir` 或 `os.environ` 突變（`C9.3 / A4`）。
- **[RFP-03] [`knowledge-db/knowledge_db/pipeline.py:L1362-L1479`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)（`sync_vector_deficit_step` 鎖粒度控制）**：初看微批次向量自癒在 `self._index_lock` 外呼叫 `embed_texts` 疑似有競態；經查驗其在 `L1422` 重新取得 `self._index_lock` 後，會二次比對 `sid in current_sym_ids`（`L1433`）過濾推論期間已被刪除的符號，設計安全且避免了持鎖執行慢速 CPU 推論（`C4.3`）。
- **[RFP-04] [`core/core/log.py:L440-L473`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk)（`DebouncedIOStreamer._flush_locked` 重入防護）**：初看在 `_lock` 內呼叫外部 `emit_chunk` 回呼疑似有重入重複寫入風險；經查驗 `L458-L459` 在呼叫 `emit_chunk` 前已先行清空 `self._buffer` 與 `self._buffer_bytes`，且 `_lock` 為 `RLock`，無死鎖與重複發送風險（`C4.3`）。
- **[RFP-05] [`server/server/master.py:L1355-L1366`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（`_cleanup_state` 保留 `daemon.lock`）**：初看關閉 Server 時未刪除 `daemon.lock` 疑似殘留檔案；經查驗註解與 POSIX `flock` 語意，保留鎖檔案可避免併發啟動者鎖定被 `unlink` 的舊 inode，屬於刻意且正確的跨平台設計（`C2.2`）。


---

## Part IV — Group D：`ast` 模組（語法樹解析、圖譜連結器、符號查詢與增量同步）

# 🛡️ `module:ast` (`ast_engine`) 第二次程式碼庫九維度單點序列深度審計與架構整理報告 (Round 2 Codebase Deep Audit: Group D)

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：[`ys_codebase/source/ast/`](https://drive.google.com/file/d/1EcHyyCiV0Ur8yCtw9ToHlBamrztCaR0G/view?usp=drivesdk) 全模組（涵蓋 `ast_engine/`、`ast_engine/parsers/`、`ast_engine/dialects/`、`assets/queries/`、`scripts/`、`contributes/` 共 4 個獨立審查單元、34 個核心檔案，已完成 100% 逐檔序列深潛與跨單元架構收斂）
- **目標語言與平台基準**：語言 `Python 3.11+`（解析目標涵蓋 `Python / C# / C++ / C / TypeScript / JavaScript / Markdown / SPICE / HTML / CSS`）｜ 平台基準 `Linux + Windows + macOS` ｜ 架構重構尺度 `Mode B 外圍 CLI/SDK 契約相容 + Mode A 內部雙軌退役與 SSOT 根因收斂`
- **診斷統計總覽**：🔴 **P0**：`2` 項 ｜ 🟠 **P1**：`4` 項 ｜ 🟡 **P2**：`3` 項 ｜ 🔵 **P3**：`1` 項（共確認 `10` 項結構與邏輯問題，並反向查證排除假陽性 `3` 項）

| 審查單元 (Audit Unit) | 涵蓋檔案 | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`** (`ast_engine` 核心結構、引擎與打包器) | [`ast_engine/__init__.py`](https://drive.google.com/file/d/1kHv49lpzfJ4UAKrc0D0YKRnbyDpxX17y/view?usp=drivesdk), [`ast_engine/schema.py`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk), [`ast_engine/engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/bundler.py`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/graph.py`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk), [`ast_engine/formatter.py`](https://drive.google.com/file/d/1N89QaHI3Uu1a3ww3aL09ezgE5KA0qxFa/view?usp=drivesdk), [`ast_engine/io_utils.py`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk), [`ast_engine/exceptions.py`](https://drive.google.com/file/d/1yga-4_TDjo9U_Cei8kf6yqCEPbg7s-os/view?usp=drivesdk) | `ARCH-01`, `AUD-02`, `ARCH-02`, `ARCH-03`, `AUD-05`, `AUD-06`, `AUD-09` | 🔴 建議優先修復 |
| **`Unit 02`** (`ast_engine` 拓撲連結器與符號查詢解析器) | [`ast_engine/linker.py`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/resolver.py`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk), [`ast_engine/provisioner.py`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) | `ARCH-01`, `ARCH-02`, `ARCH-03`, `AUD-08`, `AUD-10` | 🔴 建議優先修復 |
| **`Unit 03`** (`ast_engine/parsers` 語法解析器、方言與 `.scm`) | [`ast_engine/parsers/base.py`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk), [`ast_engine/parsers/registry.py`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk), [`ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk), [`ast_engine/parsers/python_ast.py`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk), [`ast_engine/parsers/markdown.py`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk), [`ast_engine/parsers/spice_parser.py`](https://drive.google.com/file/d/1oh0Z2cy30DOHCQQhoM4bnBe_xhL_26fL/view?usp=drivesdk), [`ast_engine/parsers/html_parser.py`](https://drive.google.com/file/d/1ReVJpaKRfztk5EDsIqo4buzKKkMzcslI/view?usp=drivesdk), [`ast_engine/parsers/css_parser.py`](https://drive.google.com/file/d/12HE1UU47wnRsus8O78x21G8bimYz6UWv/view?usp=drivesdk), [`ast_engine/dialects/*`](https://drive.google.com/file/d/1MFfZA2sghRNbTnSs0knK9FIaxaZhcBDN/view?usp=drivesdk), [`assets/queries/*.scm`](https://drive.google.com/file/d/15rmc9N2tpT10_U46Rr_8a0b553lm-1qB/view?usp=drivesdk) | `ARCH-01`, `AUD-07`, `AUD-08`, `AUD-09` | 🟠 建議修復 |
| **`Unit 04`** (`ast` 腳本、CLI 與生命週期 Hooks) | [`scripts/cli.py`](https://drive.google.com/file/d/1QFkpVeFwOH1jSPVT_lW-QXGRMLEOd3pf/view?usp=drivesdk), [`scripts/hook.core.py`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk), [`scripts/hook.dev.py`](https://drive.google.com/file/d/1eMgeW0PysuoO-j9ibs8eo1ni5fjQNwBc/view?usp=drivesdk), [`scripts/migrations/1.0.1.x.py`](https://drive.google.com/file/d/1IuTD61_fpmuntwLRufqkX7SLLsgk7lYT/view?usp=drivesdk), [`contributes/core.json`](https://drive.google.com/file/d/1mrvWM2YVddXmifc_AyzyUJgMlpd9zRFa/view?usp=drivesdk), [`contributes/ast.json`](https://drive.google.com/file/d/1LxuUtOZr7hh0SQAyjEGZgM-6UeSEmFMz/view?usp=drivesdk), [`contributes/_format.json`](https://drive.google.com/file/d/109J_lwJAR_Va9QnEwX_DAa8Ir-oFKoUN/view?usp=drivesdk), [`manifest.json`](https://drive.google.com/file/d/15gt1c0xWtWAPS0Qu4FQC-YFIliaaKPAD/view?usp=drivesdk) | `AUD-06` | 🟠 建議修復 |

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S4)

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **單軌圖譜收斂與舊代 `TopologyLinker` / 乒乓橋接層退役手術** | `ARCH-01`, `AUD-02`, `AUD-10` | `C9.2 (A2/D4)`, `C7.1`, `C7.2` | 1. **解析單軌化**：所有 Parser（含 `TreeSitterDriver`、`PythonASTParser`、`MarkdownParser`、`SpiceParser`、`HtmlParser`、`CssParser`）統一以 `extract_file_graph() -> FileSymbolGraph` 為唯一原生提取入口，直接產出 `SymbolNode` 與 `RelationEdge`；廢除 `_parse_file_task_worker` / `_parse_file_full` 對同一檔案連續呼叫 4 次提取方法的冗餘流程，需要 `UnifiedSymbol`（供下游 `knowledge-db` 相容消費）時直接從已提取的 `FileSymbolGraph` 單向投影派生，徹底拔除 270 行的反向橋接器 `convert_legacy_symbols_to_file_graph`。<br>2. **Linker 單軌化与真實增量重連**：廢除含模糊猜測的舊軌 `TopologyLinker` 與 `SymbolCallSite` 雙軌連結，統一由 `WorkspaceGraphLinker` 作為唯一圖譜連結器；於 `WorkspaceSymbolGraph` 維護檔案級反向依賴索引，使 `hot_patch_index` 僅重連受影響檔案子圖而非重跑全倉 $O(N)$ 4-Pass Linker；並消除 `file_graphs` 在 `unified.symbols.bin.gz` 與 `unified.graph.bin.gz` 的雙重重複序列化。 |
| **`S2`** | **C# `partial` 與 C/C++ 跨檔折疊單一真實來源 (SSOT) 收斂手術** | `ARCH-03`, `AUD-02` | `C9.3 (A3)`, `C1.1` | 廢除散落於 `bundler.py`（`aggregate_partial_symbols` + `_own_members` 原地塞入 `metadata`）、`engine.py`（`_cs_partial_type_key` + `_sym_to_outline_node` 手寫 50 行掃描迴圈）、`linker.py`（Pass 1 `folded_symbol_groups`）與 `resolver.py` 的 4 套平行實作。統一由 `WorkspaceGraphLinker` Pass 1 的 `folded_symbol_groups`（補齊 `(spaces, kind, fqn)` 隔離與同組傳染規則）作為唯一跨檔折疊 SSOT，`outline(merged=True/False)` 與 `UnifiedSymbol` 視圖直接查表投影，徹底移除 `_own_members` / `restore_unaggregated_partial_symbol` 狀態突變補丁。 |
| **`S3`** | **嚴格命令查詢分離 (CQS) 與測試嗅探 / PEP 562 逃逸補丁純化手術** | `ARCH-02` | `C9.1 (D1)`, `C9.2 (D5)` | 1. **純化唯讀 Getter**：移除 `get_persisted_meta()` 內解壓縮 `unified.symbols.bin.gz` 並無鎖覆寫 `unified.meta.json` 的副作用；移除 `get_workspace_graph(auto_sync=False)` 內暗中掃描全倉並覆寫二進位索引的副作用。<br>2. **拔除測試逃逸補丁**：移除 `engine.py`、`bundler.py`、`linker.py`、`dialects/__init__.py` 的 PEP 562 `__getattr__` + `globals().pop(...)` 鏡像陷阱、`get_engine()` 內的 `if not isinstance(ASTEngine, type):` Mock 嗅探，以及 `provisioner.py` 的 `_ProvisionerMeta` 元類別，改為顯式公開重置 API（如 `reset_ast_runtime_state()`）供 `ASTTestCase` 呼叫。 |
| **`S4`** | **單一交易式空間游標協調器與跨平台路徑正規化手術** | `AUD-05`, `AUD-06`, `AUD-09` | `C4.1`, `C9.1 (D2)`, `C2.2` | 1. 將散落於 `build_index`、`hot_patch_index`、`ensure_jit_synced` 與 `scripts/hook.core.py` 的 4 套游標消費與 ACK 邏輯收斂為 `ASTEngine` 單一交易方法，嚴格按目標 `target_qnames` 逐空間 ACK（禁止傳入 `ack(None)` 誤抹除其他未處理空間的游標），並在 `hook.core.py` 補齊 `has_parseable` 過濾。<br>2. 修復 `io_utils.atomic_save_gzip_pickle` 無差別 `glob` 誤刪併發進程 `.tmp` 檔問題、Windows 跨磁碟機相對路徑退化與 `_resolve_target_file` 空間覆蓋問題。 |

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：核心架構雙軌分裂 / 增量熱修補狀態腐敗 / 假增量效能崩潰）

- [x] **[ARCH-01 / AUD-01] [🔴 P0 | C9.2 (A2/D4) & C7.1 / C7.2 | All-OS] [`ast_engine/bundler.py:L436-L465`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/engine.py:L865-L894`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L1143-L1158`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/resolver.py:L949-L989`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) - 新舊兩代圖譜與雙 Linker 全量並存，導致單檔重複提取 4 次、`hot_patch_index` 重跑全倉 $O(N)$ 4-Pass 連結、雙軌快照重複序列化 3 份且查詢結果矛盾**
  - **問題座標與分類**：
    - [`ast_engine/bundler.py:L436-L465`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) (`_parse_file_task_worker`) & [`ast_engine/bundler.py:L892-L930`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) (`SemanticBundler._parse_file_full`)
    - [`ast_engine/parsers/base.py:L370-L707`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) (`convert_legacy_symbols_to_file_graph`, `BaseParser.extract_file_graph`)
    - [`ast_engine/engine.py:L865-L894`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`ASTEngine.build_index`) & [`ast_engine/engine.py:L1143-L1158`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`ASTEngine.hot_patch_index`)
    - [`ast_engine/schema.py:L1258-L1275`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk) (`ASTSnapshot.to_dict`) & [`ast_engine/graph.py:L307-L315`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk) (`CallGraphIndex.to_dict`)
    - [`ast_engine/resolver.py:L949-L989`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`query_callers`), [`ast_engine/resolver.py:L1068-L1104`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`query_callees`), [`ast_engine/resolver.py:L1195-L1232`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`query_impact`)
    - 維度：`C9.2 (A2 新舊雙軌並存 / D4 假增量)`、`C7.1 (重複解析)`、`C7.2 (序列化膨脹)`、`C1.1 (雙軌狀態矛盾)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **單檔 4 次提取與乒乓轉換**：在引入新一代 `SymbolNode` / `FileSymbolGraph` / `WorkspaceGraphLinker` / `WorkspaceSymbolGraph` 後，舊一代 `UnifiedSymbol` / `SymbolCallSite` / `TopologyLinker` / `CallGraphIndex` 並未退役。`_parse_file_task_worker` ([`ast_engine/bundler.py:L450-L461`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)) 與 `_parse_file_full` ([`ast_engine/bundler.py:L903-L929`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)) 對每個檔案連續呼叫 `extract_file_graph`、`parse_file`、`extract_call_sites`、`extract_imports` 4 個方法；而在 `TreeSitterDriver` 內，`extract_file_graph` 跑一次 `_build_recursive_symbol_nodes` + `_extract_relation_edges`，`parse_file` 又重跑一次 `_build_symbol_hierarchy` + `_materialize_unified_symbols`，`extract_call_sites` 再掃描一次 matches。對於非 Tree-sitter 解析器（`PythonASTParser`、`SpiceParser`、`HtmlParser`、`CssParser`），`BaseParser.extract_file_graph` ([`ast_engine/parsers/base.py:L671-L707`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk)) 先跑舊軌 `parse` + `extract_call_sites` + `extract_imports`，再透過 270 行的 `convert_legacy_symbols_to_file_graph` ([`ast_engine/parsers/base.py:L370-L640`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk)) 用字串 `.find()` 重新反推 `Span` 座標轉成 `FileSymbolGraph`！
    2. **熱修補假增量 (`D4`)**：在 `hot_patch_index` ([`ast_engine/engine.py:L1150-L1156`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)) 中，即便只修改了 1 個檔案，第 1150 行都會將全倉 `self._snapshot.file_graphs.values()` 傳入 `WorkspaceGraphLinker` 重新執行 Pass 1 ~ Pass 4 全域 $O(N)$ 連結！
    3. **3 倍快照膨脹 (`C7.2`)**：全倉所有檔案的 `FileSymbolGraph` 既被存入 `ASTSnapshot.file_graphs` 寫入 `unified.symbols.bin.gz` ([`ast_engine/schema.py:L1270-L1274`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk))，同時又被包在 `CallGraphIndex.workspace_graph.file_graphs` 中寫入 `unified.graph.bin.gz` ([`ast_engine/graph.py:L313-L314`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk))，造成磁碟 I/O 與記憶體佔用翻倍膨脹。
    4. **新舊 Linker 查詢結果分裂 (`C1.1`)**：`query_callers` ([`ast_engine/resolver.py:L949-L959`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk))、`query_callees` ([`ast_engine/resolver.py:L1068-L1078`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)) 與 `query_impact` ([`ast_engine/resolver.py:L1195-L1208`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)) 優先讀取舊軌 `CallGraphIndex`（由含啟發式模糊猜測 `_score_candidates` 的 `TopologyLinker` 建立），僅在 `not caller_order`（舊軌結果為空）時才讀取新軌 `WorkspaceSymbolGraph`；而 `ast traverse` 則直接讀取 `WorkspaceSymbolGraph`，導致兩套 CLI 指令對同一符號給出矛盾的呼叫拓撲。
  - **建議解決方案（Recommended Solution - Mode A 內部單軌收斂 + Mode B 對外契約保留）**：
    - **修改思路**：
      1. 以 `FileSymbolGraph` 作為單檔解析唯一真實來源（SSOT），由 `FileSymbolGraph` 直接派生 `UnifiedSymbol`（供 `ASTSnapshot.symbols` 及 `knowledge-db` 讀取），移除 `_parse_file_full` / `_parse_file_task_worker` 中的重複解析與 `convert_legacy_symbols_to_file_graph`。
      2. 以 `WorkspaceGraphLinker` 取代 `TopologyLinker`，將 `WorkspaceGraphLinker` 解析出的 `resolved` / `overload_group` `calls` 邊直接灌入 `CallGraphIndex`（或讓 `CallGraphIndex` 直接作為 `WorkspaceSymbolGraph` 的薄查詢視圖），並在 `WorkspaceSymbolGraph.to_dict()` 中不重複序列化已存於 `ASTSnapshot.file_graphs` 的 `file_graphs`（載入時由 `engine` 注入）。
    - **程式碼修改範例**：
      ```python
      # ast_engine/bundler.py: 單次提取 FileSymbolGraph 並直接投影出 UnifiedSymbol，0 重複解析
      def _parse_file_full(
          self,
          f_path: Union[str, Path],
          relpath: str,
          sorted_spaces: List[str],
      ) -> Tuple[List[UnifiedSymbol], FileSymbolGraph]:
          primary_space = sorted_spaces[0] if sorted_spaces else "unified"
          with open(f_path, "r", encoding="utf-8", errors="replace") as f:
              content = f.read()
          fg = self.parser_registry.extract_file_graph(
              file_path=relpath,
              content=content,
              space=primary_space,
          )
          self._file_graphs_cache[relpath] = fg
          self._file_graphs_cache[_safe_resolve_str(f_path)] = fg
          file_symbols = project_unified_symbols_from_file_graph(
              fg, default_space=primary_space, spaces=sorted_spaces
          )
          return file_symbols, fg
      ```

- [x] **[AUD-02] [🔴 P0 | C1.1 & C1.3 | All-OS] [`ast_engine/engine.py:L1018-L1106`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/bundler.py:L1265-L1284`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/bundler.py:L1466-L1481`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) - `hot_patch_index` 增量熱修補存在三大狀態失步漏洞：(a) C# `partial` 跨檔變更未重連未修改姊妹檔之呼叫點；(b) 重連外部進入邊漏檢查自迴圈且模糊回退誤連同名無關符號；(c) 刪除檔案時 `bundle_dirty_files` 與 `extract_dirty_file_graphs` 漏傳 `known_indexed_files` 導致舊符號與舊 `FileSymbolGraph` 殘留**
  - **問題座標與分類**：
    - [`ast_engine/engine.py:L1018-L1039`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`_evict_dirty_and_reaggregate_partials`)
    - [`ast_engine/engine.py:L1054-L1106`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`_relink_and_reconnect_edges`)
    - [`ast_engine/bundler.py:L1271-L1276`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) (`bundle_dirty_files`) & [`ast_engine/bundler.py:L1472-L1477`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) (`extract_dirty_file_graphs`)
    - 維度：`C1.1 (全量與增量路徑狀態失步)`、`C1.3 (快取與持久化 SSOT 失步)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **C# `partial` 跨檔欄位/基底型別變更漏重連姊妹檔 (`L1018-L1056`)**：當 `Foo.Part1.cs` 新增或修改了欄位 `_dep: DepService` 或基底類別 `BaseFoo` 時，`_evict_dirty_and_reaggregate_partials` 雖然更新了 `Foo.Part2.cs` 類別符號的 `metadata["field_types"]` 與 `metadata["base_types"]`，但 `_relink_and_reconnect_edges` 第 1054 行 `self.bundler.extract_dirty_call_sites_and_imports(detail, spaces=spaces)` 僅重新提取並連結 `detail`（即 `Foo.Part1.cs`）內的呼叫點，**未將受波及之存活姊妹檔 `Foo.Part2.cs` 納入重連範圍**！結果 `Foo.Part2.cs` 內透過 `_dep.Execute()` 或 `base.Helper()` 發出的呼叫邊在增量熱修補後遺失，與全量 `build_index` 結果不符。
    2. **外部進入邊重連漏擋自迴圈與跨檔誤連 (`L1092-L1101`)**：在 `_relink_and_reconnect_edges` 中，當被調用檔案的某個函式被刪除時，第 1092-1098 行退回呼叫 `linker.resolve_call_site(site)`，此時 `TopologyLinker` 會因原本目標已消失而用 `_score_candidates` 模糊匹配到其他檔案中名稱相似的符號，且第 1100 行 `if target_new_id: reconnected_incoming_edges.append((caller_id, target_new_id, site))` **漏掉了 `link_call_sites` L694-L702 的自迴圈防護 (`if caller_id == target_new_id`)**！
    3. **刪除檔案漏傳 `known_indexed_files` 造成殘留 (`bundler.py:L1271, L1472`)**：因為 `build_index` / `hot_patch_index` 結束時呼叫了 `self.bundler.clear_transient_caches()`，`_file_symbols_cache` 在下次熱修補開始時恆為空 `{}`。當檔案在磁碟上被刪除且跨多個空間/entry roots 時，`_normalize_space_dirty_paths` ([`ast_engine/bundler.py:L619-L636`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)) 依賴 `known_indexed_files` 過濾出真正曾被索引的刪檔路徑；但 `bundle_dirty_files` (L1271) 與 `extract_dirty_file_graphs` (L1472) 卻都漏傳了 `known_indexed_files`（僅 `engine.py:L650` 有傳），且同一次 `hot_patch_index` 重複執行了 3 次 `_preload_snap_entries` 與 `_normalize_space_dirty_paths`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `hot_patch_index` 中，將 `surviving_partials` 所在的姊妹檔路徑一併加入需重新提取與重連 call sites 的檔案集合（同時先清除這些姊妹檔的舊外出邊再重連）。
      2. 在 `_relink_and_reconnect_edges` 重連外部進入邊時，嚴格要求 `target_new_id` 若透過 fallback `resolve_call_site` 取得，必須具備確定性匹配且不得產生非遞迴容器自迴圈。
      3. 將 `known_indexed_files=set(self._snapshot.file_to_symbol_ids.keys()) | set(self._snapshot.file_graphs.keys())` 傳入 `bundle_dirty_files` 與 `extract_dirty_file_graphs`，並共用單次預載的 `snap_entries_by_space` 與正規化路徑集合。
    - **程式碼修改範例**：
      ```python
      # ast_engine/engine.py: 將受影響的 partial 姊妹檔納入重連範圍，並補齊 known_indexed_files 與自迴圈檢查
      known_files = set(self._snapshot.file_to_symbol_ids.keys()) | set(self._snapshot.file_graphs.keys())
      new_symbols_by_file, dirty_keys = self.bundler.bundle_dirty_files(
          detail, spaces=spaces, known_indexed_files=known_files
      )
      ...
      # 若有 surviving_partials，將其 file_path 加入重連明細，並先移除該檔舊外出邊
      relink_detail = detail
      if surviving_partials:
          sibling_files = {s.file_path for s in surviving_partials if s.file_path}
          sibling_doc_ids = {
              sid for fp in sibling_files for sid in self._snapshot.file_to_symbol_ids.get(fp, ())
          }
          old_doc_ids.update(sibling_doc_ids)
          relink_detail = ScanDiffDetail(
              added=set(detail.added),
              modified=set(detail.modified) | sibling_files,
              deleted=set(detail.deleted),
          )
      ```

### 🟠 P1 - High（顯著缺陷：違反 CQS 讀寫副作用 / 測試嗅探補丁 / Split-Brain SSOT / 跨平台路徑與游標失步）

- [x] **[ARCH-02 / AUD-03] [🟠 P1 | C9.1 (D1) & C9.2 (D5) & C4.1 | All-OS] [`ast_engine/engine.py:L97-L112`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L814-L840`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L1328-L1358`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L1876-L1879`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/bundler.py:L38-L53`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/linker.py:L49-L61`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/dialects/__init__.py:L39-L51`](https://drive.google.com/file/d/1qZvQ-VPA8hy5pf8P7fcpsJzBioaxt2wn/view?usp=drivesdk), [`ast_engine/provisioner.py:L50-L68`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) - 唯讀查詢方法 (`get_persisted_meta`, `get_workspace_graph`) 違反 CQS 暗中重解析全倉與寫盤，且 5 個核心模組植入 PEP 562 `__getattr__` 全域變數攔截、`_ProvisionerMeta` 與 Mock 嗅探補丁**
  - **問題座標與分類**：
    - [`ast_engine/engine.py:L814-L840`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`get_persisted_meta`) & [`ast_engine/engine.py:L1328-L1358`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`get_workspace_graph`)
    - [`ast_engine/engine.py:L97-L112`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L1876-L1879`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`get_engine` 內 `if not isinstance(ASTEngine, type):`)
    - [`ast_engine/bundler.py:L38-L53`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/linker.py:L49-L61`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/dialects/__init__.py:L39-L51`](https://drive.google.com/file/d/1qZvQ-VPA8hy5pf8P7fcpsJzBioaxt2wn/view?usp=drivesdk), [`ast_engine/provisioner.py:L50-L68`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk)
    - 維度：`C9.1 (D1 違反 CQS 與隱藏副作用)`、`C9.2 (D5 生產代碼混入測試嗅探與逃逸補丁)`、`C4.1 (無鎖 globals().pop 競態)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`get_persisted_meta()` 違反 CQS 與無鎖寫盤**：Docstring 明確宣告「Read lightweight AST generation/metadata without decompressing unified.symbols.bin.gz」，但第 831-837 行在 `unified.meta.json` 缺失或 mtime 不符時，卻呼叫 `self._ensure_symbols_loaded()` 解壓縮整個 `unified.symbols.bin.gz`，並在不持有 `InterProcessLock` 的情況下呼叫 `self._atomic_write_meta(meta_payload)` 覆寫磁碟！
    2. **`get_workspace_graph(auto_sync=False)` 違反 CQS**：當呼叫端顯式傳入 `auto_sync=False` 要求純讀取磁碟快照時，若舊快照中 `_graph.workspace_graph` 為 `None`（第 1342-1357 行），該方法竟直接呼叫 `self.bundler.extract_all_file_graphs()` 重新掃描並解析全倉所有檔案、執行 4-Pass Linker，最後呼叫 `self._save_snapshot_and_graph(self._snapshot, self._graph)` 覆寫磁碟上的兩個 `.bin.gz` 檔案！
    3. **生產代碼混入 Mock 嗅探與 PEP 562 / Metaclass 逃逸補丁 (`D5`)**：
       - [`ast_engine/engine.py:L1876`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 寫了 `if not isinstance(ASTEngine, type):` 以嗅探 `ASTEngine` 是否被 `unittest.mock.patch` 替換為 `MagicMock`。
       - `engine.py`、`bundler.py`、`linker.py`、`dialects/__init__.py` 為同時討好靜態檢查與白箱測試（[`tests/__init__.py:L905-L971`](https://drive.google.com/file/d/1ys-YR3yT0JIIUQizdz51AWLe0GYD-HHq/view?usp=drivesdk) 直接存取 `_DIALECT_INSTANCES`、`_LAST_LINKER_CACHE`、`bundler._worker_registry`），各自實作了 `if "_VAR" in globals(): ctx.set_module_state(..., globals().pop("_VAR"))` + `def __getattr__(name):`。當多執行緒同時執行 `if "_VAR" in globals():` 與 `globals().pop("_VAR")` 時，缺乏鎖保護會拋出 `KeyError`；且當外部賦值 `bundler._worker_registry = reg` 後，該屬性留在模組 `globals()` 中，導致 `get_runtime_context()` 切換 scope 後仍讀到舊 scope 殘留在 `globals()` 的物件！
  - **建議解決方案（Recommended Solution - Mode A 純化生產代碼邊界）**：
    - **修改思路**：
      1. `get_persisted_meta()` 若 `unified.meta.json` 失效，僅回傳記憶體中或讀取到的 `meta_payload` 計算結果，不在 Getter 內偷偷寫盤；`get_workspace_graph(auto_sync=False)` 若 `workspace_graph` 為空且 `auto_sync=False`，應僅從記憶體已載入的 `self._snapshot.file_graphs` 在記憶體中建構 `WorkspaceSymbolGraph` 返回，絕不觸發磁碟重掃描與 `_save_snapshot_and_graph` 寫盤。
      2. 移除 `engine.py`、`bundler.py`、`linker.py`、`dialects/__init__.py` 的 PEP 562 `__getattr__` 與 `globals().pop` 駭客補丁、移除 `if not isinstance(ASTEngine, type):` 嗅探與 `_ProvisionerMeta`，提供乾淨的公開/內部狀態存取函式（如 `get_dialects_map()`、`reset_linker_cache()`、`reset_worker_registry()`），並同步更新 [`tests/__init__.py`](https://drive.google.com/file/d/1ys-YR3yT0JIIUQizdz51AWLe0GYD-HHq/view?usp=drivesdk)。
    - **程式碼修改範例**：
      ```python
      # ast_engine/engine.py: 純化 get_persisted_meta 與 get_workspace_graph，遵守 CQS
      def get_persisted_meta(self) -> Optional[Dict[str, Any]]:
          with self._lock:
              if not self.symbols_index_path.exists():
                  return None
              try:
                  sym_st = self.symbols_index_path.stat()
                  if self._snapshot is not None and sym_st.st_mtime <= self._symbols_mtime:
                      return self._build_meta_payload(self._snapshot)
                  if self.meta_index_path.exists():
                      meta = json.loads(self.meta_index_path.read_text(encoding="utf-8"))
                      if (
                          isinstance(meta, dict)
                          and meta.get("symbols_mtime_ns") == int(sym_st.st_mtime_ns)
                          and meta.get("symbols_size") == int(sym_st.st_size)
                      ):
                          return meta
                  if self._ensure_symbols_loaded() and self._snapshot is not None:
                      return self._build_meta_payload(self._snapshot)
              except Exception as exc:
                  log_debug(f"get_persisted_meta fallback skipped: {exc}")
              return None
      ```

- [x] **[ARCH-03 / AUD-04] [🟠 P1 | C9.3 (A3) & C1.1 | All-OS] [`ast_engine/bundler.py:L279-L417`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk), [`ast_engine/engine.py:L210-L261`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/linker.py:L1252-L1309`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/parsers/base.py:L529-L530`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) - C# `partial` 跨檔聚合規則分裂於 4 個檔案 (Split-Brain SSOT)：`WorkspaceGraphLinker` Pass 1 漏檢查同組傳染與 `kind`/`spaces` 隔離，`convert_legacy_symbols_to_file_graph` 漏識別簽名中的 `partial`，且 `_sym_to_outline_node` 重複手寫 50 行聚合迴圈**
  - **問題座標與分類**：
    - [`ast_engine/bundler.py:L259-L417`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) (`_is_partial_symbol`, `aggregate_partial_symbols`)
    - [`ast_engine/engine.py:L115-L125`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`_cs_partial_type_key`) & [`ast_engine/engine.py:L210-L261`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`_sym_to_outline_node`)
    - [`ast_engine/linker.py:L1252-L1309`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) (`WorkspaceGraphLinker._run_pass1_global_indexing_and_folding`)
    - [`ast_engine/parsers/base.py:L529-L530`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) (`convert_legacy_symbols_to_file_graph`)
    - 維度：`C9.3 (A3 狀態真相分裂 Split-Brain SSOT)`、`C1.1 (雙軌邏輯失步)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **新舊軌 `partial` 判定與分組鍵不一致**：
       - 在 `bundler.py:L290-L337` 中，只要同一 `(sp_key, sym.kind, fqn_key)` 群組內**任一**分部帶有 `is_partial`（或簽名含 `\bpartial\s+(?:class|struct|interface|record)\b`），整組同名型別都會被聚合；
       - 但在 `WorkspaceGraphLinker._run_pass1_global_indexing_and_folding` ([`ast_engine/linker.py:L1273-L1274`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)) 中，卻只檢查單一節點自身的 `node.facets.get("is_partial") or "partial" in (node.facets.get("modifiers") or ())`，且分組鍵 `(node.language, node.fqn)` **沒有納入結構種類 (`class` vs `interface`) 與 `spaces`**！此外，在 `convert_legacy_symbols_to_file_graph` ([`ast_engine/parsers/base.py:L529`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk)) 中，只看 `if meta.get("is_partial"):` 而未檢查 `sym.signature` 中的 `partial` 關鍵字，導致透過自訂 Parser 或 legacy 路徑轉入的 `partial` 符號在 `WorkspaceSymbolGraph` 中完全不會被折疊！
    2. **`_sym_to_outline_node` 重複實作聚合邏輯**：在 [`ast_engine/engine.py:L210-L260`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 中，為了渲染 `outline` 的 `partial_siblings` 與 `merged=True` 成員，沒有複用 `bundler` 的聚合結果，而是自己重新遍歷 `snapshot.symbols`、比對 `partial_locations` 並呼叫 `_extract_unaggregated_partial_state`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：提取統一的 `is_partial_declaration(kind, signature, facets_or_meta)` 與分組鍵函式，在 `WorkspaceGraphLinker` Pass 1 中按 `(language, primary_type_kind, fqn)` 分組並支援「同組任一宣告為 `partial` 即折疊整組同型別節點」，同時讓 `_sym_to_outline_node` 複用統一輔助函式。
    - **程式碼修改範例**：
      ```python
      # ast_engine/linker.py: Pass 1 支援同組 partial 傳染與型別種類隔離
      type_container_kinds = ("class", "struct", "interface")
      candidates_by_key: Dict[Tuple[str, str, str], List[SymbolNode]] = defaultdict(list)
      for norm_path, fg in self._file_graphs.items():
          for node in self._nodes_by_file[norm_path]:
              t_kind = next((k for k in type_container_kinds if k in node.kinds), None)
              if t_kind and node.language in ("c_sharp", "csharp"):
                  candidates_by_key[(node.language, t_kind, node.fqn)].append(node)
              elif t_kind and (node.facets.get("is_partial") or "partial" in (node.facets.get("modifiers") or ())):
                  candidates_by_key[(node.language, t_kind, node.fqn)].append(node)

      for (lang, t_kind, fqn), c_nodes in sorted(candidates_by_key.items()):
          if len(c_nodes) > 1 and any(
              n.facets.get("is_partial")
              or "partial" in (n.facets.get("modifiers") or ())
              or bool(re.search(r"\bpartial\s+(?:class|struct|interface|record)\b", str(n.facets.get("signature") or "")))
              for n in c_nodes
          ):
              partial_buckets[(lang, fqn)] = c_nodes
      ```

- [x] **[AUD-05] [🟠 P1 | C2.2 (Tri-OS: Windows/macOS/Linux) & C4.1 | All-OS] [`ast_engine/io_utils.py:L31-L101`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk), [`ast_engine/engine.py:L1640-L1658`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - `atomic_save_gzip_pickle` 的 `finally` 區塊無差別 `glob` 誤刪併發寫入中之 `.tmp` 檔案；Windows 跨磁碟機相對路徑退化為純檔名引發 Canonical ID 碰撞；`_resolve_target_file` 多空間匹配未 `break` 外層迴圈導致子空間被覆蓋**
  - **問題座標與分類**：
    - [`ast_engine/io_utils.py:L87-L101`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk) (`atomic_save_gzip_pickle`)
    - [`ast_engine/io_utils.py:L31-L68`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk) (`compute_project_relpath`)
    - [`ast_engine/engine.py:L1640-L1658`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`ASTEngine._resolve_target_file`)
    - 維度：`C2.2 (三平台差異 Windows/macOS/Linux)`、`C4.1 (多進程/多執行緒檔案競態)`、`C1.1 (邏輯契約缺陷)` ｜ 平台：`All-OS (Windows 尤甚)`
  - **觸發情境與演進根因分析**：
    1. **`atomic_save_gzip_pickle` 無差別 `glob` 刪除競態 ([`ast_engine/io_utils.py:L87-L100`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk))**：
       - 第 87 行定義了 `tmp_path = p.with_name(f".{p.name}.tmp.{os.getpid()}")`，但第 89 行呼叫 `write_bytes(str(p), compressed, atomic=True)` 時，`core.vfs.write_bytes` 內部自己產生了暫存檔並執行 `os.replace`。
       - 第 90-100 行的 `finally:` 區塊在每次寫入結束後（包含正常成功時！），都會執行 `for leftover in p.parent.glob(f"*{p.name}*.tmp*"): leftover.unlink()`！若只有在寫入異常（`except Exception:`）時清理當前進程殘留檔才合理；在 `finally` 無條件掃描刪除所有 `*{p.name}*.tmp*`，一旦有併發呼叫端（如直接呼叫 `CallGraphIndex.save_binary` 或不同鎖範圍的進程/執行緒）正在寫入同名前綴的暫存檔，就會在 `os.replace` 前被無辜刪檔而拋出 `FileNotFoundError`！
    2. **Windows 跨磁碟機 `compute_project_relpath` 退化為純檔名 ([`ast_engine/io_utils.py:L45-L68`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk))**：在 Windows 下當外部空間檔案位於 `D:\ext_pkg\sub\mod.py` 而 `project_root` 位於 `C:\workspace` 時，`os.path.relpath` 拋出 `ValueError`；若 `fallback_base` 為 `None` 或同樣跨磁碟機，第 68 行直接回傳 `file_path.name`（`"mod.py"`），遺失所有父目錄資訊，導致 `D:\ext_pkg\a\mod.py` 與 `D:\ext_pkg\b\mod.py` 的 Canonical URI 碰撞為同一個 `mod.py::Foo`！
    3. **`_resolve_target_file` 空間歸屬被後續寬泛空間覆蓋 ([`ast_engine/engine.py:L1644-L1655`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk))**：內層 `for _, inc_root, exists in sp_cfg.resolve_entries(...)` 找到匹配後 `break`，但外層 `for sp_cfg in self.space_manager.list_spaces():` 繼續執行，也沒有選擇最長（最具體）的 `inc_root`，導致最後一個匹配的寬泛空間覆蓋了精確的子空間！
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `atomic_save_gzip_pickle` 中，僅在 `except BaseException:` 異常分支清理當前 PID 或失敗遺留的暫存檔，不在正常完成的 `finally` 中無差別 `glob` 刪除其他進程的 `.tmp` 檔。
      2. 在 `compute_project_relpath` 退無可退時，回傳正規化後的 POSIX 路徑（在 Windows 將 `D:\a\b.py` 轉為 `D/a/b.py` 或保留父目錄結構）而非僅回傳 `file_path.name`。
      3. 在 `_resolve_target_file` 中，挑選 `len(Path(inc_root).resolve().parts)` 最大（路徑最深、最精確）的匹配空間。
    - **程式碼修改範例**：
      ```python
      # ast_engine/io_utils.py: 僅於異常時清理當前進程殘留之 .tmp 檔
      def atomic_save_gzip_pickle(
          target_path: Union[str, Path],
          payload: Any,
          compresslevel: int = 1,
      ) -> Path:
          p = Path(target_path)
          p.parent.mkdir(parents=True, exist_ok=True)
          raw_pickle = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
          buf = io.BytesIO()
          with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=compresslevel) as gz:
              gz.write(raw_pickle)
          compressed = buf.getvalue()
          try:
              write_bytes(str(p), compressed, atomic=True)
          except BaseException:
              for leftover in p.parent.glob(f"*{p.name}*.tmp*"):
                  try:
                      leftover.unlink()
                  except OSError:
                      pass
              raise
          return p
      ```

- [x] **[AUD-06] [🟠 P1 | C4.1 & C9.1 (D2) & C9.2 (A2) | All-OS] [`scripts/hook.core.py:L15-L64`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk), [`scripts/hook.core.py:L238-L292`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk), [`ast_engine/engine.py:L895-L916`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk), [`ast_engine/engine.py:L1171-L1193`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - 游標消費與 ACK 邏輯在 4 處重複實作且行為分歧：單空間更新時誤呼叫 `ack(None)` 洗掉其他未更新空間的待處理游標，且 `hook.core.py` 漏檢查 `has_parseable` 導致純資料檔變更觸發無效重連與廣播風暴**
  - **問題座標與分類**：
    - [`scripts/hook.core.py:L54-L63`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk) (`_resolve_consume_diff`) & [`scripts/hook.core.py:L242-L292`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk) (`on_file_space_changed`)
    - [`ast_engine/engine.py:L895-L916`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`build_index`) & [`ast_engine/engine.py:L1171-L1193`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`hot_patch_index`)
    - 維度：`C4.1 (游標競爭與遺失)`、`C9.1 (D2 先寫後檢/過度 ACK)`、`C9.2 (A2 平行複製貼上)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **單空間更新誤呼叫 `ack(None)` 抹除其他空間之待處理變更**：
       - 在 [`scripts/hook.core.py:L54-L63`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk) 中，當 `space_name is not None`（例如 `on_file_space_changed` 僅針對 `"source"` 空間觸發）時，退出 `with` 後第 57 行竟呼叫 `scanner.ack(None, consumer_id="ast")`！這會把**所有其他空間（如 `"docs"`, `"plans"`）尚未被 `ast` 消費的增量游標全部強制推進到最新世代**，造成其他空間的變更事件永久遺失！
       - 同樣地，在 [`ast_engine/engine.py:L913-L914`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 與 [`L1190-L1191`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 中，當呼叫端指定 `spaces=["source"]` 執行局部空間建置或熱修補時，最後也呼叫了 `self.scanner.ack(None, consumer_id=self.CONSUMER_ID)`（只有在 `spaces is None` 即全目標空間同步時才可對齊全空間游標）。
    2. **`hook.core.py` 漏檢查 `has_parseable`**：
       - 在 `ensure_jit_synced` ([`ast_engine/engine.py:L1287-L1291`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)) 中，會先檢查 `has_parseable = any(self.parser_registry.get_parser(str(p)) is not None for p in all_dirty)`，若變更的只有 `.json` / `.txt` 等無 AST Parser 的檔案則直接略過 `hot_patch_index`。
       - 但在 [`scripts/hook.core.py:L279-L292`](https://drive.google.com/file/d/1ITL0uj-_2HgXiYpKK2bM6N028_SIkLRJ/view?usp=drivesdk) 中卻完全漏掉這道檢查，導致任何純配置檔或文字檔變更都會觸發 `engine.hot_patch_index()`，重跑 `WorkspaceGraphLinker`、遞增 `ast_generation`、重寫二進位索引並廣播 `on_ast_index_updated`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `ASTEngine` 抽取出統一的 `_align_consumer_cursors(spaces: Optional[List[str]])` 方法，僅當 `spaces is None` 且所有納管空間均已消費完畢時才對齊全空間游標；在 `hook.core.py` 中補齊 `has_parseable` 過濾（若無可解析檔案且無已索引檔案被刪除，僅推進游標並回傳 `status="noop"`，不遞增 `ast_generation`）。
    - **程式碼修改範例**：
      ```python
      # scripts/hook.core.py: 補齊 has_parseable 檢查，避免非 AST 檔案觸發無效熱修補與廣播
      all_dirty = set(diff_res.detail.dirty_files) | set(diff_res.detail.deleted)
      parser_reg = getattr(engine, "parser_registry", None)
      if parser_reg is not None and all_dirty:
          has_parseable = any(parser_reg.get_parser(str(p)) is not None for p in all_dirty)
          if not has_parseable:
              return {
                  "status": "noop",
                  "ast_generation": _get_current_ast_generation(engine),
                  "patched_count": 0,
                  "to_generation": diff_res.to_generation,
              }
      ```

### 🟡 P2 - Medium（防禦缺口與結構耦合：跨層反向依賴 / 雙重 SSOT / 字串與括號解析邊界漏洞 / 靜默吞錯）

- [x] **[AUD-07] [🟡 P2 | C8.1 & C8.3 & C9.1 (A1) | All-OS] [`ast_engine/parsers/treesitter.py:L1866-L1944`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk), [`ast_engine/parsers/markdown.py:L240-L323`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk), [`ast_engine/dialects/markdown.py:L90-L146`](https://drive.google.com/file/d/1mYClst7VJ0YrRvmo9VygJGkDTtDD1dGF/view?usp=drivesdk) - `TreeSitterDriver` 硬編碼 `language_name == "markdown"` 並反向匯入 `parsers/markdown.py` 私有正則，75 行 `documents` 邊提取迴圈重複複製貼上，且 `MarkdownParser` 產生重複的 `calls` 與 `documents` 邊**
  - **問題座標與分類**：
    - [`ast_engine/parsers/treesitter.py:L1866-L1944`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) (`TreeSitterDriver._extract_relation_edges`)
    - [`ast_engine/parsers/markdown.py:L240-L323`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk) (`MarkdownParser.extract_file_graph`)
    - [`ast_engine/dialects/markdown.py:L90-L146`](https://drive.google.com/file/d/1mYClst7VJ0YrRvmo9VygJGkDTtDD1dGF/view?usp=drivesdk) (`MarkdownDialect.extract_custom_call_sites`)
    - 維度：`C8.1 (正交職責混雜)`、`C8.3 (同構樣板重複)`、`C9.1 (A1 通用 Driver 硬編碼特定語言特例)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. `TreeSitterDriver` 設計為透過 `DialectAdapter` 隔離所有語言特例，但在 `_extract_relation_edges` ([`ast_engine/parsers/treesitter.py:L1867-L1944`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)) 中卻直接寫死 `if self.language_name == "markdown" and content: from .markdown import _FENCE_RE, _MD_BACKTICK_DOC_RE, _MD_LINK_DOC_RE`，並將 [`ast_engine/parsers/markdown.py:L263-L323`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk) 的 75 行逐行掃描邏輯完整複製貼上了一遍。
    2. 在 `MarkdownParser.extract_file_graph` ([`ast_engine/parsers/markdown.py:L240`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk)) 中，先呼叫 `super().extract_file_graph(...)`（透過 `MarkdownDialect.extract_custom_call_sites` 將 Markdown 連結與反引號轉為 `edge_kind="calls"` 的邊），接著又掃描一次全文將同一個連結與反引號轉為 `edge_kind="documents"` 的邊，造成同一處語法產生兩條不同種類的冗餘邊。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：將自訂關聯邊提取下沉至 `DialectAdapter.extract_custom_relation_edges(...)`（在 `MarkdownDialect` 實作唯一一份 `documents` 邊提取邏輯），由 `TreeSitterDriver` 與 `MarkdownParser` 統一委派呼叫，移除 `TreeSitterDriver` 對 `parsers/markdown.py` 的反向匯入與 75 行重複程式碼。

- [x] **[AUD-08] [🟡 P2 | C2.1 & C8.3 | All-OS] [`ast_engine/parsers/treesitter.py:L38-L390`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk), [`ast_engine/parsers/treesitter.py:L1677-L1710`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk), [`ast_engine/resolver.py:L83-L108`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) - `_extract_call_arg_count` 與 `_split_top_level_comma` 處理跳脫引號 `\"`、含逗號預設字串參數及比較運算子 `<` `>` 時算錯參數個數 (Arity)，且 352 行 `BUILTIN_QUERIES` 與 `assets/queries/*.scm` 雙重維護**
  - **問題座標與分類**：
    - [`ast_engine/parsers/treesitter.py:L1677-L1710`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) (`TreeSitterDriver._extract_call_arg_count`)
    - [`ast_engine/resolver.py:L83-L108`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`_split_top_level_comma`) & [`ast_engine/resolver.py:L129-L158`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`extract_signature_params`)
    - [`ast_engine/parsers/treesitter.py:L38-L390`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) (`BUILTIN_QUERIES`) vs. [`assets/queries/*.scm`](https://drive.google.com/file/d/15rmc9N2tpT10_U46Rr_8a0b553lm-1qB/view?usp=drivesdk)
    - 維度：`C2.1 (退化與邊界輸入解析缺陷)`、`C8.3 (重複樣板與雙重 SSOT)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`_split_top_level_comma` 未感知引號字串 ([`ast_engine/resolver.py:L90-L103`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk))**：當函式簽名含有帶逗號的預設字串參數（如 `def split_items(text: str, sep: str = ",", max_split: int = -1)`）時，`_split_top_level_comma` 沒有追蹤 `in_quote` 與跳脫字元 `\`，會直接將 `","` 拆成兩個 token，導致 `extract_signature_params` 算出的參數個數多 1，進而使方法重載 Arity 匹配失敗！
    2. **`_extract_call_arg_count` 未處理反斜線跳脫且誤將 `<` 當括號 ([`ast_engine/parsers/treesitter.py:L1695-L1707`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk))**：在呼叫點 `foo("a, \"b, c\"", x < y, z)` 中，① 遇到 `\"` 未處理反斜線跳脫，誤結束字串；② 遇到比較運算式 `x < y` 時，將 `<` 當成泛型左括號使 `depth += 1`，導致後續頂層逗號 `, z` 被忽略，算錯呼叫點 `arg_count`！
    3. **`BUILTIN_QUERIES` 與 `assets/queries/*.scm` 重複維護**：`treesitter.py:L38-L390` 硬編碼了與 `assets/queries/*.scm` 完全相同的 352 行查詢字串。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `_split_top_level_comma` 與 `_extract_call_arg_count` 中加入完整的引號狀態機（含 `\\` 跳脫字元處理），並在計算呼叫參數時僅對 `(`、`[`、`{` 增減深度（不對 `<` / `>` 無條件累加深度，避免將比較運算子 `<` 誤判為未閉合括號）。
      2. 將 `assets/queries/*.scm` 作為唯一真實來源（SSOT），`BUILTIN_QUERIES` 透過模組載入時按需讀取 `assets/queries/*.scm` 快取即可。
    - **程式碼修改範例**：
      ```python
      # ast_engine/resolver.py: 支援引號與反斜線跳脫的頂層逗號切分器
      def _split_top_level_comma(text: str, track_angles: bool = True) -> List[str]:
          if not text:
              return []
          parts: List[str] = []
          depth = 0
          current: List[str] = []
          in_quote: Optional[str] = None
          escaped = False
          open_chars = "<([{" if track_angles else "([{"
          close_chars = ">)]}" if track_angles else ")]}"
          for ch in text:
              if escaped:
                  current.append(ch)
                  escaped = False
                  continue
              if ch == "\\":
                  current.append(ch)
                  escaped = True
                  continue
              if in_quote:
                  if ch == in_quote:
                      in_quote = None
                  current.append(ch)
                  continue
              if ch in ("'", '"'):
                  in_quote = ch
                  current.append(ch)
              elif ch in open_chars:
                  depth += 1
                  current.append(ch)
              elif ch in close_chars:
                  depth = max(0, depth - 1)
                  current.append(ch)
              elif ch == "," and depth == 0:
                  tok = "".join(current).strip()
                  if tok:
                      parts.append(tok)
                  current = []
              else:
                  current.append(ch)
          tail = "".join(current).strip()
          if tail:
              parts.append(tail)
          return parts
      ```

- [x] **[AUD-09] [🟡 P2 | C3.1 & C1.1 | All-OS] [`ast_engine/parsers/registry.py:L461-L478`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk), [`ast_engine/schema.py:L1310-L1314`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk), [`ast_engine/graph.py:L326-L330`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk) - `ParserRegistry._matches_configured_spaces` 寫死呼叫全域 `get_default_registry()` 忽略 `ASTEngine` 實例之 `space_manager`，且 `ASTSnapshot.from_dict` / `CallGraphIndex.from_dict` 靜默吞掉損毀的圖譜結構**
  - **問題座標與分類**：
    - [`ast_engine/parsers/registry.py:L461-L478`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) (`ParserRegistry._matches_configured_spaces`)
    - [`ast_engine/schema.py:L1310-L1314`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk) (`ASTSnapshot.from_dict`)
    - [`ast_engine/graph.py:L326-L330`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk) (`CallGraphIndex.from_dict`)
    - 維度：`C1.1 (實例上下文不一致)`、`C3.1 (破壞性靜默吞錯)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. 當 `ASTEngine(project_root=custom_root, custom_spaces=...)` 建立自訂 `self.space_manager` 時，`self.parser_registry` 並未綁定該 `self.space_manager`。一旦某個語言解析器設定了 `spaces` 限制，`_matches_configured_spaces` ([`ast_engine/parsers/registry.py:L472`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk)) 是 `@staticmethod`，每次都呼叫 `get_default_registry()` 取全域預設空間註冊表比對，不僅在迴圈內重複查詢，更導致自訂 `project_root` / `custom_spaces` 下的空間匹配完全失效。
    2. 在 `ASTSnapshot.from_dict` ([`ast_engine/schema.py:L1310-L1314`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk)) 與 `CallGraphIndex.from_dict` ([`ast_engine/graph.py:L326-L330`](https://drive.google.com/file/d/1xAhQqn8Vjb1pEW3zY_BGt6b5dOjXze7p/view?usp=drivesdk)) 中，對 `FileSymbolGraph.from_dict` 與 `WorkspaceSymbolGraph.from_dict` 使用了 `except Exception: pass` / `ws_graph = None`，將結構損毀靜默吞掉，而非讓 `SchemaValidationError` 向上冒泡觸發 `ensure_jit_synced` 的自動重建。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `ParserRegistry.__init__` 支援注入 `space_manager: Optional[SpaceRegistry] = None`（並在 `ASTEngine.__init__` 傳入 `space_manager=self.space_manager`），由 `self._space_manager or get_default_registry()` 執行 `match_path`；同時在 `ASTSnapshot.from_dict` 與 `CallGraphIndex.from_dict` 中讓 `SchemaValidationError` 正常拋出（或記錄警告並標記快照無效以觸發自癒重建）。

### 🔵 P3 - Optimization（效能加速與無損結構打磨）

- [x] **[AUD-10] [🔵 P3 | C7.1 | All-OS] [`ast_engine/linker.py:L64-L69`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/linker.py:L793-L802`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk), [`ast_engine/resolver.py:L823-L829`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk), [`ast_engine/resolver.py:L960-L962`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) - 每次執行 `callers` / `callees` / `impact` 查詢時重複對全倉 `symbols_map` 執行 2 次 $O(N)$ 指紋雜湊掃描，且 `_expand_contract_from_workspace_graph` 每次呼叫皆全表掃描 `nodes_by_id` 重建型別成員索引**
  - **問題座標與分類**：
    - [`ast_engine/linker.py:L64-L69`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) (`_compute_symbols_map_fingerprint`) & [`ast_engine/linker.py:L793-L802`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) (`_expand_contract_from_workspace_graph`)
    - [`ast_engine/resolver.py:L823-L829`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`_get_or_create_resolver`) & [`ast_engine/resolver.py:L960-L962`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)
    - 維度：`C7.1 (高頻查詢路徑重複 $O(N)$ 全表掃描)` ｜ 平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. 每次呼叫 `query_callers` / `query_callees` / `query_impact` 時，`_get_or_create_resolver` ([`ast_engine/resolver.py:L824`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)) 先跑一次 `_compute_symbols_map_fingerprint(symbols_map)` 對全倉數萬個 `UnifiedSymbol` 計算 `hash(...)`；緊接著 `expand_contract_symbol_ids` ([`ast_engine/linker.py:L914`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)) 又再跑一次 `_compute_symbols_map_fingerprint(sym_dict)`！當傳入的是 `ASTSnapshot`（或來自 `engine` 的快照）時，`ast_generation` 本身已是單調遞增的世代水位，卻沒有利用 `(id(snapshot), snapshot.ast_generation)` 做 $O(1)$ 快取命中判斷。
    2. `_expand_contract_from_workspace_graph` ([`ast_engine/linker.py:L794-L802`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)) 每次被呼叫時，都會全表遍歷 `ws_graph.nodes_by_id` 重建 `members_by_type_id` 與 `type_id_by_file_and_scope`，而 `WorkspaceSymbolGraph` 本身是 `frozen=True` 的不可變物件，完全可以在 `WorkspaceSymbolGraph.__post_init__` 或綁定 `id(ws_graph)` 快取預先建好。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `ASTSnapshot` 上快取 `_symbols_fingerprint`（當 `symbols` 內容未變時 $O(1)$ 讀取），並在 `WorkspaceSymbolGraph` 內部預先建立或快取 `type_id_by_file_and_scope` 與 `members_by_type_id` 映射。

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

- **[RFP-01] [`ast_engine/__init__.py:L163-L171`](https://drive.google.com/file/d/1kHv49lpzfJ4UAKrc0D0YKRnbyDpxX17y/view?usp=drivesdk) 頂層套件 PEP 562 `__getattr__` 延遲匯入**：
  - 初看疑似 `D5` PEP 562 逃逸補丁，但經查證該處為標準頂層模組 Lazy Export Table (`_LAZY_EXPORTS`)，目的是避免 `import ast_engine` 時在頂層無條件載入 `tree_sitter` 與 `networkx`，且不涉及可變全域狀態鏡像，屬合理的 `C7.3` 冷啟動加速設計（By Design）。
- **[RFP-02] [`ast_engine/provisioner.py:L178-L194`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) `GrammarProvisioner._try_pip_install` 子進程呼叫與鎖隔離**：
  - 初看疑似 `C5.1` / `C4.3` 持鎖執行外部 `pip install` 阻塞或污染 `--json` stdout，但經查證其 `stdout=sys.stderr, stderr=sys.stderr` 已嚴格將輸出重導向至 `stderr`、設有 `timeout=30`，且 `load_language` 採用每個 `cache_key` 獨立之 `threading.Event` single-flight 機制並於呼叫 `_try_pip_install` 前釋放 `cls._LOCK`，不會阻塞已快取語言之併發解析。
- **[RFP-03] [`ast_engine/parsers/python_ast.py:L16-L36`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk) `_load_stdlib_ast` 動態載入標準庫 `ast.py`**：
  - 初看疑似繞過標準匯入機制，但因本模組目錄名為 `ast`，當 `sys.path` 包含 `source/ast` 父目錄時可能與 Python 標準庫 `ast` 發生命名衝突，透過 `sysconfig.get_path("stdlib")` 載入標準庫 `ast.py` 屬於必要的防禦性隔離。


---

## Part V — Group E：`dev` 與 `vscode-support` 模組（靜態檢查、打包發布、測試沙盒與 IDE 投影）

# 🛡️ YS-Codebase (`dev` & `vscode-support`) 第二次九維度單點序列深度審計與架構整理報告 (Round 2 Codebase Deep Audit — Group E)

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：`ys_codebase/source/dev` 與 `ys_codebase/source/vscode-support` 全模組原始碼、CLI 腳本、Lifecycle Hooks 與 Contributes 契約（共劃分為 **4 個獨立審查單元 `Unit 01` ~ `Unit 04`**，已完成 100% 逐檔逐行序列深潛、跨模組 `core` 上下游呼叫鏈核對與三步反向查證）
- **目標語言與平台基準**：語言 `Python 3.10+ (100% Standard Library)` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS / Win32) + macOS (APFS / Darwin)` ｜ 架構重構尺度 `Mode B 外圍契約相容 + Mode A 內部根因收斂`
- **診斷統計總覽**：🔴 **P0 (Critical)**：`2` 項 ｜ 🟠 **P1 (High)**：`6` 項 ｜ 🟡 **P2 (Medium)**：`6` 項 ｜ 🔵 **P3 (Optimization)**：`4` 項（共 **18 項確認問題**，並已透過三步反向查證排除假陽性與刻意設計 **5 項**）

| 審查單元 (Audit Unit) | 涵蓋檔案（附 Google Drive 連結） | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`**<br/>`dev` 靜態檢查器與鷹架 | • [`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)<br/>• [`dev/dev/scaffold.py`](https://drive.google.com/file/d/1rOtRBXNSVjnOJj6h9EzqflAGTQrHa-Qs/view?usp=drivesdk)<br/>• [`dev/dev/__init__.py`](https://drive.google.com/file/d/1ZtlS-vyLaWmWQkW5TacXtmoNAx6jrPXp/view?usp=drivesdk) | `DEV-P2-01`, `DEV-P2-02`, `DEV-P2-03`, `DEV-P3-01` | 🟡 結構耦合與守衛盲區 |
| **`Unit 02`**<br/>`dev` 打包、發布、測試協調與 CLI | • [`dev/dev/builder.py`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk)<br/>• [`dev/dev/releaser.py`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk)<br/>• [`dev/dev/tester.py`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)<br/>• [`dev/scripts/cli.py`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk)<br/>• [`dev/contributes/core.json`](https://drive.google.com/file/d/1eIQNf1f1qL1Rim2YdwA8gBaQ0fKxsjd-/view?usp=drivesdk)<br/>• [`dev/contributes/agents-workflow.json`](https://drive.google.com/file/d/1yUEypmWTmHUo4LGvNBdi3dNiH3IHMtg5/view?usp=drivesdk)<br/>• [`dev/manifest.json`](https://drive.google.com/file/d/19xr2nZZNxLoGbXhjHgXaOcMo6FwL4aaA/view?usp=drivesdk) | `DEV-P0-01`, `DEV-P0-02`, `DEV-P1-01`, `DEV-P1-02`, `DEV-P1-03`, `DEV-P2-03`, `DEV-P3-02` | 🔴 具高危狀態污染與雙軌債 |
| **`Unit 03`**<br/>`dev/testing` 測試執行器與沙盒框架 | • [`dev/dev/testing/__init__.py`](https://drive.google.com/file/d/1OC51pNcuArpYSqGAwB9sTXjzsK0d0Haz/view?usp=drivesdk)<br/>• [`dev/dev/testing/runner.py`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk)<br/>• [`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)<br/>• [`dev/dev/testing/case.py`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk)<br/>• [`dev/dev/testing/contract.py`](https://drive.google.com/file/d/1JnpafFWQaIi6mCKDQ3q9f_5ycbs-5Zuq/view?usp=drivesdk)<br/>• [`dev/dev/testing/requirement.py`](https://drive.google.com/file/d/1pXy8xwVUubPujStb718UaZmL0tFrwwxF/view?usp=drivesdk) | `DEV-P0-02`, `DEV-P1-04`, `VSC-P1-01`, `DEV-P2-03`, `DEV-P2-04`, `DEV-P3-02` | 🔴 具併發誤刪與 Metaclass 債 |
| **`Unit 04`**<br/>`vscode-support` 全模組 | • [`vscode-support/vscode_support/__init__.py`](https://drive.google.com/file/d/1DkCuXFsqZiBdHCM5RxgkQ_EvSA_AFrOA/view?usp=drivesdk)<br/>• [`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)<br/>• [`vscode-support/vscode_support/schema_compiler.py`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk)<br/>• [`vscode-support/scripts/cli.py`](https://drive.google.com/file/d/1DiQPhMjkgeoKAXGiXAG7fW52fSSrWuBg/view?usp=drivesdk)<br/>• [`vscode-support/scripts/hook.core.py`](https://drive.google.com/file/d/1jsdmXg7jeIZFlO-d-_2I-OhnBd1nH5cT/view?usp=drivesdk)<br/>• [`vscode-support/scripts/hook.dev.py`](https://drive.google.com/file/d/156PQZgP8TxYPkJD99NHVp_y1j5qoKVuJ/view?usp=drivesdk)<br/>• [`vscode-support/contributes/_format.json`](https://drive.google.com/file/d/1bYGtmwuDWIGV_W6OP7Sa6AAu7J8xe2tY/view?usp=drivesdk)<br/>• [`vscode-support/contributes/core.json`](https://drive.google.com/file/d/13tINeP_eL-jnAb7QdKTLffF-9GNnFaRg/view?usp=drivesdk)<br/>• [`vscode-support/contributes/vscode-support.json`](https://drive.google.com/file/d/1r3G5WhFdUKRbroZ88ixy9quGw4Qnb_MH/view?usp=drivesdk)<br/>• [`vscode-support/contributes/agents-workflow.json`](https://drive.google.com/file/d/1SYKrDE7Qo31iDbHIxf1qCB-dO3drxY5r/view?usp=drivesdk)<br/>• [`vscode-support/manifest.json`](https://drive.google.com/file/d/1DjP0sJ4YXhJUr072IRBUooB9mjwz2KzV/view?usp=drivesdk) | `VSC-P1-01`, `VSC-P1-02`, `VSC-P2-01`, `VSC-P2-02`, `VSC-P3-01`, `VSC-P3-02` | 🟠 具跨平台路徑與契約漂移 |

---

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S6)

針對第一輪修復後浮現的跨檔案結構性技術債（`C9`: `A1~A5` & `D1~D5`），以下提煉出 **6 項 Mode A 根因重構手術藍圖**，從源頭消滅平行複製貼上、雙軌契約分裂與測試逃逸補丁：

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **確定性歸檔、安全解壓與跨平台目錄連結基建單一化 (`core` <-> `dev` / `vscode-support` 雙軌退役)** | `DEV-P1-01`, `DEV-P2-04` | `C9.2 (A2)`<br/>`C2.2`<br/>`C6.1` | • **問題病根**：[`dev/dev/builder.py`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk) 與 [`core/core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 各自維護一套確定性 Zip 打包器、SHA-256 計算器與 `.yscbignore` 匹配器且規則已漂移；[`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 又自建一套缺損的 `_safe_extract_zip` 與 `_project_venv`（未對齊 [`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) 的三級目錄連結降級鏈）。<br/>• **根因手術**：將確定性 Zip 封裝、`_extract_zip_safely`（含 `testzip()` 與 Windows 磁碟機路徑防禦）、以及跨平台目錄 Symlink/Junction 建立與安全解除（`os.symlink -> _winapi.CreateJunction -> cmd /c mklink /J` + `_safe_remove_link`）統一收斂為 `core` 標準原語，由 `Builder`、`SandboxProvisioner` 與 `SettingsProjector` 直接委派調用，徹底刪除 `dev` 與 `vscode-support` 中的平行重複實作。 |
| **`S2`** | **`CmdBags` 原生直通架構與三處手寫 `while` CLI 解析迴圈廢除** | `DEV-P1-03`, `DEV-P2-03` | `C9.1 (A1)`<br/>`C9.2 (A2/D5)` | • **問題病根**：[`dev/scripts/cli.py`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk) 將 `core.commands` 已解析好的強型別 `CmdBags` 透過 `_build_tester_argv` 逆向展開回 `List[str]`，再交由 [`dev/dev/tester.py`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) 的 `_parse_test_run_config` 與 `_run_op_test` 執行兩輪手寫 `while idx < len(argv):` 重解析；同時 `cli.py` 仍內嵌 `_handle_bump` 版本遞增與 `__init__.py` Regex 改寫業務邏輯。<br/>• **根因手術**：① 新增 `Tester.run_from_bags(subcmd: str, bags: CmdBags) -> int` 直接消費強型別 `CmdBags`，將 `Tester.run(argv)` 降級為純薄層轉發（透過單一正規化函式轉為 `CmdBags`），徹底刪除 3 處重複的 `while` 狀態機；② 將 `_handle_bump` 與 `_sync_package_dunder_version` 遷入 `Releaser.bump_module_version()`，讓 `dev/scripts/cli.py` 回歸 100% 純路由層。 |
| **`S3`** | **測試框架執行期狀態純化、循環依賴解耦與 Mock 嗅探補丁拔除** | `DEV-P1-03`, `DEV-P1-04` | `C9.2 (D5)`<br/>`C9.3 (A3)`<br/>`C8.2` | • **問題病根**：① [`dev/dev/tester.py:L27`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) 殘留 `_ORIG_SUBPROCESS_RUN = subprocess.run` 嗅探 `unittest.mock`；② [`dev/dev/testing/sandbox.py:L152`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 以 `_SandboxStateMeta` Metaclass 規避 `[C9]` 檢查；③ [`dev/dev/testing/case.py:L44`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk) (`_shared_sandbox_ctx`) 與 [`dev/dev/testing/runner.py:L347`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk) (`OutputCapturer._ACTIVE_INSTANCE`) 直接使用類別可變單例並造成 `case.py <-> runner.py` 雙向循環匯入。<br/>• **根因手術**：① 移除 `_ORIG_SUBPROCESS_RUN` 嗅探，統一透過可注入之執行器或 `run_subprocess_with_tree_timeout` 執行；② 廢除 `_SandboxStateMeta` Metaclass，並將 `shared_sandbox_ctx` 與 `active_output_capturer` 統一收斂至 `core.context.get_runtime_context()`，消除 `case.py` 對 `runner.OutputCapturer` 的反向依賴。 |
| **`S4`** | **發布與建置管線之兩階段原子交易收斂 (`Builder` & `Releaser` Two-Phase Commit)** | `DEV-P0-01`, `DEV-P0-02`, `DEV-P1-02`, `VSC-P2-01` | `C9.1 (D2)`<br/>`C3.2`<br/>`C4.1` | • **問題病根**：`Releaser.release_git` 在測試與預檢前先改寫磁碟 `manifest.json`、失敗時漏回滾、且執行全倉 `git add -A`；`Builder._build_module_impl` 在新包產出前先清空 `build/<mod>/`；`Builder._update_release_index` 在 `index.json` 寫入前先刪除舊 `.zip` 且被幽靈版本擠佔窗口；`SettingsProjector.revert_vscode_settings` 在 `settings.json` 寫盤前先刪除 `schemas/`。<br/>• **根因手術**：全面貫徹「先驗證/先產出新檔 -> 原子切換索引/設定 -> 最後清理淘汰舊檔」的兩階段交易順序，並為 `release_module` / `release_git` 加上 `try...except/finally` 強制快照回滾與模組路徑限定之 `git add`。 |
| **`S5`** | **`Checker` 靜態合規引擎模組化拆解與 `manifest.json` 單一 Schema 真相收斂** | `VSC-P1-02`, `DEV-P2-01`, `DEV-P2-02`, `DEV-P3-01` | `C9.1 (A1)`<br/>`C9.3 (A3)`<br/>`C1.2`<br/>`C7.1` | • **問題病根**：[`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) 單檔膨脹至 2,059 行、硬編碼 `"server"` 業務模組豁免、單次檢查重複 `os.walk` 3 次，且與 [`vscode-support/vscode_support/schema_compiler.py`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk) 各自維護互相矛盾的 `manifest.json` 欄位與枚舉規則。<br/>• **根因手術**：① 將 `manifest.json` 必填欄位、型別與 `release.type` (`feature/bugfix/hotfix/refactor/security/docs`) / `release.urgency` (`optional/low/normal/recommended/high/critical`) 枚舉收斂為單一契約常數；② 將 `checker.py` 拆分為模型層、AST 守衛層與結構檢核層，改以單次 `os.walk` 掃描並支援在模組 `manifest.json` 宣告受控架構豁免。 |
| **`S6`** | **模組鷹架模板單一來源化 (`Scaffolder` / `SandboxContext` / `YSCBTestCase`) 與空殼 Hook 清理** | `DEV-P2-03`, `VSC-P2-02` | `C9.2 (A2)`<br/>`C9.3 (A5)` | • **問題病根**：[`dev/dev/scaffold.py`](https://drive.google.com/file/d/1rOtRBXNSVjnOJj6h9EzqflAGTQrHa-Qs/view?usp=drivesdk)、[`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 與 [`dev/dev/testing/case.py`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk) 各自硬編碼一套模組骨架檔案字串；[`vscode-support/scripts/hook.dev.py`](https://drive.google.com/file/d/156PQZgP8TxYPkJD99NHVp_y1j5qoKVuJ/view?usp=drivesdk) 為無實質邏輯的空殼檔案。<br/>• **根因手術**：在 `dev/dev/scaffold.py` 提煉純函式 `build_module_skeleton_files(name, version, description, deps)` 供生產鷹架與測試 Mock 套件共用，並為 `Scaffolder.create_module` 加上異常清理回滾；移除或精簡無效的空殼 Hook。 |

---

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：版本控制污染 / 跨進程誤刪沙盒 / 預檢失敗髒狀態殘留）

- [x] **[DEV-P0-01] [🔴 P0 | C6.2 & C1.1 (D2) & C3.2 | All-OS] [`dev/dev/releaser.py:L263-L300`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk) & [`dev/dev/releaser.py:L378-L447`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk) - `Releaser.release_git` 無差別執行全倉 `git add -A` 污染提交邊界，且在測試與預檢前過早改寫 `manifest.json` 並於異常或 Git 失敗時漏回滾**
  - **問題座標與分類**：[`dev/dev/releaser.py`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk)（`Releaser.release_module` `L263-L300`、`Releaser.release_git` `L378-L447`）｜ `C6.2` 外部命令邊界、`C1.1 (D2)` 先寫後檢、`C3.2` 異常資源回滾 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **全倉 `git add -A` 越界提交 (`L432`)**：`dev release-git <module_name> "<msg>"` 的職責是發布並提交單一模組 `<module_name>`。然而 `L432` 在 `yscb://` 根目錄執行 `self._run_git_cmd(["add", "-A"])`，若開發者在工作區其他模組（如 `source/other_mod/`、`config/`）有尚未提交的半成品修改或臨時檔案，會被無預警一併綁入 `<module_name>/v<ver>` 的 Commit 與 Tag 中。
    2. **先寫後檢與 Smart-Skip 狀態分裂 (`L380-L413`)**：`release_git` 在 `L380` 立即呼叫 `_apply_release_meta_to_source_manifest` 改寫 `source/<mod>/manifest.json`，隨後才執行 `tester.run(["test", module_name])` (`L404`)。更嚴重的是，若目標版本已發布且未帶 `--force`（`is_already_released and not force`, `L410`），`L380` 已經改寫了 `source/<mod>/manifest.json` 的 `release` 欄位，但 `L410` 卻跳過打包與 `index.json` 更新，導致 `source/<mod>/manifest.json` 與 `release/<mod>/<ver>.zip` 內容不一致。
    3. **異常與 Git 失敗分支漏回滾 (`L273-L300`, `L404-L445`)**：
       - 在 `release_git` 中，若 `tester.run` 拋出未捕獲例外/中斷，或 Step 4 的 `git add` (`L434`)、`git commit` (`L440`)、`git tag` (`L445`) 失敗返回 `False` 時，皆未呼叫 `self._restore_manifest_text(manifest_uri, orig_manifest_text)`。
       - 在 `release_module` (`L272-L300`) 中，寫入 `release_meta` 後若 `release_check` 或 `package_release` 拋出例外，同樣缺少 `try...except` 回滾保護。
  - **建議解決方案（Recommended Solution - Mode A 兩階段提交與路徑收斂）**：
    - **修改思路**：
      1. 在 `release_module` 與 `release_git` 中使用 `committed = False` + `try...finally` 確保任何提前返回或未預期異常皆自動還原 `orig_manifest_text`。
      2. 在 `release_git` 中，僅當需要實際打包（`not is_already_released or force`）且通過 Step 1 (`tester.run`) 後，才套用 `release_meta` 並執行 `release_check` 與 `release_module`。
      3. 將 `git add` 範圍從全倉 `["add", "-A"]` 收斂為目標模組相關路徑 `["add", "--", f"source/{module_name}", f"release/{module_name}"]`（若路徑存在；若在模擬測試環境下目錄不在 git worktree 內則安全回退）。
    - **程式碼修改範例**：
      ```python
      # dev/dev/releaser.py (Releaser.release_module & Releaser.release_git 關鍵片段)
      manifest_uri = f"module.source://{module_name}/manifest.json"
      orig_manifest_text = self._snapshot_manifest_text(manifest_uri) if release_meta else None
      manifest_mutated = False
      committed = False
      try:
          # Step 1: E2E Test first BEFORE mutating manifest.json on disk
          tester = self.tester or Tester()
          if tester.run(["test", module_name]) != 0:
              return False, f"Step 1 Failed: E2E test failed for module '{module_name}'. Release aborted."

          if is_already_released and not force:
              from core.log import log
              log(f"[dev:release-git] Target version '{module_name}@{ver}' is already released ({exact_rel_zip}). Skipping packaging step.")
          else:
              if release_meta:
                  ok_meta, err_meta = self._apply_release_meta_to_source_manifest(module_name, release_meta)
                  if not ok_meta:
                      return False, err_meta
                  manifest_mutated = True
              passed, chk_errors = self.release_check(module_name, force=force)
              if not passed:
                  err_details = "\n  - ".join(chk_errors)
                  return False, f"Step 2 Failed: Release readiness check failed for '{module_name}':\n  - {err_details}"
              ok_pkg, msg_pkg = self.release_module(module_name, force=force, _skip_check=True)
              if not ok_pkg:
                  return False, f"Step 3 Failed: Release packaging failed for '{module_name}': {msg_pkg}"
          ...
          committed = True
          return True, f"Successfully processed '{module_name}@{ver}' and updated local Git commit & tag '{tag_name}'."
      finally:
          if manifest_mutated and not committed:
              self._restore_manifest_text(manifest_uri, orig_manifest_text)
      ```

- [x] **[DEV-P0-02] [🔴 P0 | C4.1 & C3.2 | All-OS] [`dev/dev/tester.py:L689-L695`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)、[`dev/dev/tester.py:L856-L860`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) & [`dev/dev/testing/sandbox.py:L231-L247`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) - `Tester` 執行 `--all` 結束時呼叫全域 `cleanup_all_sandboxes()`，且 `_sweep_sandboxes` 在 `max_keep=None` 時漏保護 `YSCB_SANDBOX_DIR` 並跨進程誤刪活躍沙盒**
  - **問題座標與分類**：[`dev/dev/tester.py`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)（`_run_test` `L689-L695`、`_run_parallel_test` `L856-L860`）與 [`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)（`_sweep_sandboxes` `L231-L247`）｜ `C4.1` 多進程競態誤刪、`C3.2` 資源生命週期 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. 在 [`dev/dev/testing/sandbox.py:L235-L240`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 中，`_sweep_sandboxes` 僅在 `if max_keep is not None:` 時才將 `os.environ.get("YSCB_SANDBOX_DIR")` 加入 `exclude_set`。當 `cleanup_all_sandboxes()` 傳入 `max_keep=None` 時，若在子進程中呼叫（此時子進程之 `_ACTIVE_SANDBOXES` 為空），連當前自身所在的 `YSCB_SANDBOX_DIR` 都不在 `exclude_set` 中！
    2. 在 [`dev/dev/tester.py:L899-L902`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) 中，每個平行 Worker 完成單一模組測試後，已經各自呼叫 `SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)` 清理了自己的沙盒；然而 `L856-L858`（以及單進程 `L692-L693`）卻在 `--all` 結束時額外呼叫 `SandboxProvisioner.cleanup_all_sandboxes()`，無差別清空整個 `cache://dev/sandbox/` 下所有目錄，導致另一並行終端機正在執行的測試沙盒直接被刪除而崩潰。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 [`dev/dev/testing/sandbox.py:L235-L240`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 的 `_sweep_sandboxes` 中，**無條件**（移除 `if max_keep is not None:` 限制）將 `os.environ.get("YSCB_SANDBOX_DIR")` 的 `abspath`、`realpath` 與 `basename` 加入 `exclude_set`，確保任何掃除操作絕不誤刪當前活躍沙盒。
      2. 在 [`dev/dev/tester.py:L856-L859`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) 中，先清理本次 `worker_results` 實際建立的 `sandbox_dir`，並對歷史遺留沙盒改用受保護的清理邏輯。
    - **程式碼修改範例**：
      ```python
      # dev/dev/testing/sandbox.py (_sweep_sandboxes L231-L241)
      exclude_set = set(exclude or [])
      for active_p in list(SandboxProvisioner._ACTIVE_SANDBOXES):
          exclude_set.add(active_p)
          exclude_set.add(os.path.realpath(active_p))
          exclude_set.add(os.path.basename(active_p))
      active_sb_env = os.environ.get("YSCB_SANDBOX_DIR")
      if active_sb_env:
          abs_env = os.path.abspath(active_sb_env)
          exclude_set.add(abs_env)
          exclude_set.add(os.path.realpath(abs_env))
          exclude_set.add(os.path.basename(abs_env))
      ```

---

### 🟠 P1 - High（顯著缺陷：跨平台必爆 / 雙軌狀態失步 / 平行實作分歧 / 測試逃逸補丁）

- [x] **[DEV-P1-01] [🟠 P1 | C9.2 (A2) & C1.1 | All-OS] [`dev/dev/builder.py:L22-L148`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk) vs [`core/core/engine.py:L38-L50`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk)、[`core/core/engine.py:L81-L94`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk)、[`core/core/engine.py:L133-L261`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) - `Builder` 與 `core.engine` 各自維護平行 Zip 打包與忽略規則實作，且 `_should_ignore` 萬用字元截斷存在誤殺漏洞**
  - **問題座標與分類**：[`dev/dev/builder.py`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk)（`compute_file_sha256` `L22-L31`、`_should_ignore` `L56-L76`、`_is_text_archive_entry` `L85-L87`、`_create_module_archive_atomic` `L90-L148`）與 [`core/core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk)（`L38-L50`, `L81-L94`, `L133-L261`）｜ `C9.2 (A2)` 平行實作、`C1.1` 雙軌邏輯漂移 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. `dev/dev/builder.py` 與 `core/core/engine.py` 複製貼上了幾乎相同的確定性 Zip 打包管線（固定時間戳 `(2020, 1, 1, 0, 0, 0)`、固定權限 `0o644`、`manifest.json` 版本號覆寫、文字檔 CRLF 轉 LF、`.tmp` 原子替換）與 `compute_file_sha256`。
    2. 兩套平行實作已出現多處分歧：
       - `builder.py:L87` 的 `_is_text_archive_entry` 使用區分大小寫的 `rel_file.endswith(_TEXT_EXTENSIONS)`，而 `engine.py:L178` 使用 `ext.lower() in _TEXT_NORMALIZE_EXTS`。
       - `builder.py:L66-L75` 的 `_should_ignore` 將 `pat` 執行 `pat_prefix = pat.rstrip("*").rstrip("/")`，再判斷 `(pat_prefix and norm_rel.startswith(pat_prefix + "/")) or (pat_prefix and f"/{pat_prefix}/" in f"/{norm_rel}/")`。一旦 `.yscbignore` 寫入如 `sub/test*` 的萬用字元規則，`pat_prefix` 會變成 `sub/test`，只有當不含萬用字元時才應視為目錄前綴！若寫入 `docs/v1*`，`pat_prefix` 變成 `docs/v1`，會誤將目錄 `other/docs/v1/main.py` 視為匹配。
  - **建議解決方案（Recommended Solution - Mode A 統一委派 `core.engine`）**：
    - **修改思路**：
      1. 在 `builder.py` 中直接匯入並復用 `core.engine.compute_file_sha256`（或提取共用打包原語）。
      2. 修正 `_should_ignore` 中的 `pat_prefix` 邏輯：僅當 `pat` 不含中間萬用字元（或僅以 `/*` / `/**` / `/` 結尾）時才提取目錄前綴 `dir_prefix`，避免將 `foo/bar*` 截斷為目錄名 `foo/bar`；並將 `_is_text_archive_entry` 改為 `rel_file.lower().endswith(_TEXT_EXTENSIONS)`。
    - **程式碼修改範例**：
      ```python
      # dev/dev/builder.py (_should_ignore & _is_text_archive_entry 修正)
      def _should_ignore(rel_path: str, ignores: Any) -> bool:
          norm_rel = rel_path.replace("\\", "/").strip("/")
          if not norm_rel:
              return False
          name = os.path.basename(norm_rel)
          parts = norm_rel.split("/")
          for pattern in ignores:
              pat = pattern.replace("\\", "/").strip("/")
              if not pat:
                  continue
              dir_prefix = pat[:-3].rstrip("/") if pat.endswith("/**") else (
                  pat[:-2].rstrip("/") if pat.endswith("/*") else (pat if ("*" not in pat and "?" not in pat) else "")
              )
              if (
                  fnmatch.fnmatch(name, pat)
                  or fnmatch.fnmatch(norm_rel, pat)
                  or fnmatch.fnmatch(norm_rel, pat + "/*")
                  or (dir_prefix and norm_rel.startswith(dir_prefix + "/"))
                  or (dir_prefix and f"/{dir_prefix}/" in f"/{norm_rel}/")
                  or ("/" not in pat and any(fnmatch.fnmatch(p, pat) for p in parts))
              ):
                  return True
          return False

      def _is_text_archive_entry(rel_file: str) -> bool:
          base = os.path.basename(rel_file)
          return rel_file.lower().endswith(_TEXT_EXTENSIONS) or base in _TEXT_BASENAMES
      ```

- [x] **[DEV-P1-02] [🟠 P1 | C1.1 & C3.2 (D2) | All-OS] [`dev/dev/builder.py:L221-L340`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk) & [`dev/dev/builder.py:L372-L394`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk) - `Builder` 在新包完成前提前刪除舊產物，且 `_update_release_index` 被 `index.json` 幽靈版本擠佔滑動窗口並誤刪實體 `.zip`**
  - **問題座標與分類**：[`dev/dev/builder.py`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk)（`_update_release_index` `L221-L340`、`_build_module_impl` `L372-L394`）｜ `C1.1` 狀態失步、`C3.2 (D2)` 非原子清理 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`_build_module_impl` 先刪後建 (`L372-L385`)**：當 `clean=True` 時，`L372-L381` 先將 `build/<name>/` 目錄下所有檔案（含舊 `.zip` 與 `index.json`）刪除，之後才在 `L385` 呼叫 `_create_module_archive_atomic`。若壓縮過程失敗，`build/<name>/` 將完全失去建置產物與索引。
    2. **`_update_release_index` 幽靈版本擠佔與提前刪檔 (`L227-L266`, `L339`)**：
       - `L227` 定義 `candidate_active = set(existing_versions) | zip_versions`。若 `existing_versions` 含有磁碟上已不存在 `.zip` 的版本號（或之前手動移除了 `.zip`），該幽靈版本仍會參與 `triplet_map` 排序並佔據 `retained = items[:3]` 的名額，將真正存在於磁碟上的版本推入 `purge = items[3:]` 並於 `L264` 刪除其 `.zip`！
       - 若某版本曾透過 `dev index-patch --status=pruned` 標記為 `pruned`（但保留了 `.zip`），下次發布新版本時 `zip_versions` 會無條件將該版本拉回 `candidate_active`。
       - `L264` 的 `os.remove(purge_path)` 發生在 `L339` 的 `vfs.write_json(index_uri, ...)` 之前；若寫入 `index.json` 失敗，舊 `.zip` 已被刪除但 `index.json` 仍指向舊版本。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `_build_module_impl` 中，先執行 `_create_module_archive_atomic` 產出 `target_zip_path`，成功後若 `clean=True` 再刪除 `real_build_dir` 中除 `os.path.basename(target_zip_path)` 與 `index.json` 以外的舊檔，最後更新 `index.json`。
      2. 在 `_update_release_index` 中，`candidate_active` 應僅以實體存在的 `zip_versions`（加上 `new_version`）為準，並排除已在 `existing_releases` 中明確標記為 `status == "pruned"`（且非本次 `new_version`）的版本；將 `os.remove(purge_path)` 移至 `vfs.write_json(index_uri, index_data, indent=2, atomic=True)` 成功落盤之後執行。
    - **程式碼修改範例**：
      ```python
      # dev/dev/builder.py (_update_release_index 關鍵修正)
      explicitly_pruned = {
          k for k, v in existing_releases.items()
          if isinstance(v, dict) and v.get("status") == "pruned" and k != new_version
      }
      candidate_active: Set[str] = (zip_versions - explicitly_pruned)
      if new_version:
          candidate_active.add(new_version)
      # ... 計算 retained 與 purge_paths 清單，待 vfs.write_json(index_uri, ...) 成功後再刪除 purge_paths ...
      vfs.write_json(index_uri, index_data, indent=2, atomic=True)
      for purge_path in purge_paths_to_remove:
          if os.path.isfile(purge_path):
              try:
                  os.remove(purge_path)
              except OSError:
                  pass
      ```

- [x] **[DEV-P1-03] [🟠 P1 | C9.2 (A2 / D5) & C1.2 | All-OS] [`dev/scripts/cli.py:L38-L110`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk) & [`dev/dev/tester.py:L27`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)、[`dev/dev/tester.py:L73-L161`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)、[`dev/dev/tester.py:L302-L341`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)、[`dev/dev/tester.py:L576`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)、[`dev/dev/tester.py:L949`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) - `CmdBags` 逆向展開為字串陣列再經 3 處手寫 `while` 迴圈重解析，且 `tester.py` 殘留 `_ORIG_SUBPROCESS_RUN` 執行期 Mock 嗅探**
  - **問題座標與分類**：[`dev/scripts/cli.py`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk)（`_normalize_bags` `L38-L83`、`_build_tester_argv` `L92-L109`）與 [`dev/dev/tester.py`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)（`_ORIG_SUBPROCESS_RUN` `L27, L576, L949`、`_parse_test_run_config` `L73-L161`、`_run_op_test` `L302-L341`）｜ `C9.2 (A2/D5)` 平行解析與測試嗅探、`C1.2` 參數解析漂移 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **三處手寫 `while` 迴圈與逆向展開 (`A2`)**：`core.commands` 已在進入點完成 `CmdBags` 解析，但 `dev/scripts/cli.py:L92-L109` 卻把 `CmdBags` 重新轉回 `List[str]`，到了 `tester.py` 再用 `_parse_test_run_config` (`L86-L131`) 與 `_run_op_test` (`L302-L341`) 的手寫 `while` 迴圈逐字拆解。
    2. **空白分隔帶值選項漏解析 (`C1.2`)**：在 `_parse_test_run_config` (`L86-L140`) 中，僅對 `-j <N>` 與 `-k <pat>` 處理了下一個 Token，卻未對 `--type <val>`、`--target <val>`、`--report-json <val>` 處理雙 Token 形式；若傳入 `["test", "--type", "env", "core"]`，`"env"` 會被 `L140` 誤認為 `target_mod`（受測模組名稱）！此外 `_run_op_test` (`L302-L341`) 亦未支援 `--type <val>` 或 `--target <val>` 的空白分隔形式。
    3. **執行期 Mock 嗅探補丁 (`D5`)**：`tester.py:L27` 儲存 `_ORIG_SUBPROCESS_RUN = subprocess.run`，並在 `L576` 與 `L949` 檢查 `if subprocess.run is _ORIG_SUBPROCESS_RUN:`，在生產代碼中探測 `unittest.mock.patch("subprocess.run")`。
  - **建議解決方案（Recommended Solution - Mode A 收斂解析器與清理嗅探）**：
    - **修改思路**：
      1. 在 `_parse_test_run_config` 與 `_run_op_test` 中補齊對 `--type`、`--target`、`--report-json` 空白分隔雙 Token 的解析，並提供統一的選項目錄或直接支援 `CmdBags` 結構化傳遞。
      2. 在 `run_subprocess_with_tree_timeout` 或 `Tester` 中移除 `_ORIG_SUBPROCESS_RUN` 全域身份比對，或將子進程執行器抽為可替換之方法 `_exec_subprocess`，讓測試直接 Mock 該方法。
    - **程式碼修改範例**：
      ```python
      # dev/dev/tester.py (_parse_test_run_config 補齊雙 Token 帶值選項解析)
      if a in ("--type", "--target", "--report-json"):
          if idx + 1 < len(argv):
              clean_argv.append(f"{a}={argv[idx + 1]}")
              idx += 2
              continue
          idx += 1
          continue
      ```

- [x] **[DEV-P1-04] [🟠 P1 | C9.2 (D5) & C8.2 | All-OS] [`dev/dev/testing/sandbox.py:L152-L175`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)、[`dev/dev/testing/case.py:L44-L83`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk) & [`dev/dev/testing/runner.py:L18`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk)、[`dev/dev/testing/runner.py:L345-L373`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk) - `_SandboxStateMeta` Metaclass 規避靜態檢查、`YSCBTestCase._shared_sandbox_ctx` 與 `OutputCapturer._ACTIVE_INSTANCE` 類別可變單例及 `case.py <-> runner.py` 循環耦合**
  - **問題座標與分類**：[`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)（`_SandboxStateMeta` `L152-L170`）、[`dev/dev/testing/case.py`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk)（`_shared_sandbox_ctx` `L44, L60-L66, L68-L83, L136-L164`）、[`dev/dev/testing/runner.py`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk)（`OutputCapturer._ACTIVE_INSTANCE` `L347-L373`）｜ `C9.2 (D5)` 逃逸補丁、`C9.3 (A3)` 狀態管理、`C8.2` 雙向循環依賴 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. `sandbox.py:L152-L170` 為了讓 `SandboxProvisioner._ACTIVE_SANDBOXES` 與 `_ADAPTED_SPECS` 看起來像類別屬性、同時躲過 `checker.py` 的 `[C9]` 檢查，特地定義了 `_SandboxStateMeta(type)` Metaclass。
    2. `case.py:L44` 的 `YSCBTestCase._shared_sandbox_ctx = None` 與 `runner.py:L347` 的 `OutputCapturer._ACTIVE_INSTANCE = None` 則是直接定義在類別上的可變 `None` 單例（因 `checker.py:L780-L796` 漏檢類別層級的 `= None` 可變單例而僥倖逃過 `[C9]` 檢查！），違反全系統執行期狀態統一存放於 `core.context.get_runtime_context()` 的架構規範。
    3. `case.py:L70` 在 `_callTestMethod` 內反向 `from dev.testing.runner import OutputCapturer` 並讀取 `OutputCapturer._ACTIVE_INSTANCE`，與 `runner.py:L18` 的 `from dev.testing.case import YSCBTestCase` 形成雙向循環耦合。
  - **建議解決方案（Recommended Solution - Mode A 收斂至 `RuntimeContext`）**：
    - **修改思路**：
      1. 將 `YSCBTestCase` 的共享沙盒與 `OutputCapturer` 的活躍實例統一存入 `get_runtime_context().get_module_state(...)` / `set_module_state(...)`，移除 `YSCBTestCase._shared_sandbox_ctx` 與 `OutputCapturer._ACTIVE_INSTANCE` 類別可變單例。
      2. 在 `case.py` 的 `_callTestMethod` 中直接從 `get_runtime_context().get_module_state("dev.testing.active_capturer")` 取得當前捕捉器，徹底斬斷 `case.py -> runner.py` 的反向匯入。
    - **程式碼修改範例**：
      ```python
      # dev/dev/testing/runner.py (OutputCapturer.__enter__ / __exit__)
      def __enter__(self) -> "OutputCapturer":
          if self.enabled:
              get_runtime_context().set_module_state("dev.testing.active_capturer", self)
              self._orig_stdout, self._orig_stderr = sys.stdout, sys.stderr
              sys.stdout, sys.stderr = self._stdout_buf, self._stderr_buf
          return self

      def __exit__(self, exc_type, exc_val, exc_tb) -> None:
          if self.enabled:
              ctx = get_runtime_context()
              if ctx.get_module_state("dev.testing.active_capturer") is self:
                  ctx.set_module_state("dev.testing.active_capturer", None)
              if self._orig_stdout is not None:
                  sys.stdout = self._orig_stdout
              if self._orig_stderr is not None:
                  sys.stderr = self._orig_stderr
      ```

- [x] **[VSC-P1-01] [🟠 P1 | C2.2 & C1.1 | macOS / All-OS] [`vscode-support/vscode_support/projector.py:L255-L265`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)、[`vscode-support/vscode_support/projector.py:L331-L358`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) & [`dev/dev/testing/case.py:L135-L157`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk) - macOS `/var -> /private/var` 下 `abspath` 比對失準，且 `_translate_exclude_to_vscode_glob` 存在多段相對路徑與 `/*` 轉譯死路**
  - **問題座標與分類**：[`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)（`_is_under_yscb_venv` `L255-L265`、`_translate_exclude_to_vscode_glob` `L331-L358`）與 [`dev/dev/testing/case.py`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk)（`setUp` `L135-L157`）｜ `C2.2` macOS 符號連結一致性、`C1.1` 忽略規則轉譯缺陷 ｜ 受影響平台：`macOS / All-OS`
  - **觸發情境與演進根因分析**：
    1. **macOS `/var -> /private/var` `realpath` 不一致 (`C2.2`)**：
       - 在 `projector.py:L261-L262` 中，`_is_under_yscb_venv` 使用 `os.path.abspath(cand)` 與 `os.path.abspath(os.path.join(self.yscb_dir, ".venv"))`。當 `proj_root` 與 `self.yscb_dir` 其中之一經過 `realpath` 解析（例如在 macOS `/var/folders/...` vs `/private/var/folders/...`），`abs_cand.startswith(venv_root + os.sep)` 恆為 `False`。
       - 在 `dev/dev/testing/case.py:L142` 中，`os.path.abspath(getattr(shared_ctx, "root_dir", ...)) != os.path.abspath(env_sb)` 同樣因未成對使用 `os.path.realpath` 而在 macOS 下誤判共享沙盒失效。
    2. **`_translate_exclude_to_vscode_glob` 轉譯死路 (`projector.py:L331-L358`)**：
       - 當輸入帶 `://` 的語意 URI（如 `"yscb://a/b/**"`）時，`L336-L344` 允許 `after` 含 `/` 並轉出 `"**/a/b/**"`；但當輸入不帶 `://` 的相對多段目錄規則（如 `"ys_codebase/.modules/**"`、`"a/b/**"` 或 `"a/b/*"`）時，`L348` 只剝除了 `/**`（漏剝除 `/*`），且 `L352` 強制要求 `and "/" not in clean_stripped`，導致所有不含 `://` 的多段路徑與 `/*` 結尾規則全數落入死路回傳 `None`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `_is_under_yscb_venv` 與 `case.py:setUp` 中，成對使用 `os.path.normcase(os.path.realpath(os.path.abspath(...)))` 進行路徑前綴與相等性比對。
      2. 在 `_translate_exclude_to_vscode_glob` 中，將不含 `://` 的路徑與含 `://` 的路徑統一走相同的尾端 `/**` / `/*` 剝除與萬用字元檢核邏輯，支援多段相對目錄（如 `"a/b/**"` -> `"**/a/b/**"`）。
    - **程式碼修改範例**：
      ```python
      # vscode-support/vscode_support/projector.py (_is_under_yscb_venv & _translate_exclude_to_vscode_glob)
      def _is_under_yscb_venv(self, cand_path: str, proj_root: str, allow_root: bool = False) -> bool:
          try:
              cand = cand_path.replace("\\", "/")
              if not os.path.isabs(cand):
                  cand = os.path.join(proj_root, cand)
              real_cand = os.path.normcase(os.path.realpath(os.path.abspath(cand)))
              venv_root = os.path.normcase(os.path.realpath(os.path.abspath(os.path.join(self.yscb_dir, ".venv"))))
              return (allow_root and real_cand == venv_root) or real_cand.startswith(venv_root + os.sep)
          except Exception:
              return False

      @staticmethod
      def _translate_exclude_to_vscode_glob(raw_pattern: str) -> Optional[str]:
          clean = str(raw_pattern or "").strip().replace("\\", "/")
          if not clean:
              return None
          if "://" in clean:
              clean = clean.split("://", 1)[1]
          elif clean.startswith("**/") and clean.endswith("/**"):
              return clean
          body = clean.strip("/")
          if body.endswith("/**"):
              body = body[:-3].strip("/")
          elif body.endswith("/*"):
              body = body[:-2].strip("/")
          if not body or "*" in body or "?" in body or body in (".DS_Store", "Thumbs.db"):
              return None
          return f"**/{body}/**"
      ```

- [x] **[VSC-P1-02] [🟠 P1 | C1.2 & C9.3 (A3) | All-OS] [`vscode-support/vscode_support/schema_compiler.py:L437-L493`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk) vs [`dev/dev/checker.py:L1315-L1543`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) & [`dev/contributes/core.json:L275-L290`](https://drive.google.com/file/d/1eIQNf1f1qL1Rim2YdwA8gBaQ0fKxsjd-/view?usp=drivesdk) - `manifest.schema.json` 與 `Checker` 靜態檢核契約多處矛盾**
  - **問題座標與分類**：[`vscode-support/vscode_support/schema_compiler.py`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk)（`build_manifest_meta_schema` `L437-L493`）與 [`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)（`_check_manifest` `L1315-L1450`、`_check_pip_dependencies` `L1508-L1543`）｜ `C1.2` 生產者與消費者契約漂移、`C9.3 (A3)` 雙重 Schema 真相 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`release.type` 與 `release.urgency` 枚舉衝突**：[`dev/contributes/core.json:L275, L285`](https://drive.google.com/file/d/1eIQNf1f1qL1Rim2YdwA8gBaQ0fKxsjd-/view?usp=drivesdk) 定義 `type` 支援 `"hotfix"`、`urgency` 支援 `"optional"`；但 `schema_compiler.py:L484-L485` 產出的 `manifest.schema.json` 將 `type` 限制為 `["feature", "bugfix", "refactor", "security", "docs"]`、將 `urgency` 限制為 `["low", "normal", "recommended", "high", "critical"]`，導致開發者使用合法的 `"hotfix"` 或 `"optional"` 時在 VS Code 觸發假警報。
    2. **`required` 必填欄位不一致**：`schema_compiler.py:L443` 設為 `["name", "version", "description"]`，而 `checker.py:L1315` 強制要求 `("name", "version", "entry", "dependencies")`。
    3. **`dependencies` 與 `pip_dependencies` 型別衝突**：`schema_compiler.py:L471` 允許 `pip_dependencies` 為 `array`，但 `checker.py:L1513` 規定 `pip_dependencies` 必須為 `object (dict)`（否則 `FAIL`）且其值為 `string` 或 `null`；而 `dependencies` 在 `checker.py:L1353` 支援 `object` 或 `array`，在 `schema_compiler.py:L455` 卻僅允許 `object`。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：對齊 `SchemaCompiler.build_manifest_meta_schema` 與 `Checker._check_manifest` 的欄位契約，將 `"entry"` 與 `"dependencies"` 納入 `required`，將 `"hotfix"` 納入 `release.type`、`"optional"` 納入 `release.urgency`，並修正 `dependencies` 與 `pip_dependencies` 的 JSON Schema 型別定義。
    - **程式碼修改範例**：
      ```python
      # vscode-support/vscode_support/schema_compiler.py (build_manifest_meta_schema 關鍵對齊)
      "required": ["name", "version", "entry", "dependencies"],
      "properties": {
          ...
          "dependencies": {
              "oneOf": [
                  {"type": "object", "additionalProperties": {"type": "string"}},
                  {"type": "array", "items": {"type": "string"}},
              ]
          },
          "pip_dependencies": {
              "type": "object",
              "additionalProperties": {"type": ["string", "null"]},
          },
          "release": {
              "type": "object",
              "properties": {
                  "type": {"type": "string", "enum": ["feature", "bugfix", "hotfix", "refactor", "security", "docs"]},
                  "urgency": {"type": "string", "enum": ["optional", "low", "normal", "recommended", "high", "critical"]},
                  "summary": {"type": "string"},
                  "sha256": {"type": "string"},
              },
              "additionalProperties": True,
          },
      }
      ```

---

### 🟡 P2 - Medium（防禦缺口與結構耦合：巨石類別 / 守衛盲區 / 空殼 Hook / 非原子還原）

- [x] **[DEV-P2-01] [🟡 P2 | C9.1 (A1) & C8.1 | All-OS] [`dev/dev/checker.py:L342-L362`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) & [`dev/dev/checker.py:L1-L2059`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) - `checker.py` 單檔逾 2,050 行混雜多正交職責，且在基礎模組硬編碼業務模組 `"server"` 豁免清單**
  - **問題座標與分類**：[`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)（`_GUARDRAIL_EXEMPTIONS` `L342-L362` 及全檔 `L1-L2059`）｜ `C9.1 (A1)` 職責邊界、`C8.1` 正交職責混雜 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    - `dev/dev/checker.py` 單一檔案承載了報表模型、CLI AST 審計、測試類別審計、668 行的 `_SourceGuardrailVisitor` 以及 856 行的 `Checker` 主類別，任何新增規則或修改報表格式皆需修改同一巨型檔案。
    - `L342-L362` 的 `_GUARDRAIL_EXEMPTIONS` 硬編碼了 `("A2", "server", "server/worker.py")`、`("B3", "server", "server/master.py")` 等上層模組路徑，使底層開發工具反向耦合特定業務模組名稱。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：將 `checker.py` 拆分為 `dev/checker_models.py`（`CheckSeverity`, `CheckIssue`, `CheckReport`, `ModuleCheckContext`）、`dev/guardrail_visitor.py`（`_SourceGuardrailVisitor` 與 AST 輔助函式）與 `dev/checker.py`（`Checker` 協調器，保持公開匯入相容）。

- [x] **[DEV-P2-02] [🟡 P2 | C3.3 & C8.2 | All-OS] [`dev/dev/checker.py:L485-L500`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)、[`dev/dev/checker.py:L655-L707`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) & [`dev/dev/checker.py:L780-L796`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) - `Checker` AST 守衛存在類別級 `None` 單例漏檢、Hook 常數誤報、`except` 豁免過寬與 `is_test_file` 死分支**
  - **問題座標與分類**：[`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)（`_is_safe_hook_top_level_value` `L485-L500`、`_check_top_level_stmts` `L655-L693`、`analyze` `L695-L707`、`visit_ClassDef` `L780-L796`）｜ `C3.3` 假陽性/漏檢守衛、`C8.2` 死代碼 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **類別級 `= None` 可變單例漏檢 (`L780-L796`)**：`visit_ClassDef` 僅檢查 `_is_mutable_expr(bstmt.value)`（如 `[]`, `{}`），未檢查非 `@dataclass` 類別屬性賦值為 `None`（如 `_ACTIVE_INSTANCE = None`、`_shared_sandbox_ctx = None`），導致開發者可將模組頂層被禁止的 `None` 單例搬進 class body 規避 `[C8]/[C9]`。
    2. **`_is_safe_hook_top_level_value` 誤報與漏檢 (`L485-L500`)**：不支援負數常數 `ast.UnaryOp(op=ast.USub(), operand=ast.Constant(1))`（如 `DEFAULT_TIMEOUT = -1` 會報錯），卻對 `frozenset(call())` / `tuple(call())` 未檢查內部引數是否安全。
    3. **`analyze()` 中 `is_test_file` 早退造成 7 處死條件 (`L695-L707`)**：`analyze()` 在 `self.is_test_file` 為真時於 `L707` 直接返回，從未執行 `self.visit(tree)`，使 `L726, L749, L758, L815, L828, L841, L932` 的 `self.is_test_file` 判斷全數成為死分支。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `_is_safe_hook_top_level_value` 中支援對數值常數的 `ast.UnaryOp` (`UAdd`/`USub`/`Invert`) 並遞迴驗證 `frozenset`/`tuple` 的引數；清理 `_SourceGuardrailVisitor` 內重複的 `self.is_test_file` 死判斷。

- [x] **[DEV-P2-03] [🟡 P2 | C9.1 (A1) & C9.2 (A2) & C3.2 | All-OS] [`dev/scripts/cli.py:L112-L160`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk)、[`dev/dev/scaffold.py:L10-L135`](https://drive.google.com/file/d/1rOtRBXNSVjnOJj6h9EzqflAGTQrHa-Qs/view?usp=drivesdk)、[`dev/dev/testing/sandbox.py:L65-L149`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) & [`dev/dev/testing/case.py:L218-L282`](https://drive.google.com/file/d/1t1wEdUR3ro7dCijglB1UVSeVdpeImqBZ/view?usp=drivesdk) - `dev/scripts/cli.py` 內嵌版本遞增業務邏輯且寫檔漏 `atomic=True`，另模組骨架生成散落 3 處且 `Scaffolder` 失敗無回滾**
  - **問題座標與分類**：[`dev/scripts/cli.py`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk)（`_handle_bump` `L112-L138`、`_sync_package_dunder_version` `L140-L160`）與 [`dev/dev/scaffold.py`](https://drive.google.com/file/d/1rOtRBXNSVjnOJj6h9EzqflAGTQrHa-Qs/view?usp=drivesdk)（`create_module` `L10-L135`）｜ `C9.1 (A1)` CLI 職責越界、`C9.2 (A2)` 重複骨架生成、`C3.2` 失敗回滾 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. `dev/scripts/cli.py:L112-L160` 直接實作了版本號計算、`manifest.json` 寫入（`L131` 漏掉 `atomic=True`）與 `__init__.py` `__version__` 正則替換，未封裝於 `Releaser`。
    2. `Scaffolder.create_module` (`scaffold.py:L24-L134`) 分 8 次寫入檔案，若中途拋出 I/O 例外，半成品目錄將殘留於 `module.source://<name>`，導致後續重試因 `vfs.exists(target_src_uri)` (`L18`) 永久失敗；且 `scaffold.py:L30` 預設 `"core": ">=1.0.0"`，一旦加入 `locales` 即觸發 `Checker` (`>=1.2.0`) 報錯。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 將 `_handle_bump` 與 `_sync_package_dunder_version` 抽入 `Releaser.bump_version(mod_name, bump_type)` 並補上 `atomic=True`。
      2. 在 `Scaffolder.create_module` 中加上 `try...except` 保護，若建立過程失敗則呼叫 `vfs.rmtree(target_src_uri, ignore_errors=True)` 清理半成品目錄，並將預設 `core` 依賴提升為 `">=1.2.0"`。

- [x] **[DEV-P2-04] [🟡 P2 | C9.2 (A2) & C2.2 & C6.1 | Windows / POSIX] [`dev/dev/testing/sandbox.py:L21-L40`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) & [`dev/dev/testing/sandbox.py:L473-L528`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) - `sandbox.py` 平行維護缺損版 `_safe_extract_zip`，且 Windows `_project_venv` 未對齊三級目錄連結降級鏈**
  - **問題座標與分類**：[`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)（`_safe_extract_zip` `L21-L40`、`_project_venv` `L473-L528`）｜ `C9.2 (A2)` 平行實作、`C2.2` Windows 相容性、`C6.1` 歸檔安全 ｜ 受影響平台：`Windows / POSIX`
  - **觸發情境與演進根因分析**：
    1. `_safe_extract_zip` (`L21-L40`) 未如 `core/core/engine.py:L635-L658` 檢查 Windows 磁碟機代號（如 `C:foo`：`len(norm_member) > 1 and norm_member[1] == ":"`）。
    2. `_project_venv` (`L493-L500`) 在 Windows 下僅嘗試 `import _winapi; _winapi.CreateJunction(...)` 且僅捕獲 `OSError`（未捕獲 `ImportError`/`AttributeError`，亦未包含 `os.symlink` 或 `cmd /c mklink /J` 降級步驟），與 [`vscode-support/vscode_support/projector.py:L224-L249`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) 的目錄連結實作分歧。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `_safe_extract_zip` 補齊 `len(norm_member) > 1 and norm_member[1] == ":"` 檢查；在 `_project_venv` 的 Windows 分支將 `except OSError:` 擴大為 `except Exception:` 並補齊 `os.symlink` / `mklink /J` 降級鏈。

- [x] **[VSC-P2-01] [🟡 P2 | C1.1 & C3.2 (D2) | All-OS] [`vscode-support/vscode_support/projector.py:L63-L70`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)、[`vscode-support/vscode_support/projector.py:L568-L597`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) & [`vscode-support/vscode_support/projector.py:L614-L680`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) - `SettingsProjector` 於 `revert` 時在 `settings.json` 寫盤前過早刪除 `schemas/` 與穩定連結、對 JSONC 漏備份 `.bak`，且 `strip_jsonc` 未攔截未閉合 `/*` 註解**
  - **問題座標與分類**：[`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)（`strip_jsonc` `L63-L70`、`_sync_vscode_settings_impl` `L568-L597`、`revert_vscode_settings` `L614-L680`）｜ `C1.1` 狀態一致性、`C3.2 (D2)` 兩階段寫入順序 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. **`revert_vscode_settings` 先刪後寫 (`L622-L680`)**：在 `L622-L626` 先刪除了 `current-site-packages` 與 `.vscode/schemas/`，直到 `L676` 才執行 `vfs.write_json(settings_path, settings, indent=2, atomic=True)`。若 `settings.json` 寫入失敗，磁碟上的 `schemas/` 與連結已消失，但 `settings.json` 仍保留 `_yscb_managed` 與失效引用。
    2. **`revert_vscode_settings` 覆寫 JSONC 漏備份 `.bak` (`L614-L676`)**：當 `had_jsonc=True` 時，`sync_vscode_settings` 會在抹除註解寫入前備份 `settings.json.bak` (`L589-L593`)，但 `revert_vscode_settings` 卻直接覆寫 `settings.json` 而未備份 `raw_original`。
    3. **`strip_jsonc` 未閉合 `/*` 區塊註解漏檢 (`L63-L70`)**：若 `settings.json` 末尾存在未閉合的 `/* ...`，`while i + 1 < n` 迴圈在檔尾結束後未檢查是否真的匹配到 `*/`，直接 `i += 2` 吞掉整段未閉合註解。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `revert_vscode_settings` 中，先備份 `had_jsonc` 之 `.bak` 並完成 `vfs.write_json(settings_path, settings, indent=2, atomic=True)`，確認寫盤成功後再執行 `remove_stable_site_packages_link()` 與 `vfs.robust_rmtree(schemas_dir, ignore_errors=True)`。
      2. 在 `strip_jsonc` 的 `/*` 分支檢查是否找到閉合 `*/`，若至字串結尾仍未閉合則保留原字元或標記語法錯誤以阻斷覆寫。
    - **程式碼修改範例**：
      ```python
      # vscode-support/vscode_support/projector.py (revert_vscode_settings L665-L680 調整順序)
      if had_jsonc and raw_original is not None:
          try:
              vfs.write_text(settings_path + ".bak", raw_original, encoding="utf-8", atomic=True)
          except Exception:
              pass
      try:
          vfs.write_json(settings_path, settings, indent=2, atomic=True)
      except Exception as exc:
          self.last_revert_error = f"Failed to write '{settings_path}' during revert: {exc}"
          return False

      self.remove_stable_site_packages_link()
      schemas_dir = os.path.join(proj_root, ".vscode", "schemas")
      if os.path.isdir(schemas_dir):
          vfs.robust_rmtree(schemas_dir, ignore_errors=True)
      return True
      ```

- [x] **[VSC-P2-02] [🟡 P2 | C9.3 (A5) & C1.3 | All-OS] [`vscode-support/scripts/hook.dev.py:L1-L19`](https://drive.google.com/file/d/156PQZgP8TxYPkJD99NHVp_y1j5qoKVuJ/view?usp=drivesdk) & [`vscode-support/scripts/hook.core.py:L24-L78`](https://drive.google.com/file/d/1jsdmXg7jeIZFlO-d-_2I-OhnBd1nH5cT/view?usp=drivesdk) - `vscode-support` 存在無業務邏輯之空殼 `hook.dev.py`，且 `hook.core.py` 淺層目錄指紋未涵蓋子目錄內契約檔時間戳**
  - **問題座標與分類**：[`vscode-support/scripts/hook.dev.py`](https://drive.google.com/file/d/156PQZgP8TxYPkJD99NHVp_y1j5qoKVuJ/view?usp=drivesdk)（`L1-L19`）與 [`vscode-support/scripts/hook.core.py`](https://drive.google.com/file/d/1jsdmXg7jeIZFlO-d-_2I-OhnBd1nH5cT/view?usp=drivesdk)（`_dir_shallow_fingerprint` `L24-L33`）｜ `C9.3 (A5)` 空殼 Hook、`C1.3` 快取指紋粒度 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：
    1. `hook.dev.py` 僅含兩行 `log_debug`，無任何實質沙盒設定或清理工作，卻因存在於 `scripts/hook.dev.py` 而在每次沙盒啟停時被 `core.events` 載入調用。
    2. `hook.core.py:L24-L33` 的 `_dir_shallow_fingerprint` 僅讀取 `.modules`、`.mirror`、`source` 頂層目錄的 `st_mtime_ns` 與 `os.listdir`。當某個已安裝模組目錄下的 `contributes/_format.json`、`configurable/_format.json` 或 `.mirror/<mod>/*.zip` 發生變更但頂層模組資料夾未增減時，頂層 `st_mtime_ns` 不會改變。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：強化 `_dir_shallow_fingerprint` 一併採計各子目錄（`<dir>/<entry>`）之 `st_mtime_ns`，確保 2 秒去重窗口內若模組子目錄或 `.mirror/<mod>` 更新時能立即穿透快取重新編譯 Schema。

---

### 🔵 P3 - Optimization（效能加速與無損結構打磨）

- [x] **[DEV-P3-01] [🔵 P3 | C7.1 | All-OS] [`dev/dev/checker.py:L1777-L2023`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) - `Checker.check_module` 對同一模組目錄重複執行 3 次 `os.walk` 全樹掃描**
  - **問題座標與分類**：[`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)（`_check_file_structure` `L1777`、`_check_source_files` `L1899`、`_check_docs_pollution` `L2002`）｜ `C7.1` 重複 I/O 掃描 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：單次 `check_module` 內部對 `real_dir` 執行了 3 次獨立的 `os.walk`。
  - **建議解決方案（Recommended Solution）**：在 `ModuleCheckContext` 建立時執行單次 `os.walk(real_dir)`（同時排除 `__pycache__`, `.pytest_cache`, `.git`, `.venv`, `node_modules`），一次性收集 `all_files`、`py_files` 與 `doc_md_files` 供後續步驟直接迭代。

- [x] **[DEV-P3-02] [🔵 P3 | C8.3 (S3) | All-OS] [`dev/dev/tester.py:L30-L55`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk) & [`dev/dev/testing/runner.py:L521-L542`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk) - `tester.py:safe_print` 與 `runner.py:SafeStreamWriter` 重複實作主控台編碼容錯輸出**
  - **問題座標與分類**：[`dev/dev/tester.py`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)（`safe_print` `L30-L55`）與 [`dev/dev/testing/runner.py`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk)（`SafeStreamWriter` `L521-L542`）｜ `C8.3 (S3)` 重複樣板 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：兩處各自實作了針對 Windows `cp950` `UnicodeEncodeError` 的 `encode/decode(errors="replace")` 邏輯。
  - **建議解決方案（Recommended Solution）**：在 `SafeStreamWriter` 中統一實作 `write` 容錯，並讓 `safe_print(text, file=..., end=..., flush=...)` 直接透過 `SafeStreamWriter(file or sys.stdout)` 輸出。

- [x] **[VSC-P3-01] [🔵 P3 | C7.1 | All-OS] [`vscode-support/vscode_support/schema_compiler.py:L33`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk)、[`vscode-support/vscode_support/schema_compiler.py:L543-L590`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk) & [`vscode-support/scripts/cli.py:L82-L99`](https://drive.google.com/file/d/1DiQPhMjkgeoKAXGiXAG7fW52fSSrWuBg/view?usp=drivesdk) - `SchemaCompiler._mirror_zip_bundle_cache` 未掛載於 `RuntimeContext` 導致跨實例失效，且 `cli.py:sync` 重複讀取 `settings.json`**
  - **問題座標與分類**：[`vscode-support/vscode_support/schema_compiler.py`](https://drive.google.com/file/d/1GNojbq9Cz35V4V_1R6qLo9srvt1kaWH-/view?usp=drivesdk)（`L33, L543-L590`）與 [`vscode-support/scripts/cli.py`](https://drive.google.com/file/d/1DiQPhMjkgeoKAXGiXAG7fW52fSSrWuBg/view?usp=drivesdk)（`sync` `L82-L99`）｜ `C7.1` 重複 I/O ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：`_mirror_zip_bundle_cache` 存於 `SchemaCompiler` 實例字典，每次新建 `SettingsProjector()` 即重置；而 `cli.py:sync` 在 `sync_vscode_settings` 寫完 `settings.json` 後又立即呼叫 `get_status` 重新讀檔解析。
  - **建議解決方案（Recommended Solution）**：將 `_mirror_zip_bundle_cache` 改由 `get_runtime_context().get_module_state("vscode_support.mirror_zip_cache", dict)` 託管（並限制最大快取筆數如 64 筆防無界增長）。

- [x] **[VSC-P3-02] [🔵 P3 | C8.2 | All-OS] [`vscode-support/vscode_support/projector.py:L186-L192`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)、[`vscode-support/vscode_support/projector.py:L360-L365`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) & [`dev/dev/releaser.py:L137`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk) - 移除 `_resolve_workspace_exclude_patterns` 未使用之死參數 `include_all` 並校正 3 處過時 Docstring**
  - **問題座標與分類**：[`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)（`L191, L364, L526`）與 [`dev/dev/releaser.py`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk)（`L137`）｜ `C8.2` 死參數與契約文件同步 ｜ 受影響平台：`All-OS`
  - **觸發情境與演進根因分析**：`_resolve_workspace_exclude_patterns` 的 `include_all` 參數在函式體內零引用；`projector.py:L191, L526` 與 `releaser.py:L137` 的 Docstring 描述與現行實作（及單元測試驗證之刻意設計）不一致。
  - **建議解決方案（Recommended Solution）**：若無外部呼叫方依賴 `include_all` 則移除（或保留簽名但標註棄用），並更新上述 3 處 Docstring 使文件與實作 100% 對齊。

---

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

在三步反向查證過程中，以下 5 項初看疑似異常的候選點經核對上游呼叫端、`core` 基礎設施與單元測試契約後，確認為**刻意設計（By Design）或已受上游防護**：

- **[RFP-01] [`vscode-support/vscode_support/projector.py:L305-L307`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)（`ensure_stable_site_packages_link` 回傳 `None` 時仍寫入 `current-site-packages`）**：
  - **查證結論**：初看 `L191` Docstring 寫有「回傳 `None` 由呼叫端自動降級為實際路徑」，但查驗 `L300` 註解與 [`vscode-support/tests/test_vscode_support.py:L135-L142`](https://drive.google.com/file/d/10DxP4vBKPv58EQyzOqccp0DX90bQq-eu/view?usp=drivesdk) (`test_stable_path_preserved_when_symlink_unsupported`) 確認：恆定寫入 `./.yscb/.venv/current-site-packages` 為刻意設計，目的是防止在受限容器（如 virtiofs）與宿主機之間同步時造成 `.vscode/settings.json` 頻繁 Git diff 變動。僅需更新 `L191` 過時 Docstring（已併入 `VSC-P3-02`）。
- **[RFP-02] [`vscode-support/vscode_support/projector.py:L607-L620`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)（`revert_vscode_settings` 在 `settings.json` 不存在或無 `_yscb_managed` 時不刪除 `.vscode/schemas/`）**：
  - **查證結論**：經核對 [`vscode-support/tests/test_vscode_support.py:L601-L628`](https://drive.google.com/file/d/10DxP4vBKPv58EQyzOqccp0DX90bQq-eu/view?usp=drivesdk) (`test_revert_side_effects_deferred_until_valid_managed_settings`)，確認此為保護非 YSCB 託管專案中既有 `.vscode/schemas/` 目錄的刻意安全守衛；真正的問題僅在於 `L622-L626` 將刪除動作放在 `L676` `vfs.write_json` 之前（已精確收斂為 `VSC-P2-01`）。
- **[RFP-03] [`dev/dev/releaser.py:L180-L196`](https://drive.google.com/file/d/1GyylrQMoZb7k224txlTQx8fukgkUGsKU/view?usp=drivesdk)（`release_check` Gate 3 使用 `global_highest` 而非同三元組最高版本）**：
  - **查證結論**：初看 `L137` Docstring 寫「大於同三元組在庫最高 revision」，但經查驗 [`dev/tests/test_release_pipeline.py:L73-L88`](https://drive.google.com/file/d/16HO-dHonAH_JbfaorqkUoeyuOIxaLzVa/view?usp=drivesdk) (`test_release_gate3_cross_triplet_rollback_blocking`)，確認全域單調遞增（禁止跨三元組降版發布，如存在 `1.1.0.0` 時禁止發布 `1.0.0.5`）為明確的測試契約與刻意設計；僅 `L137` Docstring 表述未同步更新（已併入 `VSC-P3-02`）。
- **[RFP-04] [`dev/dev/scaffold.py:L74-L79`](https://drive.google.com/file/d/1rOtRBXNSVjnOJj6h9EzqflAGTQrHa-Qs/view?usp=drivesdk)（鷹架生成的 `TestBasic.test_sample` 直接呼叫 `cli.hello(bags)` 是否會被 `guard_dispatch` 阻斷）**：
  - **查證結論**：經查驗 [`core/core/guard.py:L29-L30`](https://drive.google.com/file/d/1jIz8Dq6-vhzEWgsJgI_ImT-F5-tYMrAT/view?usp=drivesdk) 與沙盒環境變數，當測試透過 `dev test` 在沙盒內執行時，宿主環境與沙盒皆已配置合法憑證或 `YSCB_TESTING=1`，故不會誤觸 `SystemExit(126)`。
- **[RFP-05] [`vscode-support/vscode_support/__init__.py:L24-L31`](https://drive.google.com/file/d/1DkCuXFsqZiBdHCM5RxgkQ_EvSA_AFrOA/view?usp=drivesdk)（PEP 562 `__getattr__` 延遲載入寫入 `globals()[name] = val`）**：
  - **查證結論**：經查驗 [`vscode-support/tests/test_vscode_support.py:L82-L101`](https://drive.google.com/file/d/10DxP4vBKPv58EQyzOqccp0DX90bQq-eu/view?usp=drivesdk) (`test_package_lazy_loading_and_module_exports`) 與 [`dev/dev/checker.py:L826, L874`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)，`__init__.py` 的 PEP 562 延遲匯入與 `globals()` 快取屬專案明文允許之冷啟動加速模式（非舊版符號轉發逃逸補丁）。


---

## Part VI — Group F：`agents-workflow` 與 `gdrive-support` 模組（規範編譯、計畫狀態機與雲端同步）

# 🛡️ YS-Codebase (`agents-workflow` & `gdrive-support`) 第二次九維度單點序列深度審計與架構整理診斷報告 (Round 2 Codebase Deep Audit — Group F)

### 2.1 審計執行摘要與單元健康度矩陣

- **受審範圍與規模**：
  - [`ys_codebase/source/agents-workflow/`](https://drive.google.com/file/d/1PSV6IpTS_9jrz9Ra37bO5qJey0QjYmpd/view?usp=drivesdk)（涵蓋 `Unit 01` 編譯/發布/初始化/路線圖與 `Unit 02` Plans 狀態機/檢核/自癒/掃描/歸檔/檢索/Session 軌跡/CLI/Hooks）
  - [`ys_codebase/source/gdrive-support/`](https://drive.google.com/file/d/1PU1m05aJdgcyBGP2tu0mbnriwYnmBPp4/view?usp=drivesdk)（涵蓋 `Unit 03` 同步協調器/三方對帳/設定/常駐服務與 `Unit 04` 傳輸層/本地沙盒/OAuth/CLI/Hooks）
  - 共劃分為 **4 個獨立審查單元**，100% 逐檔完整細讀全部業務原始碼、腳本與 Contributes 宣告（嚴格遵守黑盒零錨定圍欄，未讀取任何既有 `plans/` 審計報告）。
- **目標語言與平台基準**：語言 `Python 3.11+ (100% Stdlib)` ｜ 平台基準 `Linux + Windows + macOS (Tri-OS Parity)` ｜ 架構重構尺度 `Mode B 對外 CLI/SDK 契約相容 + Mode A 內部根因收斂`
- **診斷統計總覽**：🔴 **P0**：`3` 項 ｜ 🟠 **P1**：`8` 項 ｜ 🟡 **P2**：`5` 項 ｜ 🔵 **P3**：`2` 項（共 **18 項確認問題**，並完成三步反向查證排除假陽性 `3` 項）

| 審查單元 (Audit Unit) | 涵蓋核心檔案 | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :--- | :---: |
| **`Unit 01`**<br>(`agents-workflow` 編譯/發布/路線圖) | [`compiler.py`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk), [`publisher.py`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk), [`targets.py`](https://drive.google.com/file/d/1m6i78FufIMoU4Yfjf_h1Dhqmk4J-MEgs/view?usp=drivesdk), [`initializer.py`](https://drive.google.com/file/d/1rpSQmdCVrwVMOhOtB1i9tdoUU6x59U7d/view?usp=drivesdk), [`roadmap.py`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) | `AUD-01`, `AUD-02`, `AUD-03`, `AUD-04`, `AUD-05`, `AUD-08` | 🟠 存在 P1 架構與跨平台缺陷 |
| **`Unit 02`**<br>(`agents-workflow/plans` 工具鏈與 CLI/Hooks) | [`_common.py`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk), [`status.py`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk), [`scanner.py`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk), [`archiver.py`](https://drive.google.com/file/d/1Rin77sqznCMYxaFoPalyAtH_AkZLrnFG/view?usp=drivesdk), [`verifier.py`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk), [`_verifier_healer.py`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk), [`_verifier_specs.py`](https://drive.google.com/file/d/1nR2-PHMs8JO6AYi_Rni_VoC7z84PQHUy/view?usp=drivesdk), [`searcher.py`](https://drive.google.com/file/d/1-QVZWThaL8nAJNUwnKAww6FEzJfkZb19/view?usp=drivesdk), [`session_trace.py`](https://drive.google.com/file/d/1iisQ2clxlUuxO_hUzPCX6g5vSHscOnqg/view?usp=drivesdk), [`_trace_parser.py`](https://drive.google.com/file/d/1ITixBZPq-ywiyFnsb2entMqeCqhq567_/view?usp=drivesdk), [`scripts/cli.py`](https://drive.google.com/file/d/1HcaY-GoXh-KrehG9ayNpDg57KfIgsiQf/view?usp=drivesdk), [`hook.core.py`](https://drive.google.com/file/d/1J7EGK8qv5TlmXZqpwrCvsabiZyks5xsU/view?usp=drivesdk), [`hook.dev.py`](https://drive.google.com/file/d/1Fv59LRg0uApay71DjHfh4W99BgvWVAHk/view?usp=drivesdk) | `AUD-06`, `AUD-09`, `AUD-10`, `AUD-15`, `AUD-17` | 🟠 存在 P1 狀態機分裂與時區錯位 |
| **`Unit 03`**<br>(`gdrive-support` 協調器/對帳/設定/常駐服務) | [`coordinator.py`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk), [`reconciler.py`](https://drive.google.com/file/d/1PnaaNLogqRvmXNuEGfWQiEB8b67uBCXs/view?usp=drivesdk), [`config.py`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk), [`service.py`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk) | `AUD-01`, `AUD-02`, `AUD-03`, `AUD-11`, `AUD-12`, `AUD-14`, `AUD-16` | 🔴 存在 P0 並發無鎖重放與狀態損毀 |
| **`Unit 04`**<br>(`gdrive-support` 傳輸層/沙盒/CLI/Hooks) | [`transport.py`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk), [`scripts/cli.py`](https://drive.google.com/file/d/1zT7-jSaAJy0pjw5dJ9nMUMTRZbpJ4eZc/view?usp=drivesdk), [`scripts/hook.core.py`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk), [`contributes/core.json`](https://drive.google.com/file/d/1D53iMs8qpDzVwaLof_6KzrPV-ou4_20F/view?usp=drivesdk) | `AUD-07`, `AUD-12`, `AUD-13`, `AUD-14`, `AUD-16`, `AUD-18` | 🟠 存在 P1 違反 CQS、連線池洩漏與沙盒全掃描 |

---

### 2.2 跨單元根因架構整理手術藍圖 (Mode A Architecture Surgery Blueprints: S1 - S6)

| 手術編號 | 根因重構手術名稱 | 解決之問題編號 | 維度代號 | 核心架構改造與舊軌清理方案 |
| :--- | :--- | :--- | :---: | :--- |
| **`S1`** | **Plans 單一有限狀態機收斂手術 (`plans/state_machine.py`)** | `AUD-06`, `AUD-15` | `C9.2 (A2)`<br>`C9.1 (D1/D2)` | • 新建 [`agents_workflow/plans/state_machine.py`]() 作為唯一真相來源（SSOT），統一推導 `PlanTrack`、`PlanPhase`、`NormalizedStatus`、`is_completed` 與 `attached_revision_active`。<br>• 廢除 [`status.py`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk)、[`scanner.py`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk) 與 [`_common.py:evaluate_plan_completion`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) 三套各自為政的平行判斷鏈，消除「`scanner` 顯示 Completed 提示歸檔、`archiver` 卻因未完成之附掛 `revision_log.md` 拋出失敗」之雙軌矛盾，並統一 `_verifier_specs.py` 與 `status.py` 重複定義的標頭鍵常數。 |
| **`S2`** | **編譯與發布管線零冗餘 I/O、多反引號 AST 狀態掃描與投影路徑統一手術** | `AUD-04`, `AUD-05`, `AUD-08`, `AUD-10`, `AUD-17` | `C9.2 (A2/D5)`<br>`C9.3 (A3)`<br>`C7.1` | • 在 [`compiler.py`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 將 `FENCED_CODE_BLOCK_REGEX` 與 `CODE_SPAN_REGEX` 升級為符合 CommonMark 規範的「同長反引號對稱匹配」（支援 ```` ``` ```` 巢狀於 ````` ```` ````` 內，以及 `` `` `...` `` `` 多反引號行內 Code Span），並同步套用至 [`verifier.py`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) 與 [`_verifier_specs.py`](https://drive.google.com/file/d/1nR2-PHMs8JO6AYi_Rni_VoC7z84PQHUy/view?usp=drivesdk)。<br>• 移除 [`compiler.py:L570`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 與 [`publisher.py:L262`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 全程零引用的雙重 `hashlib.sha256` 計算，並使 `compile_stage1(write_cache=False)` 在 `release_all()` 內部純記憶體流轉，不再每輪重複寫入 45+ 個無用 `cache://` 中繼檔。<br>• 統一 [`publisher.py:L1030`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 本地層級 Manifest 為 `project://` 語意 URI，並拔除 [`publisher.py:L1376`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 與 [`roadmap.py:L19`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) 的測試 Mock 嗅探後門。 |
| **`S3`** | **`gdrive-support` 巨石類別正交拆分與三帳本 SSOT 收斂手術** | `AUD-01`, `AUD-02`, `AUD-03`, `AUD-11`, `AUD-14` | `C9.1 (A1)`<br>`C9.3 (A3/D4)` | • 將 3,171 行的 [`coordinator.py`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) 按正交變更軸拆分為：`coordinator.py`（高階協調與公開 API）、`readme_sync.py`（根目錄與倉庫 `README.md` 軟合併狀態機）、`ledger.py`（`sync_state.json` + WAL Journal 單一帳本管理）與 `incremental_cache.py`（Level 0/1 `changes.list` 增量快取引擎）。<br>• 將 2,197 行的 [`transport.py`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) 拆分為：`transport.py`（抽象契約與 `GoogleDriveApiTransport`）、`sandbox_transport.py`（`LocalSandboxTransport`）與 `auth_flow.py`（OAuth2 Loopback HTTP Server 與憑證交換），由 [`gdrive_support/__init__.py`](https://drive.google.com/file/d/1GbWRlv7eFXC7Vs_2f8Si1OJ_ufBODNRx/view?usp=drivesdk) 維持 100% 向下相容匯出。 |
| **`S4`** | **`gdrive-support` 嚴格 CQS 讀寫分離與資源池閉環手術** | `AUD-07`, `AUD-12`, `AUD-13` | `C9.1 (D1)`<br>`C3.2`<br>`C7.1` | • 將 [`AbstractSyncTransport.list_files`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) 預設參數改為 `deduplicate: bool = False`，並拔除 `LocalSandboxTransport.get_entry()` 內部的 `_deduplicate_same_path_items` 與無條件 `persist=True` 寫入；使 `list_branches()` 純唯讀查詢雲端，絕不暗中觸發 `README.md` 寫入、重複檔移入垃圾桶或自動初始化空倉庫。<br>• 為 `GoogleDriveApiTransport` 提供 `thread_worker_scope()` 上下文管理器，確保 `SyncCoordinator` 所有 `ThreadPoolExecutor` 工作執行緒結束時 100% 歸還 `HTTPSConnection` 至連線池，消除長駐服務的 Socket 與 `_tls_conn_dicts` 記憶體洩漏。 |

---

### 2.3 P0 - P3 分級問題與解決方案清單 (Tiered Actionable Checklist)

### 🔴 P0 - Critical（高危阻斷：並發無鎖重放覆寫 / 分支切換資料遺失 / 狀態帳本損毀）

- [x] **[AUD-01] [🔴 P0 | C4.1 & C9.3 (A3) | All-OS] [`gdrive_support/service.py:L205-L232, L254-L260`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk) & [`gdrive_support/coordinator.py:L653-L675`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — 背景 `GDriveSyncServiceWorker` 在獲取跨進程鎖 (`sync.lock`) 之前無鎖呼叫 `_load_local_state()`，併發觸發 WAL Journal 重放與刪除，直接抹除前景同步進程之交易日誌並以舊狀態反蓋新設定**
  - **問題座標與分類**：[`gdrive_support/service.py:L205-L232, L254-L260`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk)（`_refresh_active_branch`, `run_once`）、[`gdrive_support/coordinator.py:L653-L675`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)（`_load_local_state`, `_save_local_state`）｜ `C4.1` 原子性違背 / `C9.3 (A3)` 狀態真相分裂 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **無鎖搶佔與 WAL 抹除競態 (`C4.1`)**：當前景 CLI 正在執行 `yscb gdrive push / pull / sync` 時，前景進程持有 `InterProcessLock`（`sync.lock`）並在 Stage 3 逐檔寫入 `sync_state.journal.jsonl`（WAL 日誌）。此時本地檔案寫入觸發 `core.space` 檔案變更事件，喚醒背景 `GDriveSyncServiceWorker.run_once()`（[`service.py:L244-L260`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk)）。然而 `run_once()` 在第 254 行**尚未獲取 `sync.lock` 之前**，就先呼叫 `self._refresh_active_branch()` -> `self._coordinator._load_local_state()`（[`service.py:L221`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk)）。而 `_load_local_state()`（[`coordinator.py:L664-L665`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）一旦發現磁碟上有前景正在寫入的 `sync_state.journal.jsonl`，立即在**無鎖狀態下執行 `_replay_state_journal(state)` 並呼叫 `_save_local_state(state)` 覆寫 `sync_state.json` 且將 `sync_state.journal.jsonl` 直接 `unlink()` 刪除**（[`coordinator.py:L672`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）！隨後第 255 行背景執行緒才呼叫 `run_sync(non_blocking_lock=True)` 發現鎖被前景佔用而退出，但前景進程的 WAL 保護已被摧毀。
    2. **Split-Brain 優先級顛倒 (`A3`)**：在 `_refresh_active_branch()`（[`service.py:L213-L225`](https://drive.google.com/file/d/1Hen0fLMkjJSeNdXO9U1YPbr6fRzqzark/view?usp=drivesdk)）中，先讀取 `load_gdrive_config().active_branch` 賦值予 `candidate_branch`，隨即在第 221-224 行讀取 `sync_state.json` 內的 `state.get("active_branch")` **無條件覆蓋 `candidate_branch`**。由於 `sync_state.json` 自首次同步起永遠存有舊 `active_branch`（[`coordinator.py:L1318`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)），導致使用者透過設定檔或 `yscb config set` 修改 `repo_sync.active_branch`（及 `sync_spaces`、`poll_interval_sec` 等配置）時，背景服務永遠被舊的 `sync_state.json` 覆蓋而失效。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 廢除在鎖外呼叫 `_load_local_state()` 的做法：在 [`coordinator.py`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) 新增純唯讀且不觸發 Journal Replay 的 `_peek_persisted_active_branch()`，或將分支與組態刷新移入 `_run_sync_impl` 取得 `InterProcessLock` 之後執行。
      2. 在 `_refresh_active_branch()` 中，當 `self._explicit_config is None` 時，以 `load_gdrive_config()` 作為組態 SSOT（同步更新 `active_branch`、`sync_spaces`、`poll_interval_sec`、`pull_delete_default`、`push_delete_default`）；僅在開啟 `sandbox_dir`（測試沙盒不寫入全域 config，見 [`coordinator.py:L3130`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）時才以 `state.get("active_branch")` 覆寫。
    - **程式碼修改範例**：
      ```python
      # gdrive_support/service.py:L205-L232
      def _refresh_active_branch(self) -> None:
          if self._coordinator is None:
              return
          if self._explicit_config is None:
              try:
                  latest_cfg = load_gdrive_config()
                  self._coordinator.config = latest_cfg
                  self._config = latest_cfg
              except Exception:
                  pass
          # 僅於 sandbox_dir 隔離模式（checkout 不寫入全域 config）下從 state_path 唯讀提取 active_branch，且絕不無鎖觸發 _replay_state_journal
          if self._coordinator.config.sandbox_dir and self._coordinator.state_path.is_file():
              try:
                  from core import vfs
                  raw_state = vfs.read_json(self._coordinator.state_path)
                  if isinstance(raw_state, dict):
                      state_branch = normalize_remote_rel_path(str(raw_state.get("active_branch") or ""))
                      if state_branch and "/" not in state_branch and state_branch != self._coordinator.config.active_branch:
                          updated_cfg = replace(self._coordinator.config, active_branch=state_branch)
                          self._coordinator.config = updated_cfg
                          self._config = updated_cfg
              except Exception:
                  pass
      ```

- [x] **[AUD-02] [🔴 P0 | C1.1 & C3.2 | All-OS] [`gdrive_support/coordinator.py:L1101-L1245`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — `checkout_branch` 異常中斷時於 `finally` 強制改寫 `active_branch` 造成半成品工作樹與雙帳本分裂，且未清理目標分支歷史殘留 Baseline 條目**
  - **問題座標與分類**：[`gdrive_support/coordinator.py:L1155-L1226`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)（`SyncCoordinator.checkout_branch`）｜ `C1.1` 雙軌狀態失步 / `C3.2` 異常回滾損毀 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **先刪後載 + `finally` 無條件改寫分支 (`L1168-L1223`)**：`checkout_branch` 在第 1170-1177 行先將舊分支獨有的本地檔案直接 `abs_local.unlink()` 物理刪除，接著在第 1179-1198 行逐一下載目標分支檔案。若下載途中任一檔案發生網路超時、API 錯誤或遇到雲端不支援的 Google Docs MIME 型別拋出異常，程式跳入 `finally:` 區塊（[`coordinator.py:L1220-L1223`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）**無條件執行 `state["active_branch"] = norm_target` 並寫入 `sync_state.json`**，而第 1225 行的 `_persist_active_branch_to_config(norm_target)` 卻因異常未執行！這導致：
       - 本地工作樹一半是舊分支檔案、一半是新分支檔案（且舊分支獨有檔已被刪除）；
       - `sync_state.json` 記錄為新分支 `norm_target`，但 `config.project.json` 仍記錄為舊分支 `curr_branch`；
       - 下次執行 `sync` 時，未完成下載的舊分支殘留檔會被當作新分支的本地修改上傳覆蓋雲端，或被當作衝突阻斷。
    2. **目標分支舊 Baseline 幽靈條目未清理 (`L1158-L1177`)**：`target_branch_state` 是從 `state["branches"][norm_target]["files"]` 取出的既有字典，但第 1170 行僅針對 `old_tracked_paths - set(target_remote_snap.keys())`（即 `curr_branch` 的基準線）執行 `target_branch_state.pop(rel_p, None)`。若 `norm_target` 先前曾被檢出過，且其原有的某個檔案後來在雲端被刪除（且不在 `curr_branch` 中），該檔案的舊紀錄會永久殘留在 `target_branch_state` 中，導致切換完成後首次 `sync` 誤判為遠端刪除或本地刪除。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 改為「兩階段下載先於刪除（Stage-then-Commit）」：先將所有需要從 `norm_target` 拉取的新增/變更檔案下載並更新 `new_target_branch_state`（且全程配合 `_record_branch_file_upsert` / `_record_branch_file_delete` 寫入 WAL Journal）；僅當所有目標檔案皆成功就位後，才刪除 `old_tracked_paths - set(target_remote_snap.keys())` 的孤兒檔。
      2. 將 `target_branch_state` 重建為精確對應 `target_remote_snap` 的新字典（清除任何不在 `target_remote_snap` 中的歷史殘留鍵），且僅在 `try` 塊完整成功後才將 `state["active_branch"]` 與 `config` 同步更新為 `norm_target`；若中途失敗，保持 `state["active_branch"] = curr_branch` 並記錄已實際落盤之檔案狀態。
    - **程式碼修改範例**：
      ```python
      # gdrive_support/coordinator.py:L1158-L1226
      new_target_branch_state: Dict[str, Any] = {}
      fp_cache = state.setdefault("fingerprint_cache", {})
      removed_orphans: List[str] = []
      pulled_files: List[str] = []

      # Phase 1: 先下載並驗證所有目標分支檔案（失敗時尚未刪除任何 curr_branch 獨有檔，且不切換 active_branch）
      for rel_p, rem_entry in sorted(target_remote_snap.items()):
          abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
          if abs_local is None:
              continue
          loc_existing = local_snap.get(rel_p)
          if loc_existing is None or loc_existing.md5 != rem_entry.md5:
              should_backup = bool(
                  abs_local.is_file()
                  and loc_existing is not None
                  and loc_existing.md5 != rem_entry.md5
                  and (backup or rel_p not in curr_base)
              )
              if should_backup:
                  _create_conflict_backup(abs_local)
              self.transport.download_file(
                  self._repo_rel(f"{norm_target}/{rel_p}"),
                  abs_local,
                  entry_hint=target_raw_entries.get(rel_p),
              )
              pulled_files.append(rel_p)

          md5_hex, sha_hex, sz = compute_local_hashes(abs_local)
          st = abs_local.stat()
          mtime_ns = int(st.st_mtime_ns)
          fp_cache[abs_local.as_posix()] = {
              "mtime_ns": mtime_ns,
              "size": sz,
              "md5": md5_hex,
              "sha256": sha_hex,
          }
          new_base = FileEntry(
              rel_path=rel_p,
              md5=md5_hex,
              sha256=sha_hex,
              size=sz,
              mtime_ns=mtime_ns,
              file_id=rem_entry.effective_file_id(),
              is_shortcut=rem_entry.is_shortcut,
              target_file_id=rem_entry.target_file_id,
          )
          new_target_branch_state[rel_p] = new_base.to_dict()

      # Phase 2: 目標檔案全數下載成功後，清理舊分支獨有之孤兒檔案
      old_tracked_paths = set(curr_base.keys())
      for rel_p in sorted(old_tracked_paths - set(target_remote_snap.keys())):
          abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
          if abs_local and abs_local.is_file():
              if backup:
                  _create_conflict_backup(abs_local)
              abs_local.unlink()
              removed_orphans.append(rel_p)

      # Phase 3: 原子提交新分支 Baseline 與 active_branch
      state.setdefault("branches", {})[norm_target] = {"files": new_target_branch_state}
      state["active_branch"] = norm_target
      state.pop("remote_repo_cache", None)
      self._save_local_state(state)
      self._persist_active_branch_to_config(norm_target)
      self.config = replace(self.config, active_branch=norm_target)
      ```

- [x] **[AUD-03] [🔴 P0 | C1.1 & C1.3 | All-OS] [`gdrive_support/coordinator.py:L1642-L1651, L2563-L2637, L3031-L3082`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — Level 1 增量快取 (`_try_incremental_remote_cache`) 在 Stage 3 發生寫入異常或背景讓位時提前覆寫 `state["remote_repo_cache"]` 卻未推進 `page_token`，且同批次新增後修改同一檔案時漏更逆向索引導致快取失真**
  - **問題座標與分類**：[`gdrive_support/coordinator.py:L1642-L1651, L2602-L2618, L3031-L3082`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)（`_execute_stage3_reconciliation`, `_try_incremental_remote_cache`, `_apply_incremental_file_ops`）｜ `C1.1` 雙軌狀態失步 / `C1.3` 快取與持久化失步 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **Stage 1 提前突變 `remote_repo_cache` 與 Stage 3 條件式推進 `page_token` 不對稱 (`L2603-L2617` vs `L1642-L1650`)**：在 Stage 1 的 `_try_incremental_remote_cache()`（[`coordinator.py:L2603-L2617`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）中，程式直接原地修改了 `cache["branches"]`、`cache["known_folder_ids"]`、`cache["folder_meta"]` 與 `cache["repo_meta"]`，但將 `new_token` 作為 `pending_page_token` 留到 Stage 3 `finally` 區塊（[`coordinator.py:L1642-L1650`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）才寫入 `cache_obj["page_token"]`。若 Stage 3 因為 `report.yielded == True`（背景讓位）或 `first_push_err / first_pull_err` 發生錯誤，第 1646-1648 行會跳過更新 `cache_obj["page_token"]`（保留舊 `page_token`），但第 1652 行 `self._save_local_state(state)` **卻把已經套用過增量變更的 `cache["branches"]` 與 `cache["folder_meta"]` 寫入了磁碟**！下一輪同步重跑舊 `page_token` 時，`_register_incremental_new_subfolder`（[`coordinator.py:L2901`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）或 `_is_new_branch_file_valid`（[`coordinator.py:L3026`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）發現該資料夾或檔案已存在於 `b_dirs` / `raw_entries` 中，或是已經執行過 `_remove_incremental_folder_subtree`，導致增量校驗異常或狀態錯亂。
    2. **多分支同名 `parent_id` 迴圈誤用 `break` 與逆向索引未即時更新 (`L3053-L3081`)**：在 `_apply_incremental_file_ops` 新增分支檔案時（[`coordinator.py:L3080`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)），寫入 `b_data["raw_entries"][rel_p]` 後未同步更新 `ctx.file_id_to_branch_paths` 與 `ctx.target_id_to_shortcuts`。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 在 `_try_incremental_remote_cache()` 中，當 `list_changes(page_token)` 驗證並套用至 `cache["branches"]` 與 `cache["repo_meta"]` 時，因為 `remote_repo_cache` 代表的是「雲端遠端快照快取」（與本地 Stage 3 是否讓位無關），一旦 `cache["branches"]` 更新，應原子同步更新 `cache["page_token"] = new_token`；若 Stage 3 發生未知的遠端傳輸失敗（`first_push_err is not None`），則在 `finally` 直接使 `state.pop("remote_repo_cache", None)` 失效，確保 `cache["branches"]` 與 `cache["page_token"]` 永遠 100% 處於同一時間點世代。
      2. 在 `_apply_incremental_file_ops()` 新增項目時同步維護 `ctx.file_id_to_branch_paths` 與 `ctx.target_id_to_shortcuts`。
    - **程式碼修改範例**：
      ```python
      # gdrive_support/coordinator.py:L2602-L2618 (於 _try_incremental_remote_cache 內原子提交 cache 狀態與 page_token)
      assert isinstance(cache, dict)
      cache["branches"] = ctx.cache_branches
      cache["page_token"] = new_token
      if ctx.folder_patched:
          cache["known_folder_ids"] = sorted(ctx.known_folder_ids)
          cache["folder_meta"] = ctx.folder_meta
      ...
      # gdrive_support/coordinator.py:L1642-L1651 (於 _execute_stage3_reconciliation finally 中：若 push 發生異常則淘汰遠端快取避免半套狀態)
      if first_push_err is not None:
          state.pop("remote_repo_cache", None)
      self._save_local_state(state)
      ```

---

### 🟠 P1 - High（顯著缺陷：正則截斷失真 / 雙軌狀態機分歧 / 違反 CQS / 連線洩漏 / $O(\text{Branches} \times \text{Files})$ 掃描風暴）

- [x] **[AUD-04] [🟠 P1 | C1.1 & C2.1 | All-OS] [`agents_workflow/compiler.py:L34, L39, L198-L199, L717, L797-L805, L1039-L1095`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) & [`agents_workflow/plans/verifier.py:L367-L380`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) — `ArtifactCompiler` 與 `PlanVerifier` 對四反引號巢狀 Code Fence（````markdown ... ```python ... ````）及雙反引號行內 Code Span（`` `` `__@{TOKEN}__` `` ``）發生正則非貪婪截斷與誤展開**
  - **問題座標與分類**：[`agents_workflow/compiler.py:L34, L39, L198-L199, L717, L797-L805, L1039-L1095`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)、[`agents_workflow/plans/verifier.py:L367-L380`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk)、[`agents_workflow/plans/_verifier_specs.py:L87, L150, L205`](https://drive.google.com/file/d/1nR2-PHMs8JO6AYi_Rni_VoC7z84PQHUy/view?usp=drivesdk) ｜ `C1.1` 語法狀態機邊界 / `C2.1` 退化輸入 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **巢狀 Code Fence 提前截斷**：[`compiler.py:L34`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 的 `FENCED_CODE_BLOCK_REGEX = re.compile(r"```[\s\S]*?```")` 僅匹配固定 3 個反引號。當 Markdown 規範或技能手冊使用 4 個反引號（```` ````markdown ````）包裹內含 3 個反引號（```` ```python ````）的範例區塊時，`FENCED_CODE_BLOCK_REGEX` 會在開頭第 2~4 個反引號與內層第一個 ```` ```python ```` 之間提前閉合，留下開頭第 1 個孤立反引號 `` ` `` 在外層，並將 ```` ```python ```` 內部誤判為「非 Fenced Code Block 的普通正文」，導致後續 `MD_LINK_BACKTICK_CLEAN_REGEX`（[`compiler.py:L1095`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）誤刪程式碼塊內的反引號。同理，[`verifier.py:L373`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) 與 [`_verifier_specs.py:L150, L205`](https://drive.google.com/file/d/1nR2-PHMs8JO6AYi_Rni_VoC7z84PQHUy/view?usp=drivesdk) 使用 `if l.strip().startswith("```"): in_code_block = not in_code_block`，遇到 4 反引號包裹 3 反引號時會把內層程式碼範例誤判為正文，進而誤報 `PLACEHOLDER` 或 `HTML_COMMENT` 失敗。
    2. **多反引號行內 Code Span 破音**：[`compiler.py:L39`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 的 `CODE_SPAN_REGEX = re.compile(r"(`[^`\r\n]+`)")` 無法匹配雙反引號行內語法（如 `` `` `__@{TOKEN}__` `` ``），在 `check_unenclosed_tags`（[`compiler.py:L199`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）中會把左半 `` `` ` `` 當成一個空 Code Span 消掉，使中間的 `__@{TOKEN}__` 暴露在外而誤發 `Unenclosed placeholder tag` 告警；且在 `_replace_inline`（[`compiler.py:L799`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）與 `_replace_in_code_span`（[`compiler.py:L1055`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）寫死 `inner = span_text[1:-1]`，只剝除單層反引號。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 使用 CommonMark 對稱反引號反向引用正則：`FENCED_CODE_BLOCK_REGEX = re.compile(r"^[ \t]*(`{3,})[^\r\n]*\r?\n[\s\S]*?^[ \t]*\1`*[ \t]*(?=\r?\n|\Z)", re.MULTILINE)`（或保留行內單行 fence 回退），以及 `CODE_SPAN_REGEX = re.compile(r"(`+)([^`\r\n]|(?!(?<!`)\1(?!`))`)+?\1")`。
      2. 在剝離行內 Code Span 外殼時，依開頭連續反引號長度 `ticks = len(match.group(1))` 動態取 `inner = span_text[ticks:-ticks]`。
      3. 在 `verifier.py` 與 `_verifier_specs.py` 追蹤開頭 fence 的反引號數量 `fence_len`，僅當遇到行首反引號數 `>= fence_len` 且無資訊字串時才關閉 `in_code_block`。
    - **程式碼修改範例**：
      ```python
      # agents_workflow/compiler.py:L34-L40
      FENCED_CODE_BLOCK_REGEX = re.compile(
          r"(?:^[ \t]*(`{3,})[^\r\n]*\r?\n[\s\S]*?^[ \t]*\1`*[ \t]*(?=\r?\n|\Z)|(`{3,})[\s\S]*?\2)",
          re.MULTILINE,
      )
      CODE_SPAN_REGEX = re.compile(r"(`+)(?!`)(.*?[^`])\1(?!`)")
      ```

- [x] **[AUD-05] [🟠 P1 | C9.2 (A2) & C1.1 | All-OS] [`agents_workflow/compiler.py:L58-L75, L233-L379`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)、[`agents_workflow/publisher.py:L401-L467`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)、[`agents_workflow/plans/_common.py:L12-L53, L264-L343`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) & [`agents_workflow/initializer.py:L59-L97`](https://drive.google.com/file/d/1rpSQmdCVrwVMOhOtB1i9tdoUU6x59U7d/view?usp=drivesdk) — 目標投影路徑與 `workflow.*://` 退避解析散落 4 處各自獨立實作，導致預設目錄（`.agents/templates` vs `.agents/.yscb/templates`）、副檔名替換與多 Target 行為不一致**
  - **問題座標與分類**：[`agents_workflow/publisher.py:L423-L467`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)、[`agents_workflow/plans/_common.py:L264-L343`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk)、[`agents_workflow/compiler.py:L58-L75`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)、[`agents_workflow/initializer.py:L59-L97`](https://drive.google.com/file/d/1rpSQmdCVrwVMOhOtB1i9tdoUU6x59U7d/view?usp=drivesdk)、[`agents_workflow/roadmap.py:L51-L60`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) ｜ `C9.2 (A2)` 平行實作分歧 / `C1.1` 雙軌失步 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **投影路徑兩套計算器分歧**：
       - 在 [`publisher.py:L423-L430`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)（`ReleasePublisher.build_deployment_map`）中，當自訂 `release_target` 未宣告特定 `proj_rule` 時，非 skill 資產的預設目錄為 `project://.agents/{sub_folder}`（即 `.agents/templates`，不含 `.yscb`）；且對非 skill 檔案會套用 `proj_rule.get("extension", ".md")` 替換副檔名（[`publisher.py:L465`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)）。
       - 在 [`plans/_common.py:L278, L322-L340`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk)（`resolve_active_target_projected_path`）中，預設目錄卻寫為 `.agents/.yscb/{singular_type}s`（含 `.yscb`），且當 `proj_cfg` 存在但未設定 `target_dir` 時直接退回 `.agents/.yscb/...`，同時**完全忽略 `proj_cfg.get("extension")` 欄位**！若某個 Target 將 `template` 的 `extension` 設為 `.mdc` 或 `.prompt.md`，`ReleasePublisher` 會發布為 `.mdc`，但 `PlanVerifier._build_next_phase_hint`（[`verifier.py:L889`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk)）卻仍透過 `resolve_active_target_projected_path` 指引 Agent 去讀取不存在的 `.md` 路徑！
    2. **`workflow.*://` 退避解析四套邏輯**：[`compiler.py:L58-L74`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)、[`_common.py:L12-L53`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk)、[`initializer.py:L59-L96`](https://drive.google.com/file/d/1rpSQmdCVrwVMOhOtB1i9tdoUU6x59U7d/view?usp=drivesdk) 與 [`roadmap.py:L51-L60`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) 各自手寫 `workflow.*://` 的 fallback 解析；其中只有 `roadmap.py:L56-L57` 額外退避探測 `base / "roadmap"`，而 `compiler.py` 卻寫死 `("plans", "roadmap")`。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 將單一項目之 Target 投影規則解析抽取為共通純函式（例如於 `targets.py` 或 `_common.py` 提供 `resolve_target_projection_rule(target_cfg, artifact_type, artifact_name, subpath)`），統一 `.agents/.yscb/{sub_folder}` 預設基準、巨集展開（`{export.name}`, `{export.basename}`, `{target.name}`）與 `extension` 副檔名規則，供 `ReleasePublisher.build_deployment_map` 與 `resolve_active_target_projected_path` 共同調用。
      2. 將 `compiler.py`、`initializer.py`、`roadmap.py` 的 `workflow.*://` 退避解析統一委派至 `plans._common.resolve_plan_uri`。

- [x] **[AUD-06] [🟠 P1 | C9.2 (A2) & C1.1 | All-OS] [`agents_workflow/plans/status.py:L16-L38, L199-L565`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk)、[`agents_workflow/plans/scanner.py:L33-L165, L240-L246`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)、[`agents_workflow/plans/_common.py:L158-L262`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) & [`agents_workflow/plans/_verifier_specs.py:L11-L36`](https://drive.google.com/file/d/1nR2-PHMs8JO6AYi_Rni_VoC7z84PQHUy/view?usp=drivesdk) — `plans/` 尚未收斂至單一狀態機，`PlanScanner`、`PlanStatusResolver` 與 `evaluate_plan_completion` 對「附掛未完成 `revision_log.md`」、「Umbrella 狀態」與「`"passed"` 完成度」判定互相矛盾**
  - **問題座標與分類**：[`agents_workflow/plans/scanner.py:L33-L165, L240-L246`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)、[`agents_workflow/plans/status.py:L36, L199-L315`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk)、[`agents_workflow/plans/_common.py:L176-L262`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) ｜ `C9.2 (A2)` 多套平行狀態機分歧 / `C1.1` 邏輯契約失步 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **附掛 `revision_log.md` 在 `scanner` vs `archiver` 矛盾**：當一個已結案的 Full Track（`P07` 為 `Completed`）或 Fast Track（`fast_track_plan.md` 為 `Completed`）計畫新增了 `revision_log.md`（狀態為 `In Progress`）進行後續修訂時：
       - [`PlanStatusResolver.resolve_next_action`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk)（`status.py:L256, L299`）與 [`evaluate_plan_completion`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk)（`_common.py:L203-L209`）會將該計畫視為「修訂進行中（未完成）」。
       - 但 [`PlanScanner.get_plan_info`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)（`scanner.py:L138-L149`）在命中 `ft_plan.exists()` 或 `p01_req.exists()` 分支後，完全未檢查 `_has_active_attached_revision(plan_dir)`，直接回傳 `status = "Completed"`！
       - 結果：執行 `yscb agents-workflow plan status` 時，[`scanner.py:L240-L245`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk) 誤將該計畫列為已結案並輸出 `[HINT] 偵測到 1 個已結案計畫，可執行 python yscb.py agents-workflow plan archive ... 歸檔`；當開發者照提示執行 `plan archive` 時，[`archiver.py:L108`](https://drive.google.com/file/d/1Rin77sqznCMYxaFoPalyAtH_AkZLrnFG/view?usp=drivesdk) 呼叫 `evaluate_plan_completion` 立即拋出 `PlanIncompleteError` 自相矛盾！
    2. **Umbrella 空白/未知標頭狀態矛盾**：在 [`scanner.py:L56`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk) 中，若 `umbrella_overview.md` 標頭狀態為 `unknown` 但所有 `sub_*` 子計畫已完成，`_resolve_umbrella_status` 回傳 `"Completed"`；但 [`_common.py:L217`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) 的 `evaluate_plan_completion` 卻要求 `PlanStatusResolver.is_doc_completed(umbrella_overview)` 必須為 `True`，否則拒絕歸檔。
    3. **`COMPLETED_STATUS_SET` 內部不一致**：[`status.py:L36`](https://drive.google.com/file/d/1166eUWKj6YVtGAbYnaYHkq-JZ4YyrTWe/view?usp=drivesdk) 定義 `COMPLETED_STATUS_SET = frozenset({"completed", "concluded", "passed"})`（供 `is_doc_completed` 使用），但同檔案第 205、219、229、255、298、416 行卻手寫 `in ("completed", "concluded")`（漏掉 `"passed"`），導致標記為 `Passed` 的修訂紀錄在 `evaluate_plan_completion` 被視為已完成，但在 `status.py:L205` 被視為未完成。
  - **建議解決方案（Mode A 根因重構 — 手術 `S1`）**：
    - **修改思路**：
      1. 建立單一狀態機入口（或於 `PlanStatusResolver` 統一提供 `evaluate_directory_state(plan_dir)`），讓 `PlanScanner.get_plan_info`、`PlanStatusResolver.resolve_next_action` 與 `evaluate_plan_completion` 共用同一套軌道與附掛修訂檢測邏輯。
      2. 在 `PlanScanner.get_plan_info`（[`scanner.py:L138-L163`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)）中，當主軌道狀態為 `"Completed"` 或 `"Concluded"` 但 `PlanStatusResolver._has_active_attached_revision(plan_dir)` 為 `True` 時，將狀態覆寫為 `"Revising (In Progress)"`，避免誤觸發歸檔提示。
    - **程式碼修改範例**：
      ```python
      # agents_workflow/plans/scanner.py:L160-L164
      if status in ("Completed", "Concluded") and PlanStatusResolver._has_active_attached_revision(plan_dir):
          status = "Revising"
      if (plan_dir / "handoff.md").exists() and status not in ("Completed", "Concluded"):
          status = f"{status} (Paused)"
      return track_type, status
      ```

- [x] **[AUD-07] [🟠 P1 | C9.1 (D1) & C1.1 | All-OS] [`gdrive_support/transport.py:L165, L477-L530, L561-L583, L1440-L1486`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) & [`gdrive_support/coordinator.py:L829, L866-L879, L946-L954`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — 唯讀查詢方法 (`transport.list_files`, `LocalSandboxTransport.get_entry`, `SyncCoordinator.list_branches`) 仍夾帶暗中將雲端重複檔移入垃圾桶、改寫根目錄 `README.md` 與初始化空倉庫之寫入副作用（違反 CQS）**
  - **問題座標與分類**：[`gdrive_support/transport.py:L165, L477-L530, L561-L583, L1440-L1486`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)、[`gdrive_support/coordinator.py:L829, L866-L879, L946-L954`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) ｜ `C9.1 (D1)` 違反 CQS 與隱藏副作用 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **`transport.list_files` 預設 `deduplicate=True` 暗中刪除遠端重複檔**：雖然 CLI `scripts/cli.py:ls`（[`cli.py:L319`](https://drive.google.com/file/d/1zT7-jSaAJy0pjw5dJ9nMUMTRZbpJ4eZc/view?usp=drivesdk)）已透過 `bool(cmd_bags.options.get("deduplicate"))` 傳入 `False`，但底層 [`AbstractSyncTransport.list_files`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)（`L165`）、[`LocalSandboxTransport.list_files`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)（`L522`）與 [`GoogleDriveApiTransport.list_files`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)（`L1445`）的簽名預設值卻仍是 `deduplicate: bool = True`！這導致任何未顯式傳入 `deduplicate=False` 的呼叫端一旦呼叫 `list_files()`，在 `GoogleDriveApiTransport`（[`transport.py:L1466-L1484`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)）中就會對同名舊檔直接發送 `PATCH {"trashed": True}` 移入雲端垃圾桶！
    2. **`LocalSandboxTransport.get_entry` 無條件觸發全沙盒去重搬移與寫盤**：在 [`transport.py:L572-L573`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) 中，唯讀的 `get_entry()` 無條件呼叫 `_sync_filesystem_into_meta(persist=True)` 與 `_deduplicate_same_path_items(meta)`，使得單純查詢或下載單一檔案（`gdrive get`）也會暗中改寫 `.yscb_sandbox_meta.json` 並將沙盒中其他目錄的同名檔案搬入 `.trash/`。
    3. **唯讀 `gdrive branch list` (`tier: "safe"`) 暗中改寫雲端根目錄 `README.md`、`.yscb_gdrive.json` 並建立雲端目錄**：在 [`coordinator.py:L946-L954`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) 中，`list_branches()` 直接呼叫 `self._ensure_remote_repo_initialized()`（[`coordinator.py:L859-L880`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)），在無鎖狀態下不僅呼叫 `reconcile_root_readme()` 改寫雲端根目錄 `README.md`、呼叫 `_reconcile_unregistered_cloud_branches()` 覆寫雲端 `.yscb_gdrive.json`，甚至當雲端 `<repo>/` 為空時自動呼叫 `_bootstrap_remote_repo()` 建立 4 個資料夾與 2 個檔案！
  - **建議解決方案（Mode A 根因重構 — 手術 `S4`）**：
    - **修改思路**：
      1. 在 `LocalSandboxTransport.get_entry()` 與 `get_entry_by_id()` 中移除 `self._deduplicate_same_path_items(meta)`，改為在記憶體中按 `(mtime_ns, file_id)` 降序挑選最新項目回傳而不搬移檔案。
      2. 將 `SyncCoordinator.list_branches()` 改為唯讀查詢：讀取 `_read_remote_repo_meta()` 並在記憶體中合併 `list_files(repo_prefix, recursive=False, deduplicate=False)` 發現的未註冊分支目錄，不執行 `reconcile_root_readme()`、不寫回 `.yscb_gdrive.json`、亦不在空目錄時自動 `_bootstrap_remote_repo()`（若未初始化則拋出 `GDriveRepoUninitializedError` 提示執行 `gdrive init`）。

- [x] **[AUD-08] [🟠 P1 | C9.2 (D5) & C9.3 (A3) | All-OS] [`agents_workflow/publisher.py:L41-L42, L1005-L1051, L1376-L1396`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) & [`agents_workflow/roadmap.py:L19-L30`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) — 生產代碼殘留白箱測試 Mock 嗅探後門 (`hasattr(..., "assert_called")`、`_STDLIB_WRITE_TEXT`)，`release_manifest.json` 儲存裸絕對路徑破壞跨環境可攜性，且 `ensure_jit_release` 時間桶忽略 `assets/` 變更**
  - **問題座標與分類**：[`agents_workflow/publisher.py:L1029-L1050, L1376-L1396`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)、[`agents_workflow/roadmap.py:L19-L30`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) ｜ `C9.2 (D5)` 測試嗅探後門 / `C9.3 (A3)` 雙帳本格式分裂 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **殘留兩處 D5 測試嗅探後門**：
       - [`publisher.py:L1376-L1378`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)：`orig_method = getattr(ReleasePublisher.release_all, "__name__", "") == "release_all" and not hasattr(ReleasePublisher.release_all, "assert_called")` 為迎合 [`tests/test_publisher.py:L566`](https://drive.google.com/file/d/1al8f1PFxkUG54uQTF9BySbx8EI5UJmCs/view?usp=drivesdk) 的 `patch.object(ReleasePublisher, "release_all")` 而在生產代碼嗅探 `unittest.mock` 的 `assert_called` 屬性！
       - [`roadmap.py:L19-L27`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk)：`if Path.write_text is not _STDLIB_WRITE_TEXT:` 為迎合測試對 `Path.write_text` 的 monkeypatch 而在生產代碼嗅探類別方法指標！
    2. **`project_release_manifest.json` vs `release_manifest.json` 路徑格式不對稱 (`publisher.py:L1006` vs `L1030`)**：`project_release_manifest.json` 透過 `self._to_project_uri(f, eff_proj_root)` 儲存 `project://...` 語意相對路徑，但 `release_manifest.json`（Local 層級）在第 1030 行卻寫為 `sorted_local_files = sorted(list(eff_pre_local.keys()))`（儲存宿主機裸絕對路徑）！當專案資料夾移動、容器掛載路徑改變或跨平台同步時，`_check_short_circuit`（[`publisher.py:L688-L691`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)）與 `_prune_orphaned_managed_files`（[`publisher.py:L900-L902`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)）無法將舊絕對路徑映射至當前 `proj_root`，導致過期 Local Target 檔案殘留無法清理。
  - **建議解決方案（Mode A 根因重構 — 手術 `S2`）**：
    - **修改思路**：
      1. 在 [`publisher.py:L1030`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 將 `sorted_local_files` 改為 `sorted(self._to_project_uri(f, eff_proj_root) for f in eff_pre_local.keys())`，使雙軌 Manifest 100% 統一使用 `project://` 語意 URI。
      2. 移除 [`publisher.py:L1376-L1379`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 的 `hasattr(..., "assert_called")` 與 [`roadmap.py:L19-L27`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) 的 `_STDLIB_WRITE_TEXT` 嗅探，並同步更新對應單元測試。

- [x] **[AUD-09] [🟠 P1 | C1.2 & C2.1 | All-OS] [`agents_workflow/plans/_trace_parser.py:L37-L57`](https://drive.google.com/file/d/1ITixBZPq-ywiyFnsb2entMqeCqhq567_/view?usp=drivesdk) & [`agents_workflow/plans/session_trace.py:L374-L461, L718-L738`](https://drive.google.com/file/d/1iisQ2clxlUuxO_hUzPCX6g5vSHscOnqg/view?usp=drivesdk) — `_parse_ts` 將 `changelog.md` 之無時區本地時間 (`datetime.now()`) 強制替換為 `timezone.utc`，在非 UTC 時區產生數小時偏移，導致 `SessionTraceEngine` 誤判歷史會話並丟棄活躍計畫**
  - **問題座標與分類**：[`agents_workflow/plans/_trace_parser.py:L37-L57`](https://drive.google.com/file/d/1ITixBZPq-ywiyFnsb2entMqeCqhq567_/view?usp=drivesdk)（`_parse_ts`）、[`agents_workflow/plans/session_trace.py:L374-L461, L718-L738`](https://drive.google.com/file/d/1iisQ2clxlUuxO_hUzPCX6g5vSHscOnqg/view?usp=drivesdk)（`_parse_changelog_metadata`, `audit_plan_mtimes`, `analyze`）｜ `C1.2` 跨模組時間戳時區契約錯位 / `C3.3` 假陽性/假陰性守門 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **Python 3.11+ `fromisoformat` 吃掉無時區本地時間並誤貼 UTC 標籤**：[`_verifier_healer.py:L41, L335`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk) 寫入 `changelog.md` 的時間戳為 `datetime.now().strftime("%Y-%m-%d %H:%M")`（**本地時區 Naive 時間**，如台灣 `UTC+8` 的 `2026-11-09 19:26`）。然而在 [`_trace_parser.py:L45-L48`](https://drive.google.com/file/d/1ITixBZPq-ywiyFnsb2entMqeCqhq567_/view?usp=drivesdk) 中：
       ```python
       dt = datetime.fromisoformat(s)
       if dt.tzinfo is None:
           dt = dt.replace(tzinfo=timezone.utc)
       return dt.timestamp()
       ```
       因為 `datetime.fromisoformat("2026-11-09 19:26")` 在 Python 3.11+ 直接解析成功（使得下方第 51-56 行的 `strptime` 迴圈淪為 100% 死代碼！），接著 `if dt.tzinfo is None:` 竟將這個本地時間直接 `replace(tzinfo=timezone.utc)` 當作 UTC 時間換算為 epoch 秒數！
    2. **在 `UTC+8` 下偏移 +28,800 秒引發連鎖故障**：
       - 在 [`session_trace.py:L718-L725`](https://drive.google.com/file/d/1iisQ2clxlUuxO_hUzPCX6g5vSHscOnqg/view?usp=drivesdk) 中，當傳入 `--transcript` 時，`tier1_last_ts` 是含 `Z` 的真實 UTC 時間，而 `plan_earliest_ts` 來自 `changelog.md`（被 `_parse_ts` 誤加了 8 小時），導致 `(ep_t1_end + 600.0) < ep_plan_start` **永遠為真**，`analyze()` 直接誤判為 `[Historical Session Prior to Active Plan]` 並將 `plan_dir = None` 清空，跳過 `audit_plan_mtimes`！
       - 在 [`session_trace.py:L431-L437`](https://drive.google.com/file/d/1iisQ2clxlUuxO_hUzPCX6g5vSHscOnqg/view?usp=drivesdk) 中，`baseline_time = phase_epochs.get(earliest_later_code, earliest_later_mtime)` 將被誤加 8 小時的 `phase_epochs` 與真實 UTC 的檔案 `p_mtime` 比較，導致 `p_mtime > (baseline_time + 5.0)` 在 `UTC+8` 下永遠不成立（`SILENT_BACKPATCH` 完全漏報），而在 `UTC-5`（美東）下則因 `baseline_time` 少算 5 小時而大規模誤報！
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：在 `_parse_ts` 中區分 ISO-8601（含 `T` 或顯式時區偏移 `Z`/`+`/`-`）與 `changelog.md` 本地格式（`YYYY-MM-DD HH:MM(:SS)`，無 `T` 且無時區）：僅當字串含 `T`（如無尾端 `Z` 之 UTC transcript 時間戳）時才預設 `timezone.utc`，而對 `YYYY-MM-DD HH:MM(:SS)` 保持本地時區（`dt.timestamp()` 在 Python 中對 naive `datetime` 自動按系統本地時區轉換為真實 UTC epoch）。
    - **程式碼修改範例**：
      ```python
      # agents_workflow/plans/_trace_parser.py:L37-L57
      def _parse_ts(ts_str: str) -> Optional[float]:
          """解析 ISO-8601 (UTC/Offset) 或 YYYY-MM-DD HH:MM(:SS) (本地時間) 字串為真實 UTC epoch 秒數。"""
          if not ts_str:
              return None
          s = ts_str.strip()
          for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
              try:
                  return datetime.strptime(s, fmt).timestamp()
              except ValueError:
                  continue
          try:
              if s.endswith("Z"):
                  s = s[:-1] + "+00:00"
              dt = datetime.fromisoformat(s)
              if dt.tzinfo is None:
                  dt = dt.replace(tzinfo=timezone.utc)
              return dt.timestamp()
          except Exception:
              return None
      ```

- [x] **[AUD-10] [🟠 P1 | C7.1 | All-OS] [`agents_workflow/compiler.py:L567-L575, L939-L941, L968-L970`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) & [`agents_workflow/publisher.py:L260-L264, L1175`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) — `_read_and_cache_physical_file` 對每個來源檔重複計算零引用的 SHA-256，且 `ReleasePublisher.release_all` 在 Stage 1 無條件將 45+ 個中繼檔寫入 `cache://` 磁碟卻從不讀取**
  - **問題座標與分類**：[`agents_workflow/compiler.py:L567-L575, L876-L994`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)、[`agents_workflow/publisher.py:L260-L264, L1175`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) ｜ `C7.1` 迴圈內重複計算與無用磁碟 I/O ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **100% 丟棄的雙重雜湊計算**：在 [`compiler.py:L569-L575`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 與 [`publisher.py:L261-L263`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 中，每次讀取來源檔案都同時計算 `hashlib.sha1(norm_bytes).hexdigest()` 與 `hashlib.sha256(norm_bytes).hexdigest()` 並存入 `_source_file_cache` 的第 4 與第 5 欄。然而經全專案檢索確認，所有呼叫端（[`compiler.py:L593, L601, L1138`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) 與 [`publisher.py:L283`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)）皆以 `_` 丟棄第 5 欄 `sha256_hex`！
    2. **無用的 `cache://` 磁碟物化與第二次 SHA-256 計算**：當 `ReleasePublisher.release_all()` 呼叫 `self.compiler.compile_stage1()`（[`publisher.py:L1175`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)）時，`compile_stage1()`（[`compiler.py:L940-L941, L969-L970`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）對全系統 45+ 個 skills/standards/templates 逐一執行 `self._write_cache_file(cache_uri, stage1_content)`（每個檔案在 `.cache/agents-workflow/resolved_contents/` 下執行一次 `vfs.write_text(..., atomic=True)` 建立暫存檔並 `os.replace`），並再次計算 `hashlib.sha256(stage1_content.encode("utf-8"))`。然而 `ReleasePublisher._prepare_target_compilations` 只讀取記憶體中的 `it["content"]` 並直接將最終 Stage 2 結果寫入 `.agents/`，從不讀取 `cache://` 下的 skill 與 standard 中繼檔，也從不使用 `it["sha256"]`。
  - **建議解決方案（Mode A 根因重構 — 手術 `S2`）**：
    - **修改思路**：
      1. 從 `_read_and_cache_physical_file` 與 `publisher._get_source_file_sha1` 移除從未使用的 `sha256` 計算，僅保留 `sha1`。
      2. 為 `compile_stage1(materialize_cache: bool = True)` 增加參數：當由 CLI `yscb agents-workflow compile` 單獨呼叫時維持 `materialize_cache=True`；當由 `ReleasePublisher.release_all()` 呼叫時傳入 `materialize_cache=False`（完全在記憶體中傳遞 `stage1_content`，省去每輪發布 45+ 次無謂的 `.cache/` 原子寫檔 I/O）。

- [x] **[AUD-11] [🟠 P1 | C7.1 & C9.3 (D4) | All-OS] [`gdrive_support/coordinator.py:L850, L939, L1030, L1081, L1222, L1486-L1502, L2265-L2272`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — 遠端快取失效時退回 $O(\text{Branches} \times \text{Files})$ 全分支遞迴掃描，且雲端自動發現之分支因永不清除 `auto_discovered` 旗標導致每輪 GC 重複全掃描**
  - **問題座標與分類**：[`gdrive_support/coordinator.py:L850, L1486-L1502, L2265-L2272, L2663-L2668`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) ｜ `C7.1` 演算法複雜度熱點 / `C9.3 (D4)` 假增量與重複掃描風暴 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **Level 2 全分支遞迴掃描風暴 (`L1486-L1502`)**：每當 `create_branch`、`delete_branch`、`checkout_branch` 執行（皆會執行 `state.pop("remote_repo_cache", None)` 清空整個遠端快取），或 `.yscb_gdrive.json` 被外部更新、或任一資料夾改名時，`_collect_remote_stage_snapshot` 退回 Level 2。此時第 1486-1502 行不僅掃描當前活躍分支 `branch`，還對 `meta["branches"]` 中的**所有其他歷史分支 `other_b` 逐一執行 `_scan_remote_branch_with_dirs(other_b)` 全樹遞迴 API 掃描**（即使 `.yscb_gdrive.json` 的 `meta["branch_files"][other_b]` 已經完整記載了該分支的檔案 ID 映射）！當倉庫累積 10 個分支、每個分支 200 個資料夾時，單次 `sync` 會觸發上千次 Google Drive `files.list` HTTP 請求。
    2. **`auto_discovered` 旗標永不收斂導致每輪 Stage 3 GC 重複掃描 (`L850, L2265-L2272`)**：`_reconcile_unregistered_cloud_branches`（[`coordinator.py:L850`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）將雲端新建分支標記為 `"auto_discovered": True`。但在該分支已被掃描並寫入 `meta["branch_files"][b_name]` 後，程式**從未將 `"auto_discovered"` 設回 `False`**！結果在 `_gc_unreferenced_history_files`（[`coordinator.py:L2267-L2272`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）中，因為 `if is_auto or b_name not in branch_files_map:` 恆為 `True`，每一輪同步的 Stage 3 都會把所有 `auto_discovered` 分支再從頭到尾遞迴掃描一遍！
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 在 `_collect_remote_stage_snapshot`（[`coordinator.py:L1486-L1502`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）與 `_gc_unreferenced_history_files`（[`coordinator.py:L2265-L2272`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）中，一旦某個 `auto_discovered` 分支完成首次 `_scan_remote_branch_with_dirs` 並填入 `branch_files_map[b_name]`，立即將 `meta["branches"][b_name].pop("auto_discovered", None)`（或設為 `False`）並標記 `stage1_meta_dirty = True`。
      2. 在 `create_branch`、`delete_branch` 與 `checkout_branch` 中，直接增量更新 `state["remote_repo_cache"]["branches"]` 與 `repo_meta`（或僅在 Level 2 掃描當前 `active_branch` 及尚未具備 `branch_files` 紀錄的新分支），避免每次切換或增刪分支都觸發全倉庫所有分支重掃。

- [x] **[AUD-12] [🟠 P1 | C3.2 & C7.2 | All-OS] [`gdrive_support/transport.py:L1030-L1123, L1384-L1393, L1705-L1716`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) & [`gdrive_support/coordinator.py:L533-L550, L1005-L1020, L1909-L1980, L2014-L2081`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — `SyncCoordinator` 並發執行緒池結束後未歸還 `GoogleDriveApiTransport` 之執行緒局部 `HTTPSConnection`，導致跨批次連線重用失效與背景常駐服務 TLS Socket / `_tls_conn_dicts` 持續洩漏**
  - **問題座標與分類**：[`gdrive_support/transport.py:L1030-L1123, L1705-L1716`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)、[`gdrive_support/coordinator.py:L533-L550, L1005-L1020, L1909-L1980, L2014-L2081`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) ｜ `C3.2` 非確定性資源釋放 / `C7.2` 無界記憶體與句柄增長 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **連線池歸還機制僅做半套**：`GoogleDriveApiTransport._get_https_conn`（[`transport.py:L1059-L1075`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)）將每個執行緒建立的 `HTTPSConnection` 存入 `self._tls.conns` 並將字典引用加入 `self._tls_conn_dicts` 清單（`L1065`），設計上依賴短命工作執行緒結束前呼叫 `_release_thread_conns_to_pool()`（`L1077-L1086`）將連線歸還至 `self._conn_pool`。然而全程式庫只有 `_resolve_shortcut_targets`（[`transport.py:L1374`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)）呼叫了 `_release_thread_conns_to_pool()`！
    2. **`Coordinator` 四處 `ThreadPoolExecutor` 100% 漏歸還連線**：在 `SyncCoordinator` 的 `_precreate_remote_dirs`（`L533`）、`create_branch`（`L1005`）、`_execute_push_batch`（`L1909`）與 `_execute_pull_batch`（`L2014`）中，每次皆建立全新的 `ThreadPoolExecutor(max_workers=8)` 執行遠端 API 呼叫，結束後執行緒銷毀卻**從未呼叫 `transport._release_thread_conns_to_pool()`**！這導致：
       - 前一批次（如 `_precreate_remote_dirs`）建立的 8 條 TLS Keep-Alive 連線永遠留在已銷毀執行緒的 `conns` 字典中，下一批次（如 `_execute_push_batch`）的 8 個新執行緒完全無法從 `_conn_pool` 取出連線，被迫重新進行 TCP + TLS 握手；
       - 在長駐的 `GDriveSyncServiceWorker`（`self._owned_transport` 常駐不關閉）中，`self._tls_conn_dicts` 清單隨每一輪同步無上限增長，且其內部持有的 `HTTPSConnection` Socket 永遠不會關閉，造成 FD 與記憶體雙重洩漏！
  - **建議解決方案（Mode A 根因重構 — 手術 `S4`）**：
    - **修改思路**：
      1. 在 `AbstractSyncTransport` 新增預設空操作之 `release_thread_resources()` 方法，並於 `GoogleDriveApiTransport.release_thread_resources()` 內呼叫 `self._release_thread_conns_to_pool()`，同時在歸還時將空字典從 `self._tls_conn_dicts` 移除以防無界累積。
      2. 在 `SyncCoordinator` 的所有 `ThreadPoolExecutor` 任務包裝函式（`_precreate_remote_dirs`, `create_branch`, `_upload_single_push_task`, `_download_single_pull_task`）的 `finally` 區塊中統一呼叫 `self.transport.release_thread_resources()`。
    - **程式碼修改範例**：
      ```python
      # gdrive_support/transport.py:L1077-L1086
      def release_thread_resources(self) -> None:
          self._release_thread_conns_to_pool()

      def _release_thread_conns_to_pool(self) -> None:
          conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
          if not conns:
              return
          with self._conn_lock:
              for host, conn in list(conns.items()):
                  conns.pop(host, None)
                  self._conn_pool.setdefault(host, []).append(conn)
      ```

- [x] **[AUD-13] [🟠 P1 | C7.1 & C7.2 | All-OS] [`gdrive_support/transport.py:L296-L357, L416-L444, L894-L1000`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) — `LocalSandboxTransport` 每次單點操作皆執行全樹 `os.walk`，且 `_build_entry` 忽視既有元數據對每個實體檔重複計算全文 MD5 + SHA-256**
  - **問題座標與分類**：[`gdrive_support/transport.py:L296-L357, L416-L444, L894-L1000`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk)（`LocalSandboxTransport._sync_filesystem_into_meta`, `_build_entry`, `_capture_change_snapshot`）｜ `C7.1` 迴圈內重複全量 I/O 與雜湊計算 / `C7.2` 序列化膨脹 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. **`_build_entry` 無視快取每次重算全文 MD5 + SHA-256 (`L416-L420, L437-L440`)**：在 `LocalSandboxTransport._build_entry` 中，只要項目不是虛擬項目，無論 `info` 字典內是否已經存有對應 `mtime_ns` 與 `size` 的 `md5`，第 418 行與第 439 行都會無條件呼叫 `compute_local_hashes(phys)` **重讀整個實體檔案並同時計算 MD5 與 SHA-256**（且 SHA-256 算完即以 `_` 丟棄）！
    2. **單次 `sync` 觸發數倍全庫檔案雜湊重讀**：在 `get_start_page_token()`（`L960`）與 `list_changes()`（`L967`）中，每次都會先跑一次全沙盒 `os.walk`（`_sync_filesystem_into_meta`），再透過 `_capture_change_snapshot` 對 `items` 內的**每一個分支檔案、每一個 Shortcut 與每一個 `.history/` 檔案呼叫 `_build_entry`**，導致沙盒內所有檔案在單次同步中被整檔讀取並計算 MD5+SHA-256 多達 3~5 次！
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 在 `_build_entry` 中採用 `(mtime_ns, size)` Stat-First 快取比對：先執行一次 `st = phys.stat()`，若 `int(st.st_mtime_ns) == int(info.get("mtime_ns") or 0)` 且 `int(st.st_size) == int(info.get("size") or -1)` 且 `info.get("md5")` 非空，直接沿用 `info["md5"]` 而不重讀檔案內容；若需重算則僅計算 MD5（或寫回 `info`）。

---

### 🟡 P2 - Medium（防禦缺口與結構耦合：巨石類別耦合 / 跨平台路徑邊界 / 相對路徑越界 / 憑證規則錯位）

- [x] **[AUD-14] [🟡 P2 | C9.1 (A1) & C9.3 (A3) | All-OS] [`gdrive_support/coordinator.py:L1-L3171`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) & [`gdrive_support/transport.py:L1-L2197`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) — `coordinator.py` (3,171 行) 與 `transport.py` (2,197 行) 上帝類別混雜多個正交變更軸，且三處同步帳本 (`repo_meta` / `branches[b].files` / `remote_repo_cache`) 高度耦合**
  - **問題座標與分類**：[`gdrive_support/coordinator.py:L1-L3171`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)、[`gdrive_support/transport.py:L1-L2197`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) ｜ `C9.1 (A1)` 上帝類別職責耦合 / `C9.3 (A3)` 狀態真相分裂 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. [`coordinator.py`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) 單檔高達 3,171 行，將根目錄 `README.md` 軟合併器、跨進程鎖與讓位信號、本地 WAL 帳本、分支生命週期、Stage 1~4 同步執行器以及 700 行的 Level 1 `changes.list` 增量快取修補器全部塞入單一 `SyncCoordinator` 類別。
    2. [`transport.py`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) 單檔高達 2,197 行，混雜抽象介面、755 行的本地沙盒模擬器 `LocalSandboxTransport`、942 行的 `GoogleDriveApiTransport` 以及 252 行的 OAuth2 Loopback HTTP Server（`run_oauth_loopback_flow`）。
  - **建議解決方案（Mode A 根因重構 — 手術 `S3`）**：
    - **修改思路**：依手術藍圖 `S3` 拆分為 `readme_sync.py`、`ledger.py`、`incremental_cache.py`、`sandbox_transport.py` 與 `auth_flow.py`，並由 [`gdrive_support/__init__.py`](https://drive.google.com/file/d/1GbWRlv7eFXC7Vs_2f8Si1OJ_ufBODNRx/view?usp=drivesdk) 與原模組保留相容匯入，達成單一職責與零外部契約破壞。

- [x] **[AUD-15] [🟡 P2 | C9.1 (D1) & C7.1 | All-OS] [`agents_workflow/plans/verifier.py:L1046-L1116`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) & [`agents_workflow/plans/_verifier_healer.py:L243-L259, L320-L375`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk) — `PlanVerifier.verify_plan` 以 `bool(log_msg)` 隱式控制自癒副作用，且首次帶 `--log` 初始化缺失之 `changelog.md` 時在單次呼叫內連續兩次覆寫 `changelog.md` 並塞入冗餘假紀錄行**
  - **問題座標與分類**：[`agents_workflow/plans/verifier.py:L1046-L1116`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk)、[`agents_workflow/plans/_verifier_healer.py:L243-L259, L320-L375`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk) ｜ `C9.1 (D1)` 命令查詢耦合 / `C7.1` 重複檔案寫入 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. 當計畫目錄尚未建立 `changelog.md`，且開發者或 Agent 依規範執行 `plan verify <plan> --phase P00 --log "完成 P00 需求討論"` 時：
       - 在 `_verify_single_plan_directory` 中，`_auto_heal_companions`（[`_verifier_healer.py:L244-L253`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk)）將一筆摘要為 `"自動初始化變更日誌 (changelog.md)"` 的初始 `changelog.md` 放入 `pending_writes[changelog_path]`。
       - 在 `verify_plan` Step 4（[`verifier.py:L1100-L1101`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk)）中，程式先把 `pending_writes[changelog_path]` 寫入磁碟；緊接著在第 1112 行又呼叫 `_append_changelog_entry(p, summary=log_msg, ...)`，把剛寫入磁碟的 `changelog.md` 重新讀出、插入 `--log` 摘要並再次寫回磁碟！這不僅造成單次指令對同一檔案重複兩次原子寫入，還在表格底部留下一筆多餘的 `"自動初始化變更日誌 (changelog.md)"` 假紀錄。
    2. 此外，`enable_auto_heal` 應支援顯式參數 `heal: Optional[bool] = None`（預設向後相容 `bool(log_msg)`，但允許 API 呼叫端獨立控制唯讀檢驗 vs 顯式自癒）。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：當 `log_msg` 存在且 `changelog.md` 原本不存在時，在 `_auto_heal_companions` 中直接使用 `log_msg` 與 `log_type` 渲染初始 `changelog.md` 放入 `pending_writes`（並將 `report.log_status = "appended"`），在 Step 4 一次原子落盤即可，無須於第 1112 行二次讀寫檔案。

- [x] **[AUD-16] [🟡 P2 | C6.1 & C1.2 | All-OS] [`gdrive-support/contributes/core.json:L659-L673`](https://drive.google.com/file/d/1D53iMs8qpDzVwaLof_6KzrPV-ou4_20F/view?usp=drivesdk) & [`gdrive_support/config.py:L343-L392`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) — `contributes/core.json` 之 `gitignore` 空間誤填舊版 `config://` URI 字串而非專案相對 Glob，且 `is_sensitive_credential_path` 未動態納入 `GDriveConfig.credentials_uri` 與 `token_uri` 自訂路徑**
  - **問題座標與分類**：[`gdrive-support/contributes/core.json:L659-L673`](https://drive.google.com/file/d/1D53iMs8qpDzVwaLof_6KzrPV-ou4_20F/view?usp=drivesdk)、[`gdrive_support/config.py:L343-L392`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) ｜ `C6.1` 資安邊界與憑證防洩漏 / `C1.2` Contributes 契約錯位 ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. 在 [`gdrive-support/contributes/core.json:L665-L670`](https://drive.google.com/file/d/1D53iMs8qpDzVwaLof_6KzrPV-ou4_20F/view?usp=drivesdk) 中，`spaces.gitignore` 的 `entries` 為 `["project://"]`，但其 `include` 清單卻填寫了 `"config://gdrive-support/credentials.json"` 等語意 URI 字串（而非相對於 `project://` 的檔案路徑樣式，且未對齊 1.0.1.x 遷移後的 `.config.local/gdrive-support/` 路徑）。
    2. 在 [`config.py:L343-L392`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) 的 `is_sensitive_credential_path` 中，僅硬編碼比對檔名（`credentials.json`, `token.json` 等）與固定目錄前綴；若使用者在設定檔中將 `credentials_uri` 或 `token_uri` 指向專案內自訂檔名（如 `project://config/my_gdrive_oauth.json`），`collect_space_local_files_with_stat` 與 `cli.put` 的 `is_sensitive_credential_path` 將無法攔截該自訂憑證檔！
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 將 [`contributes/core.json:L665-L670`](https://drive.google.com/file/d/1D53iMs8qpDzVwaLof_6KzrPV-ou4_20F/view?usp=drivesdk) 更新為專案相對路徑與萬用字元（涵蓋 `**/credentials.json`、`**/token.json`、`**/service_account.json`、`**/*secret*.json` 與 `.config.local/gdrive-support/**`）。
      2. 在 `is_sensitive_credential_path`（或 `SyncCoordinator._collect_local_snapshot` 與 `cli.put`）中，同時將當前 `config.credentials_uri` 與 `config.token_uri` 解析後之實體路徑納入敏感路徑黑名單。

- [x] **[AUD-17] [🟡 P2 | C6.1 & C2.2 | macOS / Windows / All-OS] [`agents_workflow/plans/scanner.py:L248-L280`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)、[`agents_workflow/roadmap.py:L78-L108`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk) & [`agents_workflow/compiler.py:L254-L263, L331, L363-L376, L996-L1006, L1023`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) — `PlanScanner.resolve_target_plan_dir` 未校驗目標目錄位於 `plans_dir` 內（允許 `--plan ../..` 越界刪除 `handoff.md` 或寫入 `roadmap.md`），且 `compiler.py` 混用 `abspath` 與 `realpath` 在 macOS `/var` 下產生錯誤相對路徑**
  - **問題座標與分類**：[`agents_workflow/plans/scanner.py:L248-L280`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)、[`agents_workflow/compiler.py:L254-L263, L331, L363-L376, L996-L1006, L1023`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) ｜ `C6.1` 路徑邊界驗證 / `C2.2` macOS `/var -> /private/var` 符號連結與 Windows 跨磁碟機差異 ｜ `macOS / Windows / All-OS`
  - **觸發情境與演進根因分析**：
    1. **`resolve_target_plan_dir` 缺少根目錄邊界守門 (`scanner.py:L258-L265`)**：當執行 `plan status --resume --plan ../../other_dir` 或 `roadmap promote <topic> --plan ../../other_dir` 時，`resolve_target_plan_dir` 直接接受任何存在的絕對路徑或 `(self.plans_dir / raw_str).resolve()`，未檢驗目標是否位於 `self.plans_dir` 之下，導致 `--resume` 可越界刪除任意目錄下的 `handoff.md`（[`scanner.py:L481`](https://drive.google.com/file/d/1Ur7eB1o_8F4hziBgD2cyTX9i_BLA2aYc/view?usp=drivesdk)），`roadmap promote` / `todo promote` 可越界寫入 `roadmap.md`、`todo.md` 與 `changelog.md`。
    2. **macOS `/var` 符號連結 `abspath` vs `realpath` 混用 (`compiler.py:L331, L999, L1023`)**：在 `compiler.py` 中，`cur_dir` 與 `project_root` 使用 `os.path.abspath()`（保留 `/var/folders/...`），而透過 `uri.resolve()` 解析出的路徑可能經過 `Path.resolve()` / `realpath`（展開為 `/private/var/folders/...`）。兩者傳入 `os.path.relpath(target_abs, cur_dir)`（[`compiler.py:L257, L364`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk)）時，會算出 `../../../../private/var/folders/...` 的錯誤長相對路徑！
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：
      1. 在 `PlanScanner.resolve_target_plan_dir` 中驗證解析後的目錄必須位於 `self.plans_dir.resolve()` 內部（且深度為 1 層主計畫或 2 層 `sub_*` 子計畫）。
      2. 在 `compiler.py` 的 `_format_relative_local_path`、`_resolve_anchor_base_dir`、`_resolve_project_root` 與 `resolve_stage2_uri` 中，成對使用 `os.path.realpath` 正規化參與 `os.path.relpath` 計算的兩端路徑。

---

### 🔵 P3 - Optimization（無損結構打磨與孤兒空殼清理）

- [x] **[AUD-18] [🔵 P3 | C8.1 & C8.2 (A5) | All-OS] [`agents-workflow/scripts/hook.dev.py:L1-L16`](https://drive.google.com/file/d/1Fv59LRg0uApay71DjHfh4W99BgvWVAHk/view?usp=drivesdk) & [`gdrive-support/scripts/hook.core.py:L15-L18`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk) — 100% 空操作之 `hook.dev.py` 空殼檔案與 `hook.core.py` 單行零邏輯轉發函式 (`_load_lightweight_repo_sync_settings`)**
  - **問題座標與分類**：[`agents-workflow/scripts/hook.dev.py:L1-L16`](https://drive.google.com/file/d/1Fv59LRg0uApay71DjHfh4W99BgvWVAHk/view?usp=drivesdk)、[`gdrive-support/scripts/hook.core.py:L15-L18`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk) ｜ `C8.1 (S2)` 零邏輯 1:1 轉發殼 / `C8.2 (A5)` 空殼 Hook ｜ `All-OS`
  - **觸發情境與演進根因分析**：
    1. [`agents-workflow/scripts/hook.dev.py`](https://drive.google.com/file/d/1Fv59LRg0uApay71DjHfh4W99BgvWVAHk/view?usp=drivesdk) 內僅有 `on_test_setup` 與 `on_test_teardown` 兩個 `pass` 空函式，無任何業務邏輯。
    2. [`gdrive-support/scripts/hook.core.py:L15-L18`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk) 的 `_load_lightweight_repo_sync_settings(registry)` 僅單行轉發至 `gdrive_support.config.load_lightweight_repo_sync_settings(registry)`。
  - **建議解決方案（Mode A 根因重構）**：
    - **修改思路**：在 `on_register_file_spaces`（[`gdrive-support/scripts/hook.core.py:L30`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk)）直接呼叫 `load_lightweight_repo_sync_settings(registry)` 並移除單行轉發函式；若框架不強制要求存在 `hook.dev.py`，可移除空殼 `hook.dev.py`。

---

### 2.4 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

- **[RFP-01] [`gdrive-support/scripts/hook.core.py:L12-L30`](https://drive.google.com/file/d/1DKlvIaIfnV5JOKUNuUROF2HG04S3DXDJ/view?usp=drivesdk) — 檢查 `hook.core.py` 是否仍複製貼上獨立的設定解析器 (`A2`)**：
  - **查證結論**：已排除。現行 `hook.core.py` 已將輕量設定解析邏輯收斂至 [`gdrive_support/config.py:L472-L551`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) 之 `load_lightweight_repo_sync_settings`（刻意不觸發 `SpaceRegistry()` 以防遞迴），`hook.core.py` 僅殘留 1 行轉發殼（已歸入 P3 `AUD-18`）。
- **[RFP-02] [`gdrive_support/transport.py:L1134-L1203, L1223-L1263`](https://drive.google.com/file/d/11U4jUhduwn6auUAm_ydcLjcVQLflapaT/view?usp=drivesdk) — 檢查 `GoogleDriveApiTransport` 多執行緒 OAuth Token 刷新競態與網路請求超時 (`C4` / `C5`)**：
  - **查證結論**：已排除。`_ensure_access_token` 全程受 `self._token_lock`（`threading.RLock`）保護，且 `HTTPSConnection(host, timeout=60)`、Token 刷新 `urlopen(req, timeout=30)` 與檔案下載 `urlopen(req, timeout=120)` 皆已具備明確超時與 401 單次刷新重試防護。
- **[RFP-03] [`agents_workflow/plans/verifier.py:L1047, L1091-L1102`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) — 檢查 `PlanVerifier.verify_plan` 是否仍在跨檔檢驗完成前中途改寫磁碟 (`D2`)**：
  - **查證結論**：主體交易原子性已修復（已排除 P0/P1 中途髒寫）。現行 `verify_plan` 已引入 `pending_writes: Dict[Path, str] = {}` 暫存區，當 `report.has_fails` 為 `True` 時會清空 `pending_writes` 並跳過寫盤；唯在首次帶 `--log` 建立 `changelog.md` 時存在「先寫入預設初始化列、緊接著又讀出插入 `--log` 列」之雙重寫盤與 `bool(log_msg)` 耦合問題（已精確降級歸入 P2 `AUD-15`）。

---

## 3. 結論 (Conclusion)

- **核心結論**：第二輪九維度全量深度審計共於 12 個審計分組檢出 **94 項真實問題（14 P0、33 P1、31 P2、16 P3）** 與 **S1~S6 六大 Mode A 根因重構手術**，並排除 **36 項假陽性（RFP）**。全數 94 項問題與新環境 78 項全 CLI 實機測試發現之 2 項部署邊界問題已於 `sub_01` ~ `sub_05` 100% 修復收斂，全倉通過 `dev check`（9/9 PASS）與 `dev test --all --no-build`（869/869 PASS, `0 ResourceWarning`）。
- **後續建議（選填）**：無（全數修復項目、新環境 78 項全 CLI 實機驗證與 `P07` 結案驗收均已 100% 閉環）。
