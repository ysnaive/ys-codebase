# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`KnowledgeEngine`** | `knowledge_db/engine.py` | Public | Python SDK 頂層統一門面 Facade |
| **`SpaceManager`** | `knowledge_db/space.py` | Public | 空間配置管理與本地快取根目錄解析 (`cache://knowledge-db/`) |
| **`on_test_setup`** | `scripts/hook.dev.py` | Hook | YSCB 沙盒測試前置鉤子（建立 `.cache/knowledge-db/` 結構） |
| **`on_test_teardown`** | `scripts/hook.dev.py` | Hook | YSCB 沙盒測試後置清理鉤子 |
| **`main(argv)`** | `scripts/cli.py` | Entry Point | CLI 完整 6 大子指令路由器 |
| **`_get_module_manifest_from_provider_or_local`** | `core/engine.py` | Internal | 模組 Manifest 解析（嚴格拋錯，禁止 dummy fallback） |
| **`act_download`** | `core/engine.py` | Public | 模組鏡像下載（嚴格 Build 隔離，僅 build revision 存取 `module.build://`） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 空間治理與本地快取 API (`knowledge_db/space.py`)

```python
class SpaceManager:
    """空間治理與路徑解算服務"""

    def _get_storage_root(self) -> Path:
        """
        取得資料庫本機快取根目錄：
        1. 若有 _custom_storage_dir 則優先返回 (支援測試隔離)
        2. 解析 URI "cache://knowledge-db/" (對應 yscb://.cache/knowledge-db/)
        3. 預設回退至 Path("./.cache/knowledge-db").resolve()
        """

    @property
    def storage_dir(self) -> Path:
        """回傳本機快取儲存空間根目錄 (cache://knowledge-db/)"""
```

---

### 2.2 統一門面 SDK (`knowledge_db/engine.py`)

```python
class KnowledgeEngine:
    """knowledge-db 頂層統一門面 SDK"""

    def __init__(
        self,
        storage_dir: Optional[Union[str, Path]] = None,
        local_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        project_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
    ): ...

    def status(self) -> Dict[str, Any]: ...
    def scan(self, space: Optional[str] = None, force: bool = False) -> Dict[str, ScanDiffResult]: ...
    def bundle(self, space: Optional[str] = None, export_path: Optional[Union[str, Path]] = None) -> List[SemanticBundle]: ...
    def build_index(self, space: Optional[str] = None, force: bool = False) -> Dict[str, InvertedIndex]: ...
    def search(self, query: str, space=None, kinds=None, languages=None, min_score=0.01, limit=10) -> List[SearchResult]: ...
    def clean(self, space: Optional[str] = None) -> None: ...
```

---

### 2.3 CLI 6 大子指令體系 (`scripts/cli.py`)

| 指令 | 參數說明 | 行為描述 |
| :--- | :--- | :--- |
| **`status`** | 無 | 列出所有空間配置、來源路徑、指紋數、同義詞數與索引快取狀態 |
| **`scan`** | `[space \| --all] [--force]` | 執行單一空間或全空間聯集之雙階增量指紋掃描（寫入 `cache://`） |
| **`bundle`** | `[space \| --all] [--output=path]` | 打包空間符號為 `SemanticBundle` 並原子導出 `.bundle.json` |
| **`index`** | `[space \| --all] [--force]` | 構建空間符號倒排索引並持久化至 `cache://knowledge-db/indices/` |
| **`search`** | `<query> [--space=name] [--kind=type] [--lang=py] [--limit=10]` | 執行多欄位 BM25 檢索並以終端結構化表格輸出 |
| **`clean`** | `[space \| --all]` | 清理指定空間或全空間之本地端指紋與索引快取檔案 |

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Level 1: 空間管理本地端路徑切換 (knowledge_db/space.py) │
│ - _get_storage_root -> cache://knowledge-db/           │
│ - manifest.json (URI 協議同步更新)                     │
│ - scripts/hook.dev.py (沙盒快取結構準備)                │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 2: 門面 SDK 與 CLI 同步 (engine.py & cli.py)     │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 3: 單元測試與路徑斷言 (test_space.py, test_cli.py)│
└────────────────────────────────────────────────────────┘
```
