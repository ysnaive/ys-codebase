---
target: "Core/Base"
doc_type: "readme"
status: "active"
source_paths:
  - "source/core/manifest.json"
  - "source/core/scripts/"
related_docs:
  - "./SEMANTIC_URI_SYSTEM.md"
  - "../_project/ARCHITECTURE.md"
  - "../Installer/README.md"
  - "../AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md"
last_updated: "2026-08-23"
---

# Core 核心基底模組 (`core` / `yscb_core`)

`core` 是 `ys-codebase` 工具庫的官方運行期 SDK（Runtime SDK），為所有模組提供專案定位、語意 URI 統一轉換器、模組專屬快取/持久儲存空間、2×2 設定管理、跨模組貢獻通道與統一控制台輸出的標準工具類。

---

## 🏛️ 模組角色與分流

1. **標準相依基底 (Mandatory Dependency)**：
   - 任何業務模組均需在 `manifest.json` 宣告 `"dependencies": ["core >= 2.0.0"]`。
   - 在 Build 模式下自動安裝至 `yscb://modules/core/`；在 Source 模式下自動安裝至 `yscb://source/core/`。
2. **標準 Build 產出**：
   - `core` 支援標準 `installer build core`，產出純淨的 `build/core/` 發布物供下游使用。

---

## 📦 `yscb_core` SDK 類別總覽

### 1. `ProjectContext` (路徑定位與模組空間)
- `ProjectContext.get_project_root(start_dir) -> Path`：取得專案根目錄 (`project://`)。
- `ProjectContext.get_yscb_root(start_dir) -> Path`：動態解析工具庫根目錄 (`yscb://`)。
- `ProjectContext.get_cache_root(start_dir) -> Path`：取得工具庫快取根目錄 (`yscb://.yscb_cache/`)。
- `ProjectContext.get_module_cache_dir(module_name, start_dir) -> Path`：自動建立並回傳模組專屬快取目錄 (`yscb://.yscb_cache/modules/<module>/`)。
- `ProjectContext.get_module_storage_dir(module_name, start_dir) -> Path`：取得模組專案持久儲存目錄 (`project://.yscb_storage/<module>/`)。
- `ProjectContext.get_module_dir(module_name, start_dir) -> Path`：從 `yscb_root` 查找特定模組目錄。
- `ProjectContext.get_contributions(namespace, start_dir) -> List[Tuple[str, Path, Dict]]`：提取宣告指定 namespace 貢獻之模組名稱、根目錄與 payload。

### 2. `ProjectURI` (語意 URI 統一路徑轉換器)
*(詳見專題手冊：[`SEMANTIC_URI_SYSTEM.md`](./SEMANTIC_URI_SYSTEM.md))*
- `ProjectURI.resolve(uri, start_dir, strict=False) -> Union[Path, str]`：解析語意 URI 為實體絕對路徑。
- `ProjectURI.to_uri(file_path, start_dir) -> str`：最長前綴匹配 (LPM) 反向轉換實體路徑為語意 URI。
- `ProjectURI.validate(uri, start_dir) -> Tuple[bool, str]`：完備度與沙盒安全校驗門面。
- `ProjectURI.exists / is_file / is_dir / read_text / write_text`：Direct I/O 快捷操作門面。
- `ProjectURI.check_schemes(start_dir) -> List[Dict]`：全協議健康狀態與沙盒診斷。

### 3. `ConfigManager` (2×2 矩陣設定管理員)
- `ConfigManager.load(module_name, resolve_uris=True) -> dict`：
  依序合併：範本 ➔ Codebase.Project ➔ Codebase.User ➔ Module.Project ➔ Module.User，並自動遞迴解析語意 URI。
- `ConfigManager.resolve_config_uris(data, start_dir) -> Any`：遞迴解析字典/清單內之語意 URI。
- `ConfigManager.save_project_config(module_name, data)`：寫入 `config.project.json`（進 Git）。
- `ConfigManager.save_user_config(module_name, data)`：寫入 `config.local.json`（忽略 Git）。

### 4. `Console` (統一終端輸出)
- 提供 `info()`, `success()`, `warn()`, `error()`, `header()`, `table()` 等跨平台標準輸出。

---

## 📁 模組源碼結構
```text
source/core/
├── manifest.json                   # 模組元數據 (name: "core", version: "2.3.0")
├── README.md                       # Core 說明手冊
└── scripts/                        # Python SDK 源碼
    ├── __init__.py                 # 導出 ProjectContext, ProjectURI, ConfigManager, Console, SemVer
    ├── context.py                  # ProjectContext (空間與快取目錄解析)
    ├── uri.py                      # ProjectURI (五層協議轉換與沙盒防護)
    ├── config.py                   # ConfigManager (2x2 設定與 URI 展開)
    ├── console.py                  # Console (控制台輸出)
    └── semver.py                   # SemVer & VersionConstraint (語意化版本引擎)
```
