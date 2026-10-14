# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ContributesAggregator` | `core/contributes.py` | Internal | 聚合各模組 contributes，維護 `commands.__modules__` 隔離分桶 |
| `get_agents_cli_guild` | `core/providers.py` | Public Provider | 優先依模組獨立渲染 CLI Guild 表格，相容頂層平鋪 fallback |
| `AtomicEngine` | `core/engine.py` | Core Service | 執行模組安裝/刪除/升級，使用 `module.mirror://` 修正鏡像快取 |
| `PipManager` / `IdeProjector` | `core/pip_manager.py`, `ide_projector.py` | Public Component | 根目錄解析委派至 `core.uri._get_yscb_root()` |
| `_maybe_auto_spawn_server` | `core/commands/dispatcher.py` | Internal Helper | 依傳入之 `yscb_abs` 合併 `config.project.json` 與 `config.local.json` |
| `Installer` | `core/installer.py` | Core Service | 模組清單、更新探測與還原命令處理 |
| `resolve` / `to_uri` / `_get_merged_uri_schemes` | `core/uri.py` | Public API | 語意 URI 解析、反向解析、安全邊界防禦與 `(yscb_dir, mtime)` 記憶體快取 |
| `CommandsRegistry._parse_args_dict` | `core/commands/registry.py` | Internal Parser | 同時支援 `choice` 與 `choices` 屬性 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ContributesAggregator` 雙層分桶資料規格
```python
# 聚合產物結構保證 (Schema contract):
aggregated["core"]["commands"] = {
    # 頂層保留平鋪合併以相容 test_cli_router.py 與 test_contributes.py 的 Mock:
    "cmd": {
        "status": {...},  # 合併後之單項指令
        "list": {...},
    },
    # 新增隔離分桶:
    "__modules__": {
        "core": {"cmd": {"list": {...}, "status": {...}, "reload": {...}}},
        "knowledge-db": {"cmd": {"status": {...}, "search": {...}}},
        "server": {"cmd": {"start": {...}, "status": {...}, "reload": {...}}},
        "agents-workflow": {"cmd": {"list": {...}, "release": {...}}},
        "dev": {"cmd": {"test": {...}, "release": {...}}},
    }
}
```

### 2.2 `core.uri` 記憶體快取與邊界防禦 API
```python
# 記憶體快取資料結構
_SCHEMES_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

def _get_merged_uri_schemes(yscb_dir: str) -> Dict[str, Any]:
    """讀取並快取 contributes.merged.json 中的 uri_schemes。
    
    Pre-conditions: yscb_dir 為存在或將初始化的目錄路徑。
    Post-conditions: 當檔案未修改時直接返回記憶體字典，避免重複磁碟 I/O。
    """
    ...

def resolve(uri_str: str) -> str:
    """解析語意 URI 為實體路徑。
    
    安全性保證: 確保 resolved_path == target_base or resolved_path.startswith(target_base + os.sep)，
    杜絕同前綴兄弟目錄穿越攻擊。
    """
    ...
```

### 2.3 `dispatcher._maybe_auto_spawn_server` 雙層實體讀取簽名
```python
def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None:
    """檢查並在需要時自動喚醒 Server。
    
    Contract:
    1. 僅讀取 yscb_abs 下的 config/server/config.project.json 與 config.local.json。
    2. 若 local 設定存在，以 local 的 auto_spawn 覆蓋 project 的 auto_spawn。
    3. 不呼叫全域 core.config.get，保證測試目錄隔離。
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. 基礎契約與 Schema:
   ├── source/core/contributes/_format.json (required="bool? = true")
   ├── source/core/contributes/core.json (contributes list module args & restore provider)
   └── source/core/core/semver.py (VersionTuple.__str__ revision 保留)

2. 核心底層組件 (VFS, Registry, URI):
   ├── source/core/core/commands/registry.py (choice/choices 雙相容)
   ├── source/core/core/uri.py (記憶體快取、安全邊界檢查、to_uri 支援 config 協議)
   └── source/core/core/__init__.py (PEP 562 延遲載入映射補齊)

3. 聚合器與提供者 (Contributes & Providers):
   ├── source/core/core/contributes.py (ContributesAggregator __modules__ 分桶)
   └── source/core/core/providers.py (get_agents_cli_guild 依模組獨立呈現)

4. 核心服務與分發 (Engine, Dispatcher, Installer, Host):
   ├── source/core/core/engine.py (清理重複定義, module.mirror:// 修正)
   ├── source/core/core/pip_manager.py & ide_projector.py (_get_yscb_root 委派)
   ├── source/core/core/commands/dispatcher.py (_maybe_auto_spawn_server 雙層實體讀取)
   ├── source/core/core/installer.py (cmd_list, cmd_update, cmd_restore 契約補齊)
   └── yscb.py (進入點參數空格支援與無效來源防呆)
```

---

## 4. 架構決策記錄 (Architecture Decision Records)

- **[P03:DR-01] 零破壞性聚合契約**：
  在聚合結果中同時保留舊式頂層 `commands["cmd"]` 與新式 `commands["__modules__"]`，使所有現有單元測試（包含 Mock 物件）與新版渲染邏輯皆可 100% 正常運作。
- **[P03:DR-02] 記憶體快取線程安全考量**：
  `_SCHEMES_CACHE` 採用字典覆蓋賦值，在 GIL 下屬原子操作，足以支撐 CLI 單行程與多執行緒下的安全高頻查詢。

