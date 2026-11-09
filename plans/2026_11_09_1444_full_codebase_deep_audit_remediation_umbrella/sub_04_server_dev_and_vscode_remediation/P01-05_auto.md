# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_04_server_dev_and_vscode_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 單一擁有者 `stdout` 背景分流器、`ServiceManager` 指標聚合、忙碌感知 RSS 回收與 `restart_server` 鎖交接 (`SRV-AUD-01`, `SRV-AUD-02`, `ARCH-SRV-01`, `ARCH-SRV-03`, `ARCH-SRV-04`, Surgery `S1`) | 1. [`server/master.py`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) `_read_worker_handshake` 常駐排空背景 `log`、`service_status`、`touch_activity` 封包並將前景封包放入 `proc._yscb_task_queue`；實作 `_handle_worker_packet`、`touch()` 與 `is_any_worker_service_busy()`。<br>2. [`server/service.py`](https://drive.google.com/file/d/1a1Q4sx6sMcWXZ-UzqDumMnVH8MinyVJz/view?usp=drivesdk) `ServiceManager.get_status()` 納入 `get_custom_metrics()`；`_evaluate_worker_memory_health()` 於 `is_any_worker_service_busy()` 為真時跳過回收，並透過 `restart_worker(if_idle_only=True, touch_activity=False)` 保護忙碌任務且不重置 `_last_active_time`；`_perform_self_restart()` 持 `daemon.lock` 完成 `self.stop()` 後才釋放。 | P0 | [P00:DR-01] |
| **FR-02** | `server stop` 優雅關閉與日誌鎖保護、以及 `SpaceWatcher` / `ModulesWatcher` `.yscb.lock` 統一鎖探測與 macOS 路徑對齊 (`SRV-AUD-03`, `SRV-AUD-04`, `SRV-AUD-06`, `SRV-AUD-07`, `ARCH-SRV-02`) | 1. [`server/scripts/cli.py`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) 將 `stop` 輪詢等待上限調升至 `5.0s`，並於強制終止後以 `InterProcessLock` 保護日誌歸檔。<br>2. [`server/space_watcher.py`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) 與 [`server/watcher.py`](https://drive.google.com/file/d/1HPg_sG_c-i2OI1Z7U1MDC4M8-mIi9dba/view?usp=drivesdk) 統一使用 `InterProcessLock(blocking=False)` 探測 `.yscb.lock`；`_match_prefix_rel` 雙邊對稱剝離 macOS `/private/var` 前綴；`CoreSpaceWatcherServiceWorker.is_alive()` 消除啟動競態並於目錄移除時呼叫 `unschedule`。 | P0 | [P00:DR-01] |
| **FR-03** | `dev` 平行沙盒保護、Zip Slip 防護、發布預檢原子回滾與 `Checker` 快取加速 (`SRV-AUD-08`, `SRV-AUD-09`, `SRV-AUD-11`, `SRV-AUD-12`, `ARCH-DEV-01`, `ARCH-DEV-06`, `ARCH-DEV-09`, Surgery `S2`) | 1. [`dev/testing/sandbox.py`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) 於 `_SANDBOX_LOCK` 內先註冊 `_ACTIVE_SANDBOXES` 再執行 `prune_sandboxes`，並以 `_safe_extract_zip` 攔截越界路徑。<br>2. [`dev/checker.py`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk) 實作 mtime 驗證之 AST/JSON 快取與 `ModuleCheckContext`、修正 `"DefaultDict"` 前導空白；`dev/releaser.py` 先執行 pre-flight `release_check` 並於失敗時回滾 `manifest.json`。 | P1 | [P00:DR-02] |
| **FR-04** | `vscode-support` 排除規則修復、Hook 同狀態去重、單次 Mirror Zip 快取與 `$ref` 描述保留 (`SRV-AUD-10`, `SRV-AUD-13`, `ARCH-VSC-01` ~ `03`, `ARCH-VSC-07`, Surgery `S5`) | 1. [`vscode-support/vscode_support/projector.py`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) 修正 `_resolve_workspace_exclude_patterns` 使 `core.space` 轉譯排除規則正常納入 `merged`，並優先使用 `_winapi.CreateJunction`。<br>2. `vscode-support/scripts/hook.core.py` 以工作區指紋消除 `on_reload`/`on_env_synced` 重複編譯並防範重複註冊空間；`schema_compiler.py` 以 `_read_mirror_zip_config_bundle` 單次讀取快取 `.mirror/*.zip` 並保留 `$ref` 之 `description`/`default`。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `WarmWorker` 在閒置期間由背景服務連續輸出 `log`、`service_status (busy=True)` 與 `touch_activity` IPC 封包，隨後前景任務同時抵達 | `_read_worker_handshake` 單一執行緒即時排空所有背景封包、更新 `metrics`/`busy` 並抑制 RSS 誤殺，前景任務封包分流至 `_yscb_task_queue`，零 OS Pipe 死鎖且零封包遺失。 |
| **EC-02** | 磁碟殘留上次異常中止留下的空殼 `.yscb.lock` 檔案（無任何行程持有鎖） | `SpaceWatcher.is_transaction_locked()` 與 `ModulesWatcher._is_core_transaction_locked()` 以 `InterProcessLock` 非阻塞探測確認無人持鎖，正常執行檔案監控與熱重載而不永久凍結。 |
| **EC-03** | 惡意或損壞之歸檔內含 `../escaped_payload.txt` 路徑成員，或 `release_module` 預檢失敗 | `_safe_extract_zip` 在解壓前攔截越界成員並拋出 `ValueError`；`release_module` 在預檢失敗時不污染磁碟上的 `manifest.json`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 檢查器效能與穩定性 | `Checker.check_all()` 透過 AST/JSON 快取與測試檔快速路徑顯著降低重複檢查延遲（實測 Warm 快取延遲下降 **-86.31%**，Cold 延遲下降 **-32.28%**）。 |
| **NFR-02** | 靜態守門與回歸測試 | `python3 yscb.py dev check` 全倉 9 模組 0 違規、0 警告，且 `server`、`dev`、`vscode-support` 三模組單元測試 100% 通過、0 `ResourceWarning`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 在 `dev/tester.py` 中，部分單元測試會透過 `unittest.mock.patch("subprocess.run")` 攔截 `_handle_post_test_sync` 的子進程呼叫；因此僅當 `subprocess.run is _ORIG_SUBPROCESS_RUN` 時才切換至 `run_subprocess_with_tree_timeout`，以維持既有 Mock 測試 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

- **單一擁有者 `stdout` 分流模型 (`MasterSupervisor`)**：`proc` 綁定 `_yscb_task_queue: queue.Queue` 與 `_yscb_demux_active` 旗標；`_read_worker_handshake` 作為唯一呼叫 `proc.stdout.readline()` 的執行緒，將控制封包即時交由 `_handle_worker_control_packet` 處理，並將前景串流封包推入 `_yscb_task_queue`。
- **沙盒活躍鎖與安全解壓 (`SandboxProvisioner`)**：`_allocate_sandbox_root` 在 `_SANDBOX_LOCK` 內先註冊活躍沙盒再執行 `prune_sandboxes`；`_safe_extract_zip(zf, dest_dir)` 統一執行路徑邊界校驗。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/master.py` | Modify | 實作單一擁有者 `_read_worker_handshake` 分流器、`is_any_worker_service_busy()`、`_handle_worker_packet`、`touch()`、`restart_worker(if_idle_only=True, touch_activity=False)` 與 `_perform_self_restart` 鎖保持 |
| `ys_codebase/source/server/server/service.py` | Modify | `ServiceManager.get_status()` 納入 `get_custom_metrics()`、`set_state` fallback 補齊 `"busy"`、`touch_activity` 加入 `daemon.json` mtime 快取 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | `is_transaction_locked` 統一 `InterProcessLock` 探測、`_match_prefix_rel` 對稱處理 macOS `/private/var`、`is_alive()` 防競態、`sync_watched_directories` 呼叫 `unschedule` |
| `ys_codebase/source/server/server/watcher.py` | Modify | `_is_core_transaction_locked` 探測 `.cache/.yscb.lock` 與 `yscb_root/.yscb.lock` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | `stop` 等待時限調升至 5.0s 並以 `InterProcessLock` 保護日誌歸檔 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 實作 `ModuleCheckContext` 與 mtime 驗證之 AST/JSON 快取、修正 `"DefaultDict"` 前導空白、加速測試檔掃描 |
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

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 單一擁有者 `stdout` 讀取器取代雙執行緒直接讀 Pipe (`SRV-AUD-01`, `ARCH-SRV-01`)**：徹底廢除「握手時一條執行緒讀 `proc.stdout`、派發時主執行緒直接讀 `proc.stdout`、閒置時無人讀 `proc.stdout`」的三段式脆弱模式，改由生命週期綁定的單一 `_read_worker_handshake` Demuxer 執行緒獨佔 `proc.stdout`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/server/server/master.py
class MasterSupervisor:
    def _handle_worker_packet(self, packet: Any) -> bool: ...
    def is_any_worker_service_busy(self) -> bool: ...
    def touch(self, source: str = "probe") -> float: ...
    def restart_worker(self, *, if_idle_only: bool = False, touch_activity: bool = True) -> int: ...

# ys_codebase/source/dev/dev/testing/sandbox.py
def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: str) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_safe_extract_zip` 檢測到成員路徑解析後不在 `dest_dir` 內時，立即拋出 `ValueError("Unsafe zip member path ...")`。
- **階段決策紀錄**：[P03:DR-01] 維持 `server`、`dev`、`vscode-support` 公開 API 與 IPC JSON 封包格式 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-04 完整覆蓋 `SRV-AUD-01` ~ `SRV-AUD-14`、`ARCH-SRV-01` ~ `09`、`ARCH-DEV-01` ~ `12`、`ARCH-VSC-01` ~ `10` 與手術 `S1`、`S2`、`S5`。
- **邊界防護**：EC-01 ~ EC-03 涵蓋背景大量 IPC 輸出、殘留鎖檔、Zip Slip 惡意歸檔與預檢失敗回滾。
- **依賴純淨**：100% 符合 NFR-01 與 NFR-02。
- **靈魂拷問與防護解法**：若 Worker 進程無預警崩潰（EOF），`_read_worker_handshake` 讀到空位元組後自動在 `finally` 中將 `_yscb_demux_active` 設為 `False` 並將 `None` EOF 哨兵推入 `_yscb_task_queue`，使正在等待任務結果的前景執行緒立即感知異常並回報錯誤，絕不無窮卡死。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 補充單一擁有者 `stdout` 背景分流器與忙碌感知 RSS 回收說明 |
| **專題手冊** | `docs/server/hot_reload.md` | Modify | 更新 `.yscb.lock` 跨進程鎖探測與目錄 Watch 動態解除機制 |
| **設計決策** | `docs/dev/architecture.md` | Modify | 補充沙盒平行分配保護、`_safe_extract_zip` 安全守門與 `Checker` 快取 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `master.py`、`space_watcher.py`、`sandbox.py`、`projector.py`、`schema_compiler.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫結案時記錄 `sub_04` 修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_04` 規格定稿並完成實作與驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `FR-01`（`server/master.py` 單一擁有者 `_read_worker_handshake` 分流器、`ServiceManager.get_status()` 納入 `get_custom_metrics()`、`is_any_worker_service_busy()` 保護 RSS 回收與 `restart_server` 持鎖交接）
- [x] **TASK-02**：實作 `FR-02`（`server/scripts/cli.py` `stop` 等待時限調升與日誌歸檔鎖保護、`space_watcher.py` 與 `watcher.py` `InterProcessLock` 真實探測、macOS `/private/var` 對稱正規化、`is_alive()` 防競態與 `unschedule`）
- [x] **TASK-03**：實作 `FR-03`（`dev/testing/sandbox.py` 鎖內 `prune_sandboxes` 與 `_safe_extract_zip` Zip Slip 防護、`dev/checker.py` AST/JSON 快取與 `"DefaultDict"` 修正、`dev/releaser.py` pre-flight 預檢與 `manifest.json` 原子回滾）
- [x] **TASK-04**：實作 `FR-04`（`vscode_support/projector.py` 修復 `_resolve_workspace_exclude_patterns` 與 `_winapi.CreateJunction`、`hook.core.py` 同狀態去重與空間防重複註冊、`schema_compiler.py` 單次 `.mirror/*.zip` 快取與 `$ref` 描述/預設值保留）
- [x] **TASK-05**：補齊 `server`、`dev`、`vscode-support` 單元測試，同步至 `ys_codebase/.modules/` 並重建 release/build 壓縮包，執行 `python3 yscb.py dev check` 與 `dev test` 驗證 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | `L0 (微調)` | 為相容既有單元測試以 `MagicMock` 模擬 `subprocess.Popen`（其 `stdout.readline` 固定回傳單行 `worker_ready`），於 `_read_worker_handshake` 檢測到 `MagicMock` 假進程或重複 `worker_ready` 時自動退出背景讀取迴圈，避免假物件無窮迴圈。 | 已於 `server/master.py` 實作並通過全部 66 項 `server` 測試 |
