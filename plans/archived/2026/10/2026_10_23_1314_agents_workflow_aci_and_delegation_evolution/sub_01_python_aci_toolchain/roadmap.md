# 技術路線圖：Agents-Workflow Python 工具鏈 (ACI) 強化與狀態機下沉演進 (Roadmap)

> 主題：Agents-Workflow Python 工具鏈 (ACI) 強化與狀態機下沉演進  
> 歸檔日期：2026-10-22  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在維持 `agents-workflow` 現行三大基石（SOP 00~07 外部化思維鏈、`AGENTS.md` 極簡 Token 保護、主體規格檔單次寫入免雙重 I/O）的前提下，目前 [`agents_workflow/plans/`](../ys_codebase/source/agents-workflow/agents_workflow/plans) Python 工具鏈與 Markdown Skills 之間仍存在三項會消耗模型注意力或導致機械式失誤的痛點：
1. **斷點狀態推導與 `handoff.md` 閱後即焚依賴模型手動操作**：目前 `continue/SKILL.md` 透過 20 餘行查表指導模型判斷斷點與下一步應讀參考檔，且要求模型手動刪除已消費的 `handoff.md`，小模型偶有判錯階段或漏刪快照之風險。
2. **附屬日誌（`changelog.md`）與伴隨檔（`P06 Draft`）維護分散主任務注意力**：
   - 每推進一個階段，Agent 為了在 `changelog.md` 插入 1 行紀錄，必須先呼叫 `read_file` 將整份歷史 `changelog.md` 讀入 Context Window（造成注意力分散與 Context 污染），再猜測當前時間戳並呼叫 `edit_file` 修改（消耗 2 次 Tool Calls）。
   - 立項建立 `YYYY_MM_DD_HHMM_{topic}/` 時偶有漏建雙星伴隨之 `changelog.md`，或於 `Phase 02` 專注撰寫架構時漏建伴隨之 `P06_test_plan.md (Draft)`。
3. **跨文件追溯鏈與雙檔協同檢核時機偏晚**：[`verifier.py` (`PlanVerifier`)](../ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py) 目前雖能檢核單檔標頭、佔位符與 `FT-XX` 存在性，但尚未自動比對 **`P01` (`FR/EC/NFR`) 與 `P06` (`FT/ET/RT`) 之間的集合差集（Set Diff）**，亦未在階段推進當下即時攔截雙檔狀態不一致。

### 1.2 現況與影響範圍評估
- **架構設計取捨（保留「主體文件單次原生寫入」，將「狀態領航、伴隨鷹架與 `changelog.md` 盲寫追加」下沉至 Python CLI）**：
  - **主體規格文件（`P00`~`P07`、`fast_track_plan.md` 等）維持宿主原生單次寫入 (`write_file`)**：避免先跑 CLI 建空白檔、再讀檔、再改檔的多餘 I/O 往返。
  - **將「只寫不讀（Write-Only）」與「機械式時間戳/伴隨檔庶務」收斂至 Python CLI**：
    1. **M1（確定性狀態領航 + `--resume` 原子閱後即焚）**：由 `plan status --resume` 一次輸出下一步應讀參考檔、印出 `handoff.md` 並由 Python 立即物理刪除。
    2. **M2（單階段左移檢核 + `P01<->P06` 追溯差集比對 + 自癒型報錯）**：由 `plan verify` 精準攔截未映射之孤兒需求 ID 與雙檔狀態缺失。
    3. **M3 & M4 精華融合（立項/伴隨檔自動補齊 + `changelog.md` 免讀盲寫追加）**：擴充 `plan verify`（或 `plan log`）支援在驗證通過時，**由 Python 自動抓取系統時間 `YYYY-MM-DD HH:MM` 免讀檔直接追加 `changelog.md` 紀錄**（若缺少 `changelog.md` 或 `Phase 02` 缺少 `P06_test_plan.md (Draft)` 亦可自動從模板初始化伴隨鷹架），徹底消除為了記日誌而讀取歷史檔案的注意力分散！

