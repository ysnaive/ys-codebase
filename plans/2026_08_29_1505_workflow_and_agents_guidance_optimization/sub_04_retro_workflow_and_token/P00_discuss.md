# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 於 `agents-workflow` 建立新標準 workflow: 開發歷程自檢 (`/Retro`)，回顧開發過程並進行合規性與效益稽核，並定義 TOKEN 使其他模組可以注入自評項目。
  - 開發歷程回顧以當前上下文歷史紀錄 (Transcript / Session History) 為主，適用於任何對話情境。
  - **剛性紀律（開頭強制約束）**：若自檢發現任何不合規條目，必須進行根因回溯分析，明確指出是因為閱讀了哪份文檔/指示之延伸決策導致錯誤發生。
  - **模組分工與自檢焦點純化**：
    1. `agents-workflow` 核心自檢：逐條嚴格自檢，但**輸出時採「異常過濾呈遞」原則，僅提出不符合/違規之項目**與其根因（全數合規時僅需簡明聲明）。
    2. `knowledge-db` 擴充自檢：轉化為 **Search 效益與演算法評測**（統計調用次數、調用時機合理性、相較傳統 grep/list 工具之效益對比、搜尋結果有效性與排名靠前度分析）。
    3. `core` 擴充自檢：著重於 **CLI Default-Deny 守門**（逐一查核所有執行之指令是否合規查表、未授權與禁止情境是否嚴格阻斷）。
- **核心目標**：
  1. 新增標準工作流 `/Retro`（資產路徑：`assets/workflows/Retro.md`），支援任意 Session 之上下文反思與盤點。
  2. 於工作流頂部建立「不合規文檔溯源分析 (Documentation-Root-Cause Traceability)」剛性紀律。
  3. 設計核心自檢異常過濾呈遞機制，節省 Token 並聚焦問題。
  4. 於 `manifest.json` 與 `Retro.md` 定義擴充 Token 錨點 `__@{RETRO_CHECK_ITEMS}__`。
  5. 明確規範 `knowledge-db` (Search 效益評測) 與 `core` (CLI Default-Deny 守門) 的標準擴充注入範本，更新相關文檔。
- **邊界排除 (Explicitly Excluded)**：
  - `agents-workflow` 核心代碼中不硬編碼 `knowledge-db` 或 `core` 的具體內容，100% 透過 `RETRO_CHECK_ITEMS` 動態宣告注入。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 工作流命名與呼叫指令**：
  - 確立 Slash Command 為 `/Retro`，工作流檔案命名為 `Retro.md`。
- **[P00:DR-02] 擴充 Token 錨點命名與格式**：
  - Token 命名為 `RETRO_CHECK_ITEMS`，在 `manifest.json` 之 `contributes.token` 註冊，並在 `Retro.md` 嵌入 `__@{RETRO_CHECK_ITEMS}__`。
- **[P00:DR-03] 頂部剛性紀律：不合規文檔溯源分析 (Documentation-Root-Cause Traceability)**：
  - 若自檢中發現任何不合規/偏差條目，Agent 必須強制執行 5-Whys 根因溯源，明確指出「是因讀取了哪一份實體文檔（檔案路徑與章節/行號）或指示，導致延伸做出此錯誤決策」，直接暴露文檔瑕疵或理解偏差。
- **[P00:DR-04] 三維自檢與評測維度詳細定義**：
  - **維度 1：`agents-workflow` 核心自檢（異常過濾呈遞模式）**：
    - **自檢清單範圍**：三大核心原則（零臆測、剛性追溯、分級管控）、執行推進紀律（單 Turn 限制、Checkpoint 強制等待、問答 $\neq$ 推進、嚴禁空降實作）、排查與範疇保護（由近及遠、範疇越界阻斷、防淺層修補）、文檔與工具紀律（確定性讀檔阻斷、模板註解剝除、嚴禁主動歸檔）。
    - **輸出呈現原則**：全量比對但**僅呈報不符合/違規項目**，若 100% 合規僅簡要標記「✅ 核心紀律全數合規」，避免無效 Token 膨脹。
  - **維度 2：`knowledge-db` 擴充評測（Search 效益與演算法評測）**：
    - 由 `knowledge-db` 注入 `RETRO_CHECK_ITEMS`，包含：
      1. **總調用次數統計**：統計 Session 期間調用 `knowledge-db search` 的總次數。
      2. **調用時機合理性 (Timing Rationality)**：分析是否在探索未知符號/架構時即時調用？有無過度濫用或應調用而未調用的情境？
      3. **效益性對比 (Efficiency vs. Legacy Tools)**：相較於使用傳統 `grep_search` / `list_dir` / `view_file` 盲目翻找，估算所節省的 Token 消耗、Turn 數與往返時間。
      4. **演算法有效性 (Relevance & Ranking Quality)**：評估 search 檢索結果對解決問題的實質貢獻度，以及高相關性代碼/文檔切片是否成功排名前列 (Top 1~3)。
  - **維度 3：`core` 擴充自檢（CLI Default-Deny 守門）**：
    - 由 `core` 注入 `RETRO_CHECK_ITEMS`，包含：
      1. **CLI 執行全量查核**：檢查 Session 中調用的每一個 `python yscb.py` 指令是否 100% 符合 `AgentsCliGuild.md` 之推薦情境。
      2. **Default-Deny 阻斷有效性**：是否有未經授權執行未列指令、或違反禁止情境之情事。
- **[P00:DR-05] 計畫分流與架構歸屬**：
  - 納入 Umbrella 主計畫 `2026_08_29_1505_workflow_and_agents_guidance_optimization`，開立子計畫 `sub_04_retro_workflow_and_token`，採用 Level 1 (Full Track) 標準流程推進。

---

## 3. 開放議題與確認紀錄

- [x] 工作流名稱確認為 `/Retro`
- [x] Token 錨點確認為 `RETRO_CHECK_ITEMS`
- [x] 頂部剛性紀律（不合規文檔溯源分析）確立
- [x] agents-workflow 自檢「異常過濾呈遞」原則確立
- [x] knowledge-db 「Search 效益評測（時機/效益/演算法有效性）」維度確立
- [x] core 「CLI Default-Deny 守門」自檢焦點確立
- [x] 計畫分流納入 Umbrella `sub_04` 確立
