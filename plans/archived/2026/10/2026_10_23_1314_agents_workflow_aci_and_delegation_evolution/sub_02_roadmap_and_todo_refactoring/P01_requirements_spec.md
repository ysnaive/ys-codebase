# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Tier 1 輕量待辦帳本模板與 `todo add` 免讀盲寫登記 | 新增 `assets/templates/todo.md` 模板（對應 `plans/roadmap/TODO.md`，含 Header `> 主題：專案輕量級待辦與技術債帳本`、`> 更新日期：`、`> 狀態：Active`、`> 最後分配編號：0`、`> 模型：`）。實作 `python yscb.py agents-workflow todo add "<title>" [--scope "<scope>"] [--note "<note>"] [--model "<ModelName>"]`：若 `TODO.md` 不存在則自動初始化；讀取頂部 `> 最後分配編號：N` 並取 `max(N, 現有條目最大編號) + 1` 分配新 `[TODO-XX]`（至少兩位數補零如 `TODO-01`），更新頂部 `> 更新日期：`、`> 最後分配編號：` 與 `> 模型：`，並於檔尾追加結構化 `### [TODO-XX] <title>` 區塊（含建立日期、目標範疇、備忘與解法要點）。 **`[P01:DR-01]`**：單調計數器直接儲存於頂部 Blockquote Header `> 最後分配編號：N`，不使用 HTML 註解。 | P0 | `[P00:DR-01]`, `[P00:DR-02]`, `[P00:DR-03]` |
| **FR-02** | `todo list` 唯讀檢索與過濾列表 | 實作 `python yscb.py agents-workflow todo list [--scope "<keyword>"]`（以及直接執行 `python yscb.py agents-workflow todo` 無子命令時之預設行為）：唯讀解析 `plans/roadmap/TODO.md` 中所有 `### [TODO-XX]` 條目，支援以 `--scope` 關鍵字（不區分大小寫）比對目標範疇或標題，輸出結構化對齊摘要表格（含編號、日期、目標範疇、標題摘要）。 | P0 | `[P00:DR-01]` |
| **FR-03** | `todo promote` 單筆／多筆原子剪切立項 (`Pop & Promote`) | 實作 `python yscb.py agents-workflow todo promote <todo_ids...> --slug <ascii_slug> [--model "<ModelName>"]`：支援傳入 1 至多筆待辦編號（如 `TODO-01` 或 `TODO-01 TODO-03`，支援無前綴數字或帶框格式正規化），強制校驗 `--slug` 符合 `^[a-z0-9_]+$`；自 `plans/roadmap/TODO.md` 中將目標 `### [TODO-XX]` 區塊原子剪切拔除（保留頂部 `> 最後分配編號：` 不倒退），建立 `plans/YYYY_MM_DD_HHMM_{slug}/` 目錄，將拔除之條目寫入該目錄下之 `todo.md`（附標準 Header，模型填 `--model` 或 `Unknown`），並呼叫 `PlanVerifier.append_changelog_entry` 自動初始化伴隨 `changelog.md`，最後於終端輸出原地復用 `Seeded` 目錄之引導提示。 | P0 | `[P00:DR-01]`, `[P00:DR-02]`, `[P00:DR-03]` |
| **FR-04** | Tier 2 `roadmap.md` 模板升級与 `roadmap [list]` 狀態過濾 | 更新 `assets/templates/roadmap.md` 模板：狀態枚舉收斂為 `[Backlog \| Proposed \| Ready \| Deferred]`，並新增 `> 目標範疇：` 與 `> 前置解鎖條件：` 標頭欄位。擴充 `RoadmapManager.scan_roadmaps()` 自動排除集中式帳本 `TODO.md`（不分大小寫），解析 `scope` 與 `trigger` 欄位，並於 `python yscb.py agents-workflow roadmap [list] [--status <val>]` 支援依狀態（不區分大小寫）過濾輸出。 | P0 | `[P00:DR-01]` |
| **FR-05** | `roadmap promote` 策略路線圖物理搬移立項 (`Consume-on-Promote`) | 實作 `python yscb.py agents-workflow roadmap promote <topic> [--model "<ModelName>"]`：於 `plans/roadmap/` 查找匹配 `<topic>`（支援檔名或不含 `.md` 之主題 stem）之路線圖檔案，建立 `plans/YYYY_MM_DD_HHMM_{topic_stem}/` 目錄，使用 `shutil.move` 將原檔物理搬移至新計畫目錄下並重命名為 `roadmap.md`，且以當輪 `--model`（未傳填 `Unknown`，嚴禁繼承舊路線圖內之歷史模型名稱）自動初始化伴隨 `changelog.md`，同時輸出原地復用 `Seeded` 目錄之引導提示。 **`[P01:DR-02]`**：為支援已建立之主計畫或子計畫（如 Umbrella 下之 `sub_XX`），`roadmap promote` 與 `todo promote` 額外支援選填 `--plan <existing_plan_or_subpath>` 參數，允許直接將路線圖或待辦遷入既有計畫／子計畫目錄內。 | P0 | `[P00:DR-01]`, `[P00:DR-03]` |
| **FR-06** | `plans/` 前置源頭資產白名單 (`Seeded` 狀態) 與雙技能／CLI 契約更新 | 1. 於 `PlanScanner`、`PlanStatusResolver` 與 `PlanVerifier` 將計畫目錄內之 `roadmap.md` 與 `todo.md` 列為「前置源頭背景資產 (`ORIGIN_SEED_FILES`)」：當計畫目錄僅含前置資產（及 `changelog.md`）而尚無 `P00`~`P07` / `fast_track_plan.md` / `revision_log.md` / `umbrella_overview.md` / `RXX_*.md` 時，判定模式與階段為 `Seeded`，`plan status --resume` 提示於該目錄原地建立初始開發文件；一旦存在主體開發文件，進度完全由主體文件決定；`PlanVerifier` 豁免計畫目錄內 `roadmap.md` / `todo.md` 之模板章節鏡像、`> 所屬主計畫：` 與 `Completed` 狀態強制要求。<br/>2. 於 `contributes/core.json` 與 `scripts/cli.py` 註冊 `roadmap` 擴充與 `todo` 命令群；新增 `assets/skills/todo/SKILL.md`、更新 `roadmap/SKILL.md`、`new-plan/SKILL.md`（`Seeded` 原地復用鐵律）、`development-sop/SKILL.md`、`discuss/SKILL.md`、`research/SKILL.md` 與 `yscb-cli-guide/SKILL.md`，並同步更新 `contributes/agents-workflow.json`。 | P0 | `[P00:DR-03]`, `[P00:DR-04]` |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `plans/roadmap/TODO.md` 尚不存在或目錄不存在時執行 `todo add` / `todo list` / `todo promote` | • `todo add`：自動建立父目錄並以標準模板初始化 `TODO.md`（首筆編號為 `TODO-01`，`> 最後分配編號：1`）。<br/>• `todo list`：平穩輸出「目前尚無待辦項目」並回傳 `0`，不拋出 `FileNotFoundError`。<br/>• `todo promote`：輸出明確錯誤訊息提示 `TODO.md` 不存在並回傳非零退出碼 (`1`)。 |
| **EC-02** | `TODO.md` 中既有條目被 `todo promote` 部分或全數拔除後，再次執行 `todo add` | 讀取頂部 Header `> 最後分配編號：N` 並與檔案現存 `### [TODO-XX]` 最大編號取 `max(N, max_existing) + 1`，確保即使所有舊條目已被拔除清空，新分配之編號仍嚴格單調遞增（例如 `TODO-01` 被立項拔除後，下一筆必為 `TODO-02` 而非重回 `TODO-01`）。 |
| **EC-03** | `todo promote` 傳入不存在之 `TODO-ID`、重複 ID，或 `--slug` 包含大寫／空格／特殊字元 | • 若任一指定之 `TODO-ID` 於 `TODO.md` 中不存在：拒絕執行部分拔除（保持原子性，不修改 `TODO.md` 亦不建立新目錄），印出找不到之 ID 與現有可用 ID 提示並回傳 `1`。<br/>• 若未提供 `--slug`（且未指定 `--plan`）或 `--slug` 不符合 `^[a-z0-9_]+$`：立即拒絕並輸出格式修正提示（Fix Hint），回傳 `1`。 |
| **EC-04** | `roadmap promote <topic>` 傳入不存在之主題、模糊匹配到多個檔案，或傳入 `TODO.md` | • 嚴格排除 `TODO.md`。<br/>• 若找不到匹配檔案或模糊匹配命中超過 1 個檔案：拒絕搬移，列出候選路線圖清單並回傳 `1`。 |
| **EC-05** | 於已包含 `roadmap.md` 或 `todo.md` 之子計畫目錄（如 `sub_01`、`sub_02`）執行 `plan verify --all` | `PlanVerifier` 識別 `roadmap.md` 與 `todo.md` 為前置源頭背景資產，豁免其 `> 建立日期：`（允許 `> 歸檔日期：` 或 `> 更新日期：`）、豁免子計畫強制 `> 所屬主計畫：`、允許 `Backlog / Proposed / Ready / Deferred / Active` 狀態且不執行模板標題鏡像檢查，確保 `plan verify` 100% `PASS`。 |
| **EC-06** | `roadmap list` 掃描 `plans/roadmap/` 時存在 `TODO.md` | `RoadmapManager.scan_roadmaps()` 自動過濾跳過 `TODO.md`（不分大小寫），確保 Tier 1 集中式帳本不會混入 Tier 2 策略路線圖列表。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴與執行效能 | 100% 使用 Python 標準庫（`pathlib`, `re`, `shutil`, `datetime`）；單次 `todo add` / `todo list` / `todo promote` / `roadmap promote` CLI 執行時間 $\le 100\text{ms}$。 |
| **NFR-02** | 靜態合規與向後相容 | 新增之 `todo` 命令與擴充之 `roadmap` 命令必須 100% 通過 `python yscb.py dev check agents-workflow`（`contributes/core.json` 與 `scripts/cli.py` 1:1 頂層對稱性、ASCII 輸出純度、URI 雙階段編譯驗證）及全部單元測試。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` CLI 頂層函式 1:1 對稱性守門**：依據 `docs/dev/DESIGN_NOTES.md` 與 [R01_cli_command_specification.md](../R01_cli_command_specification.md)，`contributes/core.json` 新增頂層 `"todo"` 命令時，`ys_codebase/source/agents-workflow/scripts/cli.py` 必須定義同名頂層函式 `def todo(cmd_bags: Any) -> int:`，並於函式內部透過 `_normalize_bags(cmd_bags, "todo")` 分發 `add`、`list`、`promote` 子命令，以符合 `ModuleChecker` 靜態檢核。
- **`[!NOTE]` 新增 Skill 必須同步宣告於 `contributes/agents-workflow.json`**：新增 `assets/skills/todo/SKILL.md` 與 `assets/templates/todo.md` 時，必須檢查 `contributes/agents-workflow.json` 的匯出規則（或目錄通配規則），確保 `compile` 與 `release` 能將 `todo` 技能與模板正確物化至 `.agents/skills/todo/` 與 `.agents/.yscb/templates/todo.md`。

