# Core 模組 API 規格手冊 (Core API Reference)

> 所屬模組：`module:core`  
> 抽象維度：維度 2（微觀物件與 API 簽名規格）  

---

## 1. `core.semver` 子模組

```python
from core import semver
```

### 1.1 `parse_semver(v_str: str) -> VersionTuple`
- **說明**：解析語意化版本字串為數值四元組 `VersionTuple(major, minor, patch, prerelease)`。
- **例外**：若格式不符合 SemVer 2.0.0 拋出 `ValueError`。

### 1.2 `compare_semver(v1: str, v2: str) -> int`
- **說明**：比較兩版本優先級大小。`v1 > v2` 返回 `1`，`v1 < v2` 返回 `-1`，相等返回 `0`。

### 1.3 `match_constraint(v_str: str, constraint: Optional[str]) -> bool`
- **說明**：判斷目標版本是否滿足給定之版本範圍約束（如 `">=1.0.0, <2.0.0"`）。

### 1.4 `find_best_version(versions: List[str], constraint: Optional[str] = None) -> Optional[str]`
- **說明**：自候選版本清單中篩選並回傳符合約束之最高版本。

---

## 2. `core.context` 子模組

```python
from core.context import ExecutionContext
```

### 2.1 `ExecutionContext` (不可變數據載體 SSOT)
```python
@dataclass(frozen=True)
class ExecutionContext:
    module_name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 3. `core.uri` 子模組

```python
from core import uri
```

### 3.1 作用域上下文管理器 (Context Managers)
```python
@contextmanager
def module_scope(module_name: str) -> Iterator[str]:
    """暫時切換當前執行模組上下文 (module://)，退出時保證 100% 還原。"""

@contextmanager
def host_scope(host_dir_path: str) -> Iterator[str]:
    """暫時切換宿主環境目錄 (yscb://)，退出時保證 100% 還原。"""
```

### 3.2 VFS IO 函式庫
- `uri.resolve(uri_str: str) -> str`
- `uri.to_uri(abs_path: str) -> str`
- `uri.exists(uri_str: str) -> bool`
- `uri.isfile(uri_str: str) -> bool` (別名: `is_file`)
- `uri.isdir(uri_str: str) -> bool` (別名: `is_dir`)
- `uri.read_text(uri_str: str, encoding: str = "utf-8") -> str`
- `uri.write_text(uri_str: str, content: str, encoding: str = "utf-8") -> None`
- `uri.read_json(uri_str: str, encoding: str = "utf-8") -> Any`
- `uri.write_json(uri_str: str, data: Any, indent: int = 2, encoding: str = "utf-8") -> None`
- `uri.makedirs(uri_str: str, exist_ok: bool = True) -> None`
- `uri.listdir(uri_str: str) -> List[str]`
- `uri.copy(src_uri: str, dst_uri: str) -> None`
- `uri.rmtree(uri_str: str) -> None` (別名: `remove`)

---

## 4. `core.symbols` 子模組

```python
from core import symbols
from core.symbols import resolve_callable, parse_code_func_uri, InvalidSymbolURIError, SymbolNotFoundError
```

### 4.1 `parse_code_func_uri(uri_str: str) -> Tuple[str, str, str]`
- **說明**：解析 `code.func://<module>/<subpath>:<function_name>` 語法，拆解為 `(module_name, subpath, function_name)` 三元組。
- **例外**：若格式不符合協議或缺少 `:` 拋出 `InvalidSymbolURIError`。

### 4.2 `resolve_callable(uri_str: str, context: Optional[Any] = None, use_cache: bool = True) -> Callable`
- **說明**：解析 `code.func://` 協議並動態載入返回 Python Callable 物件。具備雙軌尋址（Package Import + VFS 檔案 Spec 載入）與快取機制。
- **例外**：模組或函式不存在拋出 `SymbolNotFoundError`。

### 4.3 `clear_callable_cache() -> None`
- **說明**：清理符號解析器之內部 Callable 物件快取。

---

## 5. `core.pip_manager` 子模組

```python
from core import PipManager, PipInstallError
```

### 5.1 `PipManager` (私有微虛擬環境管理器)

```python
class PipManager:
    def __init__(self, yscb_dir: Optional[str] = None):
        """初始化 PipManager，yscb_dir 未提供時自動向上探測 yscb.config.json。"""

    @staticmethod
    def parse_pip_dependencies(pip_deps: Any) -> List[str]:
        """
        將 manifest.json 之 pip_dependencies (dict 或 list) 正規化為去重之 pip 規格字串清單。
        - 異常輸入（None、空字典、非預期型態）安全返回 []
        - 自動 strip 空白並保持原始順序去重
        """

    @staticmethod
    def get_current_py_tag() -> str:
        """回傳當前直譯器的大/小版本標籤，例如 'py310'。"""

    def get_venv_dir(self, py_tag: Optional[str] = None) -> str:
        """取得微環境根目錄 (yscb_dir/.venv/py{ver})。"""

    def get_python_executable(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 Python 可執行檔絕對路徑。"""

    def get_site_packages_dir(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 site-packages 絕對路徑。"""

    def ensure_venv(self, py_tag: Optional[str] = None) -> str:
        """微環境就緒與加固，若不存在則以純 Python 標準庫建立。"""

    def install_packages(self, specs: List[str], py_tag: Optional[str] = None) -> None:
        """於微環境執行 Wheel-Only 靜默安裝。"""
```

### 5.2 `PipInstallError` (安裝異常)
- **說明**：當私有微環境調用 pip 安裝失敗時拋出之結構化異常，包含 `returncode`、`stdout`、`stderr`。

