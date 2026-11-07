### 📦 Core 微內核與邏輯檔案空間 (`core` / `fs` — 模組治理、語意 URI、全域組態與檔案空間引擎)

- **① 模組定位與適用時機**：
  - 提供全系統跨平台語意 URI 協議解析（`project://`、`module://`、`config://`、`config.local://`、`storage://`、`storage.local://`、`cache://`）與 `<owner>/<name>` 邏輯檔案空間引擎 (`core.space`)，支援雙階段單調世代指紋快照 (`YFP2`)、Merkle Root 計算與多消費者交易游標。
  - 當你需要查詢環境健康狀態、檢視已安裝模組版本、解析語意路徑、管理雙層組態或檢視/掃描檔案空間時使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **環境健康度總檢 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ status` 與 `python __${yscb.host://yscb.py}__ list`
  - **語意 URI 解析與驗證 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ uri list` / `python __${yscb.host://yscb.py}__ uri resolve <URI>`
  - **雙層組態檢視 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ config list` / `python __${yscb.host://yscb.py}__ config get <key>`
  - **邏輯檔案空間查詢與掃描 (`🟢 [SAFE]`)**：
    - `python __${yscb.host://yscb.py}__ fs spaces` / `python __${yscb.host://yscb.py}__ fs status [--space <name>]`：檢視已註冊空間、`head_generation`、`merkle_root` 與消費者游標狀態。
    - `python __${yscb.host://yscb.py}__ fs ls [--space <name>]` / `python __${yscb.host://yscb.py}__ fs match <path>`：列舉空間受管檔案或診斷單一檔案匹配規則。
    - `python __${yscb.host://yscb.py}__ fs scan [--space <name>] [--force]` / `python __${yscb.host://yscb.py}__ fs diff [--space <name>] [--consumer <id>]`：執行雙階段增量指紋掃描或查詢消費者游標差異。
  - **擴充契約檢驗與重載 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ contributes check` / `python __${yscb.host://yscb.py}__ reload`
  - *(注意：`install`、`update`、`remove`、`rollback`、`restore` 屬 `🔴 [GATED]` 指令，須獲明確授權方可執行)*
- **③ 隨包手冊語意連結**：
  - 深入探索完整 URI 協議表、`core.space` 規則代數與 SDK API 請按需唯讀查閱 [`core 隨包手冊`](`__#{module://core/README.md}__`)。
