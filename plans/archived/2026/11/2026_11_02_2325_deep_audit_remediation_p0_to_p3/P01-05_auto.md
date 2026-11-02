# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：deep_audit_remediation_p0_to_p3  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Installer` 跨進程交易鎖臨界區包裹快照與回滾 (`AUD-01`, `AUD-20`) | 將 `cmd_install`、`cmd_update`、`cmd_remove` 與 `cmd_restore` 之 `act_snapshot` 與異常時之 `act_restore_snapshot` 移入 `with self.engine.transaction_lock(...):` 內部，並以含 `os.getpid()` 之標籤隔離快照；當搶鎖超時拋出 `TimeoutError` 時直接返回 `1` 絕不覆寫快照或觸發回滾。同步補齊 `_discover_available_modules` fallback 清單之 `"file-space"` 與 `"ast"`。 | P0 | [P00:DR-01] |
| **FR-02** | `Server` 啟動參數安全傳遞、Worker 鎖序與鑑權強化 (`AUD-02`, `AUD-03`, `AUD-12`) | `spawn_detached_master` 改透過 `sys.argv[1..5]` 傳遞路徑與參數，杜絕單引號插值崩潰與注入；`MasterSupervisor.restart_worker` 先獲取 `self._dispatch_lock` 再獲取 `self._worker_lock`；`_write_state` 設定 `daemon.json` 為 `0o600` 權限，且 `_authenticate` 改用 `secrets.compare_digest`。 | P0 | [P00:DR-02] |
| **FR-03** | `Core` 跨平台系統呼叫、VFS Symlink 防禦、Pip 超時與註冊表隔離 (`AUD-04`~`06`, `AUD-13`, `AUD-16`, `AUD-19`) | `process.py:is_process_alive` 宣告 64-bit Windows `wintypes.HANDLE` 簽名；`lock.py:_try_lock_fd` 於 `msvcrt.locking` 前執行 `os.lseek(fd, 0, os.SEEK_SET)`；`os_backend.py:assert_safe_path` 同步檢查 `realpath` 防止 Symlink 越界並於 `exists`/`is_file`/`is_dir` 套用；`pip_manager.py` 加入 `--no-input` 與 `timeout=300`；`dispatcher.py` 以 `yscb_abs` 隔離 `_GLOBAL_REGISTRY`；`telemetry.py` 確保 `.tmp` 失敗清理；移除 `yscb.py` 未使用之 `CORE_COMMANDS` 與 `_MODULE_CACHE`。 | P1 | [P00:DR-03] |
| **FR-04** | `File-Space`、`AST` 與 `Knowledge-DB` 跨模組契約、重載符號與空轉修復 (`AUD-07`~`10`, `AUD-14`, `AUD-17`, `AUD-21`, `AUD-22`) | 補齊 `hook.server.py` 之 `on_server_worker_warming`；`file_space/service.py:is_transaction_locked` 改用 `InterProcessLock` 非阻塞探測 `cache://.yscb.lock`；`scanner.py:_is_daemon_pid_alive` 探測 `.cache/server/daemon.json` 並委派 `is_process_alive`，且 `reset_cursor` 改用原子寫入；`ast_engine` 修復 `head_generation` 讀取、重載符號列表重連、`ProcessPoolExecutor` `sys.path` 初始化器與 `treesitter.py` 重載成員保留及 `kind` 計算時序；`knowledge_db` 修復 `wait_until_worker_idle` 跨進程 `time.sleep`、`embedding.py` `setdefault` 與 `is_available` 快取、以及 `io_utils.py` SSOT 委派與 `is_dirty_file_match` 精準匹配。 | P1 | [P00:DR-04] |
| **FR-05** | `Agents-Workflow` 本地軌 Manifest URI 與 `Dev` 沙盒清理及測試輸出隔離 (`AUD-11`, `AUD-15`, `AUD-18`) | `agents_workflow/publisher.py` 本地軌 `published_files` 轉譯為 `project://` URI 並相容清理，落地檔案使用 `vfs.write_text(..., atomic=True)`；`dev/testing/sandbox.py:cleanup_sandbox` 加入 `onerror` 唯讀屬性清除回呼；`dev/testing/runner.py` 與 `case.py` 支援單一測試案例粒度之標準輸出切片捕獲。 | P1 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 進程 A 持有 `transaction_lock` 安裝模組時，進程 B 並發呼叫 `cmd_install` / `cmd_update` / `cmd_remove` 並因鎖競爭超時失敗 | 進程 B 在 `transaction_lock` 處拋出 `TimeoutError`，此時尚未建立快照且不會執行 `act_restore_snapshot`，進程 A 的安裝狀態 100% 完好無損。 |
| **EC-02** | 工作區路徑包含單引號或空格（如 `/tmp/O'Connor's Workspace/ys_codebase`）時啟動 `spawn_detached_master` | 透過 `sys.argv[1..5]` 傳遞參數給 `python -c`，零字串拼接逃逸，子進程正常解析參數啟動。 |
| **EC-03** | VFS `root_dir` 內存在指向根目錄外部（如 `/etc/passwd` 或宿主其他目錄）之軟連結（Symlink） | `OSBackend.assert_safe_path` 比對 `os.path.realpath(norm_target)` 與 `os.path.realpath(boundary_root)`，立即拋出 `PermissionError` 阻斷穿越。 |
| **EC-04** | 同目錄與不同目錄下存在同名檔案（例如根目錄 `"cli.py"` 與 `"ys_codebase/source/dev/scripts/cli.py"`）進行增量髒檔案匹配 | `is_dirty_file_match` 在輸入路徑不含 `/` 時僅允許精確相等比對，不會因 `.endswith("/cli.py")` 誤淘汰其他模組之同名檔案。 |
| **EC-05** | 前台 CLI 進程呼叫 `wait_until_worker_idle` 等待另一進程之背景 Worker 完成索引更新 | 檢測到本進程 `_IDLE_EVENT.is_set()` 為 `True` 時自動改用 `time.sleep(wait_slice)`，避免 0ms 空轉讀取磁碟。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與 CPU 保護 | `wait_until_worker_idle` 在跨進程等待 `100ms` 期間之磁碟狀態輪詢次數 $\le 8$ 次（消除原本數萬次 Tight Loop 空轉）；`EmbeddingService.is_available` 在模型已就緒時免除重複 `rglob("*.onnx")`。 |
| **NFR-02** | 全模組回歸相容性 | 全專案 7 大模組（`core`、`server`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`dev`）之 `dev check` 與 `dev test` 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Windows 虛擬磁碟機 (`subst`) 與 Junction 在 `realpath` 下的行為**：Windows Python 3.8+ 的 `os.path.realpath` 會解析 Junction 與符號連結；因此在 `OSBackend.assert_safe_path` 中，必須對 `norm_target` 與 `boundary_root` **雙邊同時取 `os.path.realpath`** 進行對稱比對，確保 macOS `/var` $\to$ `/private/var` 與 Windows 沙盒皆不會誤判。
- **`[!NOTE]` `yscb.py` 內部忽略標記常數**：`INTERNAL_IGNORE_BEGIN` 與 `INTERNAL_IGNORE_END` 在 `yscb.py:L218-L234` (`_ensure_yscb_gitignore`) 中仍被呼叫，修復 `AUD-19` 時僅移除真正未使用的 `CORE_COMMANDS` 與 `_MODULE_CACHE`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[CLI / Installer]
  └── with engine.transaction_lock(op):          <-- [AUD-01] 鎖包裹快照建立與回滾全生命週期
        ├── snap_id = engine.act_snapshot(...)
        ├── execute install / update / remove / restore (含 PipManager timeout 防護 [AUD-06])
        └── except -> engine.act_restore_snapshot(snap_id)

