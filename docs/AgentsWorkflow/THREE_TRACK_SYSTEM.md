---
target: "Modules/AgentsWorkflow/ThreeTrackSystem"
doc_type: "topic"
status: "active"
source_paths:
  - "source/agents-workflow/workflows/NewPlan.md"
  - "source/agents-workflow/workflows/templates/FT_plan.md"
  - "source/agents-workflow/workflows/templates/umbrella_overview.md"
related_docs:
  - "./README.md"
last_updated: "2026-08-22"
---

# 三大分流管控體系 (Three-Track System)

在 `NewPlan.md` 中，所有開發任務在完成 **Phase 0 語意需求確認 (`P00_semantic_requirements.md`)** 後，必須依任務規模與風險評估分流至合適的管控層級：

---

## 🚦 三大分流矩陣

| 分流層級 | 適用規模 | 產出文檔規範 | Checkpoint 控管點 |
| :--- | :--- | :--- | :--- |
| **Level 0: Fast Track (FT)** | 小修復、小優化、單一函式調整（估計 1~2 檔案變更） | 單一文檔 `FT_plan.md`（合併需求、設計、測試與驗收） | FT-1 設計確認 ➔ 實作 ➔ FT-6 測試驗證 |
| **Level 1: Full Track** | 標準功能開發、模組重構、API 變更 | 完整生命週期留痕：`P01` (需求) $\rightarrow$ `P02` (架構) $\rightarrow$ `P03` (API) $\rightarrow$ `P04` (實作) $\rightarrow$ `P06` (測試) $\rightarrow$ `P07` (Walkthrough) | 每個 Phase 結束後強制 End Turn 等待確認 |
| **Level 2: Umbrella 主計畫** | 跨子系統大型架構演進、多階段複合功能 | 主目錄 `umbrella_overview.md` + 多個子目錄 `sub_01_xxx/`, `sub_02_xxx/`（各子計畫獨立執行 FT 或 Full Track） | 主架構協調 Checkpoint + 各子計畫獨立 Checkpoint |

---

## 🚨 核心防呆鐵律 (Guardrails)

1. **嚴禁連發**：單次 Turn 最多執行一個 Phase，產出後強制 End Turn。
2. **「問答 $\neq$ 推進」防呆條款**：開發者回答問題僅代表解答，**絕不等於同意推進下一階段**。必須接收到明確推進指令才可前進。
3. **嚴禁空降實作**：未經 Checkpoint 核准前，絕對禁止編寫原始碼。
4. **Test-First 前置定稿**：`P06_test_plan.md` 必須於 Phase 4 與實作計畫同步定稿。
5. **無 Log 視同未驗證**：Phase 6 測試若無實機執行 Log，嚴禁標記 Passed。
