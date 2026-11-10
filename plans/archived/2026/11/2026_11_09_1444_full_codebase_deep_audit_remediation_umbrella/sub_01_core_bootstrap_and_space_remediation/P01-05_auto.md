# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_01_core_bootstrap_and_space_remediation  
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
| **FR-01** | `core.space` 遷移清理、熱重載單例刷新與 `_load_registry` 世代快取對齊 (`CORE-AUD-01`, `CORE-AUD-02`) | 1. [`core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 與 [`scripts/migrations/1.2.8.x.py`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) 清理舊 `file-space` 殘留目錄/快取，並於 `AtomicEngine.act_reload` 完成後重置 `core.space` 預設 `SpaceRegistry` / `SpaceScanner` 快取與 `invalidate_host_caches("all")`。2. [`core/commands/dispatcher.py`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) 之 `_load_registry` 納管單檔 `contributes.json` 並將貢獻檔 `(mtime_ns, size)` 納入快取世代鍵，消除熱更新後命令樹失步。 | P0 | [P00:DR-01] |
| **FR-02** | `AtomicEngine` 跨操作可重入鎖、日誌輪替後綴拼接與暫存檔 PID 隔離 (`CORE-AUD-03`, `CORE-AUD-04`, `CORE-AUD-05`) | 1. [`core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 將 `act_lock` / `act_unlock` 改為共用單一 `cache://.yscb.lock` 底層鎖實例並以引用計數管理，且於 `core/platform/lock.py` 集中提供 `is_transaction_locked()`。2. [`core/log.py`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) 之 `_rotate_lines_file` 保留原始副檔名；[`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) 之 `cmd_self_update` 暫存檔名加入 `os.getpid()`。3. 移除 [`core/uri.py`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) 零引用之孤兒函式並收斂 `yscb.py:cmd_restore`。 | P0 | [P00:DR-01] |
| **FR-03** | `OSBackend._safe_copytree` 大小寫敏感度適配、`atomic_swap_directory` 回滾、負 `mtime_ns` 正規化與批次掃描去重 (`CORE-AUD-06`, `CORE-AUD-07`, `AUD-U02-08`) | 1. [`core/vfs/os_backend.py`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) 依據檔案系統大小寫敏感度過濾碰撞，並提供帶 `.old` 失敗自動回滾之 `atomic_swap_directory`。2. [`core/space/scanner.py`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) 與 [`core/space/registry.py`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) 將 `mtime_ns` / `ctime_ns` 執行 `max(0, ...)` 夾限，並提供 `batch_walk_session()` 消除跨空間別名重複目錄掃描。 | P1 | [P00:DR-02] |
| **FR-04** | `contributes` $O(1)$ 去重合併、`cli.py` PEP 562 別名收斂、`cmd_restore` 單次解壓與離線 `pip` 自舉 (`CORE-AUD-08` ~ `CORE-AUD-10`, `AUD-U01-05`) | 1. [`core/contributes.py`](https://drive.google.com/file/d/14uiWHuqM93UGCeXoVN9XeDGgUnBZ8ZTX/view?usp=drivesdk) 之 `_deep_merge` 以輔助 `set` 將列表去重由 $O(N^2)$ 降至 $O(N)$。2. [`core/scripts/cli.py`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk) 以 PEP 562 `__getattr__` 動態解析 16 個空間子命令別名。3. [`core/installer.py`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk) 之 `cmd_restore` 透過 `skip_materialize_modules` 消除二次解壓；`core/pip_manager.py` 新增離線容器宿主 `pip` 複製回退。 | P1 | [P00:DR-01] |
| **FR-05** | Mode A 手術 `S4`：`RuntimeScope` 與 `uri_tls` 統一、`invalidate_host_caches`、`sys.path` 執行緒安全鎖與 `BaseServiceWorkerContract` (`ARCH-CORE-01` ~ `ARCH-CORE-16`, `ARCH-SRV-06`) | 1. `core/uri.py` 與 `core/context.py` 同步 `RuntimeScope` 與 `uri_tls`，提供 `invalidate_host_caches(scope="all")` 並確保 `core/symbols.py` 檢查實體檔案 `(mtime_ns, size)`。2. `core/events.py`、`core/platform/venv.py` 與 `core/commands/dispatcher.py` 以 `RuntimeContext.sys_path_lock` 保護 `sys.path`/`sys.argv` 並執行非破壞性移除。3. 新建 `core/service_contract.py` 匯出 `BaseServiceWorkerContract` 與 `touch_activity`。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `Installer.cmd_rollback` 或 `cmd_restore` 持有 `transaction_lock("rollback")` 時內部呼叫 `act_reload()`（再次請求 `act_lock("reload")`） | `AtomicEngine.act_lock` 識別當前進程已持有 `cache://.yscb.lock`，共用底層鎖並遞增計數；內層 `act_unlock("reload")` 僅遞減計數，待外層歸零時才釋放實體鎖。 |
| **EC-02** | 同一目錄下同時存在 `server.log` 與 `server.jsonl` 並觸發 `_rotate_lines_file` | 輪替暫存檔名採用 `.{target_path.name}.tmp.{pid}.{tid}`，保留完整原檔名與副檔名，互不覆寫。 |
| **EC-03** | 在 `bind_runtime_context(host_dir=A)` 作用域內呼叫 `uri.set_host_dir(B)` 或 `with uri.host_scope(C):` | `update_current_scope_roots` 同步更新活躍 `RuntimeScope`，使 `uri.get_host_dir()` 即時反映 `B` / `C` 並於退出 `host_scope` 時精準還原至 `B`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 複雜度與I/O開銷 | `_deep_merge` 列表合併時間複雜度為 $O(N)$；`cmd_restore` 磁碟解壓次數由 2 次降至 1 次；`SpaceScanner.scan(force=True)` 全空間掃描延遲降低 > 70%。 |
| **NFR-02** | 靜態守門與回歸測試 | `python3 yscb.py dev check` 全倉 9 模組 0 違規、0 警告；`python3 yscb.py dev test --m core` 287/287 測試 100% 通過，0 `ResourceWarning`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `module:dev` 的 `checker.py` 對 `scripts/cli.py` 強制要求頂層不得出現任何 `ast.Assign` 執行陳述式，且對 `core/` 強制執行 `[F13]`（僅豁免 `core/log.py` 直接呼叫 `threading.Thread`）；因此 `scripts/cli.py` 必須採用 PEP 562 `def __getattr__(name: str)` 動態轉發，而 `core/service_contract.py` 必須委派 `core.log.create_managed_thread` 建立受管背景執行緒。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

- **統一執行期作用域 (`RuntimeScope` + `uri_tls`)**：透過 `core.context.update_current_scope_roots` 在活躍 `RuntimeScope` 存在時原地替換凍結資料類別實例並同步 `uri_tls`，搭配 `RuntimeContext.invalidate_host_caches(scope="all")` 單點清除跨子系統快取。
- **輕量服務基底契約 (`BaseServiceWorkerContract`)**：於 `core/service_contract.py` 定義標準五態狀態機（`STARTING`、`UPDATING`、`READY`、`DEGRADED_OFFLINE`、`STOPPED`）、`bind_worker_context` 與 `touch_activity`，消除跨模組重複實作。
- **批次檔案空間掃描記憶化 (`SpaceRegistry.batch_walk_session`)**：於單次 `SpaceScanner.scan()` 批次內快取各子空間走訪結果（`_walk_memo`）與目錄 `os.scandir` 系統呼叫結果（`_scandir_memo`），並以 `CompiledRuleSet._fallback_compiled` 跳過已被 $O(1)$ 集合涵蓋之規則。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 強化 `_safe_extract_zip` Zip Slip 防護、`_atomic_swap_dir` `.old` 失敗回滾、`cmd_self_update` PID 暫存檔與 `cmd_restore` 委派收斂 |
| `ys_codebase/source/core/core/service_contract.py` | New | 新建純標準庫 `BaseServiceWorkerContract`（別名 `BaseServiceWorker`）與 `touch_activity` 常駐服務基底契約 |
| `ys_codebase/source/core/core/__init__.py` | Modify | 公開匯出 `BaseServiceWorkerContract`、`BaseServiceWorker`、`touch_activity` 與狀態常數 |
| `ys_codebase/source/core/core/context.py` | Modify | 新增 `sys_path_lock`、`invalidate_host_caches` 與 `update_current_scope_roots` |
| `ys_codebase/source/core/core/uri.py` | Modify | 同步 `set_host_dir`/`set_yscb_root`/`set_module_context` 及 `host_scope`/`yscb_scope`/`module_scope` 與活躍 `RuntimeScope`，移除 3 個未引用互動函式 |
| `ys_codebase/source/core/core/symbols.py` | Modify | 支援套件 `__init__.py` 實體路徑定位並於檔案 `(mtime_ns, size)` 更新時切換至 `core.loader` 重新載入 |
| `ys_codebase/source/core/core/contributes.py` | Modify | `_deep_merge` $O(1)$ 集合去重、`atomic=True` 寫入、頂層 `contributes.json` 命令支援與 `get_merged_contributes()` |
| `ys_codebase/source/core/core/events.py` | Modify | `broadcast()` 使用 `sys_path_lock` 與 `remove_inserted_sys_paths()` 保護執行緒安全 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `_load_registry` 支援單檔 `contributes.json` 與 `(mtime_ns, size)` 指紋快取，並以 `sys_path_lock` 保護 `sys.argv` |
| `ys_codebase/source/core/core/platform/venv.py` | Modify | 以 `sys_path_lock` 保護 `sys.path` 注入並新增 `remove_inserted_sys_paths()` |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | 確保鎖檔案句柄於 `finally` 關閉並新增 `is_transaction_locked()` |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 確保子進程標準串流與 `os.scandir` 迭代器於 `finally` 確定性關閉 (`0 ResourceWarning`) |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出 `is_transaction_locked` 與 `remove_inserted_sys_paths` |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 新增 `_try_copy_host_pip_to_site_packages()` 支援無 `ensurepip` wheel 之離線容器自舉 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | 新增帶 `.old` 回滾之 `atomic_swap_directory` 並修復 `_safe_copytree` 大小寫敏感度判定 |
| `ys_codebase/source/core/core/vfs/__init__.py` | Modify | 匯出 `atomic_swap_directory` 與 `robust_replace` |
| `ys_codebase/source/core/core/engine.py` | Modify | 跨操作可重入共用鎖、Zip Slip 守門、`act_reload` 支援 `skip_materialize_modules` 與 `invalidate_host_caches` |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_restore` 搭配 `skip_materialize_modules` 消除二次解壓 |
| `ys_codebase/source/core/core/log.py` | Modify | `_rotate_lines_file` 保留原始副檔名並新增 `create_managed_thread` |
| `ys_codebase/source/core/core/space/schema.py` | Modify | `CompiledRuleSet` 新增 `_fallback_compiled` 消除 `matches_fast` 重複規則掃描 |
| `ys_codebase/source/core/core/space/registry.py` | Modify | 新增 `batch_walk_session()` 批次走訪與 `os.scandir` 記憶化，並夾限負值 `mtime_ns` |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `scan()` 啟用 `batch_walk_session()`、`_load_snapshot_state` 納入尾部校驗碼快取鍵、`patch_files` 夾限負值 `mtime_ns` |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 以 PEP 562 `__getattr__` 收斂 16 個 `file_space_*` / `fs_*` 轉發包裝函式 |
| `ys_codebase/source/core/scripts/migrations/1.2.8.x.py` | Modify | 新增 `_cleanup_legacy_file_space_residuals` 清理舊 `file-space` 組態與目錄殘留 |
| `ys_codebase/source/core/tests/test_runtime_context.py` | Modify | 新增 `test_ft05` 驗證 `RuntimeScope` 同步、`invalidate_host_caches`、`symbols` 熱重載、`events` 執行緒安全與 `BaseServiceWorkerContract` |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 新增負值 `mtime_ns` 夾限、`batch_walk_session` 去重與 `1.2.8.x.py` 殘留清理測試 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 新增跨操作鎖重入、`is_transaction_locked`、Zip Slip 攔截、`atomic_swap_directory` 回滾、日誌輪替與離線 `pip` 複製測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 跨操作共用單一 `InterProcessLock` 引用計數**：`AtomicEngine` 內部維護 `_lock_counts: Dict[str, int]` 與共用 `InterProcessLock` 實例，任何 `act_lock(op)` 若發現已有活躍鎖，直接遞增 `_lock_counts[op]`，僅在 `sum(_lock_counts.values()) == 0` 時釋放底層鎖。
- **[P02:DR-02] 批次空間掃描兩層記憶化 (`_walk_memo` + `_scandir_memo`)**：在 `SpaceScanner.scan()` 全量掃描期間，透過 `SpaceRegistry.batch_walk_session()` 共享子空間檔案集合與目錄 `os.scandir` 結果，將 12 個空間（2,543 檔案）強制掃描耗時自 `2,253.41 ms` 壓降至 `534.96 ms`（`-76.26%`）。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/context.py
def invalidate_host_caches(scope: str = "all") -> None: ...

# ys_codebase/source/core/core/service_contract.py
class BaseServiceWorkerContract(ABC):
    @property
    def state(self) -> str: ...
    def set_state(self, new_state: str) -> None: ...
    def is_busy(self) -> bool: ...
    def start_managed_thread(self, target: Callable[[], None], *, context: Optional[Dict[str, Any]] = None, thread_name: Optional[str] = None) -> threading.Thread: ...
    def stop_managed_thread(self, thread: Optional[threading.Thread], stop_event: Optional[threading.Event] = None, *, wake_event: Optional[threading.Event] = None, timeout: float = 2.0) -> None: ...
    @contextmanager
    def bind_worker_context(self, context: Optional[Dict[str, Any]] = None) -> Iterator[Any]: ...
    def touch_activity(self) -> bool: ...

# ys_codebase/source/core/core/platform/lock.py
def is_transaction_locked(project_root: Optional[Union[str, Path]] = None, yscb_dir: Optional[Union[str, Path]] = None, explicit_lock: Optional[InterProcessLock] = None) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_extract_zip_safely` 與 `yscb._safe_extract_zip` 遇到包含 `..` 或絕對路徑之壓縮項目時拋出 `RuntimeError`（Zip Slip 防護）。
  - `AtomicEngine.act_lock` 跨進程競爭超時時拋出 `BlockingIOError`；同進程跨 `operation` 重入時正常返回 `True`。
- **階段決策紀錄**：**[P03:DR-01]** 維持所有既有公開方法與測試介面 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-05（涵蓋 `CORE-AUD-01` ~ `CORE-AUD-10`、`AUD-U01-01~09`、`AUD-U02-01~08`、`ARCH-CORE-01` ~ `ARCH-CORE-16`、`ARCH-SRV-06` 與手術 `S4`）皆已完整映射至具體檔案與方法。
- **邊界防護**：EC-01 ~ EC-03 皆具備明確之單元測試覆蓋與例外防護。
- **依賴純淨**：100% 符合 NFR-01 與 NFR-02 標準庫零外部依賴約束。
- **靈魂拷問與防護解法**：若內層 `with engine.transaction_lock("reload"):` 發生例外退出，`finally` 區塊呼叫 `act_unlock("reload")` 僅遞減 `"reload"` 計數，外層 `"restore"` 鎖依然穩固持有直至外層 `finally` 釋放。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | N/A | 內部實作加固與相容匯出，公開 CLI 契約不變 |
| **專題手冊** | `docs/core/space.md` | N/A | 內部 `mtime_ns` 夾限與批次走訪記憶化，公開契約不變 |
| **設計決策** | `P01-05_auto.md` / `P07_walkthrough.md` | Modify | 完整記錄 `S4` 架構收斂、可重入鎖與批次掃描加速設計 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `service_contract.py`、`context.py`、`engine.py`、`os_backend.py`、`registry.py` Docstrings（零單號殘留） |
| **發布日誌** | `changelog.md` | Modify | 於子計畫與主計畫結案時記錄 `sub_01` 修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_01` 規格定稿並完成實作與驗證閉環。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `FR-01`（`core/engine.py` 與 `1.2.8.x.py` 清理 `file-space` 殘留、`act_reload` 刷新 `SpaceRegistry` 與 `invalidate_host_caches`、以及 `dispatcher.py:_load_registry` 支援單檔 `contributes.json` 與 `mtime` 世代鍵）
- [x] **TASK-02**：實作 `FR-02`（`AtomicEngine.act_lock`/`act_unlock` 跨操作可重入共用鎖、`core/platform/lock.py:is_transaction_locked`、`core/log.py:_rotate_lines_file` 副檔名保留、`yscb.py` PID 暫存檔與 `uri.py`/`yscb.py` 孤兒死碼清理）
- [x] **TASK-03**：實作 `FR-03`（`OSBackend._safe_copytree` 大小寫敏感度判定、`atomic_swap_directory` `.old` 回滾、`scanner.py`/`registry.py` 負值 `mtime_ns` 夾限對齊與 `batch_walk_session()` 批次掃描去重）
- [x] **TASK-04**：實作 `FR-04`（`contributes.py:_deep_merge` $O(1)$ 集合去重、`core/scripts/cli.py` PEP 562 `__getattr__` 收斂、`installer.py:cmd_restore` 單次解壓與 `pip_manager.py` 離線宿主 `pip` 複製回退）
- [x] **TASK-05**：實作 `FR-05`（手術 `S4`：`RuntimeScope` 與 `uri_tls` 雙向同步、`invalidate_host_caches`、`symbols.py` 實體檔案世代校驗、`events.py`/`venv.py` `sys_path_lock` 非破壞性清理與新建 `core/service_contract.py`）並通過 `python3 yscb.py dev check` 與 `python3 yscb.py dev test --m core`（287/287 通過）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-04** | Minor | `core/scripts/cli.py` 若使用頂層別名賦值（`file_space_spaces = ...`）會觸發 `dev check` 之 `Forbidden top-level statement 'Assign'`，改用 PEP 562 `def __getattr__(name: str)` 動態映射，100% 通過 `dev check` 與白箱測試 | 已於 `scripts/cli.py` 實作並驗證通過 |
| **TASK-05** | Minor | `dev check` 規則 `[F13]` 僅豁免 `core/log.py` 直接呼叫 `threading.Thread()`，故於 `core/log.py` 提供 `create_managed_thread` 供 `core/service_contract.py` 委派呼叫 | 已於 `core/log.py` 與 `core/service_contract.py` 實作並驗證通過 |