### 1.3 核心根因
1. [`scanner.py`](../ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py) 與 [`status.py`](../ys_codebase/source/agents-workflow/agents_workflow/plans/status.py) 僅回傳當前階段標籤，未輸出結構化的「下一跳行動指令（Next-Action Directive）」與應讀 `references/phase_0X_*.md` 路徑。
2. [`verifier.py`](../ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py) 缺乏跨文件 ID 集合差集提取器（`P01` $\leftrightarrow$ `P06`）、雙檔協同狀態守門，以及免讀檔追加 `changelog.md` 的快捷能力。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：維持純手動查表與手動讀改 `changelog.md`（現況）** | 斷點靠 `continue` 表格推導；每次記日誌皆須 `read_file` + `edit_file` `changelog.md` | 無需修改 Python 程式碼 | 每次記日誌多花 2 次 Tool Call 且污染 Context；易漏刪 `handoff.md` 或漏映射 `FR/EC` | ⭐️⭐️ |
| **方案 2：重度 CLI 狀態機（連主體 `P0X` 都強制先跑 `step-init` 建空白檔）** | 每個階段頭尾皆強制呼叫 CLI 建立空白 `P0X`、再讀檔填寫、再呼叫 CLI 改標頭 | 所有檔案皆由腳本建立 | 主體規格檔被迫拆為「建空白檔 -> 讀檔 -> 改檔」3 步，違反 Single-Pass Write 高效原則 | ⭐️⭐️⭐️ |
| **方案 3：確定性領航 + 左移差集檢核 + 伴隨檔/`changelog.md` 免讀盲寫（推薦採納）** | 主體規格檔維持原生 `write_file` 一次寫定；由 `plan status --resume` 負責領航與銷毀 `handoff`；由 `plan verify --log` 一次完成階段檢核、伴隨檔防漏與 `changelog.md` 免讀追加 | 1. **零 Context 污染**：免讀歷史 `changelog.md` 即可 1 行追加日誌並同時完成階段合規檢核<br/>2. **主體寫檔零額外摩擦**：保留 `P01~P04` 單次寫檔直達 `Confirmed`<br/>3. 徹底根絕漏刪 `handoff.md`、漏建 `P06 Draft` 與漏映射 `FR/EC` | 需擴充 `status.py`、`scanner.py` 與 `verifier.py`（100% Python 標準庫） | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 2（重度 CLI 空白檔預建） | 方案 3（輕量領航 + 檢核與日誌盲寫合一） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | **極高（100% Python 標準庫擴充）** |
| **對當前任務注意力保護** | 中（多出空白檔讀改步驟） | **最高（免讀歷史 `changelog.md`，1 次呼叫完成檢核+記日誌）** |
| **可靠性 (Reliability)** | 中 | **極高（系統時間戳自動生成 + 確定性集合差集運算）** |
| **Token 與 Tool Call 效率** | 低（每階段多出 2~3 次工具調用） | **最高（每階段省去讀改 `changelog.md` 的 2 次 Tool Call）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 1. M1：確定性狀態領航與 handoff.md 原子閱後即焚 (Consume & Delete)
python yscb.py agents-workflow plan status [--plan <plan_name_or_subpath>] [--resume]

