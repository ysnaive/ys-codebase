# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_BOOTSTRAP_FALLBACK_SCHEMES` | `core/uri.py` | Internal | 定義核心內建語意 URI 協議（新增 `config.local` 與 `storage.local`） |
| `ConfigManager.get_config_path` | `core/config.py` (`core.config`) | Public | 取得指定模組之 Project (`config://`) 或 Local (`config.local://`) 設定檔物理絕對路徑（100% 純淨定址） |
| `ConfigManager.list_modules` | `core/config.py` (`core.config`) | Public | 掃描 `config://` 與 `config.local://` 回傳所有具備組態檔的模組名稱排序清單 |
| `AtomicEngine._resolve_target_cfg_uris` | `core/engine.py` | Internal | 解析 `configurable/` 模板對應之目標 URI（`*.local.json` 指向 `config.local://<mod>/`） |
| `AtomicEngine.act_snapshot` / `act_restore_snapshot` | `core/engine.py` | Public | 建立與還原系統交易快照（含 `config.local://`，排除 `storage.local://` 與 `cache://`） |
| `AtomicEngine.act_delete` | `core/engine.py` | Public | 刪除模組運行時與快取；當 `purge=True` 時一併抹除 `storage`、`storage.local`、`config`、`config.local` 四大空間 |
| `AtomicEngine.act_migrate` | `core/engine.py` | Public | 執行多段式增量遷移階梯（支援 `{major}.{minor}.x.py`、`{major}.{minor}.{patch}.x.py` 與 `{major}.{minor}.{patch}.{rev}.py`） |
| `migrate` | `core/scripts/migrations/1.2.7.x.py` | Internal (Hook) | `core` 升級至 `1.2.7.*` 時執行之遷移腳本：將全模組舊版 `config://<mod>/config*.local.json` 無損遷入 `config.local://<mod>/config*.local.json` |
| `SandboxContext.set_module_config` | `dev/dev/testing/sandbox.py` | Public | 於測試沙盒內設定模組組態檔（`*.local.json` 寫入 `.config.local/<mod>/`） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. ys_codebase/source/core/core/uri.py
_BOOTSTRAP_FALLBACK_SCHEMES: List[Dict[str, str]] = [
    {"token": "yscb.host", "type": "const", "value": "{yscb_host}"},
    {"token": "module.mirror", "type": "const", "value": "yscb://.mirror/"},
    {"token": "snapshot", "type": "const", "value": "yscb://.snapshots/"},
    {"token": "module", "type": "const", "value": "yscb://.modules/"},
    {"token": "config", "type": "const", "value": "yscb://config/"},
    {"token": "config.local", "type": "const", "value": "yscb://.config.local/"},
    {"token": "cache", "type": "const", "value": "yscb://.cache/"},
    {"token": "storage", "type": "const", "value": "yscb://storage/"},
    {"token": "storage.local", "type": "const", "value": "yscb://.storage.local/"},
    {"token": "module.source", "type": "const", "value": "yscb://source/"},
    {"token": "module.build", "type": "const", "value": "yscb://.build/"},
    {"token": "module.release", "type": "const", "value": "yscb://release/"},
    {"token": "yscb.venv", "type": "const", "value": "yscb://.venv/"},
]


# 2. ys_codebase/source/core/core/config.py
class ConfigManager:
    @classmethod
    def get_config_path(cls, module: str, local: bool = False) -> str:
        """
        Returns the physical absolute file path for a module's configuration file:
        - `local=False` -> `<yscb_root>/config/<module>/config.project.json` (`config://{module}/config.project.json`)
        - `local=True`  -> `<yscb_root>/.config.local/<module>/config.local.json` (`config.local://{module}/config.local.json`)
        """


# 3. ys_codebase/source/core/core/engine.py
class AtomicEngine:
    def act_migrate(self, module_name: str, old_version: str, new_version: str) -> bool:
        """
        Executes Multi-Segment Incremental Migration Ladder:
        - Evaluates version differential within the same major version across:
          1. `{major}.{minor}.x.py` (triggered when `(old.major, old.minor) < (major, minor) <= (new.major, new.minor)`)
          2. `{major}.{minor}.{patch}.x.py` (triggered when `old.triplet < (major, minor, patch) <= new.triplet`)
          3. `{major}.{minor}.{patch}.{rev}.py` (triggered when `compare_semver(old_version, script_ver) < 0` and `compare_semver(new_version, script_ver) >= 0`)
        - Executes matching scripts in ascending version order with `context` containing:
          `host_dir`, `yscb_dir`, `config_dir`, `config_local_dir`, `storage_dir`, `storage_local_dir`, `old_version`, `target_version`.
        - Raises RuntimeError on script failure to trigger atomic snapshot rollback.
        """


# 4. ys_codebase/source/core/scripts/migrations/1.2.7.x.py
def migrate(context: Dict[str, Any]) -> bool:
    """
    Core 1.2.7.x migration hook invoked by `AtomicEngine.act_migrate`:
    Scans `<yscb_dir>/config/<mod>/config*.local.json` across all modules and migrates
    them into `<yscb_dir>/.config.local/<mod>/config*.local.json`.
    If target file already exists (e.g. seeded during `act_reload`), deep-merges
    legacy user settings over the newly seeded defaults and removes the legacy file.
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

1. **Step 1 (`core.uri` / `contributes/core.json` / `gitignore.py` / `installer.py`)**：先確立 `config.local://` 與 `storage.local://` 底層協議解析與 `.gitignore` 保護規則。
2. **Step 2 (`core.config` / `dispatcher.py` / `1.2.7.x.py`)**：切換雙軌組態讀寫路徑並註冊 `core` `1.2.7.0` 遷移腳本。
3. **Step 3 (`core.engine` / `vscode-support` / `dev`)**：更新組態模板部署、快照備份、深度清理 (`--purge`)、多段式 `act_migrate` 以及 IDE Schema / 測試沙盒輔助函式。

### 3.1 資料結構與 Schema 定義 (Data Structures & Schemas)

- **`core/contributes/core.json` (`uri_schemes` & `gitignore`)**：
  ```json
  {
    "token": "config.local",
    "type": "const",
    "value": "yscb://.config.local/",
    "description": "模組本機私有設定與機密憑證空間根目錄 (Git 忽略、磁碟持久)"
  },
  {
    "token": "storage.local",
    "type": "const",
    "value": "yscb://.storage.local/",
    "description": "模組本機持久化狀態帳本、模型與索引空間根目錄 (Git 忽略、磁碟持久、免快照)"
  }
  ```
  以及 `gitignore` 陣列新增：
  ```json
  "yscb://.config.local/",
  "yscb://.storage.local/"
  ```
- **VS Code `json.schemas` `fileMatch` 綁定 (`vscode_support/schema_compiler.py`)**：
  ```json
  {
    "fileMatch": [
      "**/config/<mod>/config.*.json",
      "**/.config.local/<mod>/config.*.json"
    ],
    "url": "./.vscode/schemas/config/<mod>.schema.json"
  }
  ```
