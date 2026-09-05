# API 與介面規格書 (API & Interface Specification)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SandboxProvisioner.adapt_build_pip_dependencies` | `source/dev/dev/testing/sandbox.py` | Public | 掃描 build 產物與待測模組之 `pip_dependencies` 並調用 `core.PipManager` 物化。 |
| `SandboxProvisioner._project_venv` | `source/dev/dev/testing/sandbox.py` | Private | 跨平台雙軌微環境投影（Junction / Symlink / .pth 降級）。 |
| `Checker._check_pip_dependencies` | `source/dev/dev/checker.py` | Private | 檢驗 `manifest.json` 中 `pip_dependencies` 結構合規性。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. source/dev/dev/testing/sandbox.py
class SandboxProvisioner:
    @staticmethod
    def adapt_build_pip_dependencies(
        target_modules: Optional[List[str]] = None,
        quiet: bool = False
    ) -> List[str]:
        """
        在建置虛擬基環境之前，掃描當前 build 版（module.build://）或 source 模組中的
        manifest.json 之 pip_dependencies 宣告，調用 core.PipManager 於宿主微環境完成靜默物化。
        
        Args:
            target_modules: 可選，指定模組名稱清單。為 None 或包含 '--all' 時掃描全數。
            quiet: 是否靜默執行。
            
        Returns:
            List[str]: 本次已適配/物化之 pip 規格字串清單。
        """
        ...

    @staticmethod
    def _project_venv(host_yscb_dir: str, sandbox_engine_dir: str) -> bool:
        """
        跨平台零拷貝投影宿主微環境至沙盒 engine/.venv。
        Windows: 優先調用 _winapi.CreateJunction。
        POSIX: 優先調用 os.symlink。
        降級兜底: 若引發 OSError，建立輕量 site-packages 並寫入 host_venv.pth。
        """
        ...

# 2. source/dev/dev/checker.py
class Checker:
    def _check_pip_dependencies(self, name: str, m_data: Dict[str, Any], report: CheckReport) -> None:
        """
        檢核 manifest.json 中 pip_dependencies 欄位：
        - 若存在，必須為 dict 型態 (否則 CheckIssue FAIL)
        - 鍵名必須為合法的非空套件名稱 (否則 CheckIssue FAIL)
        - 約束值必須為字串或 None
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1. checker.py] ➔ 擴充 _check_pip_dependencies 靜態檢核
           │
           ▼
[2. testing/sandbox.py] ➔ 實作 adapt_build_pip_dependencies 與 _project_venv
           │
           ▼
[3. testing/sandbox.py] ➔ 在 create_sandbox 與 cleanup_sandbox 中整合投影與斷開
           │
           ▼
[4. tests/test_pip_adaptation.py] ➔ 編寫單元與整合測試 (FT-01~04, ET-01~02)
```
