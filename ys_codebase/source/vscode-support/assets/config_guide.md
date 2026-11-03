### ⚙️ VS Code 工作區投影與 Schema 綁定體檢 (`vscode-support`)
<!-- yscb:ignore:begin -->
供 `/how-to-config-yscb` Step 1 自動驗證之體檢片段；編輯者註記於編譯時自動抹除。
<!-- yscb:ignore:end -->
- **① 組態項目與用途**：
  - **自動單檔 Schema 編譯**：無須額外設定，自動掃描所有已安裝模組之 `module://<mod>/contributes/_format.json` 與 `module.mirror://<mod>/<ver>.zip` 內之 `configurable/config.*.json`，輸出至 `.vscode/schemas/` 並綁定至 `.vscode/settings.json` 之 `json.schemas`。
  - **自訂 JSON Schema 注入**：可於 [`config/vscode-support/contribute.json`](`__#{config://vscode-support/contribute.json}__`)（或 Donor 模組 `contributes/vscode-support.json`）透過 `json_schemas.<id>` 註冊額外檔案匹配規則。
- **② 健康度檢查條件**：
  - `python __${yscb.host://yscb.py}__ vscode-support status`：驗證 `.vscode/settings.json` 受託管狀態、`current-site-packages` 穩定連結與已編譯 Schema 數量。
  - **常見異常修復**：若新增或更新模組後欲強制重編 Schema，執行 `python __${yscb.host://yscb.py}__ vscode-support sync`。
- **③ 隨包設定手冊語意連結**：
  - 進階說明請按需唯讀查閱 [`vscode-support 隨包手冊`](`__#{module://vscode-support/README.md}__`)。

