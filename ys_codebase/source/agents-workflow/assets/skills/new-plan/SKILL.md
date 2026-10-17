---
name: new-plan
description: 標準開立新計畫流程 (NewPlan)。當需要開立新計畫並進行分流評估與延遲建檔時觸發。
---

# 開立新計畫工作流 (NewPlan)

本技能提供開立新計畫的分流評估與入口引導。標準開發生命週期與產物模板請直接遵循 [development-sop](../development-sop/SKILL.md)。

---

## 1. 核心原則：JIT 延遲建檔 (Just-In-Time)

- **先討論、後建檔**：在使用者需求或核心方案未經充分討論與確認前，**嚴禁提前在 `__${project://plans/}__` 下建立目錄或實體檔案**。
- **立項時序**：討論並收斂需求 $\to$ 決定分流模式 $\to$ 建立計畫目錄與雙星初始化（`P00`、`fast_track_plan.md` 或 `revision_log.md` + `changelog.md`；若為既有計畫之衍生修訂則直接於該計畫目錄建立 `revision_log.md`）。

---

## 2. 計畫分流導航 (Plan Modes Routing)

依據任務變更規模與影響半徑選擇分支，詳細規則請參閱 [plan_modes.md](../development-sop/references/plan_modes.md)：

| 計畫模式 | 適用情境 | 產物與推進路徑 |
| :--- | :--- | :--- |
| **標準開發計畫 (Full Track)** | 一般新功能開發、跨模組重構、Public API 變更或修改 $> 100$ 行 | 標準 8 階段 (`P00` ~ `P07` + `changelog.md`) |
| **迅捷開發計畫 (Fast Track)** | 修改 $\le 100$ 行、Public API 0 變更、零新依賴且測試 100% 守門 | 單檔 `fast_track_plan.md` (FP-01 ~ FP-03) + `changelog.md` |
| **修訂計畫 (Revision Plan)** | 不牽涉核心業務邏輯之 UI/UX/DX、靜態參數、文檔微調（支援獨立開立或衍生附掛於既有計畫） | 獨立：`[P00] + [RXX] + revision_log.md + changelog.md`<br/>衍生：於原計畫/子計畫目錄建立 `revision_log.md` |
| **調研計畫 (Research Plan)** | 純技術選型、演算法可行性探索，支援無痛升級實作計畫 | `P00_discuss.md` + `R{NN}_{topic}.md` + `changelog.md` |
| **分類型主計畫 (Umbrella)** | 統籌多個子計畫之大型跨模組史詩任務 | 主目錄 `umbrella_overview.md` 協調多個 `sub_XX` |
| **長期路線圖 (Roadmap)** | 全專案層級長期技術願景與策略資產儲備 | `__${workflow.roadmap://}__` (`{topic}.md`) |

---

## 3. 開發規範指引 (Development SOP)

開立目錄後之所有實作、產物維護與 Checkpoint 規範，請強制參閱：
👉 **[development-sop (專案標準開發流程)](../development-sop/SKILL.md)**
