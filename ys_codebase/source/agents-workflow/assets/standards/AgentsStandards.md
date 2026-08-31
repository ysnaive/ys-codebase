# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時必須遵守的通用核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

### 📌 核心三大原則 (Core Axioms)
1. **零臆測 (Zero Speculation)**：不確定細節必須向開發者釐清；嚴禁自行假設需求、猜測 API 或臆測解法。
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

---

`__@{AGENTS_STANDARDS}__`
