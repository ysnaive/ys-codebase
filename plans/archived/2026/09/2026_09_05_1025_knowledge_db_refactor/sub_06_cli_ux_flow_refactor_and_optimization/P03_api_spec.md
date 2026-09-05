# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgeDBConfig` | `knowledge_db/config.py` | Internal | 解析與封裝 Local / Project 級 4 大組態設定與預設值繼承 |
| `EmbeddingService` | `knowledge_db/embedding.py` | Public | 動態支援 `max_threads`、HF Hub 警告抑制、模型白名單校驗 |
| `VectorIndex` | `knowledge_db/embedding.py` | Public | 擴充二進位檔頭保存 `model_name` 與 `dim`，提供相容性檢查介面 |
| `KnowledgePipeline` | `knowledge_db/pipeline.py` | Public | 支援 10 符號動態探針、可配置臨界值熔斷、雙軌進度回報 |
| `TerminalStyler` | `scripts/cli.py` | Internal | 提供 ANSI 色彩與階層美化，自動處理 TTY / NO_COLOR 去色 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. 組態資料結構 (knowledge_db/config.py)
@dataclass
class KnowledgeDBConfig:
    enable_vector_search: bool = True
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    jit_vector_timeout_seconds: float = 5.0
    max_threads: Union[str, int] = "auto"

    @classmethod
    def load(cls, workspace_root: Optional[Path] = None) -> "KnowledgeDBConfig":
        """讀取 local -> project -> default 優先級配置"""
        ...

    def resolve_threads(self) -> int:
        """解析 auto 為 max(1, cpu_count // 2)，整數截斷於 [1, cpu_count]"""
        ...


# 2. 向量特徵服務與索引 (knowledge_db/embedding.py)
class EmbeddingService:
    def __init__(
        self,
        model_name: Optional[str] = None,
        cache_dir: Optional[Union[str, Path]] = None,
        max_threads: Optional[Union[str, int]] = None,
        mock_mode: bool = False,
    ): ...

    def _init_model(self) -> None:
        """設定 HF_HUB 抑制環境變數，以 resolve_threads 設定執行緒上限"""
        ...


class VectorIndex:
    def __init__(self, model_name: Optional[str] = None, dim: Optional[int] = None): ...

    def save_binary(self, file_path: Union[str, Path], compresslevel: int = 1) -> None:
        """於二進位檔頭寫入 JSON 元資料 (model_name, dim, count)"""
        ...

    @classmethod
    def load_binary(cls, file_path: Union[str, Path]) -> "VectorIndex":
        """解碼檔頭元資料並還原矩陣"""
        ...

    def is_compatible_with(self, model_name: str, dim: int) -> bool:
        """檢核當前快取之模型與維度是否相容"""
        ...


# 3. 流水線控制器 (knowledge_db/pipeline.py)
class KnowledgePipeline:
    def hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
        timeout_seconds: float = 5.0,
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        執行差量修補與動態探針：
        回傳: (patched_success: bool, vector_degraded: bool, degrade_notice: Optional[str])
        """
        ...

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
        interactive: bool = False,
    ) -> InvertedIndex:
        """若 interactive=True，輸出 5 階段進度指示與耗時統計"""
        ...


# 4. 終端色彩樣式器 (scripts/cli.py)
class TerminalStyler:
    def __init__(self, stream: Any = sys.stdout):
        self.enabled = stream.isatty() and not os.getenv("NO_COLOR")

    def path(self, text: str) -> str: ...       # 亮藍色
    def symbol(self, text: str) -> str: ...     # 亮綠色
    def kind(self, text: str) -> str: ...       # 亮黃色
    def line(self, text: str) -> str: ...       # 亮青色
    def warn(self, text: str) -> str: ...       # 亮黃色加粗
    def err(self, text: str) -> str: ...        # 亮紅色加粗
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: knowledge_db/config.py (新增 KnowledgeDBConfig 載入器與執行緒計算)
   │
Step 2: knowledge_db/embedding.py (注入 config，實作 HF 屏蔽、max_threads、VectorIndex 檔頭元資料)
   │
Step 3: knowledge_db/pipeline.py (實作 10 符號動態探針、熔斷退回、interactive 雙軌進度)
   │
Step 4: knowledge_db/engine.py (集成 config 注入 pipeline 與 embedding)
   │
Step 5: scripts/cli.py (導入 TerminalStyler、修復 status 與 --help、保證 --json stdout 純淨)
   │
Step 6: tests/test_cli_ux.py (自動化單元測試全覆蓋)
```
