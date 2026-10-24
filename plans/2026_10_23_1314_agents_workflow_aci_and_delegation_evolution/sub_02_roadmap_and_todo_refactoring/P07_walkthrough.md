# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **雙層儲備治理體系（Tier 1 `/todo` 輕量待辦帳本 + Tier 2 `/roadmap` 策略路線圖）**：
     - 新增 `assets/templates/todo.md` 模板與 `TodoManager`（`todo add` 免讀盲寫追加並維護頂部 `> 最後分配編號：N` 單調遞增計數器、`todo list [--scope]` 唯讀檢索、`todo promote <ids...> --slug <slug> [--plan <dir>]` 單筆/多筆原子剪切拔除立項）。
     - 升級 `assets/templates/roadmap.md`（收斂狀態為 `[Backlog | Proposed | Ready | Deferred]`，新增 `> 目標範疇：` 與 `> 前置解鎖條件：`）與 `RoadmapManager`（自動排除 `TODO.md`、支援 `roadmap [list] --status <val>`、實作 `roadmap promote <topic> [--plan <dir>] [--model <Model>]` 物理搬移 `shutil.move` 並隔離歷史模型）。
  2. **`plans/` 前置源頭資產白名單 (`ORIGIN_SEED_FILES`) 與 `Seeded` 狀態機**：
     - 於 `PlanStatusResolver`、`PlanScanner` 與 `PlanVerifier` 將計畫目錄內之 `roadmap.md` 與 `todo.md` 列為前置源頭資產；未建立正式規格檔前判定為 `Seeded` 狀態並引導原地復用目錄，建立 `P00` / `fast_track_plan.md` / `revision_log.md` 後自動切換為主體進度，並豁免 `roadmap.md` / `todo.md` 之子計畫 `> 所屬主計畫：` 與動態標題鏡像強制檢核。
  3. **技能體系與 CLI 合約同步**：
     - 新增 `assets/skills/todo/SKILL.md` 並更新 `roadmap`、`new-plan`（`[防呆 1] Seeded 目錄原地復用鐵律`）、`development-sop`、`discuss`、`research`、`yscb-cli-guide` 技能與 `contributes/{core,agents-workflow}.json`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/assets/templates/todo.md` | New | 新增 Tier 1 輕量待辦帳本標準模板 |
| `ys_codebase/source/agents-workflow/assets/templates/roadmap.md` | Modify | 新增 `> 目標範疇：`、`> 前置解鎖條件：` 並收斂狀態枚舉 |
| `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Modify | 實作 `TodoItem`、`TodoManager` (`add_todo`, `list_todos`, `promote_todos`, `normalize_todo_id`) 與 `RoadmapManager.promote_roadmap` |
| `ys_codebase/source/agents-workflow/agents_workflow/__init__.py` | Modify | 頂層匯出 `RoadmapManager`, `RoadmapItem`, `TodoManager`, `TodoItem` |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | 新增 `ORIGIN_SEED_FILES` 與 `Seeded` 階段領航 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Modify | 新增 `Seeded` / `Seeded (Pending Plan)` 狀態識別 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 新增 `ORIGIN_SEED_FILES` 白名單豁免與 `VALID_STATUSES` 擴充 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | 實作 `roadmap_list`, `roadmap_promote`, `todo_add`, `todo_list`, `todo_promote`, `todo` 入口 |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 註冊 `todo` 命令群並擴充 `roadmap` 參數與選項 |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 導出 `todo` 技能、`todo.md` 模板並同步 `roadmap` 描述 |
| `ys_codebase/source/agents-workflow/assets/skills/todo/SKILL.md` | New | 新增 `/todo` 輕量待辦與技術債管理技能手冊 |
| `ys_codebase/source/agents-workflow/assets/skills/{roadmap,new-plan,development-sop,discuss,research,yscb-cli-guide}/SKILL.md` | Modify | 同步雙層儲備分流、`Consume-on-Promote` 與 `Seeded` 原地復用防呆 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `sub_02` 雙層儲備與 `Seeded` 白名單完整單元與邊界測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` | Modify | 對齊 `roadmap.md` 狀態枚舉與 13 項技能集合驗證 |
| `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` | Modify | 同步中觀架構手冊、操作指南與 `[DN-AW-11]` 防坑筆記 |
| `CHANGELOG.md` | Modify | 登載 `sub_02_roadmap_and_todo_refactoring` 結案發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev check agents-workflow` `PASSED`；`python yscb.py dev test agents-workflow -q` 全套 **129/129 (100.0%)** 測試通過（含新增 `FT-01`~`FT-06`、`ET-01`~`ET-06`、`RT-01`~`RT-02`）。
- **實機 UX / 人工驗證**：`UX-01` `[測試通過]`（完成 `@build` 熱部署與 51 份資產發布，實機驗證 `todo list`、`roadmap --status Ready` 與 `plan verify --all` 並完成反向延伸檢閱）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [CHANGELOG.md](../../../CHANGELOG.md) | 已更新 | 新增 `sub_02_roadmap_and_todo_refactoring` 雙層儲備與 `Seeded` 白名單發布紀錄 |
| **中觀 (Meso)** | [docs/agents-workflow/README.md](../../../docs/agents-workflow/README.md) | 已更新 | 更新 13 項技能、16 份模板、雙層儲備與 `todo` / `roadmap` CLI 速查 |
| **中觀 (Meso)** | [docs/agents-workflow/user_guide.md](../../../docs/agents-workflow/user_guide.md) | 已更新 | 更新 §1.1 `Seeded` 狀態識別與 §1.5 雙層技術儲備 (`roadmap` & `todo`) 操作指南 |
| **中觀 (Meso)** | [docs/agents-workflow/DESIGN_NOTES.md](../../../docs/agents-workflow/DESIGN_NOTES.md) | 已更新 | 新增 `[DN-AW-11]` 記錄 `Consume-on-Promote`、`> 最後分配編號：N` 防碰撞與 `ORIGIN_SEED_FILES` 豁免設計 |
| **微觀 (Micro)** | `roadmap.py`, `status.py`, `scanner.py`, `verifier.py`, `cli.py` | 已更新 | 完整維護 Public API Docstring 與型別契約 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow): implement dual-tier todo/roadmap backlog and consume-on-promote lifecycle (sub_02)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

