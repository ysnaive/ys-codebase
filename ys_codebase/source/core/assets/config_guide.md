### ⚙️ Core 微內核與邏輯檔案空間設定 (`core` & `core.space`)

- **① 組態項目與用途（雙層組態與邏輯檔案空間）**：
  - **團隊共享組態**：[`config/core/config.project.json`](`__#{config://core/config.project.json}__`)（定義專案共享之環境屬性與 URI 路徑映射）。
  - **個人環境覆寫**：`.config.local/core/config.local.json`（`config.local://core/config.local.json`，開發者個人本機覆寫設定，由 `core.gitignore` 自動納管忽略 `.config.local/`）。
  - **專案邏輯檔案空間與預設集 (`config/core/contribute.json`)**：定義宿主專案自訂工作空間幾何範圍（`entries` URI 清單、`compose` 空間組合、`presets` 預設集、`include`/`exclude` 三座標規則、`hash_policy` 分級雜湊策略與 `watch` 監聽開關）。
  - **當前已生效空間總表**：
`__@{FILE_SPACE_REGISTERED_TABLE}__`
- **② 健康度檢查條件（供 Step 1 自動驗證）**：
  - `python __${yscb.host://yscb.py}__ status`：驗證宿主根目錄、`.modules/` 已安裝模組狀態與 `.venv/` 虛擬環境健康度。
  - `python __${yscb.host://yscb.py}__ uri check`：驗證全域語意 URI（`project://`、`config://`、`config.local://`、`storage://`、`storage.local://`、`cache://`）對應實體目錄皆存在。
  - `python __${yscb.host://yscb.py}__ contributes check`：驗證跨模組 `contributes/*.json` 與專案級 `config/<mod>/contribute.json` 契約完整性。
  - `python __${yscb.host://yscb.py}__ fs status`：驗證邏輯檔案空間註冊、二進位指紋快照 (`YFP2`) 與消費者游標狀態。
  - **常見異常修復**：若 `uri check` 報路徑缺失，透過 `config set` 修正映射；修改任何 `contribute.json` 後執行 `python __${yscb.host://yscb.py}__ reload` 刷新快取。
- **③ 隨包設定手冊語意連結**：
  - 進階組態、URI 協議與邏輯檔案空間細節請按需唯讀查閱 [`core 隨包手冊`](`__#{module://core/README.md}__`)。
