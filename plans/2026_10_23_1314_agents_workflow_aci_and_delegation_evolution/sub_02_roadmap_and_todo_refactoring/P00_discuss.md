# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：落實 [roadmap.md](./roadmap.md) 與主計畫調研報告 [R01_cli_command_specification.md](../R01_cli_command_specification.md) §3.2 定義之雙層儲備體系（Tier 1 `/todo` 集中式輕量待辦帳本 `plans/roadmap/TODO.md` + Tier 2 `/roadmap` 策略路線圖專題檔 `plans/roadmap/{topic}.md`）、單行免讀盲寫 `todo add`、立項物理遷入 (`Consume-on-Promote`: `roadmap promote` / `todo promote`)，以及 `plans/` 內前置源頭背景資產 (`Seeded` 狀態與 `roadmap.md` / `todo.md` 白名單) 機制。
- **核心目標**：
  1. **Tier 1 輕量待辦帳本 (`TODO.md` 與 `todo` 命令群)**：新增 `assets/templates/todo.md` 模板；實作 `todo add "<title>" [--scope "<scope>"] [--note "<note>"] [--model "<ModelName>"]`（免讀檔盲寫、基於頂部 `> 最後分配編號：N` 與現有最大編號之單調遞增計數器 `[TODO-XX]`）、`todo list [--scope "<keyword>"]`（唯讀檢索列表）與 `todo promote <todo_ids...> --slug <ascii_slug> [--model "<ModelName>"]`（支援單筆或多筆原子剪切拔除 Pop，遷入新建 `plans/YYYY_MM_DD_HHMM_{slug}/todo.md` 並初始化伴隨 `changelog.md`）。
  2. **Tier 2 策略路線圖專題檔 (`{topic}.md` 與 `roadmap` 命令群擴充)**：升級 `assets/templates/roadmap.md`（新增 `> 目標範疇：` 與 `> 前置解鎖條件：`，狀態收斂為 `Backlog | Proposed | Ready | Deferred`）；於 `roadmap [list]` 擴充 `--status <val>` 過濾並自動排除 `TODO.md`；實作 `roadmap promote <topic> [--model "<ModelName>"]`（將 `plans/roadmap/{topic}.md` 物理搬移 `shutil.move` 至新建 `plans/YYYY_MM_DD_HHMM_{topic}/roadmap.md` 並初始化伴隨 `changelog.md`）。
  3. **前置源頭背景資產白名單 (`Seeded` 狀態與檢核豁免)**：擴充 `PlanScanner` (`scanner.py`)、`PlanStatusResolver` (`status.py`) 與 `PlanVerifier` (`verifier.py`)，將計畫目錄下的 `roadmap.md` 與 `todo.md` 視為前置源頭背景資產（Origin Seed Assets）——當目錄僅含 `roadmap.md` / `todo.md`（及 `changelog.md`）時判定為 `Seeded` 狀態，後續建立 `P00` / `fast_track_plan` / `revision_log` 後即以主體開發文件判定進度，且 `PlanVerifier` 豁免對計畫目錄內 `roadmap.md` / `todo.md` 的 `Completed` 終態強制要求與模板章節鏡像檢查。
  4. **雙技能極致精簡契約與中樞導流**：新增主動指令型技能 `assets/skills/todo/SKILL.md`、收斂 `assets/skills/roadmap/SKILL.md` 描述契約，並更新 `new-plan/SKILL.md`（`Seeded` 目錄原地復用防呆）、`development-sop/SKILL.md`、`discuss/SKILL.md`、`research/SKILL.md` 與 `yscb-cli-guide/SKILL.md` 導流說明。
