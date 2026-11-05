### 💻 VS Code 工作區與單檔 Schema 投影 (`vscode-support`)

- **① 模組定位與適用時機**：
  - 選配官方 IDE 賦能模組，透過 `hook.core.py` 自動維護 `.vscode/settings.json` 之 Pylance `extraPaths`（指向無版本號穩定連結 `yscb.venv://current-site-packages`）、目錄排除規則，並為所有已安裝模組動態編譯單檔級 JSON Schema（`contributes/<mod>.json`、`config/<mod>/config.*.json`、`.config.local/<mod>/config.*.json`、`_format.json`、`manifest.json`）至 `.vscode/schemas/`（由 `core.gitignore` 統一納管於根目錄 `.gitignore`）。
- **② 標準用法速查 (Golden Recipes)**：
  - **檢視託管狀態與 Schema 清單 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ vscode-support status [--json]`
  - **手動強制刷新設定與重編 Schema (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ vscode-support sync [--json]`
  - **乾淨還原所有注入設定与移除 Schema (`🟡 [CONDITIONAL]`)**：`python __${yscb.host://yscb.py}__ vscode-support revert [--json]`
- **③ 隨包手冊語意連結**：
  - 深入探索雙軌 Schema 編譯規則與自訂 Schema 注入請按需唯讀查閱 [`vscode-support 隨包手冊`](`__#{module://vscode-support/README.md}__`)。

