# API 與介面規格書 (API & Interface Specification)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Installer.cmd_restore` | `source/core/core/installer.py` | Public | 批量還原 installed_modules 清冊內之模組並觸發 reload |
| `generate_internal_gitignore` | `source/core/core/installer.py` | Public | 非破壞性維護 yscb_dir 下之 .gitignore 內部管理區塊 |
| `print_global_help` | `source/core/core/contributes.py` | Public | 掃描所有已安裝模組之 contributes/core.json 與 manifest.json 聚合輸出全域說明 |
| `dispatch_module` | `yscb.py` | Internal | 宿主入口雙管道路由核心 (優先嘗試管道 B，連線失敗透明降級至管道 A) |
| `_try_hot_dispatch` | `yscb.py` | Internal | 管道 B：透過 HTTP POST /api/dispatch 轉發至常駐 server 模組 |
| `_try_cold_dispatch` | `yscb.py` | Internal | 管道 A：透過 importlib.util 進程內載入 scripts/cli.py 並執行 process(args) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. core.installer
class Installer:
    def cmd_restore(self, force: bool = False, provider: Optional[str] = None) -> int:
        """
        批量從 Provider/Build/Mirror 還原 yscb.config.json 所列模組至 .modules/。
        若模組已存在且 force=False 則跳過；完成後自動觸發 reload。
        回傳值: 0 代表成功，1 代表部分或全部還原失敗。
        """

def generate_internal_gitignore(yscb_dir: str) -> None:
    """
    非破壞性維護 .gitignore 中之 YSCB 內部管理標記區塊 (/.modules/, /.venv/, *.local.json 等)。
    """

# 2. core.contributes
def print_global_help() -> int:
    """
    聚合並格式化印出 YSCB 全域指令清單：
    1. CORE COMMANDS (init, restore, install, update, remove, list, status, reload, rollback, event)
    2. MODULE COMMANDS (動態自各模組 contributes/core.json 與 manifest.json 解析子命令)
    3. GLOBAL OPTIONS (-h, --help)
    回傳值: 0
    """

# 3. yscb.py (Ultra-Thin Router)
def _try_hot_dispatch(module_name: str, args: List[str], base_dir: str, yscb_root: str) -> Optional[int]:
    """
    管道 B：嘗試透過 Localhost HTTP 將指令熱派發至常駐 Server。
    若 Server 未啟動、連線超時、回傳異常或 module_name == 'server'，回傳 None 觸發管道 A 降級。
    若成功，串流接收 NDJSON 輸出終端並回傳 exit_code (int)。
    """

def _try_cold_dispatch(module_name: str, args: List[str], base_dir: str, yscb_root: str) -> int:
    """
    管道 A：進程內冷啟動。注入 Token 後以 importlib.util 載入 target_cli 並呼叫 process(args)。
    剛性透傳 Exit Code。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 承接層擴充]
  ├── core/installer.py (實作 generate_internal_gitignore, cmd_restore, _restore_module_package)
  ├── core/contributes.py (實作 print_global_help 支援 contributes/core.json + manifest.json)
  └── scripts/cli.py (掛載 cmd_restore 與 cmd_help)
        ↓
[Step 2: yscb.py 宿主入口瘦身重構]
  ├── 剝除 cmd_restore, gitignore, print_global_help 等業務代碼
  ├── 保留極簡 cmd_init (<40 行自舉解壓 core)
  ├── 實作純淨 _try_hot_dispatch 與 _try_cold_dispatch
  └── 代碼行數精確收斂至 200~250 行
        ↓
[Step 3: 單元與整合測試驗證]
  ├── 驗證 core restore 與 global help 單元測試
  └── 驗證 yscb.py 雙管道路由、Exit Code 與模糊拼寫
```