[Server MasterSupervisor]
  ├── spawn_detached_master -> sys.argv[1..5]    <-- [AUD-02] 零字串拼接注入
  ├── restart_worker -> with _dispatch_lock: with _worker_lock:  <-- [AUD-03] 固定鎖序防強殺
  └── _write_state (chmod 0600) & _authenticate (compare_digest) <-- [AUD-12]

[File-Space -> AST -> Knowledge-DB]
  ├── hook.server.py: on_server_worker_warming   <-- [AUD-07] 對齊 Server 預熱廣播
  ├── service.py: is_transaction_locked          <-- [AUD-07] 非阻塞探測 cache://.yscb.lock
  ├── ast_engine: head_generation + 重載符號列表 + treesitter 重載成員保留 <-- [AUD-08, AUD-09]
  └── knowledge_db: wait_until_worker_idle (sleep fallback) + io_utils SSOT <-- [AUD-10, AUD-14, AUD-22]
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 移除未使用之 `CORE_COMMANDS` 與 `_MODULE_CACHE` 死常數 (`AUD-19`) |
| `ys_codebase/source/core/core/installer.py` | Modify | 將 `cmd_install`、`cmd_update`、`cmd_remove`、`cmd_restore` 之快照與回滾移入 `transaction_lock` 內 (`AUD-01`)；補齊 `_discover_available_modules` fallback 清單 (`AUD-20`) |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 於 `is_process_alive` 補齊 Windows 64-bit `wintypes.HANDLE` `ctypes` 型別宣告 (`AUD-04`) |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | 於 `_try_lock_fd` Windows 分支補上 `os.lseek(fd, 0, os.SEEK_SET)` (`AUD-04`) |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | 於 `assert_safe_path` 加入對稱 `realpath` Symlink 越界檢核，並於 `exists`/`is_file`/`is_dir` 套用邊界檢核 (`AUD-05`) |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 為 `ensurepip` 與 `pip install` 補上 `--no-input` 與 `timeout=300` (`AUD-06`) |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 為 `_GLOBAL_REGISTRY` 綁定 `_GLOBAL_REGISTRY_ROOT`，切換 `yscb_abs` 時自動重建 (`AUD-13`) |
| `ys_codebase/source/core/core/telemetry.py` | Modify | 於 `_rotate_telemetry_file` 加入 `finally` 確保殘留 `.tmp` 檔案清理 (`AUD-16`) |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 新增鎖競爭超時不觸發破壞性回滾與 Symlink 越界攔截測試 |
| `ys_codebase/source/server/server/master.py` | Modify | `spawn_detached_master` 改用 `sys.argv` (`AUD-02`)；`restart_worker` 取得 `_dispatch_lock` (`AUD-03`)；`daemon.json` `0o600` 與 `secrets.compare_digest` (`AUD-12`) |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增單引號路徑命令組裝與 `restart_worker` 鎖序測試 |
| `ys_codebase/source/file-space/scripts/hook.server.py` | Modify | 新增 `on_server_worker_warming` 入口別名 (`AUD-07`) |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | `is_transaction_locked` 改用 `InterProcessLock` 非阻塞探測 `cache://.yscb.lock` (`AUD-07`) |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | `_is_daemon_pid_alive` 納入 `.cache/server/daemon.json` 並使用 `is_process_alive` (`AUD-07`)；`reset_cursor` 改用 `_atomic_write_bytes` (`AUD-16`) |
| `ys_codebase/source/file-space/tests/test_service_and_cli.py` | Modify | 更新並擴充 `is_transaction_locked` 與 `on_server_worker_warming` 測試 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 讀取 `head_generation`、同檔重載符號列表重連 (`AUD-08`) |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 為 `ProcessPoolExecutor` 提供 `_init_bundle_worker` 同步 `sys.path` (`AUD-08`) |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 先執行 `method` 正規化與 `resolve_out_of_line_scope`，並以 `(kind, short_name, signature, start_line)` 保留重載成員 (`AUD-09`) |
| `ys_codebase/source/ast/ast_engine/io_utils.py` | Modify | `is_dirty_file_match` 優先 $O(1)$ 查找並防止無斜線檔名誤判 (`AUD-14`) |
| `ys_codebase/source/ast/tests/test_partial_and_outline.py` | Modify | 新增重載方法成員保留、`head_generation` 與 `is_dirty_file_match` 測試 |
| `ys_codebase/source/knowledge-db/scripts/hook.server.py` | Modify | 新增 `on_server_worker_warming` 入口別名 (`AUD-07`) |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 修復 `wait_until_worker_idle` 在跨進程等待時之 `time.sleep` 退避 (`AUD-10`) |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 改用 `os.environ.setdefault` (`AUD-17`) 並快取已驗證模型路徑加速 `is_available` (`AUD-21`) |
| `ys_codebase/source/knowledge-db/knowledge_db/io_utils.py` | Modify | 委派重導出 `ast_engine.io_utils` 達成 SSOT (`AUD-14`, `AUD-22`) |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增跨進程 `wait_until_worker_idle` 非空轉測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 本地軌 `release_manifest.json` 轉譯 `project://` URI 並相容解析，且落地寫入改用原子替換 (`AUD-15`) |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `cleanup_sandbox` 加入 Windows 唯讀屬性清除回呼 (`AUD-11`) |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | 記錄單一測試方法執行區間之標準輸出切片 (`AUD-18`) |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 提供緩衝偏移讀取供單一失敗測試提取專屬輸出 (`AUD-18`) |
| `ys_codebase/source/dev/dev/tester.py` | Modify | 優先取用單一失敗測試自身捕獲之輸出切片 (`AUD-18`) |
| `CHANGELOG.md` | Modify | 記錄本計畫全專案深度審計 22 項修復摘要 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `OSBackend.assert_safe_path` 對稱 `realpath` 與虛擬磁碟機相容策略**：
  - 在 `OSBackend.assert_safe_path` 中，先以 `os.path.normpath(os.path.abspath(path))` 檢查詞法路徑邊界；若詞法邊界通過且 `boundary_root` 存在，再計算 `real_target = os.path.normpath(os.path.realpath(norm_target))` 與 `real_root = os.path.normpath(os.path.realpath(boundary_root))` 驗證實體路徑亦位於 `real_root` 內。此雙重對稱檢核同時防禦了詞法 `../` 逃逸、目錄內惡意 Symlink 逃逸，並完美相容 macOS `/var` $\to$ `/private/var` 與 Windows `subst` 虛擬磁碟機。
