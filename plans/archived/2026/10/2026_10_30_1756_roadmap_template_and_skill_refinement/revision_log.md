# 修訂紀錄書 (Revision Log)

> 功能名稱：2026_10_30_1756_roadmap_template_and_skill_refinement  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] `roadmap.md` 模板輕量化與 `/roadmap` 技能抽象敘述規範優化
- **修訂類別**：Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/templates/roadmap.md`
  - `ys_codebase/source/agents-workflow/assets/skills/roadmap/SKILL.md`
  - `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py`
  - `ys_codebase/source/agents-workflow/tests/test_roadmap.py`
  - `plans/roadmap/gui_kit_declarative_host_module.md`
- **修訂摘要**：
  1. **模板輕量化與移除硬湊方案表格 (`roadmap.md` v1.1)**：刪除舊版強制要求之「候選架構方案對比」、「多維度綜合可行性評估（方案 A/B/C）」、`### 1.2 現況與影響範圍評估` 與 `bash` 落地步驟區塊；參考 `RXX` / `P00` 設計概念改為高寬容度之 3 大抽象章節（`## 1. 背景與長期願景`、`## 2. 抽象架構原則與核心設計概念`、`## 3. 解鎖條件與演進構想`）。
  2. **`/roadmap` Skill 強制抽象敘述與去現況耦合**：於 `roadmap/SKILL.md` 明定近期具體工作歸入 `/todo`，`plans/roadmap/` 專責收錄非近期執行之長期藍圖；強制以類 `P00` 抽象概念與架構不變量敘述，嚴禁混雜非強耦合之當前代碼實作現況，並嚴禁虛構無用的陪跑方案。
  3. **摘要提取相容與 `gui_kit` 路線圖同步**：擴充 `roadmap.py` 首章節正則以同時支援新版 `## 1. 背景與長期願景` 與舊版 `## 1. 問題陳述`，並將 `plans/roadmap/gui_kit_declarative_host_module.md` 對齊至新模板。
- **驗證結果**：執行 `dev check agents-workflow`、`dev test agents-workflow -q`、本機 `@build` 熱部署與 `agents-workflow release` 二層物化同步驗證。

### [REV-02] 拆分單體 `plan_modes.md` 為按需單點載入之獨立模式手冊（方案 A）
- **修訂類別**：Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/fast_track_plan.md`（新增）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/revision_plan.md`（新增）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/umbrella_plan.md`（新增）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/plan_modes.md`（移除）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/new-plan/SKILL.md`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py`
  - `ys_codebase/source/agents-workflow/tests/test_compiler.py`
- **修訂摘要**：
  1. **廢除單體 `plan_modes.md` 並拆分為 3 份無獨立 Skill 之專屬模式手冊**：將原本涵蓋 6 大模式之 156 行單體 `references/plan_modes.md` 移除；僅為無專屬 Skill 的 3 種輕量軌道建立獨立參考檔 `fast_track_plan.md`（39 行）、`revision_plan.md`（50 行）、`umbrella_plan.md`（33 行），而 `Full Track`、`Research`、`Roadmap` 則直接路由至既有 `phase_00_discuss.md`、`research/SKILL.md` 與 `roadmap/SKILL.md`，消除重複描述並節省每次讀取約 70%~80% 的非目標模式 Token。
  2. **分流表與 `plan status` 按需指標同步**：更新 `development-sop/SKILL.md` §4、`new-plan/SKILL.md` §1~§2 分流表連結，並同步更新 `plans/status.py` (`resolve_next_action`) 中 `Umbrella`、`Fast Track`、`Revision`、`Research` 的 `required_reference_path` 精確指向各模式專屬手冊。
- **驗證結果**：執行 `dev check agents-workflow`、`dev test agents-workflow -q`（136/136 通過）、本機 `@build` 熱部署與 `plan verify` 驗證通過。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 docs/ 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 CHANGELOG.md。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

