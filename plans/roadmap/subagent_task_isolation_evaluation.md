# 技術路線圖：Subagent 任務級上下文隔離與三支柱委派協定 (Roadmap)

> 主題：Subagent 任務級上下文隔離與三支柱委派協定  
> 歸檔日期：2026-10-22  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在現行 `agents-workflow` 標準開發流程中，雖然檔案級狀態機（`P00`~`P07`）與跨視窗交接（`/pause` + `/continue`）已解決大部分跨階段記憶問題，但在單一主對話視窗（Main Agent Session）執行以下三種高認知負荷場景時，仍存在明顯的物理瓶頸：
1. **廣域探索與深度調研的「搜索雜訊污染」（`/research` 與 `/discuss`）**：
   執行跨模組調研或根因排查時，Agent 需檢索並翻閱 10~20 份源碼與外部文檔，其中 80% 屬於過程性淘汰資訊，卻永久殘留於主視窗 Context Window 中，干擾後續規格制定。
2. **長鏈條連續實作的「上下文熵增」（`/auto` 與大型 `Phase 05`）**：
   在 `/auto` 模式連續生成 `P01`~`P04` 後進入 `Phase 05/06`，或當 `P05_task.md` 含多個跨模組任務時，前序任務的讀取紀錄與測試失敗 Stack Trace 會快速塞爆主視窗，引發自動壓縮（Compaction）與注意力退化。
3. **球員兼裁判的「同視窗確認偏誤（Confirmation Bias）」（`Phase 07` 結案審查）**：
   讓剛寫完程式碼的同一個主視窗自己執行 `Phase 07` Step 1（三層文檔對齊與代碼品質審查），極易因近因記憶偏誤而流於形式勾選 `[x]`，漏抓淺層敷衍修補（Anti-Patterns）或遺漏 `P04` 承諾之文檔更新。

### 1.2 現況與影響範圍評估
- **架構裁決：內化「三支柱門檻觸發式 Subagent 委派協定」，不新增獨立 Skill，不開發 `task-brief` 切片 CLI**：
  1. **三支柱高投報委派場景（Research 探索隔離 + Implement 實作隔離 + Review 冷眼審計）**：
     - **支柱一（`/research` 與 `/discuss` 廣域探索隔離 — 純唯讀）**：將跨模組檢索、多方案探勘委派予唯讀 Subagent（支援平行或單一派發），主視窗僅接收濃縮證據與優劣對比以撰寫 `R{NN}_{topic}.md`。
     - **支柱二（`/auto` 與大型 `Phase 05/06` 實作隔離 — 受限讀寫）**：當處於 `/auto` 模式或 `Phase 05` 含 $\ge 3$ 個跨模組任務組時，依耦合度按「單一任務或高內聚任務組（Cohesive Task Group）」**強制序列派發**實作 Subagent，將編碼與單元測試除錯 Log 隔離於子視窗；小型任務（`Fast Track`、`Revision` 或 $\le 2$ 個任務）維持主視窗直接執行以規避 Token 入場稅。
     - **支柱三（`Phase 07` 結案三層文檔與品質審查 — 純唯讀 Fresh-Eyes Review）**：派發全新無偏誤的 Reviewer Subagent，直接對照 `P01/P03/P04` 規格與實際 `git diff` 執行挑刺審計（查核核心原則 3 敷衍修補紅線、三層文檔對齊與需求覆蓋度），回傳缺失清單由主視窗修正。
  2. **採用「檔案路徑傳址（Pass-by-Reference）」，剔除 `plan task-brief` 切片 CLI**：
     - 由於 Subagent 與主視窗共享工作區檔案系統，主視窗委派時僅需在 Prompt 中傳遞 **3 行檔案路徑指針**（如 `請讀取 plans/<plan>/P03_api_spec.md、P04 與 P05 中對應 [TASK-XX] 之規格...`），由 Subagent 在獨立視窗直接讀取完整規格。這比用 Python CLI 正則切片再貼回主視窗更準確（不漏共用型別定義）且主視窗 **0 額外 Token 消耗**。
  3. **單一寫入者鐵律（Single-Writer SSOT）**：
     - 所有 `plans/` 目錄下的計畫文件（`P00`~`P07`、`R{NN}`、`changelog.md`）**100% 僅由主視窗統一寫入**，Subagent 嚴禁修改任何計畫文件，徹底保護模型紀錄規則（Model Record）與狀態一致性。

