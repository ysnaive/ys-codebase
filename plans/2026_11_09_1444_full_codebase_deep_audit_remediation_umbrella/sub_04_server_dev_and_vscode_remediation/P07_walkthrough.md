# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_04_server_dev_and_vscode_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 實作成果總覽 (Implementation Summary)

### 1.1 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`module:server` 單一擁有者背景 Pipe 分流器、狀態指標聚合與生命週期隔離 (`ARCH-SRV-01` ~ `09`, `SRV-AUD-01` ~ `07`, `14`, Surgery `S1`)**：
     - 於 `server/service.py` 之 `ServiceManager.get_status()` 與 `start_all()` 狀態通知器納入 `get_custom_metrics()`（`"metrics"`），於 `BaseServiceWorker.set_state()` fallback 補齊 `"busy"` 欄位，並於 `touch_activity()` 實作 `daemon.json` 之 `(mtime_ns, port, token)` 快取。
     - 於 `server/master.py` 將 `_read_worker_handshake` 升級為常駐單一擁有者 `stdout` 分流執行緒（Single-Owner Demuxer），在 Worker 閒置期間持續排空背景 `"log"`、`"service_status"` 與 `"touch_activity"` 封包（連動 `self.touch_activity()` 更新活躍時間），並透過 `proc._yscb_task_queue` 無縫轉交前景任務串流封包。
     - 於 `MasterSupervisor` 新增 `is_any_worker_service_busy()`，確保 `_evaluate_worker_memory_health()` 在背景索引或同步服務忙碌時絕不觸發 RSS 記憶體回收，且透過 `restart_worker(if_idle_only=True, touch_activity=False)` 在 `_dispatch_lock` 保護下重啟閒置 Worker 而不重置 `_last_active_time`；於 `_perform_self_restart()`（`restart_server`）保持持有 `daemon.lock` 直至 `self.stop()` 完成清理後才釋放。
     - 於 `server/watcher.py` 與 `server/space_watcher.py` 統一使用 `InterProcessLock(blocking=False)` 探測 `.yscb.lock`（解決崩潰殘留空鎖檔永久凍結監控問題）、修復 macOS `/private/var` 對稱路徑前綴匹配、消除 `CoreSpaceWatcherServiceWorker.is_alive()` 啟動競態，並於監控目錄移除時呼叫 `self._observer.unschedule(watch_obj)`。
  2. **`module:vscode-support` 排除規則修復、Hook 同狀態去重與單次 Mirror Zip 快取 (`ARCH-VSC-01` ~ `10`, `SRV-AUD-10`, `13`, Surgery `S5`)**：
     - 於 `vscode_support/projector.py` 修復 `_resolve_workspace_exclude_patterns` 中 `if pat in translated_set` 恆真短路缺陷，使 `core.space` 轉譯之排除規則（如 `**/__pycache__/**`、`**/.pytest_cache/**`）於預設 `include_all=False` 下完整納入 `merged`，並於 Windows 優先使用 `_winapi.CreateJunction`。
     - 於 `vscode-support/scripts/hook.core.py` 透過 `RuntimeContext` 快取工作區同步指紋，消除 `on_reload` 與 `on_env_synced` 連續觸發時的重複編譯，並防止 `on_register_file_spaces` 重複註冊 `"vscode-support/gitignore"`。
     - 於 `vscode_support/schema_compiler.py` 新增 `_read_mirror_zip_config_bundle()` 單次讀取並以 `(path, mtime_ns)` 快取 `.mirror/<mod>/*.zip` 組態模板與格式契約，同時於 `$ref` 節點完整保留 `description`、`markdownDescription` 與 `default`。
  3. **`module:dev` 檢查器快取加速、發布預檢原子回滾與沙盒安全加固 (`ARCH-DEV-01` ~ `12`, `SRV-AUD-08`, `09`, `11`, `12`, Surgery `S2`)**：
     - 於 `dev/checker.py` 實作跨呼叫之 `(norm_p, mtime_ns, size)` AST/JSON 快取（`_parsed_py_cache`、`_json_cache`）與 `ModuleCheckContext`、修正 `_MUTABLE_TYPE_NAMES` 中 `"DefaultDict"` 前導空白與 `_visit_func` 空分支，並為測試檔案與 `_method_calls_mark_passed` 建立快速路徑。
     - 於 `dev/releaser.py` 確保 `release_module` 與 `release_git` 在寫入磁碟 `manifest.json` 前先通過 pre-flight `release_check()`，並在後續打包或測試失敗時原子回滾 `manifest.json`。
     - 於 `dev/testing/sandbox.py` 實作 `_safe_extract_zip` 攔截 Zip Slip 越界路徑，並在 `_allocate_sandbox_root` 鎖內動態調整 `effective_keep` 保護並行活躍沙盒；於 `dev/tester.py` 支援 `run_subprocess_with_tree_timeout`。

