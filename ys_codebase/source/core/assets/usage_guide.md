### 📦 Core 微內核 (`core` — 模組治理、語意 URI 與全域組態基座)

- **① 模組定位與適用時機**：
  - 提供全系統跨平台語意 URI 協議解析（`project://`、`module://`、`config://`、`cache://`），消除硬編碼路徑耦合。
  - 當你需要查詢環境健康狀態、檢視已安裝模組版本、解析語意路徑或管理雙層組態時使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **環境健康度總檢 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ status` 與 `python __${yscb.host://yscb.py}__ list`
  - **語意 URI 解析與驗證 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ uri list` / `python __${yscb.host://yscb.py}__ uri resolve <URI>`
  - **雙層組態檢視 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ config list` / `python __${yscb.host://yscb.py}__ config get <key>`
  - **擴充契約檢驗與重載 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ contributes check` / `python __${yscb.host://yscb.py}__ reload`
  - *(注意：`install`、`update`、`remove`、`rollback`、`restore` 屬 `🔴 [GATED]` 指令，須獲明確授權方可執行)*
- **③ 隨包手冊語意連結**：
  - 深入探索完整 URI 協議表與 SDK API 請按需唯讀查閱 [`core 隨包手冊`](`__#{module://core/README.md}__`)。
