# API 與介面規格書 (API & Interface Specification)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PipManager` | `source/core/core/pip_manager.py` | Public | 私有微環境之建立、跨平台路徑解析與 Wheel-Only 靜默安裝引擎 |
| `PipInstallError` | `source/core/core/pip_manager.py` | Public | 私有微環境 pip 安裝失敗時拋出之結構化異常 |
| `IdeProjector` | `source/core/core/ide_projector.py` | Public | 專案 IDE 自動感知與明確標示 `_yscb_managed` 之可復原軟合併投影器 |
| `_ensure_private_venv_path` | `yscb.py` | Internal | 命令分發前置之微環境 `sys.path` 極速嗅探與動態注入進入點 |
| `Installer.install_pip_dependencies` | `source/core/core/installer.py` | Public | 收集全模組 `pip_dependencies` 聯集並調用 `PipManager` 批次物化 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ==============================================================================
# 1. source/core/core/pip_manager.py
# ==============================================================================

class PipInstallError(RuntimeError):
    """當私有微環境調用 pip 安裝失敗時拋出。"""
    def __init__(self, message: str, returncode: int = 1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class PipManager:
    """YSCB 私有微虛擬環境管理器：管理 yscb.venv://，實施版本分層與 Wheel-Only 安裝。"""

    def __init__(self, yscb_dir: Optional[str] = None):
        self.yscb_dir = yscb_dir or self._resolve_yscb_root()

    @staticmethod
    def get_current_py_tag() -> str:
        """回傳當前直譯器的大/小版本標籤，例如 'py310' 或 'py311'。"""
        ...

    def get_venv_dir(self, py_tag: Optional[str] = None) -> str:
        """取得特定 Python 版本標籤之微環境根目錄 (yscb_dir/.venv/py{ver})。"""
        ...

    def get_python_executable(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 Python 可執行檔絕對路徑 (POSIX: bin/python, Windows: Scripts/python.exe)。"""
        ...

    def get_site_packages_dir(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 site-packages 絕對路徑 (POSIX: lib/pythonX.Y/site-packages, Windows: Lib/site-packages)。"""
        ...

    def ensure_venv(self, py_tag: Optional[str] = None) -> str:
        """若微環境不存在則以純 Python 標準庫 venv 建立，保證 include-system-site-packages = false。"""
        ...

    def install_packages(self, specs: List[str], py_tag: Optional[str] = None) -> None:
        """
        調用微環境之 python -m pip 執行 Wheel-Only 靜默安裝。
        強制附加參數: ['install', '--only-binary=:all:', '--no-warn-script-location', '--quiet', *specs]
        """
        ...


# ==============================================================================
# 2. source/core/core/ide_projector.py
# ==============================================================================

class IdeProjector:
    """IDE 自動感知投影器：探測 project://.vscode 並以 _yscb_managed 執行非破壞性可復原軟合併。"""

    YSCB_MANAGED_KEY = "_yscb_managed"

    def __init__(self, yscb_dir: Optional[str] = None):
        self.yscb_dir = yscb_dir or self._resolve_yscb_root()

    def is_vscode_configured(self, proj_root: str) -> bool:
        """探測專案是否配置 VS Code (即 project://.vscode 是否存在為目錄)。"""
        ...

    def sync_vscode_settings(
        self,
        proj_root: str,
        pip_mgr: Optional[PipManager] = None,
        extra_paths: Optional[List[str]] = None,
    ) -> bool:
        """
        若 project://.vscode 存在，原子增量更新 settings.json：
        - 於 _yscb_managed 登記 YSCB 注入之路徑清單；
        - 更新 python.analysis.extraPaths (差集替換舊 YSCB 路徑，100% 保留使用者自訂路徑)；
        - 更新 python.defaultInterpreterPath 指向微環境 Python；
        - 若 project://.vscode 不存在則靜默略過，回傳 False。
        """
        ...

    def revert_vscode_settings(self, proj_root: str) -> bool:
        """依據 _yscb_managed 標記清冊，100% 乾淨剔除 YSCB 注入之所有路徑與鍵值，復原原檔。"""
        ...


# ==============================================================================
# 3. yscb.py (宿主注入進入點)
# ==============================================================================

def _ensure_private_venv_path(yscb_dir: str) -> None:
    """
    極速探測 (<0.1ms) 當前 Python 版本對應之 yscb_dir/.venv/py{ver}/.../site-packages。
    若存在且不在 sys.path 則插入至 sys.path[0]。
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 基礎協議與忽略規則]
  ├── 1.1 yscb.py: INTERNAL_IGNORE_PATTERNS 加入 /.venv/
  ├── 1.2 source/core/contributes/core.json: 宣告 yscb.venv 協議
  ├── 1.3 source/core/core/uri.py: 註冊 _BOOTSTRAP_FALLBACK_SCHEMES["yscb.venv"]
  └── 1.4 docs/_project/STANDARDS.md: 更新空間協議表，政策標記 🚫 忽略
        │
        ▼
[Step 2: 私有微環境管理器]
  └── 2.1 source/core/core/pip_manager.py (PipManager, PipInstallError)
        │
        ▼
[Step 3: IDE 自動感知與可復原軟合併投影器]
  └── 3.1 source/core/core/ide_projector.py (IdeProjector)
        │
        ▼
[Step 4: 宿主啟動動態注入與還原管線]
  ├── 4.1 yscb.py: _ensure_private_venv_path 動態注入
  └── 4.2 yscb.py: cmd_restore 整合 Pip 依賴物化
        │
        ▼
[Step 5: 安裝器對接]
  └── 5.1 source/core/core/installer.py: pip_dependencies 聯集解析與觸發物化
        │
        ▼
[Step 6: 單元測試與回歸驗證]
  ├── 6.1 source/core/tests/test_venv_core.py
  └── 6.2 python yscb.py dev test core --quiet
```