---

## 2. 效能基準實測與結構量化對照 (Performance Benchmark & Structural Delta)

### 2.1 效能基準實測對照表 (`perf_counter_ns()`)

於獨立沙盒工作區同進程對全倉 9 大模組（247 個 `.py` 源碼與測試檔案）執行 `Checker.check_all()` apples-to-apples 實測對照：

| 測試項目 | 修改前 (Baseline) | 修改後 (After) | 變化幅度 (Delta) | 優化根因說明 |
| :--- | :---: | :---: | :---: | :--- |
| **`Checker.check_all()` 首次全倉靜態檢查 (Cold)** | `4,160.66 ms` | `2,817.57 ms` | **-32.28%** (`-1,343.09 ms`) | 移除 docstring 雙重 `ast.walk(tree)`、移除葉節點 `ast.Constant` 無效 `generic_visit`、測試檔案無裸 `except:` 快速跳過與 `_method_calls_mark_passed` 尾端 `O(1)` 檢查 |
| **`Checker.check_all()` 同實例重複檢查 (Warm Cache)** | `4,805.51 ms` | `657.83 ms` | **-86.31%** (`-4,147.68 ms`, **7.30x 加速**) | 保留跨 `check_module` 之 `(norm_p, mtime_ns, size)` AST/JSON 快取（`_parsed_py_cache`、`_json_cache`）與 `ModuleCheckContext`，徹底消除重複磁碟讀取與 `ast.parse` |

### 2.2 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/master.py` | Modify | 單一擁有者 `_read_worker_handshake` 分流器、`is_any_worker_service_busy()`、`_handle_worker_packet`、`touch()`、`restart_worker(if_idle_only=True, touch_activity=False)` 與 `_perform_self_restart` 鎖保持 |
| `ys_codebase/source/server/server/service.py` | Modify | `ServiceManager.get_status()` 納入 `get_custom_metrics()`、`set_state` fallback 補齊 `"busy"`、`touch_activity` 加入 `daemon.json` mtime 快取 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | `is_transaction_locked` 統一 `InterProcessLock` 探測、`_match_prefix_rel` 對稱處理 macOS `/private/var`、`is_alive()` 防競態、`sync_watched_directories` 呼叫 `unschedule` |
| `ys_codebase/source/server/server/watcher.py` | Modify | `_is_core_transaction_locked` 探測 `.cache/.yscb.lock` 與 `yscb_root/.yscb.lock` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | `stop` 等待時限調升至 5.0s 並以 `InterProcessLock` 保護強制終止後之日誌歸檔 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 實作 `ModuleCheckContext` 與 mtime 驗證之 AST/JSON 快取、修正 `"DefaultDict"` 前導空白、加速測試檔掃描與 `mark_passed` 檢查 |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | `release_module` 與 `release_git` 先執行 pre-flight `release_check` 並支援 `manifest.json` 原子回滾 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `_allocate_sandbox_root` 鎖內活躍沙盒保護与 `_safe_extract_zip` Zip Slip 防護 |
| `ys_codebase/source/dev/dev/tester.py` | Modify | `_handle_post_test_sync` 支援 `run_subprocess_with_tree_timeout` |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | `_normalize_bags` 參數串接 `str(a)` 轉型保護 |
| `ys_codebase/source/vscode-support/vscode_support/projector.py` | Modify | 修復 `_resolve_workspace_exclude_patterns` 恆真過濾 Bug 並優先使用 `_winapi.CreateJunction` |
| `ys_codebase/source/vscode-support/vscode_support/schema_compiler.py` | Modify | 新增 `_read_mirror_zip_config_bundle` 單次讀取快取並於 `$ref` 保留 `description`/`default` |
| `ys_codebase/source/vscode-support/scripts/hook.core.py` | Modify | 實作 `RuntimeContext` 工作區同步指紋去重與 `on_register_file_spaces` 防重複註冊 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增單一擁有者分流器閒置排空、`get_status` 指標聚合与忙碌感知 RSS 回收測試 |
| `ys_codebase/source/server/tests/test_space_watcher.py` | Modify | 新增殘留空 `.yscb.lock` 探測、macOS `/private/var` 前綴切片与 `unschedule` 測試 |
| `ys_codebase/source/vscode-support/tests/test_vscode_support.py` | Modify | 新增 `_resolve_workspace_exclude_patterns`、`hook.core.py` 去重与 `$ref` 描述/預設值保留測試 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 新增 `DefaultDict` 型別集合與 AST/JSON 快取複用測試 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 新增 `_safe_extract_zip` Zip Slip 攔截與平行配置 10 個沙盒不誤刪測試 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 新增 `release_module` pre-flight 失敗回滾 `manifest.json` 測試 |

