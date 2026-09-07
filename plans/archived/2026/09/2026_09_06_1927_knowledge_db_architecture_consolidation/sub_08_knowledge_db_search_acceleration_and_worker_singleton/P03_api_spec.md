# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ServerWorker.execute_task` | `source/server/server/worker.py` | Public | 任務派發中樞，支援 `_module_cache` 模組快取與零重複 exec 派發 |
| `ServiceManager.register` / `get_status` | `source/server/server/service.py` | Public | 服務納管器，支援附加 `provider` 與 `description` 元數據，輸出詳細健康度 |
| `ServerMaster._discover_service_workers` | `source/server/server/master.py` | Internal | 調用 `core.contributes.get("server")` 動態加載領域 ServiceWorker |
| `get_engine` | `source/knowledge-db/scripts/cli.py` | Public | 提供模組級 `KnowledgeEngine` 單例實例，跨請求複用內部管線 |
| `KnowledgeEngine.pre_warm` | `source/knowledge-db/knowledge_db/engine.py` | Public | 預先解壓縮載入倒排索引、圖譜與 FastEmbed 向量模型單例至記憶體 |
| `on_worker_warming` | `source/knowledge-db/scripts/hook.server.py` | Public | 響應 `server` 模組 `worker_warming` 生命週期事件之勾點進入點 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. ServerWorker 模組快取簽名 (source/server/server/worker.py)
class ServerWorker:
    def __init__(self, yscb_root: str, port: int, token: str, emit_packet_fn: Optional[Callable] = None):
        ...
        self._module_cache: Dict[str, Any] = {}

    def _get_or_load_module(self, module_name: str) -> Any:
        """
        若 module_name 已在 _module_cache 中則直接回傳；
        否則從 .modules/ 或 source/ 動態加載並放入快取。
        """

# 2. ServiceManager 增強簽名 (source/server/server/service.py)
class ServiceManager:
    def register(self, worker: BaseServiceWorker, provider: str = "core", description: str = "") -> None:
        """註冊背景服務，記錄 provider 與 description"""

    def get_status(self) -> List[Dict[str, Any]]:
        """回傳 [{"name": str, "provider": str, "description": str, "alive": bool}]"""

# 3. Knowledge-DB 單例取得 (source/knowledge-db/scripts/cli.py)
def get_engine() -> KnowledgeEngine:
    """取得進程級唯一 KnowledgeEngine 單例，惰性初始化並全域複用。"""

# 4. 預熱進入點 (source/knowledge-db/knowledge_db/engine.py)
class KnowledgeEngine:
    @classmethod
    def pre_warm(cls) -> "KnowledgeEngine":
        """
        預加載 FastEmbed 向量模型單例、二進位倒排索引與圖譜快照至記憶體。
        回傳預熱完成之 KnowledgeEngine 單例。
        """

# 5. 生命週期預熱 Hook (source/knowledge-db/scripts/hook.server.py)
def on_worker_warming(ctx: Any) -> str:
    """
    接收 server:worker_warming 事件，在背景線程觸發 KnowledgeEngine.pre_warm()。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 基礎設施] (既有 core.contributes & core.events 已就緒)
       │
       ▼
[Step 2: Server 服務納管與狀態擴充]
  ├── service.py (擴充 provider/description/status)
  ├── master.py (_discover_service_workers 接入 core.contributes)
  └── worker.py (實作 _module_cache 與 worker_warming 廣播)
       │
       ▼
[Step 3: Knowledge-DB 宣告與預熱進入點]
  ├── contributes/server.json (宣告 knowledge-db-watcher)
  ├── scripts/hook.server.py (定義 on_worker_warming)
  ├── knowledge_db/engine.py (實作 pre_warm)
  └── scripts/cli.py (實作 get_engine 單例化)
       │
       ▼
[Step 4: Watcher 事件驅動 Dirty Flag 閉環]
  ├── pipeline.py (接入 dirty flag 查詢)
  └── service.py (與 Watcher 狀態聯動)
```
