# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_dev_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `CheckReport` | `ys_codebase/source/dev/dev/checker.py` | Public | 封裝靜態檢查結果 (`passed`, `status`, `errors`, `warnings`, `issues`)，移除序列解包魔術方法 (`FR-01`) |
| `Checker` | `ys_codebase/source/dev/dev/checker.py` | Public | 執行 8 步模組靜態合規檢查與扁平化 AST 驗證 (`FR-02`, `FR-07`) |
| `Builder` | `ys_codebase/source/dev/dev/builder.py` | Public | 執行模組開發打包 (`build_module`) 與純淨發布打包 (`package_release`) (`FR-05`) |
| `_create_module_archive_atomic` | `ys_codebase/source/dev/dev/builder.py` | Internal | 原子化建立模組 `.zip` 壓縮包並以 `try...finally` 清理 `.zip.tmp` (`FR-05`, `EC-02`) |
| `Releaser` | `ys_codebase/source/dev/dev/releaser.py` | Public | 執行 3-Gate 發布預檢、拓撲排序批次發布與本地 Git 發布流水線 (`FR-01`, `FR-02`, `FR-08`) |
| `resolve_module_dependency_order` | `ys_codebase/source/dev/dev/releaser.py` | Public | 依模組依賴表執行 Kahn 字母序穩定拓撲排序純函式 (`FR-08`, `EC-04`) |
| `Scaffolder` | `ys_codebase/source/dev/dev/scaffold.py` | Public | 建立標準模組骨架 (`create_module(name, description="")`) (`FR-02`) |
| `Tester` / `_TestRunConfig` | `ys_codebase/source/dev/dev/tester.py` | Public / Internal | 解析測試執行配置並調度單一或平行沙盒測試執行 (`FR-06`) |
| `SandboxProvisioner` | `ys_codebase/source/dev/dev/testing/sandbox.py` | Public | 管理虛擬測試沙盒建置、pip 依賴物化、執行緒安全清理与失敗回滾 (`FR-04`, `EC-01`, `EC-03`) |
| `Requirement` | `ys_codebase/source/dev/dev/testing/requirement.py` | Public | 定義正統測試分類與隔離需求旗標 (`LOGIC`, `ENV`, `NETWORK`, `WORKFLOW`, `PERF`, `ISOLATED_SANDBOX`) (`FR-01`) |
| `filter_suite` | `ys_codebase/source/dev/dev/testing/runner.py` | Public | 依 `pattern`、`test_type`、`target` 遞迴過濾 `unittest.TestSuite` (`FR-02`) |
| `YSCBTestCase` | `ys_codebase/source/dev/dev/testing/case.py` | Public | 提供沙盒測試基類、環境上下文備份還原與 VFS 斷言輔助 (`FR-02`, `FR-03`) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ys_codebase/source/dev/dev/scaffold.py
class Scaffolder:
    def create_module(self, name: str, description: str = "") -> Tuple[bool, str]: ...

# ys_codebase/source/dev/dev/checker.py
@dataclass
class CheckReport:
    module: str
    issues: List[CheckIssue] = field(default_factory=list)
    @property
    def passed(self) -> bool: ...
    @property
    def errors(self) -> List[str]: ...
    @property
    def warnings(self) -> List[str]: ...
    def to_dict(self) -> Dict[str, Any]: ...

class Checker:
    def check_module(self, name: str) -> CheckReport: ...
    def check_all(self) -> Dict[str, CheckReport]: ...

# ys_codebase/source/dev/dev/builder.py
def _create_module_archive_atomic(
    source_dir: str,
    target_zip_path: str,
    ignores: List[str],
    manifest_data: Dict[str, Any],
    target_version: str,
) -> int: ...

class Builder:
    def __init__(self) -> None: ...
    def build_module(self, name: str, clean: bool = True) -> Tuple[bool, str]: ...
    def package_release(self, name: str, target_version: str) -> Tuple[bool, str]: ...
    def build_all(self, clean: bool = True) -> Dict[str, Tuple[bool, str]]: ...

