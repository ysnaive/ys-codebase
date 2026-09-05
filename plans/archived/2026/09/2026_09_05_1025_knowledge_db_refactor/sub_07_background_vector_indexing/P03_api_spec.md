# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgeDBConfig` | `knowledge_db/config.py` | Public | 提供 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec` 組態模型與型態防禦 |
| `HotReloadServer` | `knowledge_db/daemon.py` | Public | 專屬守護服務核心，管理 Watcher、500ms 防抖熱修補、PID/日誌滾動與閒置超時自動退出 |
| `DaemonInfo` | `knowledge_db/daemon.py` | Internal | PID 與日誌中繼資料資料模型 (`pid`, `start_time`, `version`, `workspace_root`, `log_file`) |
| `on_pre_cli_dispatch` | `scripts/hook.core.py` | Hook Public | YSCB 核心生命週期前置勾點，執行版本比對與 Server 背景喚醒 |
| `cmd_daemon` | `scripts/cli.py` | CLI Entry | CLI `knowledge-db daemon [start\|stop\|status\|watch]` 命令調度入口 |
| `AtomicEngine._deep_infill_dict` | `core/engine.py` | Internal | 組態軟合併算法，擴充支援 project_data 隔離以在 local 軟合併時跳過 project 既有設定 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ==============================================================================
# 1. 組態資料模型擴充 (knowledge_db/config.py)
# ==============================================================================
@dataclass
class KnowledgeDBConfig:
    enable_vector_search: bool = True
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    jit_vector_timeout_seconds: float = 5.0
    max_threads: Union[str, int] = "auto"
    enable_hot_reload_server: bool = False                     # [FR-01]
    hot_reload_server_inactivity_timer_sec: int = 600          # [FR-01]

    @classmethod
    def load(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        local_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        project_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
    ) -> "KnowledgeDBConfig":
    @property
    def is_jit_effective(self) -> bool:
        """當啟用 HotReloadServer 時，JIT 機制邏輯上全面失效由 Server 常駐接管 [FR-14]"""
        ...

    def resolve_jit_vector_timeout(self) -> Optional[float]:
        """若啟用 Server，JIT 設定視為無效 (回傳 None)；未啟用時回傳配置之 timeout 秒數 [FR-14]"""
        ...


# ==============================================================================
# 2. 專屬守護進程核心 (knowledge_db/daemon.py)
# ==============================================================================
def check_and_notify_hot_reload_server(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Optional["DaemonInfo"]]:
    """
    探測後台是否有運行中之 HotReloadServer [FR-12]。
    若有運行，向 stderr 提示 "Hot reload server(pid:<pid>) exist, skip JIT check."，
    並於該進程生命週期內僅提示一次。
    """
    ...


@dataclass
class DaemonInfo:
    pid: int
    start_time: float
    version: str
    workspace_root: str
    log_file: str
    spaces: List[str] = field(default_factory=list)             # [FR-09]
    spaces_signature: str = ""                                  # [FR-09, FR-11]

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DaemonInfo": ...


