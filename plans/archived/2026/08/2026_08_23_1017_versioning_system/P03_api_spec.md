# API 規格書 (API Specification)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.2  

---

## 1. 類別與成員總覽 (Architecture Class Overview)

| 類別 / 模組名稱 | 檔案路徑 | 類型 | 職責概述 |
|:---|:---|:---:|:---|
| `SemVer` | `ys_codebase/source/core/scripts/semver.py` | **NEW** | SemVer 2.0.0 解析器、富比較運算符與版本剛性遞進 (Bump) 引擎。 |
| `VersionConstraint` | `ys_codebase/source/core/scripts/semver.py` | **NEW** | 版本相依約束表達式解析與匹配器 (`^`, `~`, `>=`, `<=`, `==`, `*`)。 |
| `MigrationRunner` | `ys_codebase/source/core/scripts/migration.py` | **NEW** | 鏈式線性增量遷移框架，支援 `@runner.step("1.1.x")` 註冊與依序執行。 |
| `ProjectContext` (擴充) | `ys_codebase/source/core/scripts/yscb_core.py` | **MOD** | 新增 `get_module_version()` 與 `get_module_manifest()` 公開介面。 |
| `InstallerManager` (擴充) | `ys_codebase/yscb_installer.py` | **MOD** | 實作相依約束檢查與五階段事務升級回滾流水線 (`safe_upgrade_module`)。 |
| `CLI Router` (擴充) | `ys_codebase/source/core/scripts/cli.py` | **MOD** | 實作 `version status`, `version check-update`, `version bump`, `version check`。 |
| `verify_plan` (擴充) | `ys_codebase/source/agents-workflow/scripts/verify_plan.py` | **MOD** | 實作抽象外掛式 Hook (`run_extension_verifiers`)。 |
| `DogfoodingVerifier` | `extensions/dogfooding_pipeline_verify.py` | **NEW** | 專案特化發布守門：源碼修改版本遞增、三態一致性與 CHANGELOG 稽核。 |

---

## 2. API 介面定義 (Python Typed Signatures & Specs)

### 2.1 `SemVer` 語意化版本引擎 (`source/core/scripts/semver.py`)

```python
from typing import Optional, Union, Tuple

class SemVer:
    """
    純標準庫 SemVer 2.0.0 語意化版本解析與比較引擎。
    支援 MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD] 格式解析與富比較運算。
    """
    major: int
    minor: int
    patch: int
    prerelease: Optional[str]
    build: Optional[str]

    def __init__(self, version_str: Union[str, 'SemVer']):
        """
        初始化 SemVer 物件。
        
        :param version_str: 版本字串（如 "2.1.0", "v1.0.0-beta+exp"）或既有 SemVer 實例。
        :raises ValueError: 當版本字串無法解析為合法 SemVer 格式時拋出。
        """
        ...

    @classmethod
    def parse(cls, version_str: str) -> 'SemVer':
        """安全解析版本字串，寬容去除前綴 'v'、空格與短格式補齊。"""
        ...

    @classmethod
    def is_valid(cls, version_str: str) -> bool:
        """判定版本字串是否為合法 SemVer 格式。"""
        ...

    def bump_major(self) -> 'SemVer':
        """遞進 MAJOR 版本 (X.0.0)，MINOR 與 PATCH 歸零。"""
        ...

    def bump_minor(self) -> 'SemVer':
        """遞進 MINOR 版本 (X.Y.0)，PATCH 歸零。"""
        ...

    def bump_patch(self) -> 'SemVer':
        """遞進 PATCH 版本 (X.Y.Z)。"""
        ...

    def bump(self, level: str) -> 'SemVer':
        """
        依指定級別遞進版本。
        
        :param level: 'major' | 'minor' | 'patch' (不分大小寫)
        :return: 遞進後的新 SemVer 物件
        :raises ValueError: 當 level 不合法時拋出
        """
        ...

    # 富比較運算符 (Rich Comparisons)
    def __lt__(self, other: Union[str, 'SemVer']) -> bool: ...
    def __le__(self, other: Union[str, 'SemVer']) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __ne__(self, other: object) -> bool: ...
    def __ge__(self, other: Union[str, 'SemVer']) -> bool: ...
    def __gt__(self, other: Union[str, 'SemVer']) -> bool: ...

    def __str__(self) -> str:
        """回傳規範化版本字串 (例: '2.1.0' 或 '1.0.0-alpha.1')。"""
        ...
```

---

### 2.2 `VersionConstraint` 相依約束引擎 (`source/core/scripts/semver.py`)

```python
class VersionConstraint:
    """
    語意版本相依約束表達式解析與匹配器。
    支援語法：
      - 精確比對: "==1.2.0" 或 "1.2.0"
      - 區間比較: ">=1.0.0, <2.0.0" 或 ">=2.0.0"
      - Caret 相容: "^1.2.3" (鎖定 major 或 0.x minor)
      - Tilde 相容: "~1.2.0" (鎖定 major.minor)
      - 萬用字元: "*" 或 ""
    """
    raw_expr: str

    def __init__(self, constraint_expr: str):
        """
        解析約束表達式。
        
        :param constraint_expr: 約束字串 (例: ">=2.0.0", "^1.0.0")
        """
        ...

    def matches(self, version: Union[str, SemVer]) -> bool:
        """
        判定目標版本是否滿足本約束條件。
        
        :param version: 待校驗之版本字串或 SemVer 實例
        :return: True 表相容滿足，False 表衝突不滿足
        """
        ...

    @classmethod
    def parse_dependency_spec(cls, spec_str: str) -> Tuple[str, 'VersionConstraint']:
        """
        解析 manifest.json 中的 dependencies 項目。
        
        :param spec_str: 如 "core >= 2.0.0" 或 "core"
        :return: (module_name, VersionConstraint 實例)
        :example:
            parse_dependency_spec("core >= 2.0.0") -> ("core", VersionConstraint(">= 2.0.0"))
            parse_dependency_spec("core") -> ("core", VersionConstraint("*"))
        """
        ...
```

