# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 專題報告：[R01_dev_toolchain_refactor.md](./R01_dev_toolchain_refactor.md), [R02_release_toolchain_support.md](./R02_release_toolchain_support.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Builder` | `source/dev/dev/builder.py` | Public | 本地開發包 (`build`) 與純淨發布包 (`release`) 打包封裝、3-Revision 淘汰演算法與 `index.json` 實體 SSOT 同步 |
| `Releaser` | `source/dev/dev/releaser.py` | Public | 純淨發布調度器：3-Gate 發布就緒預檢、DAG 依賴拓撲排序批次發布、`release-git` 4 步安全流水線 |
| `Tester` | `source/dev/dev/tester.py` | Public | 端到端沙盒測試調度器：支援預設自動前置執行 `dev build` 與 `--no-build` 旗標 |
| `CLI Commands` | `source/dev/scripts/cli.py` | Public (CLI) | CLI 指令解析與派發門面（`build`, `release`, `test`, `bump-*`, `release-check`, `release-git`） |
| `ReleaseVersionExistsError` | `source/dev/dev/releaser.py` | Public (Exception) | Gate 2 異常：發布四元版本已存在時拋出，阻斷無聲覆蓋 |
| `VersionRollbackError` | `source/dev/dev/releaser.py` | Public (Exception) | Gate 3 異常：發布版本號小於或等於同三元組在庫最高 revision 時拋出，阻斷版本倒退 |
| `CyclicDependencyError` | `source/dev/dev/releaser.py` | Public (Exception) | DAG 拓撲排序異常：全量發布偵測到模組間循環依賴時拋出 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 例外類別規格 (`source/dev/dev/releaser.py`)
```python
class ReleaseVersionExistsError(RuntimeError):
    """當待發布四元版本號已存在於 release 倉庫中時拋出 (Gate 2 阻斷)"""
    pass

class VersionRollbackError(RuntimeError):
    """當待發布版本號小於或等於在庫同三元組最高 revision 時拋出 (Gate 3 阻斷)"""
    pass

class CyclicDependencyError(RuntimeError):
    """當模組依賴關係存在循環時拋出"""
    pass
```

### 2.2 `Builder` 類別規格 (`source/dev/dev/builder.py`)
```python
class Builder:
    def __init__(self, checker: Optional[Checker] = None) -> None: ...

    def build_module(self, name: str) -> Tuple[bool, str]:
        """
        本地開發建置 (dev build <mod>):
        1. 自動清空目標目錄：物理刪除 `build/<name>/` 下所有舊產物。
        2. 讀取 manifest.json，將版本號標記為 `{major}.{minor}.{patch}.build`。
        3. 100% 完整打包所有檔案（包含 `tests/` 與內部開發資產）。
        4. 產出 `build/<name>/<ver>.build.zip` 並更新 `build/<name>/index.json`。
        - Returns: (success: bool, message: str)
        """
        ...

    def build_all(self) -> Dict[str, Tuple[bool, str]]:
        """批次打包 source/ 下所有模組的開發包。"""
        ...

    def package_release(self, name: str, version: str) -> Tuple[bool, str]:
        """
        純淨發布打包 (dev release <mod>):
        1. 純淨過濾：依據 .yscbignore 與 RELEASE_IGNORES 排除 `tests/` 與開發檔案。
        2. 產出單一 `release/<name>/<version>.zip`。
        3. 調用 `_update_release_index` 執行 3-Revision 滑動窗口保留演算法與跨三元組收斂淘汰。
        - Returns: (success: bool, message: str)
        """
        ...

    def _update_release_index(
        self, 
        name: str, 
        description: Optional[str] = None, 
        new_version: Optional[str] = None
    ) -> None:
        """
        3-Revision 時序滑動窗口與跨三元組收斂淘汰演算法：
        1. 若 new_version 存在，掃描 release/<name>/ 所有現存 zip。
        2. 規則 1 (同三元組)：同一個 X.Y.Z 僅保留最新 3 個 Revision zip，第 4 份及更早者物理刪除。
        3. 規則 2 (跨三元組)：若 new_version 為新三元組，所有舊 X.Y.Z 僅保留最高 1 份 Revision zip，其餘延遲 Revision 物理刪除。
        4. 規則 3 (索引 SSOT)：以當前磁碟上真實存在的 zip 包動態生成 release/<name>/index.json。
        """
        ...
```

