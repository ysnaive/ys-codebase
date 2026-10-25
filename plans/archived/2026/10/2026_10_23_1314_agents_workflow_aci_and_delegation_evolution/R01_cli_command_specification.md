# 技術調研報告：Agents-Workflow CLI 指令契約整合與邊界規範 (R01_cli_command_specification.md)

> 調研主題：Agents-Workflow CLI 指令契約整合與邊界規範  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  - 在推進主計畫 `2026_10_23_1314_agents_workflow_aci_and_delegation_evolution`（涵蓋 `sub_01` Python ACI 工具鏈強化、`sub_02` Roadmap 與 TODO 雙層儲備重構、`sub_03` Subagent 三支柱隔離協定、`sub_04` 二次驗收與打磨）前，需先跨子計畫統籌審查預計新增與擴充之 CLI 指令清單。
  - 若未預先定調 CLI 結構，容易產生冗餘頂層命令、子命令語意不對稱，或因跨子計畫分階段實作導致 `contributes/core.json` 與 `scripts/cli.py` 1:1 對稱性靜態檢查（`dev check agents-workflow`）失敗。
- **調研目標**：
  1. 盤點並收斂 `sub_01` ~ `sub_04` 全週期預計擴充與新增之 CLI 指令、位置參數 (`args`)、選項旗標 (`options`) 與權限分級 (`tier`)。
  2. 確立「既有命令旗標擴充優先」與「雙層儲備命令對稱設計」原則，並鎖定各子計畫之分階段交付邊界。

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：大量新增獨立子命令（如 `plan resume`、`plan log`、`plan task-brief`）** | 為每項新能力各自獨立新增 `plan` 子命令或頂層命令 | 各子命令功能單一 | 1. 導致 `plan` 子命令數量膨脹，增加 Agent 查表與記憶負擔<br/>2. 檢核 (`verify`) 與記日誌 (`log`) 拆成兩次 CLI 呼叫，多耗費 1 次終端往復且無法強制綁定「檢核通過才記日誌」之原子時序 | ⭐️⭐️ |
| **方案 B：既有 `plan` 命令旗標內聚擴充 + `roadmap`/`todo` 對稱雙層命令群（推薦採納）** | 1. `sub_01` 零新增頂層/次層命令，直接於 `plan status` 擴充 `--resume`，於 `plan verify`/`check` 擴充 `--phase` 與 `--log`<br/>2. `sub_02` 將儲備拆分為對稱之 `roadmap` (`list`/`promote`) 與 `todo` (`add`/`list`/`promote`)<br/>3. `sub_03` 採檔案路徑傳址，零新增 CLI | 1. **極簡命令表面積**：`sub_01` 不增加任何新子命令名稱<br/>2. **檢核與日誌原子合一**：`plan verify --phase P02 --log "..."` 單次呼叫完成檢核、伴隨檔自癒與免讀盲寫追加<br/>3. **`roadmap` 與 `todo` 語意 100% 對稱**，且完全符合 `dev check` 1:1 對稱性守門 | 需於 `PlanVerifier` 內部嚴格實作四步執行管線時序 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `sub_01`：Python 工具鏈 (ACI) 強化（零新頂層命令，僅擴充既有 `plan` 子命令旗標）

保持既有 `plan status` 與 `plan verify`（及同義詞 `plan check`）指令不變，僅擴充參數與選項：

| 指令簽名 | 新增參數 / 選項 (`args` / `options`) | 權限分級 | 用途與行為說明 |
| :--- | :--- | :---: | :--- |
| **`python yscb.py agents-workflow plan status`** | • `[plan_name]` *(選填位置參數或 `--plan <name>`)*：指定計畫或 `sub_XX` 子計畫路徑<br/>• `--resume`：啟用斷點領航與 `handoff.md` 原子閱後即焚 | `[SAFE]` | 1. **未加 `--resume`**：維持 100% 純唯讀掃描矩陣（若指定計畫則附帶下一步領航提示）。<br/>2. **加上 `--resume`**：輸出目標計畫之 `mode`、`current_phase`、`next_phase`、`required_reference_path`；若存在 `handoff.md`，印出完整內容後立即呼叫 `os.unlink()` 物理刪除。 |
| **`python yscb.py agents-workflow plan verify`**<br/>*(同義：`plan check`)* | • `[plan_name]` *(既有選填位置參數)*：支援傳入主計畫或 `<umbrella>/sub_XX`<br/>• `--phase <val>`：指定檢核階段（`P00`~`P07`、`current`、`all`，預設 `all`）<br/>• `--log "<摘要>"`：檢核 100% `PASS` 時免讀檔自動追加 `changelog.md`<br/>• `--type <val>`：搭配 `--log` 指定日誌類型（`PHASE` \| `DECISION` \| `REVISION`，預設 `PHASE`）<br/>• `--model "<ModelName>"`：指定當輪平台宣告模型名稱 | `[SAFE]` | 1. **單階段與雙檔協同檢核 (`--phase`)**：檢核 `P02` 時確認 `P06 Draft` 存在；檢核 `P04` 時確認 `P06` 已 `Confirmed` 且 `P01 <-> P06` 需求 ID 100% 覆蓋。<br/>2. **伴隨檔自癒與免讀盲寫 (`--log`)**：遵循四步管線（檢核主體 $\to$ 自動補齊缺失之 `changelog.md` 或 `P02` 伴隨 `P06 Draft` $\to$ 雙檔/追溯檢核 $\to$ `PASS` 後以系統時間戳寫入 `changelog.md` 並具冪等防重入）。 |

