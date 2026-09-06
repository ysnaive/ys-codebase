# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_service_worker_and_pipeline  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgeDBServiceWorker` | `source/knowledge-db/knowledge_db/service.py` | Public | 實作 `server.service.BaseServiceWorker`，管理 Watchdog 監聽與防抖修補 |
| `KnowledgeEngine` | `source/knowledge-db/knowledge_db/engine.py` | Public | 知識庫檢索編排中樞，封裝 mtime 驗證與記憶體快取單例 |
| `scripts/cli.py` | `source/knowledge-db/scripts/cli.py` | Public | CLI 進入點，移除 `daemon` 子命令 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 KnowledgeDBServiceWorker

```python
from typing import Any, Dict, Optional
from server.service import BaseServiceWorker


class KnowledgeDBServiceWorker(BaseServiceWorker):
    """
    Knowledge-DB 檔案變更監聽與背景熱自癒 Service Worker。
    生命週期完全由 Server Master 託管，跟隨 Server 共享 15 分鐘 TTL。
    """

    @property
    def name(self) -> str:
        return "knowledge-db-watcher"

    def start(self, context: Dict[str, Any]) -> None:
        """
        啟動背景 Watchdog 檔案監聽器。
        動態提取受監聽空間與語言副檔名，設定 500ms 防抖計時器。
        """
        ...

    def stop(self) -> None:
        """
        優雅停止 Watchdog Observer 與防抖計時器，釋放線程資源。
        """
        ...

    def health_check(self) -> bool:
        """
        探測 Observer 線程是否正常存活且未異常崩潰。
        """
        ...
```

### 2.2 KnowledgeEngine 快取與預熱機制

```python
class KnowledgeEngine:
    """知識庫多空間查詢與索引編排引擎"""

    _cached_index: Optional[Any] = None
    _cached_index_mtime: float = 0.0
    _cached_vector: Optional[Any] = None
    _cached_vector_mtime: float = 0.0
    _cached_graph: Optional[Any] = None
    _cached_graph_mtime: float = 0.0

    @classmethod
    def pre_warm(cls) -> None:
        """
        響應 server_worker_warming 事件，預先加載倒排索引、圖譜快照與 FastEmbed 模型。
        """
        ...

    def check_and_reload_cache(self) -> None:
        """
        微秒級比對磁碟二進位快照 mtime；若磁碟快照 mtime > 記憶體 mtime 則原地熱刷新。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. service.py (實作 KnowledgeDBServiceWorker)
       |
2. engine.py (整合 mtime 比對、預熱監聽、單例快取)
       |
3. daemon.py (瘦身與廢棄自製守護進程)
       |
4. scripts/cli.py (移除 daemon 子命令)
       |
5. tests/test_service_worker.py (測試驗證)
```
