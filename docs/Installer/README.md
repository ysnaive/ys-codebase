---
target: "Core/Installer"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb_installer.py"
related_docs:
  - "./DESIGN_NOTES.md"
  - "../_project/CLI_SPECIFICATION.md"
last_updated: "2026-08-22"
---

# Installer 核心引擎架構 (`yscb_installer.py`)

`yscb_installer.py` 是 `ys-codebase` 體系的唯一安裝與管理執行入口，負責全生命週期的設定、遠端同步、相依解析、模組安裝與建置發布。

---

## 🏛️ 內部核心架構與元件劃分

```text
[yscb_installer.py]
  ├── ConfigManager
  │     - 讀寫 yscb_config.json 與 yscb_config.local.json
  │     - 追蹤 installed_modules 狀態矩陣
  │
  ├── GitRemoteClient
  │     - 管理本機 Git 倉庫快取 (cache/)
  │     - 支援 pull、push 與多分支切換
  │
  └── ModuleManager
        - discover_modules()：掃描本機與遠端可用模組
        - resolve_dependencies()：遞迴解析相依性（自動包含 core）
        - install_module()：支援 build (modules/) 與 source (source/) 模式
        - build_module()：將 source/ 打包為純淨 build/ 發布物
        - remove_module()：安全卸載與清理
```

---

## 🔍 關鍵機制解析

### 1. 相依解析器 (Dependency Resolution)
- 透過 DFS 拓撲排序，遞迴解析各模組之 `dependencies`。
- 所有宣告相依 `core` 的模組，皆自動遞迴安裝 `core`（Build 模式 ➔ `modules/core/`，Source 模式 ➔ `source/core/`）。

### 2. 檔案同步與安裝隔離
- 使用 `shutil.copytree` 搭配 `dirs_exist_ok=True`，支援乾淨覆寫與增量補全。
- 使用者安裝模式（預設）從遠端/本地 `build/<module>/` 拉取最低執行需求產物並安裝至本地 `modules/<module>/`。
- 開發者模式（`--source`）則安裝至 `source/<module>/`。
