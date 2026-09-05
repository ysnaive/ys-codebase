# API 與介面規格書 (API & Interface Specification)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_generate_internal_gitignore` | `yscb.py` | Internal | 生成含 `/.modules/` 與 `/.build/` 忽略規則之內部標記區塊軟合併 |
| `_restore_module_package` | `yscb.py` | Internal | 模組還原提取函式，將 `build_candidates` 優先級對齊至 `.build/` |
| `contributes/core.json` | `source/core/contributes/core.json` | Manifest | 宣告 `module.build` 空間協議預設解析值為 `yscb://.build/{module}/{version}/` |
| `_BOOTSTRAP_FALLBACK_SCHEMES` | `source/core/core/uri.py` | Internal | 提供內核冷啟動時 `module.build` 預設路徑 `yscb://.build/` |
| `Builder.build_package` | `source/dev/dev/builder.py` | Public | 建置打包發布套件，產物輸出至 `module.build://`（即 `.build/`） |
| `SandboxProvisioner.create_sandbox` | `source/dev/dev/testing/sandbox.py` | Internal | 沙盒環境中自 `module.build://`（即 `.build/`）提取覆蓋最新建置套件 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. 宿主 Git 忽略生成器 (yscb.py)
def _generate_internal_gitignore(engine_dir: str) -> None:
    """
    於 engine_dir 建立或更新 .gitignore。
    使用標記區塊軟合併，注入包含 /.modules/ 與 /.build/ 之規則，
    完整保留宿主既有自訂規則與其他模組之忽略標記區塊。
    """

# 2. 宿主模組還原提取函式 (yscb.py)
def _restore_module_package(
    module_name: str,
    version: str,
    provider_arg: str,
    base_dir: str,
    yscb_root: str,
    dest_dir: str,
    mirror_dir: str
) -> bool:
    """
    自 yscb_abs/.build/<module>/<version>.zip、本地鏡像或 Provider 提取模組。
    建置包候選清單優先探測:
      - os.path.join(yscb_abs, ".build", module_name, f"{version}.zip")
    """

# 3. 語意空間虛擬檔案系統解析契約 (core.uri)
def resolve(uri_str: str, **kwargs) -> str:
    """
    'module.build.root://' -> <yscb_root>/.build/
    'module.build://'      -> <yscb_root>/.build/<current_module>/<current_version>/
    """

# 4. 模組建置打包契約 (dev.dev.builder)
class Builder:
    @classmethod
    def build_package(cls, module_name: str, version: Optional[str] = None, dry_run: bool = False) -> BuildResult:
        """
        打包 source/<module> 輸出至 module.build:// (即 yscb://.build/<module>/<version>.zip)
        並產出 index.json 索引清單。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: yscb.py]
  ├── 1.1 _generate_internal_gitignore 注入 /.build/
  └── 1.2 _restore_module_package 優先探測 .build/
        │
        ▼
[Step 2: core 語意協議層]
  ├── 2.1 source/core/contributes/core.json (module.build -> yscb://.build/{module}/{version}/)
  └── 2.2 source/core/core/uri.py (_BOOTSTRAP_FALLBACK_SCHEMES -> yscb://.build/)
        │
        ▼
[Step 3: dev 工具鏈與沙盒]
  ├── 3.1 source/dev/dev/builder.py (確認 build_package 輸出路徑指向 module.build://)
  └── 3.2 source/dev/dev/testing/sandbox.py (沙盒覆蓋提取對齊 module.build://)
        │
        ▼
[Step 4: 最高工程規範]
  └── 4.1 docs/_project/STANDARDS.md (空間協議表更新為 yscb://.build/，政策標記 🚫 忽略)
        │
        ▼
[Step 5: 單元測試套件與回歸跑測]
  ├── 5.1 source/core/tests/test_build_git_decoupling.py (FT-01~FT-05, ET-01, PT-01)
  └── 5.2 python yscb.py dev test --all (全生態系回歸驗證)
```
