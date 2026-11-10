# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_server_dev_and_vscode_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將全倉深度審計報告（[`R01_full_codebase_deep_audit_report.md`](../R01_full_codebase_deep_audit_report.md)）中針對 `Unit 07`（`module:server` `MasterSupervisor`、`WarmWorker`、`ServiceManager`、`SpaceWatcher`、RSS 監控）與 `Unit 08`（`module:dev` 靜態守門檢查器、測試沙盒、建置發布器 + `module:vscode-support`）檢出之全部 **14 項問題（`SRV-AUD-01` ~ `SRV-AUD-14`：1 P0, 6 P1, 6 P2, 1 P3）**，以及架構與演進技術債報告（[`R02_architecture_and_evolutionary_debt_audit.md`](../R02_architecture_and_evolutionary_debt_audit.md)）中針對 `server`、`dev`、`vscode-support` 檢出之 **`ARCH-SRV-01` ~ `09`、`ARCH-DEV-01` ~ `12`、`ARCH-VSC-01` ~ `10` 與 Mode A 架構手術 `S1`、`S2`、`S5`** 全量轉化為 `sub_04` 修補與驗證閉環。
- **核心目標**：
  1. **根除 P0 `WarmWorker` 閒置期間背景 IPC 封包無人排空導致 OS Pipe 緩衝區塞滿與雙執行緒爭搶 `stdout` 死鎖缺陷（`SRV-AUD-01`, `ARCH-SRV-01`），並落實 Mode A 手術 `S1` & `S2`**：
     - 重構 [`server/server/master.py`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)，將 `_read_worker_handshake` 升級為常駐之單一擁有者背景 `stdout` 分流執行緒（Single-Owner Demuxer Thread），全天候即時消費 `worker_alive`、`worker_ready`、`log`、`service_status`、`touch_activity` 控制封包，並將前景任務封包（`terminal_stream`、`task_finish`）透過 `proc._yscb_task_queue` 轉交 `_stream_task_over_worker_pipe`。
     - 於 [`server/server/service.py`](https://drive.google.com/file/d/1a1Q4sx6sMcWXZ-UzqDumMnVH8MinyVJz/view?usp=drivesdk) 之 `ServiceManager.get_status()` 與 `start_all()` 狀態通知器納入 `get_custom_metrics()`（`ARCH-SRV-01`），並於 `MasterSupervisor` 實作 `is_any_worker_service_busy()` 與 `_handle_worker_packet`（支援 `"service_status"` 與 `"touch_activity"` 連動 `self.touch()`），確保 RSS 記憶體超標回收前檢查背景服務忙碌狀態，絕不中途擊殺活躍索引或同步任務（`ARCH-SRV-03`）。
     - 於 `server/master.py` 之 `_perform_self_restart()`（`restart_server`）保持持有 `daemon.lock` 直至 `self.stop()` 完成清理、緊接於 `spawn_detached_master()` 前才釋放鎖，根除重啟交接期間的鎖空窗競態（`ARCH-SRV-04`）。
  2. **修復 `module:vscode-support` P0 動態排除規則恆真短路與重複編譯（`SRV-AUD-10`, `ARCH-VSC-01` ~ `10`, Surgery `S5`）**：
     - 修復 [`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) `_resolve_workspace_exclude_patterns` 中 `if pat in translated_set` 恆真短路 Bug，使 `core.space` 轉譯之工作區排除規則（如 `**/__pycache__/**`、`**/.pytest_cache/**`）於預設 `include_all=False` 下完整納入 `merged`，並於 Windows 優先使用 `_winapi.CreateJunction`（`SRV-AUD-10`, `SRV-AUD-13`, `ARCH-VSC-01`）。
     - 於 `vscode-support/scripts/hook.core.py` 實作 `RuntimeContext` 工作區指紋快取以消除 `on_reload` 與 `on_env_synced` 連續觸發時的雙重 Schema 編譯，並防止 `on_register_file_spaces` 重複註冊（`ARCH-VSC-02`, `ARCH-VSC-03`）。
     - 於 [`vscode-support/vscode_support/schema_compiler.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) 新增 `_read_mirror_zip_config_bundle()` 單次讀取並以 `(path, mtime_ns)` 快取 `.mirror/<mod>/*.zip` 內之 `_format.json` 與 `config.*.json`，同時於 `$ref` 節點完整保留 `description`、`markdownDescription` 與 `default` 元資料（`ARCH-VSC-03`, `ARCH-VSC-07`）。
  3. **修復 `module:dev` 檢查器快取與型別漏檢、發布預檢原子回滾、平行沙盒保護與 Zip Slip 防護（`SRV-AUD-08` ~ `12`, `SRV-AUD-14`, `ARCH-DEV-01` ~ `12`）**：
     - 於 [`dev/dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) 實作跨呼叫之 `(norm_p, mtime_ns, size)` AST/JSON 快取（`_parsed_py_cache`、`_json_cache`）與 `ModuleCheckContext`，修正 `_MUTABLE_TYPE_NAMES` 中 `"DefaultDict"` 前導空白與 `_visit_func` 空分支，並加速測試檔案靜態掃描（`ARCH-DEV-01`, `SRV-AUD-11`）。
     - 於 `dev/dev/releaser.py` 確保 `release_module` 與 `release_git` 在修改磁碟 `manifest.json` 前先通過 pre-flight `release_check()`，並在後續打包或測試失敗時原子還原 `manifest.json`（`ARCH-DEV-06`, `ARCH-DEV-09`）。
     - 於 [`dev/dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 實作 `_safe_extract_zip` 攔截 Zip Slip 路徑穿越，並在 `_allocate_sandbox_root` 鎖內動態調整 `effective_keep` 保護所有並行活躍沙盒；於 `dev/tester.py` 支援 `run_subprocess_with_tree_timeout`（`SRV-AUD-08`, `SRV-AUD-09`, `SRV-AUD-12`）。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `InterProcessLock`、`run_subprocess_with_tree_timeout`、`RuntimeContext` 與 `_winapi.CreateJunction`。
- **邊界排除 (Explicitly Excluded)**：僅修改 `ys_codebase/source/{server,dev,vscode-support}`，嚴守公開 API 與 Mode B 向下相容契約。
- **架構影響範圍**：`ys_codebase/source/server/server/{master,service,space_watcher,watcher}.py`、`server/scripts/cli.py`、`dev/dev/{checker,releaser,tester}.py`、`dev/dev/testing/sandbox.py`、`dev/scripts/cli.py`、`vscode-support/vscode_support/{projector,schema_compiler}.py`、`vscode-support/scripts/hook.core.py` 及對應測試套件。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 單一擁有者 `stdout` 背景分流執行緒與忙碌感知 RSS 回收 (`SRV-AUD-01`, `SRV-AUD-02`, `ARCH-SRV-01`, `ARCH-SRV-03`, `ARCH-SRV-04`, Surgery `S1`)**：由 `_read_worker_handshake` 在完成 `worker_alive` / `worker_ready` 握手後無縫轉為常駐 Demuxer 迴圈，獨佔讀取 `proc.stdout.readline()`：遇 `log` / `service_status` / `touch_activity` 即時寫入 `ServerLogger`、更新 `_worker_services`（含 `metrics` 與 `busy`）並觸發 `self.touch_activity()`；遇前景任務封包則推入 `proc._yscb_task_queue`。RSS 監控於回收前先檢查 `is_any_worker_service_busy()` 並透過 `restart_worker(if_idle_only=True, touch_activity=False)` 非阻塞獲取 `_dispatch_lock`，避免誤殺背景任務或重置閒置計時器。
- **[P00:DR-02] 沙盒配置鎖內清理、Zip Slip 防護與發布預檢原子回滾 (`SRV-AUD-08`, `SRV-AUD-09`, `ARCH-DEV-01`, `ARCH-DEV-06`, `ARCH-DEV-09`, Surgery `S2`)**：`_allocate_sandbox_root` 在 `_SANDBOX_LOCK` 內先將新沙盒加入 `_ACTIVE_SANDBOXES` 再以 `effective_keep = max(8, len(_ACTIVE_SANDBOXES) + 2)` 呼叫 `prune_sandboxes`；`_safe_extract_zip` 對每個壓縮包成員驗證 `os.path.commonpath([dest_real, target_real]) == dest_real`；`Releaser` 在寫入 `manifest.json` 前先完成 `release_check` 並在異常時原子回滾。
- **[P00:DR-03] `vscode-support` 排除規則修復、Hook 去重與單次 Mirror Zip 快取 (`SRV-AUD-10`, `ARCH-VSC-01` ~ `03`, `ARCH-VSC-07`, Surgery `S5`)**：移除 `_resolve_workspace_exclude_patterns` 中多餘的 `pat in translated_set` 條件使 `core.space` 轉譯規則正常生效；於 `hook.core.py` 透過 `RuntimeContext` 快取工作區同步指紋；於 `SchemaCompiler` 實作 `_read_mirror_zip_config_bundle` 單次讀取快取與 `$ref` 欄位 `description`/`default` 保留。

---

## 3. 開放議題與確認紀錄

- 全部 `SRV-AUD-01` ~ `14`、`ARCH-SRV-01` ~ `09`、`ARCH-DEV-01` ~ `12`、`ARCH-VSC-01` ~ `10` 與 Mode A 手術 `S1`、`S2`、`S5` 均已實作並驗證結案。