class HotReloadServer:
    """知識庫熱重載專屬守護進程，整合檔案系統監聽、防抖熱修補、PID 治理與閒置釋放"""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        config: Optional[KnowledgeDBConfig] = None,
        pipeline: Optional[Any] = None,
        space_manager: Optional[Any] = None,
    ): ...

    @classmethod
    def get_cache_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """解析 cache://knowledge-db 實體目錄 (yscb://.cache/knowledge-db)"""
        ...

    @classmethod
    def get_pid_file(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """回傳 cache://knowledge-db/daemon.pid 路徑 [FR-09]"""
        ...

    @classmethod
    def get_logs_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """回傳 cache://knowledge-db/logs 目錄路徑 [FR-10]"""
        ...

    @classmethod
    def get_current_spaces_signature(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        space_manager: Optional[Any] = None,
    ) -> str:
        """計算當前注入空間與 include 路徑之結構化 Hash 簽名 [FR-11, EC-09]"""
        ...

    def get_watch_directories(self) -> List[Path]:
        """根據注入之 SpaceManager 空間聯集定義動態解算監聽目錄清單 [FR-03]"""
        ...

    @classmethod
    def is_running(cls, workspace_root: Optional[Union[str, Path]] = None) -> Tuple[bool, Optional[DaemonInfo]]:
        """探測守護進程存活狀態，自動清理死進程殭屍 PID [EC-01]"""
        ...

    @classmethod
    def ensure_running(cls, workspace_root: Optional[Union[str, Path]] = None) -> bool:
        """
        若未運行則以 Detached 背景進程啟動 Server；
        若已運行但模組版本或空間簽名不一致則強制終止舊進程並重新啟動 [FR-02, FR-11, EC-09]
        """
        ...

    @classmethod
    def stop(cls, workspace_root: Optional[Union[str, Path]] = None) -> bool:
        """發送 SIGTERM/SIGINT 優雅停止守護進程並清除 PID 鎖 [FR-07, EC-05]"""
        ...

    @classmethod
    def status(cls, workspace_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """查詢當前守護進程運作狀態、空間簽名與日誌路徑 [FR-07]"""
        ...

    def run_foreground(self) -> None:
        """前台阻塞式運行（用於 watch 模式或背景進程主回圈）"""
        ...

    def _run_startup_check(self) -> None:
        """啟動時先執行一次與 JIT 相同的增量/無效檢查，修補伺服器離線期間的檔案變更 [FR-13, EC-10]"""
        ...

    def _setup_logger(self) -> logging.Logger:
        """建立即時寫入之日誌輸出器，並觸發 3 世代滾動清理 [FR-10, EC-08]"""
        ...

    def _rotate_logs(self) -> None:
        """以每次 PID 生命週期為單位，保留最新 3 份日誌，清理舊日誌 [FR-10]"""
        ...

    def is_path_watched(self, file_path: Union[str, Path]) -> bool:
        """判定檔案是否屬於有效變更 (VCS 忽略目錄、支援副檔名與 Space exclude/pattern 雙軌判定) [FR-15]"""
        ...

    def on_file_changed(self, file_path: str) -> None:
        """監聽回呼：委派 is_path_watched 初篩、重設 500ms 防抖計時器 [FR-03, FR-15, EC-02]"""
        ...

    def _execute_debounced_patch(self) -> None:
        """防抖到期：由單工作線程呼叫 pipeline 執行 AST/BM25/Graph/Vector 熱修補 [FR-04, FR-05]"""
        ...

    def _inactivity_check_loop(self) -> None:
        """定時監測線程：每 10 秒檢查一次，超過 inactivity_timer_sec 自動退出 [FR-06]"""
        ...


def resolve_watch_extensions(
    space_manager: Optional[Any] = None,
    parser_registry: Optional[Any] = None,
) -> Set[str]:
    """動態彙整受監聽之副檔名集合 (100% 由 contributes.languages 與 SpaceConfig 動態決定) [FR-15]"""
    ...



# ==============================================================================
# 3. 生命週期前置勾點 (scripts/hook.core.py)
# ==============================================================================
def on_pre_cli_dispatch(ctx: Optional[Any] = None) -> bool:
    """
    在任何 YSCB CLI 命令分發前觸發：
    1. 檢測 enable_hot_reload_server 組態是否啟用。
    2. 若啟用，調用 HotReloadServer.ensure_running() 確保 Server 存活且版本匹配。
    3. 耗時 <= 10ms，不阻塞前台命令。
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[manifest.json] (宣告 watchdog 相依性)
       │
       ▼
[knowledge_db/config.py] (新增 enable_hot_reload_server 與 inactivity_timer_sec)
       │
       ▼
[knowledge_db/daemon.py] (實作 HotReloadServer 核心、PID/Log 滾動、Watcher、防抖與超時)
       │
       ├────────────────────────────────────────┐
       ▼                                        ▼
[scripts/hook.core.py] (on_pre_cli_dispatch)   [scripts/cli.py] (daemon 子命令)
       │                                        │
       └───────────────────┬────────────────────┘
                           ▼
[tests/test_hot_reload_server.py] (單元與整合測試驗證)
```