- **[P02:DR-02] 單測方法級輸出切片捕獲 (`Per-Test Output Slice`)**：
  - 為維持既有 `OutputCapturer` 對整個 Suite 的零干擾攔截，同時解決 `AUD-18` 單一失敗案例混入其他測試輸出的問題，在 `OutputCapturer` 暴露當前串流長度快照方法，並於 `YSCBTestCase.run`（或 `TestResult` 鉤子）記錄每個測試案例開始與結束時的緩衝區切片存於 `test._yscb_captured_output`，供 `tester.py` 在組裝失敗報告時優先讀取該測試專屬輸出。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/vfs/os_backend.py
class OSBackend(VFSBackend):
    def assert_safe_path(self, path: str, root: Optional[str] = None) -> str: ...
    def exists(self, path: str) -> bool: ...
    def is_file(self, path: str) -> bool: ...
    def is_dir(self, path: str) -> bool: ...

# ys_codebase/source/file-space/scripts/hook.server.py & knowledge-db/scripts/hook.server.py
def on_server_worker_warming(context: Any) -> str: ...
def on_worker_warming(context: Any) -> str: ...

# ys_codebase/source/ast/ast_engine/bundler.py
def _init_bundle_worker(parent_sys_path: List[str]) -> None: ...

# ys_codebase/source/knowledge-db/knowledge_db/io_utils.py
from ast_engine.io_utils import (
    atomic_save_gzip_pickle,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
)
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `Installer` 各命令在 `transaction_lock` 拋出 `TimeoutError` 時直接印出錯誤並回傳 `1`，不呼叫 `act_restore_snapshot`。
  - `OSBackend.assert_safe_path` 在目標路徑詞法或 Symlink 實體路徑超出 `boundary_root` 時拋出 `PermissionError`；`exists`/`is_file`/`is_dir` 遭遇越界時拋出 `PermissionError`（或於無邊界限制時返回 `bool`）。
  - `PipManager` 在 `subprocess.run` 超時（`300s`）時捕獲 `subprocess.TimeoutExpired` 並拋出 `PipInstallError`。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有模組既有公開 API 簽名 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05（涵蓋 `AUD-01` ~ `AUD-22`）皆已於介面簽名與實作清單中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：若 `OSBackend.exists`、`is_file`、`is_dir` 改為呼叫 `self.assert_safe_path(path)`，當呼叫端在設定了 `root_dir` 的 `OSBackend` 實例上傳入越界路徑時，既有測試預期是拋出 `PermissionError` 還是回傳 `False`？*
  - *答*：查閱 `ys_codebase/source/core/tests/test_vfs.py`，預設全域 `vfs` 的 `self.root_dir` 為 `None`（僅正規化路徑不拋例外）；而顯式指定 `OSBackend(root_dir=...)` 的沙盒測試專注於防禦路徑穿越。為確保 `exists`/`is_file`/`is_dir` 既能攔截 `root_dir` 越界拋出 `PermissionError`，又對一般無效路徑返回 `False`，在 `exists`/`is_file`/`is_dir` 中先呼叫 `norm_path = self.assert_safe_path(path)`（讓 `PermissionError` 直接向上拋出），再於 `try ... except OSError:` 中執行 `os.path.exists(norm_path)`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | N/A | 既有架構描述已涵蓋 |