---

### 2.3 `MigrationRunner` 鏈式增量遷移框架 (`source/core/scripts/migration.py`)

```python
from pathlib import Path
from typing import Callable, List, Dict

class MigrationRunner:
    """
    鏈式線性增量遷移執行器。
    管理模組各代際步階 handler，按版本序列 old_ver < step_base <= new_ver 循序調用。
    """
    def __init__(self):
        self._steps: List[Tuple[SemVer, str, Callable[[Path, Path], None]]] = []

    def step(self, milestone: str) -> Callable:
        """
        裝飾器：註冊特定 Minor 代際步階 handler。
        
        :param milestone: 代際字串 (例: "1.1.x", "1.2.x", "2.0.x" 或 "1.1.0")
        """
        def decorator(func: Callable[[Path, Path], None]) -> Callable:
            ...
            return func
        return decorator

    def run(
        self,
        old_version_str: str,
        new_version_str: str,
        project_root: Optional[Path] = None,
        module_dir: Optional[Path] = None
    ) -> List[str]:
        """
        執行鏈式增量遷移。
        
        :param old_version_str: 舊版本號
        :param new_version_str: 新版本號
        :param project_root: 專案根目錄 (預設由 ProjectContext 解析)
        :param module_dir: 模組安裝目錄 (預設為當前執行路徑)
        :return: 已成功執行的步階標籤清單 (例: ["1.1.x", "1.2.x"])
        :raises Exception: 任一步階執行失敗時立即拋出，中斷流水線
        """
        ...
```

---

### 2.4 `ProjectContext` 與 `InstallerManager` 核心擴充

```python
# yscb_core.py
class ProjectContext:
    @classmethod
    def get_module_version(cls, module_name: str) -> Optional[SemVer]:
        """讀取指定模組之 manifest.json 並回傳 SemVer 實例，未安裝回傳 None。"""
        ...

    @classmethod
    def get_module_manifest(cls, module_name: str) -> Optional[Dict[str, Any]]:
        """讀取指定模組之 manifest.json 內容。"""
        ...

# yscb_installer.py
class InstallerManager:
    def check_module_dependencies(self, module_name: str, manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        校驗模組相依性約束。
        
        :return: (is_valid: bool, error_messages: List[str])
        """
        ...

    def safe_upgrade_module(
        self,
        module_name: str,
        src_path: Path,
        mode: str = "build",
        force: bool = False
    ) -> bool:
        """
        五階段事務性安全升級流水線：
          Stage 1: Pre-flight Check (SemVer & 相依性檢查)
          Stage 2: Staging & Snapshot Backup (.yscb_cache/backup/)
          Stage 3: Protected Merge (代碼覆蓋, 2x2 config 增量合併, AGENTS.md 軟合併)
          Stage 4: Migration Execution (_migration.py 鏈式調用，失敗立即觸發 Rollback)
          Stage 5: Commit & Finalize (_installed.py, 更新 installed_modules)
        """
        ...
```

---

### 2.5 抽象外掛式稽核與專案特化守門 API

```python
# verify_plan.py (通用抽象 Hook)
def run_extension_verifiers(plan_dir: Path, header_info: Dict[str, Any]) -> List[Tuple[str, bool, str]]:
    """
    掃描 Plan Header 之 '> 擴充項目：'，自動探測並調用 sop_ext://<ext_name>_verify.py。
    
    :return: [(ext_name, passed: bool, message: str)]
    """
    ...

# extensions/dogfooding_pipeline_verify.py (專案特化發布守門)
def verify_dogfooding_release(plan_dir: Path) -> Tuple[bool, List[str]]:
    """
    本專案特化發布校驗：
      1. 檢查源碼若有實質變更，manifest.json 版本號是否已遞增
      2. 檢查全模組【源碼 == 建置 == 安裝】三態版本一致性
      3. 檢查 CHANGELOG.md 是否已記錄本次變更摘要
    """
    ...
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 依賴項目與檔案位置 | 呼叫方式 / 簽名 | 驗證狀態 |
|:---|:---|:---|:---:|
| 正則解析 | `re` (標準庫) | `re.compile(SEMVER_REGEX)` | ✅ 已驗證 |
| 路徑與複製 | `pathlib.Path`, `shutil` (標準庫) | `shutil.copytree`, `Path.read_text` | ✅ 已驗證 |
| 子程序調用 | `subprocess` (標準庫) | `subprocess.run([sys.executable, ...])` | ✅ 已驗證 |
| JSON 處理 | `json` (標準庫) | `json.loads`, `json.dumps` | ✅ 已驗證 |

> **第三方依賴**：**無 (100% Zero External Dependency)**。

---

## 4. Decision Records

### `[API:DR-01]`: 相依相容性表達式寬容語法與解析器設計
- **議題**：相依表達式中模組名稱與約束條件的切分方式。
- **結論**：支援空白或比較運算符直接切分，如 `"core >= 2.0.0"`、`"core^1.0.0"`、`"core"`。
- **理由**：相容不同開發者在 `manifest.json` 中的書寫習慣，並相容既有純名稱寫法。
