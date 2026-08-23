# API 規格書 (API Specification)

> 功能名稱：fix_yscb_root_path_isolation (Module 檔案系統、快取儲存與 yscb:// 統一路徑轉換器完備性架構)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.2  

---

## 1. 類別與成員總覽

| 類別名稱 | 模組 / 檔案路徑 | 類型 | 職責概述 |
|:---|:---|:---:|:---|
| `ProjectContext` | `core`<br>([`ys_codebase/source/core/scripts/context.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/context.py)) | Modify | 專案環境路徑定位器（修正 `get_yscb_root()`、`get_module_dir()`，新增 `get_module_cache_dir()`、`get_cache_root()`） |
| `ProjectURI` | `core`<br>([`ys_codebase/source/core/scripts/uri.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/uri.py)) | Modify | 語意 URI 統一轉換器（泛型 `cache://`、`storage://` 分流、沙盒圍欄防護、LPM 匹配、`validate()` 與高階 I/O API） |
| `ConfigManager` | `core`<br>([`ys_codebase/source/core/scripts/config.py`](file:///d:/repos/ys_codebase/ys_codebase/source/core/scripts/config.py)) | Modify | 2×2 配置管理器（支援配置值語意 URI 自動遞迴解析展開） |
| `ConfigManager` (Installer) | `installer`<br>([`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py)) | Modify | 安裝器專用配置管理器（修正 `get_yscb_root()` 正確解析相對路徑） |
| `ModuleManager` | `installer`<br>([`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py)) | Modify | 模組管理器（全量安裝/建置/快照路徑錨定 `yscb_root`，新增快取清理與卸載連動） |

---

## 2. API 介面定義 (Python Type Signatures & Docstrings)

### 2.1 `yscb_core.ProjectContext`

```python
class ProjectContext:
    """提供標準化的專案路徑定位、空間解析與模組快取目錄管理能力"""

    CONFIG_FILE: str = "yscb_config.json"
    LOCAL_CONFIG_FILE: str = "yscb_config.local.json"

    @classmethod
    def get_project_root(cls, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得專案使用者主體根目錄 (Project Root, project://)。
        優先序：
        1. 環境變數 YSCB_PROJECT_ROOT
        2. 從 start_dir 向上查找 yscb_config.json (讀取 paths.project_root)
        3. 從 start_dir 向上查找 .git
        4. 當前工作目錄 (Path.cwd())
        """
        ...

    @classmethod
    def get_yscb_root(cls, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得工具庫安裝或配置目錄 (YSCB Root, yscb://)。
        優先序：
        1. 環境變數 YSCB_ROOT
        2. 從 proj_root / yscb_config.json 讀取 paths.yscb_root（相對於 proj_root 解析）
        3. 回退至 proj_root (同層預設)
        """
        ...

    @classmethod
    def get_cache_root(cls, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得工具庫中繼快取總根目錄 (預設為 yscb://.yscb_cache/)。
        優先序：
        1. 環境變數 YSCB_CACHE_ROOT
        2. get_yscb_root(start_dir) / ".yscb_cache"
        """
        ...

    @classmethod
    def get_module_cache_dir(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None, auto_mkdir: bool = True) -> Path:
        """
        取得特定模組專屬的命名空間快取目錄 (yscb://.yscb_cache/modules/<module_name>/)。
        :param module_name: 模組名稱（如 "knowledge-db", "agents-workflow"）
        :param auto_mkdir: 若為 True，目錄不存在時自動遞迴建立 (mkdir -p)
        :return: 該模組專屬快取目錄之絕對 Path
        """
        ...

    @classmethod
    def get_module_storage_dir(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None, auto_mkdir: bool = True) -> Path:
        """
        取得特定模組專屬的持久化儲存目錄 (project://.yscb_storage/<module_name>/)。
        :param module_name: 模組名稱
        :param auto_mkdir: 自動建立目錄
        :return: 該模組專屬持久儲存目錄之絕對 Path
        """
        ...

    @classmethod
    def get_module_dir(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得特定模組的安裝目錄。
        優先自 yscb://modules/<name> (Build 模式)，次之 yscb://source/<name> (Source 模式)。
        徹底移除硬編碼 'ys_codebase'。
        """
        ...
```

---

### 2.2 `yscb_core.ProjectURI`

```python
class ProjectURI:
    """Codebase 專用語意 URI 統一轉換器、格式正規化與沙盒圍欄防護門面"""

    RESERVED_SCHEMES: Tuple[str, ...] = ("project", "yscb", "cache", "storage", "temp")

    @classmethod
    def parse_uri(cls, uri: str) -> Tuple[Optional[str], str, Optional[str]]:
        """
        解析 URI 字串，分離 scheme, subpath 與 authority (namespace)。
        :return: Tuple[scheme, subpath, authority]
        - cache://knowledge-db/index.json -> ("cache", "index.json", "knowledge-db")
        - project://AGENTS.md             -> ("project", "AGENTS.md", None)
        """
        ...

    @classmethod
    def get_base_path(cls, scheme: str, start_dir: Optional[Union[str, Path]] = None, authority: Optional[str] = None) -> Union[Path, str]:
        """
        取得特定 scheme 的基礎路徑 (Base Path)。
        支援泛型 scheme（cache 依 authority 解析至模組快取；storage 解析至模組儲存）。
        若目標模組未安裝或未設定，回傳 "!undefined"。
        """
        ...

    @classmethod
    def validate(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> Tuple[bool, str]:
        """
        校驗傳入 URI 格式完備度與沙盒安全性。
        :return: (is_valid: bool, error_message: str)
        - 檢查 scheme 是否為合法註冊協議
        - 檢查 scoped 協議是否具備 authority
        - 檢查是否包含 .. 越界逃逸嘗試
        """
        ...

    @classmethod
    def resolve(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None, strict: bool = False) -> Union[Path, str]:
        """
        將語意 URI 解析為本機實體絕對 Path。
        1. 格式正規化 (反斜線轉正斜線、去除重複斜線)
        2. 沙盒圍欄檢查 (is_relative_to(base_path))，越界時拋出 SecurityError 或回傳 "!undefined"
        3. 若傳入一般相對路徑，回退至 ProjectContext.resolve()
        """
        ...

    @classmethod
    def to_uri(cls, path: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> str:
        """
        將本機實體路徑反向匹配轉換為最短、最精確的語意 URI。
        採用最長前綴匹配演算法 (Longest Prefix Match, LPM) 與優先級排序。
        """
        ...

    @classmethod
    def exists(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 對應之實體路徑是否存在"""
        ...

    @classmethod
    def is_file(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 是否指向存在之檔案"""
        ...

    @classmethod
    def is_dir(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 是否指向存在之目錄"""
        ...

    @classmethod
    def read_text(cls, uri: Union[str, Path], encoding: str = "utf-8", start_dir: Optional[Union[str, Path]] = None) -> str:
        """自語意 URI 直讀文字內容"""
        ...

    @classmethod
    def write_text(cls, uri: Union[str, Path], content: str, encoding: str = "utf-8", auto_mkdir: bool = True, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """將文字內容直接寫入語意 URI (支援自動建立父目錄)"""
        ...

    @classmethod
    def check_schemes(cls, start_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
        """全量協議健康度檢查，包含實體目錄存在性、權限與越界防護驗證"""
        ...
```

---

### 2.3 `yscb_core.ConfigManager` (遞迴展開支援)

```python
class ConfigManager:
    """管理 2x2 設定檔讀寫與語意 URI 自動遞迴解析"""

    @classmethod
    def load(cls, module_name: Optional[str] = None, include_local: bool = True, start_dir: Optional[Union[str, Path]] = None, resolve_uris: bool = True) -> Dict[str, Any]:
        """
        載入模組或全域設定。
        :param resolve_uris: 若為 True，自動遞迴尋找以 '://' 開頭之字串值並調用 ProjectURI.resolve() 展開為實體路徑
        """
        ...
```

---

### 2.4 CLI 指令介面規範

```bash
# 1. 語意 URI 健康檢查與診斷
python yscb_cli.py uri check

# 2. 模組快取狀態檢視
python yscb_cli.py cache status

# 3. 模組快取清理
python yscb_cli.py cache clean knowledge-db
python yscb_cli.py cache clean --all
```

---

## 3. 關鍵依賴與相容性

| 呼叫功能 | 依賴項目與檔案位置 | 呼叫方式 / 簽名 | 驗證狀態 |
|:---|:---|:---|:---:|
| 專案根目錄解析 | `ProjectContext.get_project_root` | `ProjectContext.get_project_root(start_dir)` | ✅ 已驗證 |
| 工具庫根目錄解析 | `ProjectContext.get_yscb_root` | `ProjectContext.get_yscb_root(start_dir)` | ❌ 待修正 (本次修復) |
| 模組命名空間快取 | `ProjectContext.get_module_cache_dir` | `ProjectContext.get_module_cache_dir(mod)` | ❌ 需新增 (本次新增) |
| 沙盒圍欄檢查 | `pathlib.Path.is_relative_to` | `resolved_p.is_relative_to(base_p)` | ✅ 已驗證 (Python 3.8+ 降級適配) |

> **第三方依賴**：100% 無第三方依賴 (Zero External Dependency)，維持標準庫純淨度。

---

## 4. Decision Records

### [API:DR-01] `ProjectURI.parse_uri` 三元元組回傳契約
- **議題**：`cache://knowledge-db/index.json` 需要區分 Authority (`knowledge-db`) 與 Subpath (`index.json`)，舊版 API 僅回傳 `(scheme, subpath)`。
- **結論**：升級為 `(scheme, subpath, authority)`，非 scoped 協議之 authority 設為 `None`，向後相容 unpack。

### [API:DR-02] Python 3.8 `is_relative_to` 降級相容
- **議題**：標準庫 `Path.is_relative_to()` 於 Python 3.9 引進，而專案承諾支援 Python 3.8+。
- **結論**：內部封裝 `_is_relative_to(p, base)`，在 Python 3.8 透過 `try: p.relative_to(base) except ValueError: False` 實現安全無縫相容。
