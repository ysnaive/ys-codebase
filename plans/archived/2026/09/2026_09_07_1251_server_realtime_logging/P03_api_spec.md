# API 與介面規格書 (API & Interface Specification)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ServerLogger` | `source/server/server/logger.py` | Public | 管理 `cache://server/log` 即時寫入、異常自癒、滾動清理與格式化輸出 |
| `MasterSupervisor` (整合擴充) | `source/server/server/master.py` | Public | 伺服器主控進程，持有 `ServerLogger` 並在生命週期與 HTTP/Task 各節點記錄日誌 |
| `WarmWorker` (整合擴充) | `source/server/server/worker.py` | Internal | 子進程工作者，透過 stdout 串流向 Master 發送 `{"type": "log"}` 封包 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ServerLogger` (`server.logger`)

```python
import os
import re
import threading
from datetime import datetime
from typing import List, Optional, Tuple

class ServerLogger:
    """
    即時 Flush 日誌管理引擎。
    掌管 cache://server/log 檔案控制代碼、異常中斷歷史自癒與滾動清理。
    """

    TIME_FORMAT: str = "%Y_%m_%d_%H.%M.%S"
    HIST_REGEX: re.Pattern = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$")
    MAX_HIST_FILES: int = 5
    START_BANNER_PREFIX: str = 'server start at time "'

    def __init__(self, yscb_root: str, log_dir: Optional[str] = None) -> None:
        """
        初始化 ServerLogger。
        
        Args:
            yscb_root: YS-Codebase 根目錄路徑。
            log_dir: 自訂日誌儲存目錄（預設為 .cache/server）。
        """
        ...

    @property
    def log_file_path(self) -> str:
        """當前運行中 log 檔案之絕對路徑。"""
        ...

    @property
    def is_opened(self) -> bool:
        """目前檔案 Handle 是否處於開啟寫入狀態。"""
        ...

    def recover_and_open(self) -> str:
        """
        啟動檢查、異常自癒與新日誌初始化：
        1. 檢查是否存在未歸檔之舊 log。
        2. 若存在，讀取首行解析 start at time 時間戳；解析失敗則以舊 log 之 mtime 格式化。
        3. 將舊 log 重新命名為 {timestamp}_log，並執行 5 份滾動清理。
        4. 開啟新 log 檔案，寫入首行 server start at time "{now}" 並 immediate flush。
        
        Returns:
            str: 本次 Server 啟動之時間戳字串 (格式：YYYY_MM_DD_HH.MM.SS)。
        """
        ...

    def archive_and_close(self) -> Optional[str]:
        """
        正常優雅停機時的歷史歸檔：
        1. 若檔案處於開啟狀態，記錄優雅關閉時間並關閉檔案 Handle。
        2. 若當前 log 檔案存在，以本次啟動時間戳（或檔案 mtime）歸檔為 {timestamp}_log。
        3. 執行 5 份歷史檔案滾動清理。
        
        Returns:
            Optional[str]: 歸檔後之歷史檔案路徑；若無檔案則返回 None。
        """
        ...

    def write_raw(self, line: str) -> None:
        """
        線程安全地寫入單行日誌字串並立即 flush()。
        
        Args:
            line: 待寫入字串（若結尾無換行自動補齊）。
        """
        ...

    def log(
        self,
        level: str,
        msg: str,
        component: str = "master",
        exc_info: Optional[Exception] = None,
    ) -> None:
        """
        寫入標準平衡級格式化日誌：
        格式：[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{COMPONENT}] {MESSAGE}
        若有 exc_info 則緊隨其後輸出 Stacktrace。
        """
        ...

    def info(self, msg: str, component: str = "master") -> None:
        ...

    def warning(self, msg: str, component: str = "master") -> None:
        ...

    def error(self, msg: str, component: str = "master", exc_info: Optional[Exception] = None) -> None:
        ...

    def clean_rolling_history(self) -> List[str]:
        """
        掃描日誌目錄，過濾符合 HIST_REGEX 之歷史檔案，按字串/時間排序。
        保留最新 5 份，清理超過之最舊檔案。
        
        Returns:
            List[str]: 本次被清理刪除的檔案路徑清單。
        """
        ...

    def extract_start_time_from_header(self, file_path: str) -> Optional[str]:
        """
        讀取指定日誌首行，以正則提取 server start at time "{timestamp}"。
        
        Returns:
            Optional[str]: 提取成功返回 timestamp 字串，失敗返回 None。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Stage 1: 核心引擎實作]
  └── source/server/server/logger.py (ServerLogger 類別實作與單元測試)
         │
         v
[Stage 2: Master 整合與 HTTP 攔截]
  └── source/server/server/master.py (整合 ServerLogger、生命週期與請求日誌)
         │
         v
[Stage 3: Worker IPC 串流日誌匯流]
  └── source/server/server/worker.py (WarmWorker 發送 log 封包)
  └── source/server/server/master.py (Master 攔截 log 封包並寫入 ServerLogger)
         │
         v
[Stage 4: 自動化測試與回歸]
  └── source/server/tests/test_server_logging.py (FT-01~08, RT-01)
```
