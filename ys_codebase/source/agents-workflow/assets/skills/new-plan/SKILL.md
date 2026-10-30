---
name: new-plan
description: 針對全新開發需求執行邊界訪談、6 大計畫模式 (Full Track / Fast Track / Revision / Research / Umbrella / Roadmap) 分流判定與 JIT 延遲建檔，於 `__${project://plans/}__` 產出初始化計畫目錄、首份規格檔與 changelog.md。觸發情境：輸入 /new-plan 或 /NewPlan、提出新功能開發、跨模組重構、表層修訂或專題調研立項請求 (create new development plan)。排除情境：接續已存在於 `__${project://plans/}__` 的進行中計畫（改用 continue）、盤點或推薦長期技術儲備項目（改用 roadmap）。
---

# 開立新計畫工作流 (NewPlan)

本技能提供開立新計畫的分流評估與入口引導，透過「先討論定調、後延遲建檔（JIT）」與「6 大計畫模式精準分流」，避免在需求未明前於 `__${project://plans/}__` 產生無效空殼檔案。標準開發生命週期與產物模板請直接遵循 [development-sop](../development-sop/SKILL.md)。

---

## 1. 核心原則：JIT 延遲建檔 (Just-In-Time)

- **先討論、後建檔**：在使用者需求或核心方案未經充分討論與確認前，**嚴禁提前在 `__${project://plans/}__` 下建立目錄或實體檔案**。
- **立項時序**：討論並收斂需求 $\to$ 決定分流模式 $\to$ 建立計畫目錄與雙星初始化（`P00`、`fast_track_plan.md` 或 `revision_log.md` + `changelog.md`；若為既有計畫之衍生修訂則直接於該計畫目錄建立 `revision_log.md`）。
- **[防呆 1] `Seeded` 目錄原地復用鐵律 (In-Place Seeded Directory Reuse)**：若目標計畫目錄已由 `roadmap promote` 或 `todo promote` 預先建立並置入起源種子檔（`roadmap.md` 或 `todo.md`）與 `changelog.md`（此時 `plan status` 識別為 `Seeded` 模式），**嚴禁另行建立第二個帶時間戳的新目錄**！必須直接於該既有 `Seeded` 目錄內原地補齊首份正式規格檔（`P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md`），並透過 `plan verify --log` 追加進度列。
- **立項細則指針**：建檔與分流守門細節依 [phase_00_discuss.md](../development-sop/references/phase_00_discuss.md) 執行；Umbrella 新增 `sub_XX` 時之父目錄登記規則依 [umbrella_plan.md](../development-sop/references/umbrella_plan.md) §2。

---

## 2. 計畫分流導航 (Plan Modes Routing)

依據任務變更規模與影響半徑先由下表鎖定計畫模式，再按需**單點讀取**右側對應之專屬模式手冊或技能：

| 計畫模式 | 適用情境與判定標準 | 產物與推進路徑 | 專屬模式手冊 / 技能 |
| :--- | :--- | :--- | :---: |
| **標準開發計畫 (Full Track)** | 一般新功能開發、跨模組重構、Public API 變更或修改 $> 100$ 行 | 標準 8 階段 (`P00` ~ `P07` + `changelog.md`) | [phase_00_discuss.md](../development-sop/references/phase_00_discuss.md) |
| **迅捷開發計畫 (Fast Track)** | 修改 $\le 100$ 行、Public API 0 變更、零新依賴且測試 100% 守門 | 單檔 `fast_track_plan.md` (FP-01 ~ FP-03) + `changelog.md` | [fast_track_plan.md](../development-sop/references/fast_track_plan.md) |
| **修訂計畫 (Revision Plan)** | **不牽涉核心業務邏輯**之 UI/UX/DX、靜態參數、文檔微調（支援獨立開立或衍生附掛於既有計畫；嚴禁用於 Bug Fix） | 獨立：`[P00] + [RXX] + revision_log.md + changelog.md`<br/>衍生：於原計畫/子計畫目錄建立 `revision_log.md` | [revision_plan.md](../development-sop/references/revision_plan.md) |
| **調研計畫 (Research Plan)** | 純技術選型、演算法可行性探索，支援無痛升級實作計畫 | `P00_discuss.md` + `R{NN}_{topic}.md` + `changelog.md` | [research/SKILL.md](../research/SKILL.md) |
| **分類型主計畫 (Umbrella)** | 統籌多個子計畫之大型跨模組史詩任務（最多 2 層） | 主目錄 `umbrella_overview.md` 協調多個 `sub_XX` | [umbrella_plan.md](../development-sop/references/umbrella_plan.md) |
| **長期路線圖 (Roadmap)** | 全專案層級長期技術願景與策略資產儲備 | `__${workflow.roadmap://}__` (`{topic}.md`) | [roadmap/SKILL.md](../roadmap/SKILL.md) |

---

## 3. 執行步驟與開發規範指引 (Development SOP)

```markdown
/NewPlan 立項檢核表：
- [ ] 步驟 1：釐清需求目標與影響檔案範圍（若有歧義先反問，禁止在未釐清前建檔）
- [ ] 步驟 2：依分流表判定計畫模式（Full Track / Fast Track / Revision / Research / Umbrella / Roadmap）
- [ ] 步驟 3：讀取對應標準模板，於 `__${project://plans/}__` 建立計畫目錄與首份文件（含 `> 模型：` 紀錄）
- [ ] 步驟 4：呈遞極簡狀態卡（依 development-sop 規範）並立即 End Turn 等待確認
```

開立目錄後之所有實作、產物維護與 Checkpoint 規範，請強制參閱：
👉 **[development-sop (專案標準開發流程)](../development-sop/SKILL.md)**

---

## 常見踩坑指南 (Gotchas)

- **切勿將 Bug 修復分流至 Revision 模式**：Revision 僅限非業務邏輯之表層微調；任何程式碼 Bug 修復應視修改範圍走 **Fast Track**（$\le 100$ 行且無 API 變更）或 **Full Track**。
- **建檔前務必先讀取標準模板**：建立 `P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md` 前，必須先依 [development-sop](../development-sop/SKILL.md) 模板索引讀取對應模板以保留完整標頭結構。
