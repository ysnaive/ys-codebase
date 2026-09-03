# API 與介面規格書 (API & Interface Specification)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 函式名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_generate_internal_gitignore` | `yscb.py` | Internal | 自動生成包含 `/.modules/` 的內部 Git 忽略清單 |
| `_is_modules_dirty` | `yscb.py` | Internal | 極速嗅探 (<2ms) 比對 `installed_modules` 與本機 `.modules/` |
| `_restore_module_package` | `yscb.py` | Internal | 自本地 provider、build、mirror 或遠端提取單一模組至 `.modules/` |
| `cmd_restore` | `yscb.py` | CLI Command | 批量還原 `installed_modules` 清冊中之所有模組並重載環境 |
| `_ensure_jit_modules_sync` | `yscb.py` | Guard Gate | 命令分發前置之 JIT 自動同步守門與自愈進入點 |
| `_BOOTSTRAP_FALLBACK_SCHEMES` | `source/core/core/uri.py` | Configuration | 預設 `module` 協議解析為 `yscb://.modules/` |
| `uri_schemes[module]` | `source/core/contributes/core.json` | Configuration | 宣告 `module` 空間協議預設為 `yscb://.modules/` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
def _generate_internal_gitignore(yscb_dir: str) -> None:
    """
    自動生成 yscb://.gitignore，確保運行端產物與中繼快取 100% 阻斷於 Git 追蹤之外。
    注入規則包含：/.modules/, /build/, /.mirror/, /.temp/, /.snapshots/, /.cache/ 等。
    """
    ...

def _is_modules_dirty(base_dir: str, yscb_root: str, installed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    極速嗅探 (<2ms) 檢查本機運行端 .modules/ 是否處於 Dirty 狀態。
    
    返回：
        (is_dirty, list_of_missing_or_mismatched_modules)
    判定邏輯：
        1. 若 installed 為空，返回 (False, [])。
        2. 檢查 base_dir/yscb_root/.modules 是否存在；若否，所有模組標記為 dirty。
        3. 走訪 installed 中的每個 module，檢查 .modules/<mod>/manifest.json：
           - 目錄或 manifest 缺失 -> dirty
           - manifest.version != installed[mod]["version"] -> dirty
    """
    ...

def _restore_module_package(
    module_name: str,
    target_version: str,
    provider_arg: str,
    modules_dir: str,
    mirror_dir: str
) -> bool:
    """
    自 Provider 或本機 Mirror 提取指定版本模組，原子解壓縮至 modules_dir/<module_name>。
    支持順序：
        Tier 1: 本地 Provider (release/<mod>/<ver>.zip, release/<mod>)
        Tier 2: 本地 Build (build/<mod>/<ver>.zip, build/<mod>)
        Tier 3: 本機鏡像 (.mirror/<mod>/<ver>.zip)
        Tier 4: 遠端 Provider (HTTP/HTTPS)
    """
    ...

def cmd_restore(argv: List[str]) -> int:
    """
    CLI 指令：python yscb.py restore [--force]
    讀取 yscb.config.json 之 installed_modules 清冊，遍歷批量還原所有模組至 .modules/，
    並於完成後自動調用 dispatch_module('core', ['reload'])。
    """
    ...

def _ensure_jit_modules_sync(base_dir: str, cfg: Dict[str, Any]) -> None:
    """
    JIT 模組同步守門：在 main() 分發 dispatch_module 前調用。
    若偵測到 dirty，非阻塞/自動觸發 cmd_restore([]) 達成自愈。
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: yscb.py 基礎結構]
  └── 1.1 _generate_internal_gitignore (注入 /.modules/)
  └── 1.2 全面切換 modules 路徑組裝為 .modules
       ├── os.path.join(yscb_abs, ".modules")
       ├── dispatch_module -> .modules/<name>/scripts/cli.py
       └── _get_installed_module_commands -> .modules/

[Step 2: yscb.py 還原與 JIT 守門]
  └── 2.1 _restore_module_package (四階 Tier 提取解壓)
  └── 2.2 cmd_restore (批次還原與 reload)
  └── 2.3 _is_modules_dirty & _ensure_jit_modules_sync (JIT 守門)

[Step 3: core 模組協議對齊]
  └── 3.1 source/core/contributes/core.json ("value": "yscb://.modules/")
  └── 3.2 source/core/core/uri.py (_BOOTSTRAP_FALLBACK_SCHEMES "value": "yscb://.modules/")

[Step 4: 最高工程規範更新]
  └── 4.1 docs/_project/STANDARDS.md (module.root:// 與 module:// 更新)

[Step 5: 測試套件建立與驗收]
  └── 5.1 source/core/tests/test_restore_and_jit_modules.py
  └── 5.2 dev test core --sync & dev test --all
```
