# 技術路線圖：Roadmap 與 TODO 雙層儲備體系重構 (Roadmap)

> 主題：Roadmap 與 TODO 雙層儲備體系重構  
> 歸檔日期：2026-10-22  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
檢視現行 `agents-workflow` 中關於長期儲備與待辦事項的設計（`assets/skills/roadmap/SKILL.md`、`assets/templates/roadmap.md` 與 `agents_workflow/roadmap.py`），目前存在三項架構短板：
1. **缺乏戰術級輕量待辦載體（Missing Lightweight TODO Ledger）**：
   現行體系僅支援「一主題一專題檔（`plans/roadmap/{topic}.md`）」。但日常開發中約 80% 的待辦屬於「局部修繕、技術債清理、待補邊界測試、或經 `/discuss` 開發者裁定暫緩另案處理的次要衍生問題」，為這類小型事項建立完整 5 章節 `roadmap.md` 摩擦過高，若為記錄一筆小待辦而去讀取與編輯多份檔案，更會分散當前主要任務的注意力（Context Pollution）。
2. **儲備項目立項後的「雙頭狀態漂移」與「殭屍檔案堆積」**：
   現行 `roadmap` 採用「立項時改標頭為 `In Progress`、結案時回頭改為 `Completed`」的原地保留機制。違反單一真理來源（SSOT），一旦結案時忘記跨目錄回頭更新，`plans/roadmap/` 就會堆積早已完工的殭屍檔案。
3. **儲備模板缺乏「前置解鎖條件 (`Trigger`) 與目標範疇 (`Scope`)」**：
   僅靠 `Backlog | Proposed | Ready | Deferred` 靜態標籤，缺乏明確的觸發時機與影響模組標註，不利於跨期精準推薦。

### 1.2 現況與影響範圍評估
- **雙層粒度拆分與「立項即物理遷入 (`Consume-on-Promote`)」架構定調**：
  1. **獨立拆分 `/todo` 與 `/roadmap` 雙技能（皆採「主動指令型：極致精簡指令契約」描述）**：
     - **Tier 1 (`todo` 技能 + `plans/roadmap/TODO.md` 集中式帳本)**：管理輕量待辦與技術債。
     - **Tier 2 (`roadmap` 技能 + `plans/roadmap/{topic}.md` 獨立專題檔)**：管理跨模組或大型架構演進藍圖。
     - 兩個技能皆歸類為**主動指令型技能（Command-Driven）**，YAML `description` 採用極致精簡契約（僅於顯式輸入 `/todo` 或 `/roadmap` 或明確指示時觸發），並於中樞技能（`development-sop`、`discuss`、`research`）按需導流，零常駐注意力稀釋。
  2. **提供零 Context 污染的單行盲寫 CLI (`todo add`)，並嚴守核心原則 3 範疇保護**：
     - 針對開發中途不經意發現的小型問題或點子，提供 `python yscb.py agents-workflow todo add "<title>" [--scope "<scope>"] [--note "<note>"]` 單行盲寫指令——Agent **無需讀取 `TODO.md` 歷史內容**，由 Python 自動初始化帳本、自動計算遞增編號 `[TODO-XX]`、自動押上今日日期並追加至檔尾，100% 保護當前任務 Context 不被分散。
     - **防敷衍守門（對齊 `AGENTS.md` 核心原則 3）**：實作或測試中途遭遇非當前範疇之次要問題時，Agent 仍須先向開發者請示或透過 `/discuss` 裁定；**獲開發者確認轉入待辦後**，即可用 1 行 `todo add` 秒速登記並無縫回到原任務，嚴禁 Agent 未經請示私自將 Bug 塞入 `todo add` 逃避修復。
  3. **立項即物理遷入計畫資料夾，結案隨計畫自然歸檔 (`Consume-on-Promote`)**：
     - **Roadmap 立項 (`roadmap promote <topic>`)**：建立 `plans/YYYY_MM_DD_HHMM_{topic}/`，直接將 `plans/roadmap/{topic}.md` **物理搬移（`shutil.move`）**至新計畫目錄下命名為 **`roadmap.md`**（並自動初始化伴隨之 `changelog.md`）。
     - **TODO 立項 (`todo promote <TODO-ID>`)**：將目標 `[TODO-XX]` 區塊自 `plans/roadmap/TODO.md` **原子剪切拔除（Pop）**，遷入新建計畫目錄存為 **`todo.md`**（並初始化 `changelog.md`）。
     - **自然歸檔**：`plans/roadmap/` 永遠維持 100% 純淨的未立項活水池；結案執行 `plan archive` 時，計畫目錄內的 `roadmap.md` / `todo.md` 自動隨整個計畫資料夾移入 `plans/archived/`。

