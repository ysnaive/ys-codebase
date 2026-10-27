# API 與介面規格書 (API & Interface Specification)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `MasterSupervisor.start` | `ys_codebase/source/server/server/master.py` | Public | 獲取 `daemon.lock` 單例鎖（失敗時剛性返回不穿透）、寫入初始 `daemon.json`、拉起 HTTP Server 與 `WarmWorker`。 |
| `MasterSupervisor.restart_server` | `ys_codebase/source/server/server/master.py` | Public | 具備 `_restarting` 單次重入守門鎖之 Master 自重啟控制。 |
| `ModulesWatcher._is_core_transaction_locked` | `ys_codebase/source/server/server/watcher.py` | Internal | 探測父目錄 `.cache/.yscb.lock` 是否正被 `core` 交易持有或核心模組處於切換瞬態。 |
| `AtomicEngine._atomic_swap_dir` | `ys_codebase/source/core/core/engine.py` | Internal | 執行 `staging_dir` 與 `target_dir` 同父目錄雙步 `os.replace` 原子切換、Windows 退避重試與異常回滾。 |
| `AtomicEngine._deploy_and_strip_single_module_config` | `ys_codebase/source/core/core/engine.py` | Internal | 針對單一模組目錄（支援 Staging 目錄或正式運行目錄）提取部署組態至 `config://` 並物理剝離模板檔與 `.yscbignore`。 |
| `_maybe_auto_spawn_server` | `ys_codebase/source/core/core/commands/dispatcher.py` | Internal | 檢查 `daemon.json` 與 `daemon.lock`，按需在背景非同步喚醒 Server。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ys_codebase/source/core/core/engine.py
class AtomicEngine:
    @staticmethod
    def _atomic_swap_dir(staging_dir: str, target_dir: str, retries: int = 3, retry_delay: float = 0.05) -> None:
        """將已預組裝完成的 staging_dir 原子替換至 target_dir，具備舊目錄回滾與自動清理保護。"""

    def _deploy_and_strip_single_module_config(self, mod: str, mod_dir_real: str) -> None:
        """從指定模組實體目錄提取 configurable/ 與根目錄 config.*.json 部署至 config://<mod>/，並物理刪除模板與 .yscbignore。"""

    def act_deploy_configs_from_modules(self) -> None:
        """掃描 module:// 下所有已安裝模組並委派 _deploy_and_strip_single_module_config 執行組態部署與模板剝離。"""

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        """4-Stage Atomic Reload Pipeline：於 .modules/.staging_<mod>_<pid>_<ts> 完成解壓與組態剝離後，呼叫 _atomic_swap_dir 原子切換。"""

# ys_codebase/source/server/server/watcher.py
class ModulesWatcher:
    def _is_core_transaction_locked(self) -> bool:
        """檢查 yscb_root/.cache/.yscb.lock 是否正被持有，或 .modules/core/manifest.json 正在切換中。"""

# ys_codebase/source/server/server/master.py
class MasterSupervisor:
    def start(self, foreground: bool = False) -> int:
        """若 self._lock.acquire(blocking=False) 為 False，立即返回既有活躍 PID 或 0，嚴禁往下穿透啟動。"""

    def restart_server(self) -> None:
        """以 self._restarting 旗標確保單一實例僅啟動一次自重啟執行緒，並優先停止 self.watcher。"""
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `AtomicEngine._atomic_swap_dir`：若 `staging_dir` 替換入 `target_dir` 失敗且舊目錄已移至 `old_dir`，必須在 `except` 區塊將 `old_dir` 移回 `target_dir` 後再向上拋出 `OSError` / `RuntimeError`。
  - `MasterSupervisor.start`：當 `self._lock.acquire(blocking=False)` 返回 `False` 時，不拋出未捕獲例外，直接返回 `int`（既有活躍 PID 或 `0`），使呼叫端安全結束。
- **階段決策紀錄**：`[P03:DR-01]` `_deploy_and_strip_single_module_config` 直接操作實體檔案系統路徑 `mod_dir_real`（同時透過 `uri` 讀寫 `config://<mod>/`），使其既能處理 `.modules/.staging_<mod>_*` 臨時目錄，也能向下相容 `act_deploy_configs_from_modules()` 對 `.modules/<mod>` 的直接調用。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: ys_codebase/source/server/server/master.py & watcher.py
        (修復單例鎖穿透、daemon.json 寫入時序、restart_server 重入鎖、Watcher 感知 .yscb.lock)
          |
          v
Step 2: ys_codebase/source/core/core/engine.py, installer.py, dispatcher.py & yscb.py
        (實作 Staging 預組裝與 _atomic_swap_dir、生命週期指令免預喚醒、daemon.lock 探測、reload/restore 交易鎖)
          |
          v
Step 3: ys_codebase/source/server/tests/test_server.py & ys_codebase/source/core/tests/test_distribution_lifecycle.py
        (補齊單元與並發回歸測試，執行 dev check --all 與 dev test --all)
```