| **專題手冊** | `docs/server/README.md` | N/A | 既有 IPC 與守護進程描述已涵蓋 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 本次屬標準邊界加固與 Bug 修復，依 DN 防膨脹原則免新增 DN |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新各修復函式之 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `2026_11_02_2325_deep_audit_remediation_p0_to_p3` 修復摘要 |

- **決策定稿**：**[P04:DR-01]** 依開發者指示，本計畫全數為確定性修復，Pre-Code 階段採主代理 Inline 核驗通過，並於 P06 驗收階段派發盲審子代理執行全量冷眼靜態審查。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (`core` & `yscb.py`)**：實作 `AUD-01` (`installer.py` 交易鎖包裹快照與回滾)、`AUD-04` (`process.py` 64-bit HANDLE 與 `lock.py` `lseek`)、`AUD-05` (`os_backend.py` 對稱 `realpath` 與 `exists/is_file/is_dir` 邊界檢核)、`AUD-06` (`pip_manager.py` timeout)、`AUD-13` (`dispatcher.py` `_GLOBAL_REGISTRY_ROOT`)、`AUD-16` (`telemetry.py` `.tmp` 清理)、`AUD-19` (`yscb.py` 死常數清理)、`AUD-20` (`installer.py` fallback 清單) 與單元測試
- [x] **TASK-02 (`server`)**：實作 `AUD-02` (`spawn_detached_master` `sys.argv` 傳參)、`AUD-03` (`restart_worker` 獲取 `_dispatch_lock`)、`AUD-12` (`daemon.json` `0o600` 與 `secrets.compare_digest`) 與單元測試
- [x] **TASK-03 (`file-space`, `ast`, `knowledge-db`)**：實作 `AUD-07` (`hook.server.py`、`is_transaction_locked`、`_is_daemon_pid_alive`)、`AUD-08` (`head_generation`、重載符號重連、`_init_bundle_worker`)、`AUD-09` (`treesitter.py` 重載成員保留與 `kind` 時序)、`AUD-10` (`wait_until_worker_idle` 跨進程 sleep)、`AUD-14` & `AUD-22` (`io_utils.py` SSOT 與 `is_dirty_file_match`)、`AUD-16` (`reset_cursor` 原子寫入)、`AUD-17` & `AUD-21` (`embedding.py` `setdefault` 與 `is_available` 快取) 與單元測試
- [x] **TASK-04 (`agents-workflow` & `dev`)**：實作 `AUD-11` (`sandbox.py` 唯讀屬性清除回呼)、`AUD-15` (`publisher.py` 落地檔與 `.gitignore` `vfs.write_text(..., atomic=True)` 原子寫入)、`AUD-18` (`runner.py` / `case.py` / `tester.py` 單測輸出切片) 與單元測試
- [x] **TASK-05 (全量驗證與熱部署)**：執行 7 大模組 `dev check` 與 `dev test`、安裝 `@build` 並更新 `CHANGELOG.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-04** | Minor | `AUD-15` 報告建議將本地軌 `cache://agents-workflow/release_manifest.json` 轉為 `project://` URI，惟既有單元測試 `TestManifestPlacementAndDualTrack.test_ft_02_local_target_saves_absolute_paths_in_cache` 明確鎖定 `cache://` 本地軌儲存本機絕對路徑、僅 `project://` 軌儲存 `project://` 相對 URI 之雙軌架構設計。 | 保留本地軌絕對路徑契約，僅採納 `AUD-15` 後半段將 `_materialize_target_files` 與 `sync_gitignore` 升級為 `vfs.write_text(..., atomic=True)` 原子寫入。 |