### 2.3 `Releaser` 類別規格 (`source/dev/dev/releaser.py`)
```python
class Releaser:
    def __init__(self, builder: Optional[Builder] = None, checker: Optional[Checker] = None) -> None: ...

    def release_check(self, module_name: str) -> Tuple[bool, List[str]]:
        """
        獨立發布就緒預檢門面 (dev release-check <mod>):
        - Gate 1: Checker.check_module(module_name) 靜態合規性。
        - Gate 2: 版本不可重複（release/<mod>/<target_ver>.zip 不得存在）。
        - Gate 3: 版本單調遞增（target_ver 必須嚴格大於在庫同三元組最高 revision）。
        - Returns: (passed: bool, error_messages: List[str])
        """
        ...

    def release_module(self, module_name: str) -> Tuple[bool, str]:
        """
        單一模組純淨發布 (dev release <mod>):
        1. 執行 release_check(module_name)，若未通過拋出錯誤/中斷。
        2. 調用 Builder.package_release(module_name, target_version)。
        - Returns: (success: bool, message: str)
        """
        ...

    def release_all(self) -> Dict[str, Tuple[bool, str]]:
        """
        全量模組依賴拓撲批次發布 (dev release --all):
        1. 讀取 source/ 下所有模組 manifest.json 中的 dependencies。
        2. 建構 DAG 並使用 Kahn 演算法計算拓撲發布序列。
        3. 依序調用 release_module()。
        - Returns: Dict[module_name, (success, message)]
        """
        ...

    def release_git(self, module_name: str, commit_msg: str) -> Tuple[bool, str]:
        """
        4 步發布與版本控制安全流水線 (dev release-git <mod> <msg>):
        1. 調用 Tester 執行 dev test <mod>（失敗即中斷）。
        2. 調用 release_check(module_name)（失敗即中斷）。
        3. 調用 release_module(module_name)（失敗即中斷）。
        4. 本地 Git 提交：git add -A -> git commit -m commit_msg -> git tag -a "<mod>/v<ver>" -m commit_msg。
        🚨 防呆約束：嚴禁調用 git push，所有操作僅於本地端完成。
        - Returns: (success: bool, message: str)
        """
        ...
```

### 2.4 CLI 路由規格 (`source/dev/scripts/cli.py`)
```text
python yscb.py dev build [module_name | --all]
python yscb.py dev release [module_name | --all]
python yscb.py dev test [module_name | --all] [--no-build] [test_options]
python yscb.py dev bump-major <module_name>
python yscb.py dev bump-minor <module_name>
python yscb.py dev bump-patch <module_name>
python yscb.py dev bump-revision <module_name>
python yscb.py dev release-check <module_name>        # 傳入 --all 立即阻斷並報錯
python yscb.py dev release-git <module_name> <commit_msg>
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[層級 1: 基礎引擎層]
  └─ Builder (source/dev/dev/builder.py)
     • 移除 clean 選項，build 自動清理目標目錄
     • package_release 純淨打包
     • 實作 3-Revision 滑動窗口與跨三元組收斂淘汰演算法

[層級 2: 測試調度層]
  └─ Tester (source/dev/dev/tester.py)
     • 升級 _run_test 支援預設前置 build 與 --no-build

[層級 3: 發布調度層]
  └─ Releaser (source/dev/dev/releaser.py)
     • 實作 3-Gate 校驗 (release_check)
     • 實作 DAG 依賴拓撲排序 (release_all)
     • 實作 release-git 4 步本地流水線 (嚴禁 push)

[層級 4: 表現層 CLI 路由]
  └─ CLI (source/dev/scripts/cli.py)
     • 簡化 build / release 參數
     • 新增 bump-*, release-check, release-git 路由派發與防呆

[層級 5: 自動化驗證測試]
  └─ test/test_dev_toolchain_refactor.py
     • FT-01 ~ FT-08, ET-01 ~ ET-07, RT-01
```

---

## 4. 架構決策記錄 (Architecture Decision Records)

- **[P03:DR-01] 例外型別分級與精準語意**：
  - 顯式定義 `ReleaseVersionExistsError` 與 `VersionRollbackError`，提供明確的錯誤訊息與阻斷根因，杜絕籠統的 `RuntimeError`。
- **[P03:DR-02] 淘汰演算法於 Builder 內閉環封裝**：
  - 將 3-Revision 滑動窗口與跨三元組收斂邏輯封裝於 `Builder._update_release_index` 內部，確保所有產生發布包的路徑均統一自動執行產物治理。