### 1.3 核心根因
1. 現行 `research/SKILL.md`、`discuss/SKILL.md`、`auto/SKILL.md`、`phase_05_task.md` 與 `phase_07_walkthrough.md` 預設均以單一視窗內聯執行表述，缺乏跨平台通用的 Subagent 門檻委派與回傳協定。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：全域強制 Subagent + 新增獨立 SDD Skill + CLI 切片器** | 不分任務大小一律派發 Subagent；新增獨立 Skill 與 `plan task-brief` CLI | 隔離最徹底 | 小任務承受 3~10 倍 Token 入場稅；主視窗轉貼 CLI 切片反耗 Token 且易漏共用上下文；增加常駐 Skill 路由負擔 | ⭐️⭐️ |
| **方案 2：內化「三支柱門檻觸發協定」+ 檔案路徑傳址 + Single-Writer（推薦採納）** | 不新增獨立 Skill；於 `research`/`discuss`（探索）、`auto`/`phase_05`（實作）、`phase_07`（冷眼審查）內化門檻觸發之傳址委派協定 | 1. **小任務零額外開銷，大任務與 `/auto` 零爆窗**<br/>2. **Fresh-Eyes Review 徹底打破球員兼裁判盲區**<br/>3. 檔案路徑傳址 0 主視窗 Token 浪費、100% 跨平台相容 | 僅需更新 5 份現有技能與階段手冊（純規範層升級，零複雜代碼維護成本） | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（全域強制 + CLI 切片器） | 方案 2（三支柱門檻觸發 + 檔案傳址） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 中（跨平台靜態 Agent 定義檔不相容） | **極高（提示詞動態委派，無子代理環境自動降級內聯執行）** |
| **審查客觀性 (Review Quality)** | 高 | **極高（獨立乾淨 Context 對照 `P01/P03/P04` 與 `git diff` 挑刺）** |
| **Token 經濟性 (Cost Efficiency)** | 低（小任務重複載入 `AGENTS.md`） | **最高（門檻守門 + 高內聚任務組批次委派 + 路徑傳址）** |
| **計畫狀態安全性 (SSOT Safety)** | 中（多代理改計畫檔易衝突） | **最高（Single-Writer：Subagent 禁碰 `plans/`，主視窗唯一寫入）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```markdown
# 三支柱門檻觸發式 Subagent 委派總覽 (1-Level Hub-and-Spoke)
1. [Pillar 1: Research / Explore] (Read-Only, 可平行)
   - 適用：/research 多方案調研、/discuss 跨模組根因探勘
   - 行為：子代理執行廣域檢索與源碼閱讀 -> 僅回傳「關鍵證據、檔案行號與方案優劣摘要」 -> 主視窗撰寫 R{NN}_{topic}.md

2. [Pillar 2: Implementation] (Read-Write 僅限業務源碼/測試, 強制序列)
   - 適用：/auto 進入 Phase 05/06，或 Phase 05 含 >= 3 個跨模組獨立任務組 (Fast Track / Revision 禁用)
   - 行為：主視窗傳遞 P03/P04/P05 路徑與目標 [TASK-XX] -> 子代理編碼並跑單元測試 (內部最多嘗試修復 2 次，第 2 次失敗強制熔斷回傳 MAJOR_BLOCKER) -> 僅回傳 5 行狀態摘要 (COMPLETED | MINOR_DEVIATION | MAJOR_BLOCKER | CRITICAL_BLOCKER) -> 主視窗更新 P05_task.md

3. [Pillar 3: Fresh-Eyes Review] (Read-Only, 單一派發)
   - 適用：Phase 07 Step 1 (三層文檔與結案審查) 或大型 Phase 06 驗收
   - 行為：主視窗傳遞 P01/P03/P04 路徑 -> 乾淨子代理結合 P04 變更清單、git status --short、git diff HEAD 與直讀 Untracked 新檔進行冷眼審計 (僅查核 3 大硬性契約，無缺失直接回傳 REVIEW_STATUS: PASSED) -> 主視窗修正後進入 Step 2/3
```