# ys_codebase/source/dev/dev/releaser.py
def resolve_module_dependency_order(
    available_modules: Set[str],
    dep_map: Dict[str, List[str]],
) -> List[str]: ...

class Releaser:
    def __init__(
        self,
        builder: Optional[Builder] = None,
        checker: Optional[Checker] = None,
        tester: Optional[Any] = None,
    ) -> None: ...
    def release_check(self, module_name: str, force: bool = False) -> Tuple[bool, List[str]]: ...
    def release_module(self, module_name: str, force: bool = False, _skip_check: bool = False) -> Tuple[bool, str]: ...
    def release_all(self, force: bool = False) -> Dict[str, Tuple[bool, str]]: ...
    def release_git(self, module_name: str, commit_msg: str, force: bool = False) -> Tuple[bool, str]: ...

# ys_codebase/source/dev/dev/testing/sandbox.py
class SandboxProvisioner:
    @staticmethod
    def adapt_build_pip_dependencies(target_modules: Optional[List[str]] = None) -> List[str]: ...
    @staticmethod
    def create_sandbox(
        target_dir: Optional[str] = None,
        copy_source: bool = True,
        target_modules: Optional[List[str]] = None,
    ) -> SandboxContext: ...
    @staticmethod
    def cleanup_sandbox(sandbox_dir: str, force: bool = False, is_harness_cleanup: bool = False) -> bool: ...
    @staticmethod
    def cleanup_all_sandboxes(
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        is_harness_cleanup: bool = True,
    ) -> int: ...
    @staticmethod
    def prune_sandboxes(
        max_keep: int = 3,
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> int: ...

# ys_codebase/source/dev/dev/testing/runner.py
def filter_suite(
    suite: unittest.TestSuite,
    pattern: Optional[str] = None,
    test_type: Optional[str] = None,
    target: Optional[str] = None,
) -> unittest.TestSuite: ...

# ys_codebase/source/dev/dev/tester.py
@dataclass(frozen=True)
class _TestRunConfig:
    clean_argv: List[str]
    target_mod: Optional[str]
    target_param: Optional[str]
    is_all: bool
    no_build: bool
    keep_sandbox: bool
    is_sequential: bool
    quiet_mode: bool
    verbose: bool
    jobs: Optional[int]
    sync_requested: bool
    is_nested: bool
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `resolve_module_dependency_order`：偵測到循環依賴時拋出 `CyclicDependencyError` (`EC-04`)。
  - `SandboxProvisioner.create_sandbox`：建置中途發生 `FileNotFoundError` 或 `OSError` 時，自動執行 `cleanup_sandbox` 回滾清理並重新拋出原異常 (`EC-01`)。
  - `_create_module_archive_atomic`：壓縮或替換失敗時於 `finally` 區塊清理 `.zip.tmp` 並向上拋出 `OSError` (`EC-02`)。
- **階段決策紀錄**：`[P03:DR-01]` 確立 `_create_module_archive_atomic` 與 `resolve_module_dependency_order` 為模組級純函式，並以 `@dataclass(frozen=True)` 定義 `_TestRunConfig` 統一 `Tester` 單模與多模調度介面。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Layer 1 (Testing Primitives & Leaf Modules):
  - dev/testing/requirement.py
  - dev/scaffold.py
  - dev/checker.py
        |
        v
Layer 2 (Packaging, Release & Sandbox Core):
  - dev/builder.py
  - dev/releaser.py
  - dev/testing/sandbox.py
        |
        v
Layer 3 (Test Execution Framework & CLI Entry):
  - dev/testing/case.py
  - dev/testing/contract.py
  - dev/testing/runner.py
  - dev/testing/__init__.py
  - dev/tester.py
  - scripts/cli.py
        |
        v
Layer 4 (Test Suite Synchronization):
  - tests/test_checker.py, test_release_pipeline.py, test_case.py, test_sandbox.py, test_scaffold.py
```
