---
target: "Core/Base"
doc_type: "readme"
status: "active"
source_paths:
  - "source/core/manifest.json"
  - "source/core/yscb_core/"
related_docs:
  - "../_project/ARCHITECTURE.md"
  - "../Installer/README.md"
  - "../AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md"
last_updated: "2026-08-23"
---

# Core 核心基底模組 (`core` / `yscb_core`)

`core` 是 `ys-codebase` 工具庫的官方運行期 SDK（Runtime SDK），為所有模組提供專案定位、2×2 設定管理、跨模組貢獻通道與統一控制台輸出的標準工具類。

---

## 🏛️ 模組角色與分流

1. **標準相依基底 (Mandatory Dependency)**：
   - 任何業務模組均需在 `manifest.json` 宣告 `"dependencies": ["core"]`。
   - 在 Build 模式下自動安裝至 `modules/core/`；在 Source 模式下自動安裝至 `source/core/`。
2. **標準 Build 產出**：
   - `core` 支援標準 `installer build core`，產出純淨的 `build/core/` 發布物供下游使用。

---

## 📦 `yscb_core` SDK 類別總覽

### 1. `ProjectContext` (路徑與專案環境定位)
- `ProjectContext.get_project_root(start_dir) -> Path`：自動向上查找專案根目錄。
- `ProjectContext.get_yscb_root(start_dir) -> Path`：取得工具庫核心目錄。
- `ProjectContext.get_module_dir(module_name, start_dir) -> Path`：取得特定模組目錄。
- `ProjectContext.resolve(rel_path, start_dir) -> Path`：將相對路徑轉換為專案絕對路徑。
- `ProjectContext.get_all_installed_manifests(start_dir) -> Dict[str, Tuple[Path, Dict[str, Any]]]`：安全掃描已安裝/源碼模組之 `manifest.json`。
- `ProjectContext.get_contributions(namespace: str, start_dir) -> List[Tuple[str, Path, Dict[str, Any]]]`：提取所有宣告指定 namespace 貢獻之模組名稱、根目錄與 payload 字典。

### 2. `ConfigManager` (2×2 矩陣設定管理員)
- `ConfigManager.load(module_name) -> dict`：
  依序合併：範本 ➔ Codebase.Project ➔ Codebase.User ➔ Module.Project ➔ Module.User。
- `ConfigManager.save_project_config(module_name, data)`：寫入 `config.project.json`（進 Git）。
- `ConfigManager.save_user_config(module_name, data)`：寫入 `config.local.json`（忽略 Git）。

### 3. `Console` (統一終端輸出)
- 提供 `info()`, `success()`, `warn()`, `error()`, `header()`, `table()` 等跨平台標準輸出。

---

## 📁 模組源碼結構
```text
source/core/
├── manifest.json                   # 模組元數據 (name: "core", version: "2.1.0")
├── README.md                       # Core 說明手冊
└── yscb_core/                      # Python Package
    ├── __init__.py                 # 導出 ProjectContext, ConfigManager, Console
    ├── context.py                  # ProjectContext (含 get_contributions)
    ├── config.py                   # ConfigManager
    └── console.py                  # Console
```
