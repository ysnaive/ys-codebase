---
target: "Core/Installer"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb_installer.py"
related_docs:
  - "./DESIGN_NOTES.md"
  - "../_global/CLI_SPECIFICATION.md"
last_updated: "2026-08-22"
---

# Installer 核心引擎架構 (`yscb_installer.py`)

[`yscb_installer.py`](../../yscb_installer.py) 是 `ys-codebase` 體系的唯一執行與管理入口，負責全生命週期的設定、遠端同步、相依解析、模組安裝與建置發布。

---

## 🏛️ 內部核心架構與類別劃分

```mermaid
classDiagram
    class ConfigManager {
        +Path root_dir
        +Path config_path
        +Path template_path
        +exists() bool
        +create_default(repo, branch, force) dict
        +load() dict
        +save(config) void
        +record_installed_module(name, mode, version, meta) void
        +remove_installed_module(name) void
    }

    class GitRemoteClient {
        +Path root_dir
        +str repo
        +str branch
        +Path cache_dir
        +is_git_available() bool
        +sync_cache(force_refresh) Path
        +push_changes(commit_msg, branch) bool
    }

    class ModuleManager {
        +Path root_dir
        +ConfigManager config_mgr
        +GitRemoteClient git_client
        +read_manifest(path) dict
        +discover_modules(from_remote) dict
        +resolve_dependencies(modules, is_source) list
        +resolve_build_dependencies(modules) list
        +install_module(name, mode, force) bool
        +remove_module(name, force) bool
        +build_module(name) bool
    }

    ModuleManager --> ConfigManager : 讀寫狀態
    ModuleManager --> GitRemoteClient : 同步遠端快取
```

---

## 🔍 關鍵機制解析

### 1. 相依解析器 (Dependency Resolution)
- 透過 DFS 拓撲排序，遞迴解析各模組之 `dependencies`。
- **`--source` 源碼模式**：無條件自動將 `core` 置於安裝序列第一位。
- **`build` 建置模式**：自動遞迴解析待建置相依模組，但自動過濾排除 `core`。

### 2. 檔案同步與安裝隔離
- 使用 `shutil.copytree` 搭配 `dirs_exist_ok=True`，支援乾淨覆寫與增量補全。
- 使用者安裝模式只拉取 `build/<module>/`，杜絕開發期垃圾檔案污染專案。
