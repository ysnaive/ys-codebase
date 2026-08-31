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
- **確定性文檔讀取失效阻斷**：SOP 指定文檔（`__${project://AGENTS.md}__`、`__${module://agents-workflow/assets/standards/AgentsCliGuild.md}__`、`__${workflow.docs://_project/STANDARDS.md}__`、Phase 模板等）讀取失敗時，禁止自主同義詞搜尋或全專案模糊探勘，必須立即停手呈報路徑錯誤。

### 🛡️ 除錯排查與範疇保護
- **本體優先階層**：排查錯誤優先排查當前組件內部邏輯與傳參，未排除自身問題前禁止深入下游外部模組。
- **範疇越界阻斷**：問題超出本次 Dev Plan 範疇時禁止擅改外部代碼，必須立即發起 `/Discuss` 呈遞調用證據。
- **阻斷盲目修補**：同一問題連續 2 次修復失敗或破壞 API 簽名時，強制停手發起 `/Discuss` 進行 5-Whys 根因分析。

### ⚙️ 工具調度與 CLI 守門
- **CLI Default-Deny 守門**：執行指令前比對 `__${module://agents-workflow/assets/standards/AgentsCliGuild.md}__`，僅在符合推薦情境下方可執行；未列或禁令組合禁止調用。
- **SOP 模板與標準資產直達**：SOP / 工作流指定之模板與規範文件（如 `__${project://.agents/.yscb/templates/}__`、`__${project://AGENTS.md}__`、`__${module://agents-workflow/assets/standards/AgentsCliGuild.md}__`），強制使用檔案讀取工具直達精確路徑（如 `view_file` / `read_file` / `View` 等原生讀檔工具）；嚴禁在已知精確路徑時使用檔案搜尋或文字搜尋工具（如 `find_by_name` / `file_search` / `grep_search` / `grep`）進行模糊盲搜（避免底層搜尋引擎預設過濾 `.` 隱藏目錄與 `.gitignore` 產生讀取盲點）。
- **編譯原型隔離防呆**：執行開發計畫落檔時，禁止讀取或引用 `__${module://}__` 或 `__${module.source://}__` 未編譯原型（含 `__@{...}__` 巨集標籤），唯一來源為物化之 `__${project://.agents/.yscb/templates/}__`（落檔時剝除頂部 HTML 導引註解 `<!-- ... -->`）。
- **目錄歸檔紀律**：計畫目錄預設留存 `__${workflow.plans://}__` 原位，禁止主動歸檔。

### 📚 專案文檔與代碼註解紀律 (Documentation & In-Code Integrity)
- **三層文檔交付對齊**：
  - **宏觀發布日誌**：專案全域版本日誌（`__${project://CHANGELOG.md}__`）於結案交付時追加高階變更紀錄。
  - **中觀模組手冊**：涉及 Public API 增刪、架構重構或資料流轉向時，1:1 同步更新對應模組手冊、專題手冊與決策手冊。
  - **微觀代碼註解**：代碼內部必須落實結構化介面註解與型別契約。
- **公開介面註解保護 (Docstring Preservation)**：
  - 編寫或重構 Public API 時，嚴禁刪減或破壞標準介面註解結構（說明、傳參、回傳與例外規範）。
- **意圖導向行內註解 (Why-Driven Comments)**：
  - 凡涉及非直觀演算法、邊界補償、數學推導或特定常數定義，行內註解必須記錄設計動機與理由 (Why)，嚴禁僅複述語法操作 (What)。
- **交付閉環驗收**：
  - 任務實作時將文檔與註解列為一等公民任務同步交付；結案與審查時嚴格執行 1:1 文檔交付核對，未完整交付嚴禁結案。

---

`__@{AGENTS_STANDARDS}__`

