<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時必須遵守的通用核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

### 📌 核心三大原則 (Core Axioms)
1. **零臆測 (Zero Speculation)**：
   - 不確定細節必須向開發者釐清；嚴禁自行假設需求、猜測 API 或臆測解法。
   - **面對寬泛/模糊指令防呆**：當開發者下達抽象或寬泛目標時（例如「本次目標為 XXX 系統之優化/打磨」），**嚴禁主動自行發散腦補或羅列大批未經確認的具體需求清單**；必須優先向開發者反問並確認「請問具體的優化目標與期望範圍為何？」。
   - **分析授權例外**：唯有當開發者明確指示「幫我初步分析/評估」或「分析要達到這樣的需求，怎麼改比較好」時，Agent 方可基於代碼現況展開客觀架構分析與候選方案對比。
2. **剛性追溯 (Traceability)**：決策每步必須 100% 文件可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：依分流矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 主計畫)。

### 🚨 執行與推進紀律（禁止條款）
- **嚴禁連發與強制 Checkpoint**：一次回應 (Turn) **僅限執行一個 Phase 或獨立動作**；產出階段文件後必須詢問開發者並**立即 End Turn**，嚴禁空降編寫代碼。
- **「問答 $\neq$ 推進」防呆條款**：
  - **回覆意圖二分法**：開發者回覆若為「局部反饋/解答提問」(類型 A) ➔ **僅更新當前文件，呈遞摘要並詢問「是否可推進」後立即 End Turn**，絕對禁止直接跨入下一 Phase；唯有接收到明確「推進/定稿指令」(類型 B) 方可推進。
  - **嚴禁複合推論**：嚴禁自行假設「解答疑問 = 同意推進」，修訂後必須重新呈遞摘要並等待二次確認。
- **確定性文檔讀取失效阻斷**：SOP 指定文檔（AGENTS.md、.agents/.yscb/standards/AgentsCliGuild.md、docs/_project/STANDARDS.md、Phase 模板等）讀取失敗時，禁止自主同義詞搜尋或全專案模糊探勘，必須立即停手呈報路徑錯誤。

### 🛡️ 除錯排查與範疇保護
- **本體優先階層**：排查錯誤優先排查當前組件內部邏輯與傳參，未排除自身問題前禁止深入下游外部模組。
- **範疇越界阻斷**：問題超出本次 Dev Plan 範疇時禁止擅改外部代碼，必須立即發起 `/Discuss` 呈遞調用證據。
- **阻斷盲目修補**：同一問題連續 2 次修復失敗或破壞 API 簽名時，強制停手發起 `/Discuss` 進行 5-Whys 根因分析。

### ⚙️ 工具調度與 CLI 守門
- **CLI Default-Deny 守門**：執行指令前比對 .agents/.yscb/standards/AgentsCliGuild.md，僅在符合推薦情境下方可執行；未列或禁令組合禁止調用。
- **SOP 模板與標準資產直達**：SOP / 工作流指定之模板與規範文件（如 .agents/.yscb/templates、AGENTS.md、.agents/.yscb/standards/AgentsCliGuild.md），強制使用檔案讀取工具直達精確路徑（如 `view_file` / `read_file` / `View` 等原生讀檔工具）；嚴禁在已知精確路徑時使用檔案搜尋或文字搜尋工具（如 `find_by_name` / `file_search` / `grep_search` / `grep`）進行模糊盲搜（避免底層搜尋引擎預設過濾 `.` 隱藏目錄與 `.gitignore` 產生讀取盲點）。
- **編譯原型隔離防呆**：執行開發計畫落檔時，禁止讀取或引用 ys_codebase/modules 或 ys_codebase/source 未編譯原型（含 `__@{...}__` 巨集標籤），唯一來源為物化之 .agents/.yscb/templates（落檔時剝除頂部 HTML 導引註解 `<!-- ... -->`）。
- **目錄歸檔紀律**：計畫目錄預設留存 plans 原位，禁止主動歸檔。

### 📚 專案文檔與代碼註解紀律 (Documentation & In-Code Integrity)
- **三層文檔交付對齊**：
  - **宏觀發布日誌**：專案全域版本日誌（CHANGELOG.md）於結案交付時追加高階變更紀錄。
  - **中觀模組手冊**：涉及 Public API 增刪、架構重構或資料流轉向時，1:1 同步更新對應模組手冊、專題手冊與決策手冊。
  - **微觀代碼註解**：代碼內部必須落實結構化介面註解與型別契約。
- **公開介面註解保護 (Docstring Preservation)**：
  - 編寫或重構 Public API 時，嚴禁刪減或破壞標準介面註解結構（說明、傳參、回傳與例外規範）。
- **意圖導向行內註解 (Why-Driven Comments)**：
  - 凡涉及非直觀演算法、邊界補償、數學推導或特定常數定義，行內註解必須記錄設計動機與理由 (Why)，嚴禁僅複述語法操作 (What)。
- **交付閉環驗收**：
  - 任務實作時將文檔與註解列為一等公民任務同步交付；結案與審查時嚴格執行 1:1 文檔交付核對，未完整交付嚴禁結案。

---

### 🏛️ 模組開發與 Dogfooding 閉環鐵律 (Module Dev & Dogfooding)

凡安裝 `dev` 模組，Agent 進行生態系模組開發時**必須強制遵守**三大空間隔離與雙軌流水線：