### 1.3 核心根因
1. 缺乏集中式 `TODO.md` 模板、單行免讀盲寫 `todo add` CLI 與獨立 `/todo` 技能。
2. `RoadmapManager` (`roadmap.py`) 僅支援唯讀掃描，尚未實作立項物理搬移（`promote`）與 `TODO.md` 條目拔除（Pop）機制。
3. `PlanStatusResolver` (`status.py`) 與 `PlanVerifier` (`verifier.py`) 尚未將遷入計畫目錄內的 `roadmap.md` 與 `todo.md` 列為前置源頭背景資產白名單。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：原地保留 + 跨目錄狀態同步（現況）** | 檔案留在 `plans/roadmap/`，立項改 `In Progress`，結案回頭改 `Completed` | 不移動檔案 | 違反 SSOT，極易遺忘回寫導致殭屍檔案堆積；缺乏輕量 `TODO.md` 帳本 | ⭐️⭐️ |
| **方案 2：雙層拆分 (`/todo` + `/roadmap`) + `todo add` 免讀盲寫 + `promote` 物理遷入（推薦採納）** | Tier 1 集中於 `TODO.md`（支援 1 行 CLI 盲寫追加與 Pop 立項），Tier 2 為 `{topic}.md`（支援物理 Move 進計畫目錄為 `roadmap.md`），兩技能皆採極致精簡指令契約 | 1. **`plans/roadmap/` 100% 零殭屍檔案**<br/>2. **`todo add` 單行免讀盲寫**，零 Context 污染、不中斷當前任務注意力<br/>3. 結案隨計畫資料夾零成本自動歸檔 | 需擴充 `roadmap.py`、新增 `todo` 技能與模板，並於 `status.py` / `verifier.py` 加入 `roadmap.md` / `todo.md` 白名單 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（現況原地狀態同步） | 方案 2（雙層體系 + 免讀盲寫 + 立項物理遷入） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | **極高（100% Python 標準庫檔案與正則操作）** |
| **後續維護難度 (Maintenance)** | 高（需人工清理過期路線圖） | **極低（立項即搬移、結案即隨計畫歸檔，全自動閉環）** |
| **注意力保護 (Context Economy)** | 低（記錄小待辦需讀改多檔） | **最高（`todo add` 免讀檔 1 行盲寫；雙技能採極簡指令描述）** |
| **落地難度 (Implementation)** | — | **低（約 150~200 行標準庫代碼 + 模板與技能更新）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 1. Tier 1 (TODO.md)：單行免讀盲寫追加、列表檢索與多筆原子拔除立項
python yscb.py agents-workflow todo add "<簡短標題>" [--scope "<模組或檔案>"] [--note "<單行解法備忘或觸發條件>"] [--model "<ModelName>"]
python yscb.py agents-workflow todo list [--scope "<keyword>"]
python yscb.py agents-workflow todo promote <TODO-ID> [<TODO-ID> ...] --slug <ascii_plan_slug> [--model "<ModelName>"]

# 2. Tier 2 ({topic}.md)：策略路線圖掃描與物理搬移立項
python yscb.py agents-workflow roadmap [list] [--status <status>]
python yscb.py agents-workflow roadmap promote <topic> [--model "<ModelName>"]
```

### 4.1 雙層模板規格與單調遞增防呆 (`assets/templates/todo.md` & `roadmap.md`)

1. **新增 `assets/templates/todo.md`（對應 `plans/roadmap/TODO.md`）**：
   - 頂部具備標準 Header（`> 主題：專案輕量級待辦與技術債帳本`、`> 更新日期：[YYYY-MM-DD]`、`> 狀態：Active`、`> 最後分配編號：0`、`> 模型：[平台宣告之模型名稱；無法確認填 Unknown]`）。
   - **[防呆 2] 單調遞增計數器（Monotonic ID Counter）**：每次執行 `todo add` 時，Python 讀取頂部 Header 的 `> 最後分配編號：N`，取 `max(N, 現有條目最大編號) + 1` 作為新編號並同步更新回寫 `> 最後分配編號：`，確保即使舊條目經 `todo promote` 拔除（甚至全部拔空），後續新增之 `[TODO-XX]` 編號依然嚴格單調遞增，絕不發生歷史 ID 碰撞（且不使用 HTML 註解以符合 `PlanVerifier` 零 HTML 註解規範）。
   - **[防呆 3] 多筆打包立項與 `--slug` 英文蛇形校驗**：`todo promote <TODO-ID> [<TODO-ID> ...] --slug <ascii_plan_slug>` 支援一次傳入多個同模組/相近待辦 ID（如 `TODO-02 TODO-05`），原子拔除並合併寫入新計畫目錄的 `todo.md`，同時強制校驗 `--slug` 必須符合 `^[a-z0-9_]+$` 合法目錄命名規範。
   - **[防呆 4] 當輪 `--model` 參數對齊（嚴禁繼承舊檔案歷史模型）**：`todo add`、`todo promote` 與 `roadmap promote` 均支援 `[--model "<ModelName>"]`（未傳時預設填 `Unknown`）；尤其在執行 `roadmap promote <topic>` 自動生成伴隨 `changelog.md` 時，其標頭與首列模型**必須取自當輪 `--model`（或填 `Unknown`），嚴禁從數週前建立的舊 `{topic}.md` 抄錄歷史模型名稱**。
   - 每筆待辦採用輕量結構化區塊（且 `todo add` 標題與備忘字串同受 `yscb-cli-guide` 約束，禁止夾帶雙引號 `"` 與反引號 `` ` ``）：
     ```markdown
     ### [TODO-01] <簡短動作標題>
     - **建立日期**：YYYY-MM-DD
     - **目標範疇**：`<scope>`
     - **備忘與解法要點**：<note>
     ```