# 2. M2 + M3/M4 精華：單階段左移檢核、伴隨檔自癒與 changelog.md 免讀盲寫追加
python yscb.py agents-workflow plan verify [plan_name_or_subpath] [--phase <P00..P07|current|all>] [--log "<摘要>" [--type PHASE|DECISION|REVISION] [--model "<ModelName>"]]
```

### 4.1 里程碑 M1：狀態機領航與 `handoff.md` 原子閱後即焚 (`M1: Deterministic State Driver`)
- **`FR-M1-01` (`resolve_next_action`)**：於 `PlanStatusResolver` / `PlanScanner` 新增下一步推導邏輯，根據目標計畫（自動深入 `Umbrella` 活躍之 `sub_{編號}_{名稱}` 子目錄）現有檔案與標頭狀態，輸出 `{mode, current_phase, current_status, next_phase, required_reference_path}`。
- **`FR-M1-02` (`--resume` 原子化 Consume & Delete)**：`plan status` 新增 `--resume` 旗標；當目標計畫或活躍子計畫存在 `handoff.md` 時，於輸出中完整印出 `handoff.md` 內容，並於讀取成功後**立即呼叫 `os.unlink()` 物理刪除該檔案**。
- **`FR-M1-03` (唯讀安全預設)**：未傳入 `--resume` 時，`plan status` 維持 100% 純唯讀掃描，絕不刪除 `handoff.md`。
- **`FR-M1-04` (`continue/SKILL.md` 查表瘦身)**：`continue/SKILL.md` 改為優先調用 `plan status --resume` 取得下一步指令與參考檔路徑（保留極簡唯讀沙盒 Fallback）。

### 4.2 里程碑 M2：階段左移檢核與追溯鏈差集引擎 (`M2: Shift-Left PlanVerifier`)
- **`FR-M2-01` (`--phase` 局部與雙檔協同檢核)**：`PlanVerifier` 支援 `--phase <P00..P07|current|all>`；在 `P02` 完成時檢核同目錄是否已建立 `P06_test_plan.md`，在 `P04` 定稿時檢核 `P06_test_plan.md` 狀態是否已更新為 `Confirmed`（或更高階段狀態）。
- **`FR-M2-02` (`P01` $\leftrightarrow$ `P06` 追溯鏈集合差集比對與排除項過濾)**：
  - 自動解析 `P01_requirements_spec.md` 中定義之 `FR-\d+`、`EC-\d+`、`NFR-\d+` 集合，於檢核 `P04` / `P06` / `all` 時比對 `P06_test_plan.md` 內文是否 100% 涵蓋，精準揪出漏映射之孤兒需求 ID。
  - **[防呆 3] 刪除線與註解預過濾**：提取 `P01` 需求 ID 集合前，必須先剝除 Fenced Code Blocks（`` ```...``` ``）、HTML 註解區塊（`<!--[\s\S]*?-->`）與 Markdown 刪除線語法（`~~.*?~~`），避免將已作廢/延後之需求（如 `~~FR-04~~`）或範例誤判為孤兒 ID。
- **`FR-M2-03` (自癒型 Actionable Fix Hint)**：所有 `FAIL` / `WARN` 診斷訊息均附帶具體修復指引（明確列出缺失檔案、未替換佔位符或未映射之 `FR-XX` / `EC-XX` 清單）。

### 4.3 里程碑 M3：`changelog.md` 免讀盲寫追加與伴隨鷹架自癒 (`M3: Zero-Read Changelog & Companion Scaffold`)
- **`FR-M3-01` (`--log` 免讀盲寫追加與冪等防重入)**：於 `plan verify`（或獨立子命令 `plan log`）提供 `--log "<摘要>" [--type PHASE] [--model "<ModelName>"]`：
  - 若目標目錄尚無 `changelog.md`，自動從模板初始化 `changelog.md`。
  - 自動抓取系統當前時間 `YYYY-MM-DD HH:MM`，直接於 `changelog.md` 表格頂部插入新紀錄列，**完全免除 Agent 讀取與編輯 `changelog.md` 的 Context 污染與 Tool Call 開銷**。
  - **[防呆 1-B] 冪等防重入（Idempotent Log Append）**：寫入前自動比對 `changelog.md` 表格第一筆資料列之 `(類型, 摘要)`，若完全相同則跳過插入，防止 Agent 修正重跑指令時產生重複日誌列。
- **`FR-M3-02` (`P02` 伴隨 `P06 Draft` 自動補齊與嚴格管線時序)**：
  - **[防呆 1-A] 四步執行管線時序（先補齊、後檢核、全過才寫 Log）**：當執行 `plan verify --phase P02 --log "..."` 時，`verifier.py` 內部嚴格固定順序為：
    1. **Step 1**：先檢核 `P02_architecture_plan.md` 本體合規性（Header、佔位符、章節標題）。
    2. **Step 2**：若 `P02` 本體通過且同目錄尚無 `P06_test_plan.md`（或尚無 `changelog.md`），立即自動從模板生成 `P06_test_plan.md (Draft)`（及 `changelog.md`）。
    3. **Step 3**：執行 `FR-M2-01` 雙檔協同與全項合規檢核。
    4. **Step 4**：**僅當上述檢核 100% `PASS` 時，方執行 `FR-M3-01` 將 `--log` 寫入 `changelog.md`**（若檢核為 `FAIL` 絕對禁止寫入日誌）。
- **`FR-M3-03` (伴隨檔模型紀錄鐵律與終端引號防呆)**：
  - **[防呆 2] 模型紀錄規則對齊（嚴禁跨階段回溯舊檔）**：Python 自動初始化伴隨檔（`changelog.md` 或 `P06_test_plan.md (Draft)`）時，其標頭 `> 模型：` 優先取用 CLI 顯式傳入之 `--model "<ModelName>"`；若未傳入 `--model`，僅允許讀取當下同階段剛寫好的主體檔（如 `--phase P02` 時讀取 `P02_architecture_plan.md`）之標頭模型，否則預設填入 `Unknown`，**嚴禁跨階段回溯讀取舊階段檔案（如 `P00_discuss.md`）**。
  - **[防呆 4] 終端單行引號與反引號逃逸防呆（對齊 `yscb-cli-guide`）**：於 `yscb-cli-guide` 與 `development-sop` 明確規範 `--log "<摘要>"` 字串內文**嚴禁使用雙引號 `"` 與反引號 `` ` ``**（避免引發 Bash / PowerShell 命令替換與引號崩潰），如需強調識別符或階段名稱一律改用單引號 `'...'` 或方括號 `[...]`。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 高優先級技術儲備，可與「Roadmap 與 TODO 雙層儲備體系重構」協同排程，透過 `/new-plan` 開立標準開發計畫（Full Track）落地。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (M1 狀態導航與 `--resume` 實作)**：擴充 `status.py`、`scanner.py` 與 `commands.py`，實作 `resolve_next_action` 與 `--resume` 原子閱後即焚，並精簡 `continue/SKILL.md`。
2. **Stage 2 (M2 追溯鏈差集與雙檔協同檢核)**：擴充 `verifier.py` 實作 `P01` $\leftrightarrow$ `P06` 集合差集檢查、`P02/P04` 對 `P06` 雙檔狀態檢查與 `--phase` 參數。
3. **Stage 3 (M3 免讀日誌追加與伴隨鷹架)**：實作 `--log` 系統時間戳自動追加 `changelog.md` 與伴隨檔初始化，補齊單元測試並完成 `@build` 自部署。