#### 1. 三層空間隔離矩陣 (3-Tier Space Matrix)
- **空間 ① 源碼空間 (`source/<module>/`)**：【唯一 SSOT】所有代碼、腳本與工作流修改 **100% 必須在此進行**。
- **空間 ② 測試空間 (`cache://dev/sandbox/`)**：【品質閘門】自動化測試於隔離沙盒執行（`dev test <module>`），未 100% 通過嚴禁同步。
- **空間 ③ 運行空間 (`modules/<module>/` 與 `.mirror/`)**：【編譯產物】**嚴禁手動直接修改**，一律由 CLI 同步物化。

#### 2. 雙軌開發與發布閉環 (Dual-Track Pipeline)
- **軌道 A：日常開發調試 (Dogfooding Track)**（未晉升版本之日常修改）：
  $$\text{編輯 } \texttt{source/} \;\longrightarrow\; \texttt{dev check <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{install <mod>@build --force}$$
- **軌道 B：版本晉升交付 (Release Track)**（獲明確指示 bump/release/交付）：
  $$\texttt{dev bump-[part] <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{dev release <mod>} \;\longrightarrow\; \texttt{install <mod> --force}$$

#### 3. 🚨 發布與部署防呆守門 (Guardrails)
- **嚴禁未授權正式發布**：日常熱開發未獲明確指示前，**絕對禁止**自主切入軌道 B 執行 `dev release`，一律維持軌道 A (`@build`)。
- **部署後免重複測試鐵律**：通過沙盒測試並完成 `@build` 或正式安裝後，**嚴禁重複調用 `dev test` 跑測**；物化完成即結案交付。
- **語意 URI 解耦鐵律**：模組內部跨空間存取**嚴禁硬編碼相對路徑**，必須 100% 使用語意協議（`storage://`、`cache://`、`config://`、`module.*://`）。

### 🧠 知識庫檢索與搜尋規範 (Knowledge-DB Standards)

#### 1. 目標導向工具三分流決策矩陣 (Outcome-Driven Tool Routing)

| 下一步目標行為 | 唯一指定工具 | 守門規範與授權邊界 |
| :--- | :---: | :--- |
| **閱讀代碼 / 理解邏輯 / 查簽名 / 架構探索** | **知識庫語意檢索**<br>`knowledge-db search -s` | • 一步到位取得 AST 切片與 Docstring。<br>• 🚨 **嚴禁「文字搜尋 ➔ 逐檔翻讀」鏈式作業**（如 Grep $\rightarrow$ ReadFile / ViewFile）。<br>• 💡 **切片缺行補足授權**：上下文缺失時，允許用檔案讀取工具（如 `view_file` / `read_file` / `View`）定點補讀（**限原切片行數 + 最多 30 行**，嚴禁擴大為整檔翻讀）。 |
| **調用源追蹤 / 下游依賴 / 重構影響面評估** | **調用圖譜與依賴拓撲**<br>`knowledge-db callers`<br>`knowledge-db callees`<br>`knowledge-db impact` | • **查誰調用了我**：`knowledge-db callers <symbol> -s`（精準列出調用點與切片）。<br>• **查我調用了誰**：`knowledge-db callees <symbol> -s`（精準列出子函式與依賴）。<br>• **重構影響半徑評估**：`knowledge-db impact <symbol> --depth=N`（樹狀擴散拓撲分析）。<br>• 🚨 **嚴禁使用 Grep 多檔模糊盲搜代替調用圖譜**。 |
| **代碼替換 / 行號精確定位 / 標點與常數** | **原生文字搜尋工具**<br>（如 `grep_search` / `grep`） | 僅供已知代碼外觀且**不需閱讀上下文**時定位行號，或比對分詞器忽略之標點/常數（如 `<!--`、`0x7FFF`）。 |

---

#### 2. 三維語意構詞與兩階段分流 (Query Formulation & Routing)

- **三維語意構詞**：
  $$\text{Query} = \text{[領域概念/簽名]} + \text{[架構機制/情境]} + \text{[核心動詞]}$$
  - 通用函式名（如 `resolve`、`update`）強制附加業務情境詞（例：`search 'resolve 佔位符 拓撲' -s`）以交叉過濾同名簽章。
- **兩階段 `--ftype` 分流**：
  - **Phase A (宏觀脈絡/廣度)**：`python yscb.py knowledge-db search '<情境詞組>' --ftype=md -s` (或全域搜尋)。
  - **Phase B (微觀實作/深度)**：`python yscb.py knowledge-db search '<簽名詞 業務詞>' --ftype=c,cpp,py -s`。

---

#### 3. 四大防呆阻斷鐵律 (Guardrails & Anti-Patterns)

1. **第一反射與鏈式翻讀阻斷**：探索閱讀強制以 `knowledge-db search -s` 為第一反射；排查調用源與重構影響面強制以 `knowledge-db callers` / `impact` 為第一反射；嚴禁未定位行號即以目錄走訪/讀檔工具（如 `list_dir` / `view_file` / `read_file`）盲目翻讀，嚴禁以文字搜尋工具（如 `grep_search` / `grep`）進行未指定精確符號之模糊廣蒐。
2. **🚨 阻斷連續同義詞抖動重搜 (Anti-Query Thrashing)**：
   - 針對同一目標**嚴禁連續發起超過 2 次微調關鍵字的無效重搜**。
   - **嚴禁將 Search 當捲軸**：命中切片需相鄰上下文時，強制依授權以檔案讀取工具（如 `view_file` / `read_file`，限原範圍+30行）定點補讀或進入邏輯推理。
3. **新概念主動補足**：遭遇上下文未具備之新名詞或新協議，嚴禁憑字面臆測，必須即刻以語意化查詢補足知識後再推進。
4. **註解結構保護**：編寫或重構 Public API 時，嚴禁破壞標準 Docstring 結構。
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*

- 執行任何指令時，嚴禁在反饋時長超過 1.5 秒前，將其掛載為異步 task 。