- **邊界排除 (Explicitly Excluded)**：
  - 不於本子計畫處理 `testing-sop` 技能與 Subagent 三支柱隔離協定（屬 `sub_03` 範疇）。
  - 不於本子計畫提前遷移主計畫與生態系主計畫正在消費中的 14 份 Roadmap 專題檔（留待 `ecosystem/sub_05` 與 `agents-workflow/sub_06` 結案驗收時透過本子計畫建置之 `roadmap promote` 閉環遷移）。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py`（擴充 `RoadmapManager` 與新增 `TodoManager` / `promote` 邏輯）
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/{scanner.py,status.py,verifier.py}`（`roadmap.md` / `todo.md` 前置資產白名單與 `Seeded` 狀態支援）
  - `ys_codebase/source/agents-workflow/scripts/cli.py` 與 `contributes/core.json`（擴充 `roadmap` 並新增 `todo` 頂層命令與子命令分發）
  - `ys_codebase/source/agents-workflow/assets/templates/{todo.md,roadmap.md}` 與 `assets/skills/{todo,roadmap,new-plan,development-sop,discuss,research,yscb-cli-guide}/SKILL.md`
  - `ys_codebase/source/agents-workflow/tests/`（新增雙層儲備與 `Seeded` 白名單單元測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 雙層儲備粒度拆分與立項物理遷入 (`Consume-on-Promote`)**：
  將日常輕量待辦集中於 `plans/roadmap/TODO.md`（Tier 1），大型跨模組架構藍圖維持 `plans/roadmap/{topic}.md`（Tier 2）。立項時透過 `todo promote`（原子剪切 Pop 為 `todo.md`）或 `roadmap promote`（物理搬移 `shutil.move` 為 `roadmap.md`）遷入新計畫目錄並自動建立 `changelog.md`，使 `plans/roadmap/` 永遠保持 100% 純淨未立項狀態，結案時隨計畫目錄自動歸檔。
- **[P00:DR-02] `TODO.md` 單調遞增編號計數器與多筆打包立項防呆**：
  於 `TODO.md` 頂部 Header 維護 `> 最後分配編號：N`（不使用 HTML 註解以符合 `PlanVerifier` 規範），每次 `todo add` 取 `max(N, 現有最大編號) + 1` 分配新 `[TODO-XX]` 並回寫 Header，杜絕條目拔除後的歷史 ID 碰撞；`todo promote` 支援一次傳入多個 `TODO-ID` 並強制校驗 `--slug` 符合 `^[a-z0-9_]+$`。
- **[P00:DR-03] 當輪 `--model` 參數隔離與 `Seeded` 目錄原地復用鐵律**：
  `todo add`、`todo promote` 與 `roadmap promote` 產生或更新檔案（含伴隨 `changelog.md`）時，模型欄位一律採用當輪傳入之 `--model`（未傳預設 `Unknown`），嚴禁繼承舊 `{topic}.md` 的歷史模型名稱；且於 `new-plan` 與 CLI 輸出明確規範 `Seeded` 計畫目錄必須原地復用，嚴禁重複新建第二個時間戳資料夾。
- **[P00:DR-04] `PlanScanner` / `PlanStatusResolver` / `PlanVerifier` 前置源頭資產白名單**：
  計畫目錄內的 `roadmap.md` 與 `todo.md` 定義為「前置源頭背景資產（Origin Seed Assets）」。當目錄下尚無 `P00`~`P07`、`fast_track_plan.md`、`revision_log.md`、`umbrella_overview.md` 或 `RXX_*.md` 時，計畫狀態回報為 `Seeded`，`plan status --resume` 提示於該目錄原地建立初始開發文件；一旦主體開發文件建立，進度判定完全由主體文件主導，且 `PlanVerifier` 不對計畫目錄內的 `roadmap.md` / `todo.md` 執行模板標題鏡像或 `Completed` 狀態強制檢查。

---

## 3. 開放議題與確認紀錄

- 所有 CLI 簽名、防呆機制與跨階段全局執行順序均已於前置調研 [R01_cli_command_specification.md](../R01_cli_command_specification.md) 及 [roadmap.md](./roadmap.md) 確認定案，無未決開放議題。