### 4.1 八大安全與收斂護欄（Safety & Convergence Guardrails）
1. **嚴格單層星型拓撲（1-Level Hub-and-Spoke）**：僅主視窗可派發 Subagent，Subagent 嚴禁再遞迴派發子代理（100% 相容 Antigravity / Claude Code / Codex 三平台限制）。
2. **編碼強制序列、唯讀允許平行**：支柱二（修改源碼）每次僅能序列執行 1 個 Subagent，嚴禁平行改碼引發工作樹衝突；支柱一與支柱三（純唯讀探索與審查）允許平行派發。
3. **Single-Writer 計畫檔保護**：Subagent 嚴禁建立或修改 `plans/` 下的任何檔案，確保 `> 模型：` 標頭與 `changelog.md` 100% 由主視窗管控。
4. **極簡回傳格式約束（Return Throttle）**：強制要求 Subagent 回傳結構化摘要（控制在 150~300 Tokens 內），嚴禁將完整源碼或數百行測試通過 Log 傾倒回主視窗。
5. **[防呆 1] 支柱二內部「二振失敗熔斷（2-Strike Limit）」**：Subagent 在執行單元測試遇錯時，**內部最多僅允許自主嘗試修復 2 次**；若第 2 次修改後測試仍未通過，嚴禁在子視窗內繼續盲目試錯燒耗 Token，必須立即停手並回傳 `STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)` 與異常現場摘要交還主視窗，由主視窗無縫轉入 `/discuss`。
6. **[防呆 2] 支柱三檢視新建檔案之 `git diff` 盲區防護**：由於 `Phase 07` Step 1 尚未執行最終 `git commit`，新建之源碼或測試檔處於 `Untracked (??)` 狀態（單跑 `git diff` 無法顯示）。強制規定 Reviewer Subagent **先讀取 `P04_implementation_plan.md` 預計變更清單，搭配 `git status --short` 與 `git diff HEAD`，並針對新增（Untracked）檔案直接讀取檔案內容進行審查**，杜絕漏審新建檔案。
7. **[防呆 3] 支柱三「防吹毛求疵（Anti-Nitpicking）」三項硬性收斂邊界**：為防止 Reviewer Subagent 為交差而回報無謂的主觀風格建議導致重改迴圈，明確限制其**僅允許回報違反下列三項硬性契約之具體缺失**：
   - **(1) 違反 `AGENTS.md` 核心原則 3 之淺層敷衍修補**（如空白 `except` 吞例外、硬編碼假資料、刪除或放寬測試斷言）；
   - **(2) `P01` 功能/邊界需求或 `P03` 介面契約未落實之遺漏**；
   - **(3) `P04` 文檔衝擊盤點表列應同步但未更新之三層文檔或公開 API Docstring**。
   - 嚴禁回報純主觀命名偏好或表層排版微調；若無上述三類硬性缺失，強制直接回傳 `REVIEW_STATUS: PASSED`。
8. **[防呆 4] 對齊 `Phase 07` 最新三步結案管線時序**：支柱三植入 `phase_07_walkthrough.md` 時，嚴格維持既有三步順序：
   - **Step 1**：執行 Pillar 3 冷眼審查 ＋ 三層文檔對齊修正與代碼清理。
   - **Step 2**：產出 `P07_walkthrough.md`，將所有結案檢核 Checkbox 勾選為 `[x]`，並將頂部標頭 `> 狀態：` 更新為 `Completed`（同步更新根目錄 `CHANGELOG.md` 與主計畫 `umbrella_overview.md`）。
   - **Step 3**：最後實機執行 `plan verify`（或 `plan verify --log`）完成最終合規守門與日誌盲寫。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術儲備，可作為獨立 `Fast Track` / `Full Track` 計畫或與 `python_aci_toolchain_roadmap.md` 協同落地。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (支柱一：探索隔離植入)**：於 `research/SKILL.md` 與 `discuss/SKILL.md` 增補唯讀 Subagent 廣域探索委派指引與回傳摘要格式。
2. **Stage 2 (支柱二：實作隔離植入)**：於 `auto/SKILL.md`、`phase_05_task.md` 與 `phase_06_test.md` 增補門檻判定表、高內聚任務組序列傳址委派、三級偏差熔斷回傳碼（`MAJOR_BLOCKER` / `CRITICAL_BLOCKER`）與 Single-Writer 規則。
3. **Stage 3 (支柱三：冷眼審查植入與驗證)**：於 `phase_07_walkthrough.md`（Step 1）增補 Fresh-Eyes Reviewer Subagent 審計指引，補齊合規單元測試並執行 `@build` 自部署。
