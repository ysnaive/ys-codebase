# API 規格書 (API Specification)

> 功能名稱：核心微內核基礎設施模組 (Core Infrastructure Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.2

---

## 1. 模組與類別總覽

| 模組 / 檔案路徑 | 匯出成員 | 類型 | 職責概述 |
| :--- | :--- | :---: | :--- |
| `source/core/core/context.py` | `ExecutionContext` | Add | 極簡 3 欄位執行期語意上下文資料模型 |
| `source/core/core/uri.py` | `core.uri` (模組級 VFS) | Add | 9 大語意協議解析、佔位符代換與一級 VFS 檔案操作 SDK |
| `source/core/core/engine.py` | `AtomicEngine` | Add | 12 大原子操作實作（鏡像下載、清冊維護、相依求解、兩階段重載、快照備份） |
| `source/core/core/contributes.py` | `ContributesAggregator` | Add | 5 大來源 contributes 掃描、拓撲排序與靜態依賴注入引擎 |
| `source/core/core/installer.py` | `Installer` | Add | 7 大套件管理子指令的高階業務管線實現 |
| `source/core/scripts/cli.py` | `main(argv)` | Add | `core` 模組對外 CLI 進入點，解析命令列並分發給 `Installer` |

---

## 2. API 介面定義 (Python Signature & Specs)

### 2.1 模組：`core.context`

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class ExecutionContext:
    """
    極簡執行期語意上下文介面（嚴禁包含底層實體路徑）。
    """
    module_name: str
    command: str
    args: List[str] = field(default_factory=list)
```

---

### 2.2 模組：`core.uri` (一級 VFS 虛擬檔案系統)

```python
from typing import Optional, List, Any, Dict

# ── 協議解析與路徑轉換 ───────────────────────────────────
def resolve(uri: str, current_module: Optional[str] = None) -> str:
    """將語意 URI 解析為作業系統實體絕對路徑。"""
    ...

def to_uri(abs_path: str, current_module: Optional[str] = None) -> str:
    """將實體路徑反向轉換為標準語意 URI。"""
    ...

# ── VFS 檔案內容讀寫 ─────────────────────────────────────
def read_text(uri: str, encoding: str = 'utf-8', current_module: Optional[str] = None) -> str:
    """直接自語意 URI 讀取純文字內容。"""
    ...

def write_text(uri: str, content: str, encoding: str = 'utf-8', current_module: Optional[str] = None) -> None:
    """直接向語意 URI 寫入純文字內容（自動建立父目錄並原子寫入）。"""
    ...

def read_json(uri: str, encoding: str = 'utf-8', current_module: Optional[str] = None) -> Any:
    """自語意 URI 讀取並解析 JSON 資料。"""
    ...

def write_json(uri: str, data: Any, indent: int = 2, encoding: str = 'utf-8', current_module: Optional[str] = None) -> None:
    """向語意 URI 原子寫入格式化 JSON 資料。"""
    ...

def read_bytes(uri: str, current_module: Optional[str] = None) -> bytes:
    """自語意 URI 讀取二進位資料。"""
    ...

def write_bytes(uri: str, data: bytes, current_module: Optional[str] = None) -> None:
    """向語意 URI 原子寫入二進位資料。"""
    ...

# ── VFS 檔案狀態與目錄維護 ───────────────────────────────
def exists(uri: str, current_module: Optional[str] = None) -> bool:
    """檢查語意 URI 指向之檔案或目錄是否存在。"""
    ...

def is_file(uri: str, current_module: Optional[str] = None) -> bool:
    """檢查語意 URI 是否為一般檔案。"""
    ...

def is_dir(uri: str, current_module: Optional[str] = None) -> bool:
    """檢查語意 URI 是否為目錄。"""
    ...

def makedirs(uri: str, exist_ok: bool = True, current_module: Optional[str] = None) -> None:
    """於語意 URI 建立多層目錄結構。"""
    ...

def remove(uri: str, current_module: Optional[str] = None) -> None:
    """自語意 URI 刪除單一檔案。"""
    ...

def rmtree(uri: str, ignore_errors: bool = False, current_module: Optional[str] = None) -> None:
    """遞迴刪除語意 URI 目錄樹。"""
    ...

def listdir(uri: str, current_module: Optional[str] = None) -> List[str]:
    """列出語意 URI 目錄下所有子檔案與子資料夾名稱。"""
    ...

def copy(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    """在兩個語意 URI 之間複製檔案或目錄。"""
    ...

def move(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    """在兩個語意 URI 之間移動檔案或目錄。"""
    ...
```

---

### 2.3 模組：`core.engine` (12 大原子操作引擎)

```python
from typing import Optional, List, Tuple, Dict, Any
from core.context import ExecutionContext

class AtomicEngine:
    def __init__(self): ...
    
    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
        """ACT-02: 自 provider 抓取純淨 build 包至 mirror://{module}/{version}/。"""
        ...
        
    def act_delete(self, module_name: str, version: Optional[str] = None) -> None:
        """ACT-03: 自 mirror:// 刪除指定版本或全部鏡像產物。"""
        ...
        
    def act_register(self, module_name: str, version: str, provider: str, description: str = '') -> None:
        """ACT-04: 於 yscb.config.json 登記模組與版本元數據。"""
        ...
        
    def act_unregister(self, module_name: str) -> None:
        """ACT-05: 自 yscb.config.json 註銷模組。"""
        ...
        
    def act_solve_deps(self, target_module: str, version_constraint: Optional[str], provider_url: str) -> List[Tuple[str, str]]:
        """ACT-06: 執行 Kahn 拓撲相依求解與循環相依檢驗。"""
        ...
        
    def act_prepare(self, target_list: List[Tuple[str, str]], provider_url: str) -> None:
        """ACT-07: 遍歷清冊檢查鏡像，按需調用 act_download。"""
        ...
        
    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        """ACT-08: RELOAD 兩階段純淨物化與依賴注入/廣播。"""
        ...
        
    def act_fetch(self, provider_url: str, subpath: str) -> Tuple[bool, Any]:
        """ACT-09: 自 HTTP/HTTPS/Local 來源抓取 index.json 或套件包。"""
        ...
        
    def act_snapshot(self, tag: Optional[str] = None) -> str:
        """ACT-10: 備份當前組態清冊至 snapshot://。"""
        ...
        
    def act_restore_snapshot(self, snapshot_id: str) -> None:
        """ACT-11: 自 snapshot:// 還原組態清冊並觸發 reload。"""
        ...
        
    def act_broadcast_event(self, event_name: str, context: ExecutionContext) -> None:
        """生命週期事件廣播：調度各模組 scripts/hook.*.py 響應事件。"""
        ...
```

---

### 2.4 模組：`core.installer` (7 大套件管理指令)

```python
from typing import Optional, List

class Installer:
    def __init__(self): ...
    
    def cmd_install(self, module_name: str, version: Optional[str] = None, provider: Optional[str] = None) -> int: ...
    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int: ...
    def cmd_remove(self, module_name: str, clean: bool = False) -> int: ...
    def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int: ...
    def cmd_status(self) -> int: ...
    def cmd_rollback(self, target: Optional[str] = None) -> int: ...
    def cmd_reload(self) -> int: ...
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 標準庫模組與函式 | 呼叫方式 / 簽名 | 驗證狀態 |
| :--- | :--- | :--- | :---: |
| **JSON 解析與序列化** | `json` | `json.loads` / `json.dumps` | ✅ 原生支援 |
| **二進位與封裝處理** | `zipfile` / `shutil` | `zipfile.ZipFile` / `shutil.copytree` | ✅ 原生支援 |
| **雜湊計算** | `hashlib` | `hashlib.sha256` | ✅ 原生支援 |
| **HTTP 下載傳輸** | `urllib.request` | `urllib.request.urlopen` | ✅ 原生支援 |

> **第三方依賴**：**無**（100% 純 Python 3.8+ 標準庫）。

---

## 4. Decision Records

### [P03:DR-01] 模組級 core.uri 與物件導向 Engine 分工
- **議題**：`uri` 與 `engine` 應如何設計 API 暴露形式？
- **結論**：`core.uri` 採用模組級純函式（便於外部模組隨處呼叫 VFS），`AtomicEngine` 與 `Installer` 採用類別封裝（便於管理內部組態快取與測試 Mock 替換）。
- **理由**：兼顧調用端極簡體驗與內部微內核架構的可維護性。
