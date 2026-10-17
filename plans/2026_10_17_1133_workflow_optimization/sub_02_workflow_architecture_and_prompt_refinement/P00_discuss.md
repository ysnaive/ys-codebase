# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Discussing  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Research  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「`/plans/2026_10_17_1133_workflow_optimization` 中 sub-01 處理了一些基本的邏輯缺漏，現欲建立 sub 02，專注於提示詞、流程架構上的設計而不是邏輯運行層面」、「先進行調研，從一個業務流程分析師角度，拆解當前 agents workflow 所設計之流程架構，查漏補缺，評估是否有需優化處 (僅 assets 中之原始文件，不包含當前 .agents 中的編譯輸出後文件)」、「先儲存為 R01 調研計畫後 /pause」。
- **核心目標**：以業務流程分析師（BPA）與提示詞架構師視角，針對 `ys_codebase/source/agents-workflow/assets/` 下全部 37 份原始文件進行端到端業務流程拆解與查漏補缺，固化產出 [R01_workflow_process_and_prompt_analysis.md](./R01_workflow_process_and_prompt_analysis.md)，作為後續裁定與實作升級之依據。
- **邊界排除 (Explicitly Excluded)**：
  - 僅針對 `ys_codebase/source/agents-workflow/assets/` 內之原始資產文件（Standards、Skills、References、Templates），不包含已編譯物化之 `.agents/` 輸出文件。
  - 聚焦於業務流程架構、狀態流轉閉環、模板對齊與提示詞設計，不涉及底層 Python 工具鏈運行邏輯修改。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 先以調研計畫（Research Track）開立 `sub_02_workflow_architecture_and_prompt_refinement`，將 37 份 `assets/` 原始文件之業務流程拆解與 12 項缺口盤點（`GAP-01` ~ `GAP-12`）固化為 `R01_workflow_process_and_prompt_analysis.md`（狀態：`Concluded`），並執行 `/pause` 凍結交接現場。

---

## 3. 開放議題與確認紀錄

- [ ] **Q1 調研出口與範疇確認**：確認是否採納 `R01` 盤點之 `GAP-01` ~ `GAP-12` 全數或部分項目，並由「出口 ① 立即實作」原地追加 `P01~P07` 升級為實作子計畫？
- [ ] **Q2 `handoff.md` 消費後生命週期（GAP-01）**：當 `/continue` 成功讀取 `handoff.md` 恢復斷點並開始推進下一步時，是否規定立即刪除已消費之 `handoff.md`（防止後續 `/continue` 誤讀過期快照），並明定 Umbrella 子計畫之 `handoff.md` 置於 `sub_XX/` 目錄下？
- [ ] **Q3 Umbrella 主從狀態同步與主目錄產物（GAP-02）**：是否確認 Umbrella 主目錄僅有 `umbrella_overview.md`（修正 `continue §3-U` 讀取主目錄 `P00_discuss.md` 之指令），並在 `new-plan` / `P00` 與 `P07` / `FP-03` 補齊回寫父目錄 `umbrella_overview.md` 狀態與里程碑之步驟？
- [ ] **Q4 跨軌道升級舊產物處置（GAP-03）**：Fast Track 升級 Full Track 時是否刪除或遷移原 `fast_track_plan.md`？附掛於已結案計畫之 `revision_log.md` 觸發熔斷時，是否明定「結算/回滾當前附掛修訂並另開新計畫或新 `sub_XX`」？
- [ ] **Q5 `P04` vs `P05` 任務清單去重與三層文檔表對齊（GAP-10）**：是否將可勾選之 `- [ ] TASK-XX` 收斂至 `P05_task.md` 單一載體（`P04` 專注於檔案變更矩陣、文檔衝擊、靈魂拷問與交叉驗證），並將 `P04 §2` 與 `P07 §4.1` 三層文檔表統一為 5 列（發布日誌、模組手冊、專題手冊、設計決策、微觀註解）與 `<Category>` 命名？

