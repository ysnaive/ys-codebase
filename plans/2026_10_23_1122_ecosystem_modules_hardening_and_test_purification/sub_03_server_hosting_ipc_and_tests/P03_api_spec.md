# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ServiceManager` | `server/service.py` | Public | 背景服務註冊、`core.contributes` 載入、生命週期 (`start_all` / `stop_all`) 管理 |
| `WarmWorker` / `worker_main` | `server/worker.py` | Public / Package | 常駐 Worker 資料平面主迴圈、私有 `_ipc_stdout` 隔離、任務派發與退場清理 |
| `MasterSupervisor` | `server/master.py` | Public | 常駐 Master 控制平面、HTTP IPC 轉發、兩階段優雅停機、組態熱刷新 |
| `scripts/cli.py` (CLI Handlers) | `scripts/cli.py` | Public | `start`, `stop`, `status`, `reload` CLI 具名函式合約與參數防禦 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. ServiceManager (server/service.py)
class ServiceManager:
    def load_from_contributes(self, yscb_root: str) -> None:
        """從 core.contributes.get('server', 'services') 優先載入背景服務宣告並注入 provider 路徑。"""
        ...

    def _load_service_item(self, item: dict, provider: str, yscb_root: str) -> None:
        """動態載入單一背景服務項目，支援 code.class:// 協議與 auto_start 註冊。"""
        ...

    def start_all(self, context: dict) -> None:
        """依據 auto_start==True 屬性啟動已註冊之背景服務執行緒。"""
        ...

    def stop_all(self, timeout_sec: float = 3.0) -> None:
        """依序優雅停止所有運行中背景服務並等待退場。"""
        ...


# 2. Worker IPC 隔離與停機協議 (server/worker.py & server/master.py)
def worker_main(yscb_root: str, in_stream: Optional[Any] = None, out_stream: Optional[Any] = None) -> None:
    """
    Worker 主進程迴圈：
    1. 保存 orig_stdout = sys.stdout, ipc_out = out_stream or orig_stdout
    2. 執行 sys.stdout = sys.stderr (finally 還原)
    3. 以 ipc_lock 保護 emit_fn 寫入 ipc_out
    4. 接收 {"action": "exit"} 時跳出迴圈並於 finally 觸發 service_manager.stop_all(1.5)
    """
    ...

class MasterSupervisor:
    def _kill_worker_locked(self, timeout_sec: float = 3.0) -> None:
        """
        兩階段優雅停機：
        Stage 1: 向 proc.stdin 寫入 b'{"action": "exit"}\\n' 並 proc.wait(timeout=min(timeout_sec, 1.5))
        Stage 2: 逾時或異常時降級呼叫 kill_process_tree(proc.pid)
        """
        ...

    def restart_worker(self) -> int:
        """重啟 Worker 並同步以 ServerConfig.load() 刷新 idle_timeout_sec。"""
        ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_load_service_item` 遇未知類別或無效協議時，記錄 `logging.warning` 並略過，不阻斷其他服務載入。
  - `POST /api/dispatch` 傳入不相符之 `yscb_root` 時，立即回傳 HTTP `400 Workspace Root Mismatch`。
  - `scripts/cli.py:start` 收到 `ttl <= 0` 時，立即回傳退出碼 `1` 並印出錯誤訊息。
- **階段決策紀錄**：
  - `[P03:DR-01]` **全通道雙重隔離**：`sys.stdout = sys.stderr` 阻斷雜訊，`ipc_lock` 阻斷多執行緒並發寫入交錯。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[TASK-01: service.py 服務託管引擎修復]
  │ (補齊 import os, core.contributes 接入, .modules/<provider> 注入, auto_start 控制)
  ▼
[TASK-02: worker.py & master.py IPC 硬隔離與兩階段優雅停機]
  │ (sys.stdout 重導向, ipc_lock, {"action": "exit"} 停機握手, start_time 持久化, 移除 source/ 注入)
  ▼
[TASK-03: contributes 宣告、Reload 熱刷新與 cli.py 清理]
  │ (contributes/core.json events 補齊, restart_worker 組態刷新, 刪除 _handle_start 死代碼)
  ▼
[TASK-04: 測試套件純化收斂 4 檔 -> 3 檔與高風險路徑補盲]
  │ (物理刪除 test_basic.py, test_server.py 主邏輯實測, test_server_config.py, test_server_logging.py)
  ▼
[TASK-DOC: 系統文檔與 DESIGN_NOTES 增補]
```

