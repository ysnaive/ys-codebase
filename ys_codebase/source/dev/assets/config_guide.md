### ⚙️ Dev 開發者工具箱設定與體檢 (`dev`)

- **① 組態項目與用途（雙層組態分流）**：
  - **適用判定**：僅當本專案為「YSCB 模組源碼開發專案」（存在模組 `source/` 目錄）時需配置；一般純業務專案保持預設即可。
  - **團隊共享組態**：[`config/dev/config.project.json`](`__#{config://dev/config.project.json}__`)（配置 `source_dir`、`build_dir`、`release_dir` 等模組工程目錄映射）與 `config/dev/contribute.json`（自訂靜態檢查規則）。
  - **個人環境覆寫**：`config/dev/config.local.json`（個人本機暫存或構建路徑覆寫）。
- **② 健康度檢查條件（供 Step 1 自動驗證）**：
  - `python __${yscb.host://yscb.py}__ uri resolve module.source://`：驗證模組源碼根目錄映射是否指向真實存在的源碼空間（如 `ys_codebase/source`）。
  - `python __${yscb.host://yscb.py}__ dev check --all`：對源碼空間內所有開發中模組執行 Manifest、Contributes Schema 與靜態合規檢查。
  - **常見異常修復**：若 `module.source://` 無效，於 `config/dev/config.project.json` 對齊實際源碼目錄；若 `dev check` 報錯則補齊 `manifest.json` 或 `_manifest.md`。
- **③ 隨包設定手冊語意連結**：
  - 進階模組工程配置與檢查規則請按需唯讀查閱 [`dev 隨包手冊`](`__#{module://dev/README.md}__`)。