2. **升級 `assets/templates/roadmap.md`（對應 `plans/roadmap/{topic}.md`）**：
   - 保持與現有 `PlanStatusResolver` 及模型紀錄規則 100% 相容之 Header（`> 主題：`、`> 歸檔日期：`、`> 狀態：[Backlog | Proposed | Ready | Deferred]`、`> 模型：[平台宣告之模型名稱；無法確認填 Unknown]`），移除不再需要的 `In Progress | Completed` 狀態，並增補 `> 目標範疇：` 與 `> 前置解鎖條件：`。

### 4.2 雙技能極致精簡指令契約與中樞導流

1. **`roadmap/SKILL.md`（收斂為主動指令型極致精簡契約）**：
   - `description`: `管理與推薦 __${workflow.roadmap://}__ 長期技術路線圖專題檔 ({topic}.md)，並於立項時物理遷入新計畫目錄。僅於顯式輸入 /roadmap 或明確指示管理長期路線圖時觸發。`
2. **新增 `todo/SKILL.md`（主動指令型極致精簡契約）**：
   - `description`: `管理 __${workflow.roadmap://}__/TODO.md 輕量待辦帳本，執行待辦快速盲寫登記、檢索與立項拔除遷入。僅於顯式輸入 /todo 或明確指示管理輕量待辦時觸發。`
3. **中樞技能按需導流与 `[防呆 1]` Seeded 目錄復用規則**：
   - 於 `development-sop/SKILL.md`、`discuss/SKILL.md`（三大範疇出口 ③）、`research/SKILL.md`（三大出口 ②）與 `yscb-cli-guide/SKILL.md` 注入對 `/todo`（及 `todo add` 快捷指令）與 `/roadmap`（及 `roadmap promote`）的按需導流說明。
   - **[防呆 1] `new-plan/SKILL.md` 既有 `Seeded` 目錄原地復用鐵律**：於 `new-plan/SKILL.md` 與 `promote` CLI 輸出提示中明確規定——若目標計畫已透過 `roadmap promote` 或 `todo promote` 預先建立 `plans/YYYY_MM_DD_HHMM_{topic}/` 目錄（内含 `roadmap.md` / `todo.md` 與伴隨 `changelog.md`），後續轉入 `/new-plan` 定稿時**必須直接在該既有 `Seeded` 目錄內建立 `P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md`，嚴禁重複新建第二個時間戳資料夾**！

### 4.3 `status.py`、`scanner.py` 與 `verifier.py` 前置源頭資產白名單
- 當 `{topic}.md` 或 `[TODO-XX]` 被遷入 `plans/YYYY_MM_DD_HHMM_{topic}/` 成為 `roadmap.md` 或 `todo.md` 時：
  1. `PlanScanner` 與 `PlanStatusResolver` 將計畫目錄下的 `roadmap.md` 與 `todo.md` 視為「前置源頭背景資產（Origin Seed Assets）」，不以其標頭狀態覆蓋 `P00`~`P07` / `fast_track_plan.md` / `revision_log.md` 的進度判定；若新計畫目錄下**僅有** `roadmap.md` 或 `todo.md`（剛執行完 `promote`），則顯示狀態為 `Seeded (Pending P00/Plan)`。
  2. `PlanVerifier` 在檢核計畫目錄時，豁免計畫目錄內 `roadmap.md` / `todo.md` 的 `Completed` 終態強制要求與模板章節鏡像檢查，保留其立項當時的原始提案樣貌，待結案時隨整個計畫目錄由 `PlanArchiver` 一併歸檔。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 高優先級技術儲備，可與「Python 工具鏈 (ACI) 強化 (`python_aci_toolchain_roadmap.md`)」合併或依序開立開發計畫落地。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (模板與 Python 雙層引擎擴充)**：新增 `assets/templates/todo.md`、更新 `roadmap.md` 模板；於 `agents_workflow/roadmap.py` 實作 `todo add/list/promote` 與 `roadmap promote`（含自動建立計畫目錄與初始化 `changelog.md`）。
2. **Stage 2 (`plans/` 白名單對接與雙技能更新)**：於 `scanner.py`、`status.py`、`verifier.py` 加入計畫目錄內 `roadmap.md` / `todo.md` 前置資產白名單；新增 `todo/SKILL.md`、重構 `roadmap/SKILL.md` 為極致精簡指令契約，並更新 `contributes/{core,agents-workflow}.json`。
3. **Stage 3 (沙盒測試與 `@build` 自部署)**：新增單元測試驗證 `todo add` 免讀自動編號、`todo promote` 原子 Pop、`roadmap promote` 物理搬移與 `PlanVerifier` 相容性，100% 通過後執行 `@build` 自部署。
