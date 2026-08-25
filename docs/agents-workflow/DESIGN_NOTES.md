# 設計決策與工程妥協 (Design Notes)

本文件記錄 `agents-workflow` 模組中的核心設計決策、邊界取捨與歷史妥協。

---

## 登錄索引表

| 編號 | 決策 / 妥協主題 | 影響範圍 | 狀態 |
| :--- | :--- | :--- | :---: |
| **[DN-AW-01]** | 協議產物工廠化與宣告式 Contributes 替代硬編碼 | 模組架構、微內核整合 | `Active` |
| **[DN-AW-02]** | 多輪遞迴狀態機之自指死鎖防護與標籤清除機制 | 工廠編譯器 (`compiler.py`) | `Active` |
| **[DN-AW-03]** | 統一靜態資產空間收納至 `assets/` | 目錄結構、Manifest 規格 | `Active` |
| **[DN-AW-04]** | 佔位符 Markdown 可視化語法選型與殘留抹除策略 | 工廠編譯器、全量資產庫 | `Active` |
| **[DN-AW-05]** | 組態模板 `!undefined` 剛性解耦與推薦預設值封裝 | 組態治理、一鍵初始化引擎 | `Active` |
| **[DN-AW-06]** | HTML 註解 Token 自宣告與字面值 Replace 解算 | 工廠編譯器、資產導出 | `Active` |

---

### [DN-AW-01] 協議產物工廠化與宣告式 Contributes 替代硬編碼
- **背景**：原 SOP 規格將特定專案的特化工程規範（如 Dogfooding 等）硬編碼於標準檔案中，破壞了工作流模組的通用抽象性。
- **決策**：引入宣告式 `export`、`insert` 與 `token` 體系，將規範與模板轉化為工廠原料，允許第三方模組動態向錨點注入自定義內容。
- **效益**：模組 100% 純淨通用，可開箱供任何 YSCB 下游專案使用。

---

### [DN-AW-02] 多輪遞迴狀態機之自指死鎖防護與標籤清除機制
- **背景**：當注入片段本身包含同名 Token 或多模組連續 below 追加時，易造成無窮遞迴展開或殘留未解算標籤。
- **決策**：在單次注入時將內容視為原子字面值，禁止本輪自指展開；並在 Step 3 依 Step 1 快照乾淨抹除殘留錨點標籤。
- **效益**：徹底保證收斂性，防止無窮死鎖。

---

### [DN-AW-03] 統一靜態資產空間收納至 `assets/`
- **背景**：模組根目錄分散存在 `standards/`、`workflows/`、`templates/`，內聚度偏低。
- **決策**：將三者統籌收納於 `assets/` 子目錄下，保持模組根目錄乾淨清爽。

---

### [DN-AW-04] 佔位符 Markdown 可視化語法選型與殘留抹除策略
- **背景**：原 HTML 註解格式（`<!-- __TOKEN__ -->`）在 Markdown 渲染模式下被隱藏，不易於肉眼審閱模板結構與未展開錨點。
- **決策**：
  1. 全面重構為原生可視語法：插入佔位符 `__@{token}__`（主動注入）與路徑佔位符 `__#{uri}__`（被動參照）。
  2. 抹除正則工廠 `make_purge_regex` 採用 `r"([ \t]*__@\{\s*" + re.escape(token_name) + r"\s*\}__[ \t]*\r?\n?)"`，自動吞噬行首縮排與行尾換行，確保抹除後文檔不留多餘空行。
  3. `__#{uri}__` 於編譯階段 100% 原樣保留，作為 Markdown 文檔的語意參照與路徑錨點。

---

### [DN-AW-05] 組態模板 `!undefined` 剛性解耦與推薦預設值封裝
- **背景**：若將預設路徑（如 `.agent_workflow/plans`）直接寫死在 `config.project.json` 模板中，將破壞微內核「未配置即 `!undefined`」的零臆測鐵律。
- **決策**：
  1. `config.project.json` 模板中 `paths` 欄位剛性保持 `"!undefined"`，並保留 `ide: []` 等未來擴充欄位。
  2. 將一鍵初始化推薦路徑（`project://.agent_workflow/plans` 等）封裝於 `WorkflowInitializer` 類別中。
  3. 僅當使用者顯式執行 `--init-default` 並確認後，才由引導引擎原子寫入 `config.project.json` 並刷新 Core URI 快取。

---

### [DN-AW-06] HTML 註解 Token 自宣告與字面值 Replace 解算
- **背景**：當模板或標準文檔需要動態產生原生 HTML 註解（如 `<!-- slide -->` 或隱藏標記）時，直接寫入 HTML 註解會在某些 Markdown 編輯器被過濾或混淆。
- **決策**：
  1. 宣告 `BEGIN_HTML_ANNOTATION` 與 `END_HTML_ANNOTATION` Token。
  2. 在 `manifest.json` 中配置 `type: "const"` 與 `mode: "replace"`，分別替換為字面值 `<!--` 與 `-->`。
  3. 編譯期由工廠狀態機原子替換，解算後產生合規 HTML 註解。
