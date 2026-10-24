### ⚙️ Core 微內核設定與體檢 (`core`)

- **① 組態項目與用途（雙層組態分流）**：
  - **團隊共享組態**：[`config/core/config.project.json`](`__#{config://core/config.project.json}__`)（定義專案共享之環境屬性與 URI 路徑映射）。
  - **個人環境覆寫**：`config/core/config.local.json`（開發者個人本機覆寫設定，須確認專案 `.gitignore` 已忽略 `*.local.json`）。
- **② 健康度檢查條件（供 Step 1 自動驗證）**：
  - `python __${yscb.host://yscb.py}__ status`：驗證宿主根目錄、`.modules/` 已安裝模組狀態與 `.venv/` 虛擬環境健康度。
  - `python __${yscb.host://yscb.py}__ uri check`：驗證全域語意 URI（`project://`、`config://`、`cache://`、`storage://`）對應實體目錄皆存在。
  - `python __${yscb.host://yscb.py}__ contributes check`：驗證跨模組 `contributes/*.json` 與專案級 `config/<mod>/contribute.json` 契約完整性。
  - **常見異常修復**：若 `uri check` 報路徑缺失，透過 `config set` 修正映射；修改任何 `contribute.json` 後執行 `python __${yscb.host://yscb.py}__ reload` 刷新快取。
- **③ 隨包設定手冊語意連結**：
  - 進階組態與 URI 協議細節請按需唯讀查閱 [`core 隨包手冊`](`__#{module://core/README.md}__`)。