### 3.2 `sub_02`：Roadmap 與 TODO 雙層儲備體系重構（擴充 `roadmap` + 新增 `todo` 命令群）

將儲備管理拆分為策略層 `roadmap` 與戰術層 `todo`：

| 指令簽名 | 參數 / 選項 (`args` / `options`) | 權限分級 | 用途與行為說明 |
| :--- | :--- | :---: | :--- |
| **`python yscb.py agents-workflow roadmap [list]`** | • `[topic]` *(既有)*：指定主題名稱檢視單篇詳情<br/>• `--list` / `-l` *(既有)*：列出所有路線圖摘要表格<br/>• `--status <val>` *(新增)*：依狀態過濾（`Backlog` \| `Proposed` \| `Ready` \| `Deferred`） | `[SAFE]` | 唯讀掃描與過濾 `plans/roadmap/{topic}.md` 策略路線圖儲備庫（自動排除集中式帳本 `TODO.md`）。 |
| **`python yscb.py agents-workflow roadmap promote`** | • `<topic>` *(必填)*：欲立項之路線圖主題名稱<br/>• `--model "<ModelName>"` *(選填)*：當輪模型名稱（未傳填 `Unknown`） | `[SAFE]` | **立項物理遷入 (`Consume-on-Promote`)**：建立 `plans/YYYY_MM_DD_HHMM_{topic}/`，將 `plans/roadmap/{topic}.md` 物理搬移 (`shutil.move`) 至新計畫目錄下命名為 `roadmap.md`，並自動初始化伴隨 `changelog.md`。 |
| **`python yscb.py agents-workflow todo add`** | • `<title>` *(必填)*：簡短待辦動作標題<br/>• `--scope "<範圍>"` *(選填)*：目標模組或檔案路徑<br/>• `--note "<備忘>"` *(選填)*：單行解法備忘或觸發條件<br/>• `--model "<ModelName>"` *(選填)*：當輪模型名稱 | `[SAFE]` | **單行免讀盲寫登記**：無需讀取 `TODO.md` 歷史內容，自動讀取並遞增頂部 `> 最後分配編號：N`，產生 `[TODO-XX]` 結構化區塊追加至 `plans/roadmap/TODO.md` 檔尾（若無檔案則自動從模板初始化）。 |
| **`python yscb.py agents-workflow todo list`** | • `--scope "<keyword>"` *(選填)*：依目標範疇或關鍵字過濾 | `[SAFE]` | 唯讀列出 `plans/roadmap/TODO.md` 中所有活躍待辦項目摘要表格（若直接執行 `python yscb.py agents-workflow todo` 無子命令時亦預設執行 `list`）。 |
| **`python yscb.py agents-workflow todo promote`** | • `<todo_ids...>` *(必填，支援單筆或多筆如 `TODO-01 TODO-03`)*<br/>• `--slug <ascii_slug>` *(必填)*：新計畫目錄英文蛇形後綴（校驗 `^[a-z0-9_]+$`）<br/>• `--model "<ModelName>"` *(選填)*：當輪模型名稱 | `[SAFE]` | **原子拔除立項 (`Pop & Promote`)**：將指定之 1~N 筆 `[TODO-XX]` 區塊自 `plans/roadmap/TODO.md` 原子剪切拔除，建立 `plans/YYYY_MM_DD_HHMM_{slug}/` 並寫入 `todo.md`，同時初始化伴隨 `changelog.md`。 |

### 3.3 架構方案 / 時序說明与 PoC 合規驗證
- **架構方案 / 時序說明**：
  - `sub_01` 階段僅更新 `contributes/core.json` 中 `plan.cmd.status` 與 `plan.cmd.{verify,check}` 之 `args`/`options` 宣告，並於 `scripts/cli.py` 對應入口解析。
  - `sub_02` 階段更新 `contributes/core.json` 中 `roadmap` 子命令並新增頂層 `todo` 命令（含 `add`、`list`、`promote`），同步於 `scripts/cli.py` 新增 `def todo(cmd_bags: Any) -> int:` 入口函式。
  - `sub_03` 與 `sub_04` 不涉及新增 CLI 命令。
- **PoC 實作或 Benchmark 數據**：
  - 對照 `dev/checker.py` (`ModuleChecker`) 靜態檢查規則：頂層命令 `plan`、`roadmap`、`todo` 與 `scripts/cli.py` 頂層函式 `plan`、`roadmap`、`todo` 1:1 嚴格對稱，複合子命令（`plan status/verify`、`roadmap list/promote`、`todo add/list/promote`）由內部透過 `CmdBags` 分發，100% 符合 YSCB CLI 活躍合約。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：採納 **方案 B**（出口 ① 立即實作），作為主計畫下 `sub_01` 與 `sub_02` 的 CLI 契約唯一真理來源（SSOT）。
- **後續行動與 P00 銜接**：本報告已標記為 `Concluded` 並存檔於主計畫根目錄；接下來直接依此 CLI 契約推進 `sub_01_python_aci_toolchain` 之 Phase 2（`P02_architecture_plan.md` + `P06_test_plan.md (Draft)`）。