---

## 3. 測試驗證與合規檢核結果 (Test & Verification Results)

### 3.1 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python3 yscb.py dev test --m server`：**66 項測試（3 項 Contract 測試 + 63 項 Custom 測試）100% 通過（0 Failed, 0 Skipped，耗時 9.71s）**。
  - `python3 yscb.py dev test --m dev`：**112 項測試（3 項 Contract 測試 + 109 項 Custom 測試）100% 通過（0 Failed, 0 Skipped，耗時 32.83s）**。
  - `python3 yscb.py dev test --m vscode-support`：**23 項測試（3 項 Contract 測試 + 20 項 Custom 測試）100% 通過（0 Failed, 0 Skipped，耗時 0.40s）**。
  - 合計 **201 / 201 項測試 100% 通過**，0 `ResourceWarning`。
- **實機 UX / 人工驗證**：執行 `python3 yscb.py dev check`，全倉 9 大模組 **100% Passed（0 Warnings, 0 Failed）**，且源碼與測試註解中 0 審計單號殘留。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `changelog.md` | 已完成 | 同步記錄 `sub_04` 實作、基準測試與驗證結案 |
| **中觀 (Meso)** | `ys_codebase/source/{server,dev,vscode-support}/README.md` | 免更 | 公開 CLI 與 IPC 封包契約維持 100% 相容 |
| **中觀 (Meso)** | `P01-05_auto.md` | 已完成 | 完整記錄單一擁有者 `stdout` 分流器、沙盒鎖保護、`Checker` 快取與 `vscode-support` 排除規則修復 |
| **中觀 (Meso)** | `P00_discuss.md` | 已完成 | 記錄核心設計決策 `DR-01` ~ `DR-03` |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 嚴格維護 Docstring，零審計單號或任務標籤殘留 |

### 4.2 品質與清理檢核

- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack、無審計單號殘留。
- [x] **測試完整覆蓋**：所有 201 項單元測試與契約測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(server,dev,vscode-support): implement idle worker pipe demuxer, checker AST/JSON caching, and workspace exclude fix

- Upgrade MasterSupervisor._read_worker_handshake to a single-owner stdout demuxer draining background packets while idle
- Include get_custom_metrics() in ServiceManager.get_status() and guard RSS worker recycling with is_any_worker_service_busy()
- Unify InterProcessLock probing for .yscb.lock in SpaceWatcher and ModulesWatcher and unschedule removed watch directories
- Fix tautological filter in SettingsProjector._resolve_workspace_exclude_patterns, deduplicate hook.core syncs, and preserve $ref metadata
- Add mtime-validated AST/JSON caching in Checker, pre-flight manifest rollback in Releaser, and Zip Slip guard in SandboxProvisioner
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：實機執行 `PlanVerifier` 驗證 `sub_04_server_dev_and_vscode_remediation` 100% Passed（`0 Errors, 0 Warnings`）。

### 模擬新環境全 CLI 部署驗收補充紀錄

- **實機驗收結果**：於模擬新環境部署全 CLI 實機測試中，於 `server/service.py:ServiceManager.start_all()` 補齊背景服務啟動異常時強制重置為 `STATE_STOPPED` (`busy=False`) 之防禦機制，並驗證 `server` (`start`/`status`/`reload`/`stop`)、`dev` (`check`/`create`/`bump-*`/`release-check`/`build`/`test`/`release`) 與 `vscode-support` (`status`/`sync`/`revert`) 全數 CLI 指令 100% 通過。

---

### 第二輪九維度深度審計 (`R03`) 增補驗收成果

- **修復範圍**：完成 `R03-G-01` ~ `R03-G-08`、`R03-H-01` ~ `R03-H-06`、`R03-I-01` ~ `R03-I-07`（共 21 項）、`S4` 雙語系靜態守門（`RuleH14` 自動重用 `ast_engine.parsers` 掃描 `.ts/.js`）及新環境實測發現之 `ModulesWatcher.refresh_snapshot()` 手動 `reload` 快照同步修復。
- **驗證結果**：`python3 yscb.py dev check server dev vscode-support` **PASS**；`dev test`（`server` **67/67**、`dev` **120/120**、`vscode-support` **23/23**，合計 **210/210 PASS, `0 ResourceWarning`**）；模擬新環境常駐 Daemon 熱 IPC 與全 CLI 指令驗證 **100% PASS**。
