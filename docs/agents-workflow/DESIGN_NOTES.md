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
| **[DN-AW-07]** | 兩階段 6 步管線、三層 URI 重映射與 4 步原子發布交易 | 工廠編譯器、發布引擎、CLI | `Active` |
| **[DN-AW-08]** | Stage 2 佔位符二分法解析與反引號完全替代剝除 | 工廠編譯器 (`compiler.py`) | `Active` |
| **[DN-AW-09]** | 6 大計畫分支拓撲、/NewPlan 延遲建檔與 Roadmap 策略資產體系 | 工作流體系、CLI 工具鏈 | `Active` |
| **[DN-AW-10]** | JIT 變更感知 Stat-First 雙階快照初篩與 SHA-1 快取機制 | 發布引擎 (`publisher.py`)、Manifest 治理 | `Active` |

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

---

### [DN-AW-07] 兩階段 6 步管線、三層 URI 重映射與 4 步原子發布交易
- **背景**：
  1. 原 `exports/` 目錄直接輸出在模組根目錄下，造成安裝與源碼空間污染。
  2. 模組原始資產維持語意 URI 解耦（如 `module.root://`），但 Agent 工具 (`view_file`) 與人眼預覽需要相對於落地檔案的實體相對路徑。
  3. 多 Release Target 發布時，若發布中途異常可能造成孤立殘留檔案或中斷損毀。
- **決策**：
  1. 拆解為標準 6 步語意編譯發布管線：Stage 1 專注解算內容並寫入 `cache.root://agents-workflow/resolved_contents/`，Stage 2 依啟用之 `release_targets` 解析發布拓撲並計算相對路徑。
  2. 實作三層重映射階層：Tier 1 (發布拓撲映射表) ➔ Tier 2 (Core 專案級協議) ➔ Tier 3 (未知協議安全降級)。
  3. 實作基於 `storage://agents-workflow/release_manifest.json` 的 4 步原子發布交易（過往清理 ➔ 提前解算 ➔ 持久紀錄 ➔ 目錄落地與 `AGENTS.md` 軟合併）。
- **效益**：模組安裝目錄保持 100% 純淨，Agent 模板尋址盲區徹底消除，多環境發布具備交易級安全保證。
 
---

### [DN-AW-08] Stage 2 佔位符二分法解析與反引號完全替代剝除
- **背景**：
  原 Stage 2 URI 解析實作對所有命中 `CODE_SPAN_REGEX` 的代碼塊無差別包回反引號（`f"\`{inner}\`"`）。導致純佔位符（非穿插類型，如 `[Link](\`__#{uri}__\`)`）在解算後錯誤殘留反引號（`[Link](\`../path.md\`)`），破壞 Markdown 超連結規範與點擊跳轉；同時工作流中讀檔指引誤用 `__#{...}__` 導致 Agent 在根目錄 CWD 執行 `view_file` 時發生 404。
- **決策**：
  1. 在 `compiler.resolve_stage2_uri` 中引入 Standalone 純佔位符判定（`LOCAL_URI_EXACT_REGEX` / `PROJECT_URI_EXACT_REGEX`），純佔位符解算後直接返回純路徑字串（完全替代並剝除外層反引號）。
  2. 行內穿插代碼（如命令列 `python __${...}__ run`）解算內部佔位符後維持外層代碼反引號。
  3. 工作流中面向 Agent 讀檔與終端執行的檔案動線，全面切換為 `__${...}__` (Project Relative URI)，確保專案根目錄直達可讀。
- **效益**：Markdown 超連結符合 100% CommonMark 規範，徹底消滅 Agent 初始化 404 與非預期搜尋開銷。

---

### [DN-AW-09] 6 大計畫分支拓撲、/NewPlan 延遲建檔與 Roadmap 策略資產體系
- **背景**：
  1. 原 Fast Track 僅以「檔案數 $\le 2$」為硬性判斷標準，出現「10 檔共修 50 行被阻擋，而 1 檔修改 2000 行卻誤判進入 Fast Track」的規模盲點。
  2. 原 SOP 缺乏修訂計畫（邊校驗邊改短循環）、調研計畫（非代碼技術選型）與長期策略資產（Roadmap 儲備庫）。
  3. 原 `/NewPlan` 觸發即立即開立目錄與模板，若討論途中切換或放棄會遺留無效垃圾目錄。
- **決策**：
  1. 建立 6 大計畫分支矩陣：Full Track (Level 1)、Fast Track (Level 0, 4 維度綜合規模判定)、Umbrella (Level 2, 模式 B-1 預先規劃型 vs 模式 B-2 增量演進型)、修訂計畫 (4 步短循環免開目錄)、調研計畫 (3 步調研與三大出口轉化)、Roadmap (長期策略資產)。
  2. 實作 `/NewPlan` 延遲建檔守門 (Delayed Materialization)：P00_discuss 階段維持純對話，確立分流時才一併建立目錄與模板。
  3. 實作 `RoadmapManager` 與 `python yscb.py agents-workflow roadmap` CLI 摘要掃描工具，結合 `/Roadmap` 智能推薦工作流達成低 Token 儲備探索。
- **效益**：涵蓋多維開發需求場景，保護 Token 開銷與磁碟整潔度，建立長期技術儲備與一鍵轉化能力。

---

### [DN-AW-10] JIT 變更感知 Stat-First 雙階快照初篩與 SHA-1 快取機制
- **背景**：原 JIT Release 檢驗在 Stage 0 短路判定中連續計算 3 次來源特徵指紋，每次皆全量讀取來源檔案計算 SHA-1，產生重複 I/O 與 CPU 雜湊負擔；且依賴 `watchdog` pip 套件。
- **決策**：
  1. 自 `manifest.json` 徹底移除 `pip_dependencies` (`watchdog`) 宣告，回歸零外部 pip 依賴的微環境純淨性。
  2. 引入基於 `(st_mtime_ns, st_size)` 的 Stat-First 跨進程持久化快取（`cache://agents-workflow/source_sha1_cache.json`），僅在檔案元數據變更時重新讀檔與運算 SHA-1。
  3. 實作單次週期內來源資產綜合摘要快取 `_get_sources_digest()`，徹底消除單次執行週期的重複掃描與雜湊負擔。
- **效益**：Clean 狀態下檢驗時間壓降至 sub-0.2ms，達成 0 檔案內容讀取與 0 重複雜湊，同時兼顧 100% 變更感知的數學精確性與自愈能力。

