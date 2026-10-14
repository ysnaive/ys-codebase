# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_dev_and_server_reliability_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `dev/scripts/cli.py` | `source/dev/scripts/cli.py` | Public | CLI 指令轉派與 `bags.get_option_value()` 參數萃取 |
| `ModuleTester` | `source/dev/dev/tester.py` | Public | `-k` 測試過濾與 `--target` 冒號前後模組解析 |
| `ModuleScaffolder` | `source/dev/dev/scaffold.py` | Public | 產出標準微內核模組骨架代碼 |
| `ModuleChecker` | `source/dev/dev/checker.py` | Public | 檢查具名葉節點函式合約並串接 `custom_checks` |
| `ModuleReleaser` | `source/dev/dev/releaser.py` | Public | 執行 `release-check --all` 批次模組預檢 |
| `MasterSupervisor` | `source/server/server/master.py` | Public | IPC 並發加鎖保護、`stderr` 排空執行緒與管道安全關閉 |
| `WarmWorker` | `source/server/server/worker.py` | Public | 託管 `ServiceManager` 動態服務與巢狀指令解析 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. Tester -k 支援與 --target 解析
class ModuleTester:
    def _parse_filter_args(self, args: list[str]) -> tuple[Optional[str], list[str]]:
        """萃取 -k / --pattern 參數並回傳過濾字串與剩餘參數。"""
        ...

# 2. Releaser 批次預檢
class ModuleReleaser:
    def check_all_release_readiness(self) -> dict[str, bool]:
        """走訪 project://source 下所有模組執行 release-check，回傳模組檢驗結果映射。"""
        ...

# 3. Master 加鎖派發與 stderr 守護
class MasterSupervisor:
    def __init__(self, ...):
        self._dispatch_lock = threading.Lock()
        ...
        
    def _start_stderr_drain(self, proc: subprocess.Popen) -> None:
        """啟動背景 Daemon 執行緒持續讀取 proc.stderr 並記錄。"""
        ...

    def _kill_worker_locked(self) -> None:
        """安全終止 Worker 程序並關閉 stdin/stdout/stderr pipes。"""
        ...

# 4. Worker 服務管理整合
class WarmWorker:
    def __init__(self, ...):
        self._service_manager = ServiceManager(yscb_root)
        ...

    def run(self) -> None:
        """在啟動循環前啟動 services，在 finally 確保 stop_all()。"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[TASK-01: dev 模組 CLI 選項與骨架修復] (cli.py, scaffold.py, case.py)
                   |
                   v
[TASK-02: dev 模組測試器與發布預檢] (tester.py, releaser.py, core.json)
                   |
                   v
[TASK-03: dev 靜態檢查器合約升級] (checker.py, _manifest.md)
                   |
                   v
[TASK-04: server 模組 Master 鎖與 Stderr 排空] (master.py, logger.py)
                   |
                   v
[TASK-05: server 模組 Worker 服務託管與測試對齊] (worker.py, test_server*.py)
```

