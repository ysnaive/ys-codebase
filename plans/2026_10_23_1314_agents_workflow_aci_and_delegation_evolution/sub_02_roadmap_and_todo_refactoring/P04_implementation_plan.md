# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書中有對應介面 (`TodoManager`, `RoadmapManager`, `PlanStatusResolver`, `PlanScanner`, `PlanVerifier`, `scripts/cli.py`)
- [x] **邊界防護**：EC-01 ~ EC-06 有具體錯誤處理策略（原子 Pop 校驗、`--slug` 正則校驗、單調編號防倒退、`TODO.md` 自動排除與 `Seeded` 檢核豁免）
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-02 指標約束（100% Python 標準庫、通過 `dev check agents-workflow` 1:1 頂層對稱性檢核）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新雙層儲備體系（`/todo` + `/roadmap`）與 CLI 指令清冊 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 補充 `todo add/list/promote` 與 `roadmap promote` 立項物理遷入操作指南 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-11]`：`TODO.md` 頂部 Header 單調計數器、`Consume-on-Promote` 與 `Seeded` 前置源頭資產白名單設計 |
| **微觀註解** | `agents_workflow/{roadmap.py,plans/*.py}` | Modify | 同步更新 `TodoManager`, `RoadmapManager` 與 `Seeded` 狀態解析之公開介面 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於結案時記錄雙層儲備體系重構與 `Consume-on-Promote` 發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 `TODO.md` 中的最後一筆條目（如 `TODO-03`）被 `todo promote` 原子拔除，此時檔案中僅剩 `TODO-01` 與 `TODO-02`（甚至全部拔空），下一次執行 `todo add` 時會不會重分配出已經用過的 `TODO-03` 或 `TODO-01`，造成歷史計畫中的 `todo.md` 編號與新待辦碰撞？  
> [*] **防護解法**：於 `TODO.md` 頂部 Blockquote Header 顯式維護 `> 最後分配編號：N`。每次 `todo add` 時計算 `next_num = max(header_last_id, max_existing_item_id) + 1` 並回寫 `> 最後分配編號：`，且 `todo promote` 拔除條目時保持 `> 最後分配編號：` 不變，100% 保證單調遞增且不使用任何 HTML 註解。

> [?] **尖銳問題 2**：當 `roadmap promote <topic>` 將 `plans/roadmap/{topic}.md` 物理搬移為 `plans/YYYY_MM_DD_HHMM_{topic}/roadmap.md`（或子計畫內之 `roadmap.md`）後，執行 `plan verify --all` 時，`roadmap.md` 頂部為 `> 歸檔日期：` 與 `> 狀態：Ready` 且無 `> 所屬主計畫：`，會不會導致 `PlanVerifier` 報錯 `FAIL`？  
> [*] **防護解法**：於 `PlanVerifier` 將 `roadmap.md` 與 `todo.md` 列入 `ORIGIN_SEED_FILES` 前置源頭背景資產白名單——保留其「零 HTML 註解」與「零未替換模板佔位符」檢查，但日期標頭接受 `歸檔日期 / 更新日期 / 建立日期`，狀態接受 `Backlog / Proposed / Ready / Deferred / Active`，並豁免子計畫 `> 所屬主計畫：`、模板標題鏡像與結案 Checkbox 檢查。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01（雙層模板建置與升級）**：新增 `ys_codebase/source/agents-workflow/assets/templates/todo.md`，並更新 `assets/templates/roadmap.md`（新增 `> 目標範疇：`、`> 前置解鎖條件：`，收斂狀態枚舉）。
2. **TASK-02（`roadmap.py` 雙層引擎實作）**：於 `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` 擴充 `RoadmapItem`/`RoadmapManager`（排除 `TODO.md`、`status_filter`、`promote_roadmap`），並實作 `TodoItem`/`TodoManager`（`add_todo` 單調計數盲寫、`list_todos`、`promote_todos` 多筆原子剪切與 `--slug` 校驗）。
3. **TASK-03（`plans/` 前置源頭資產白名單與 `Seeded` 狀態）**：更新 `status.py`、`scanner.py` 與 `verifier.py`，實作 `ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}`、`Seeded` 狀態判定與 `PlanVerifier` 白名單檢核規則。
4. **TASK-04（CLI 入口、Contributes 契約與技能導流）**：更新 `scripts/cli.py`（擴充 `def roadmap`、新增 `def todo`）、`contributes/core.json`、`contributes/agents-workflow.json`，新增 `assets/skills/todo/SKILL.md` 並更新 `roadmap`、`new-plan`、`development-sop`、`discuss`、`research`、`yscb-cli-guide` 技能手冊。
5. **TASK-05（單元測試、靜態檢查與 `@build` 熱部署）**：於 `tests/test_plans_toolchain.py` 新增涵蓋 `FT-01`~`FT-06`、`ET-01`~`ET-06`、`RT-01`~`RT-02` 之自動化測試，執行 `dev check agents-workflow`、`dev test agents-workflow -q`、安裝 `agents-workflow@build --force` 並執行 `compile` 與 `release`。
6. **TASK-DOC（系統知識庫與微觀註解同步）**：更新 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`（新增 `[DN-AW-11]`）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] `PlanVerifier.get_dynamic_placeholders()` 排除 `todo.md` 動態數值標頭干擾**：
  `assets/templates/todo.md` 頂部之 `> 最後分配編號：0` 為具體數值 `0`，不含方括號佔位符；`> 更新日期：[YYYY-MM-DD]` 與 `> 模型：[平台宣告之模型名稱；無法確認填 Unknown]` 則與既有模板一致，確保動態佔位符推導 100% 相容。
- **[P04:DR-02] `promote` 伴隨 `changelog.md` 模型紀錄防回溯強制約束**：
  `RoadmapManager.promote_roadmap` 與 `TodoManager.promote_todos` 在初始化新計畫目錄之 `changelog.md` 時，強制將 CLI 傳入之 `--model`（未傳時預設 `"Unknown"`）顯式傳遞給 `PlanVerifier.append_changelog_entry(..., model=clean_model)`，絕不讀取被搬移之舊 `roadmap.md` 標頭模型。

