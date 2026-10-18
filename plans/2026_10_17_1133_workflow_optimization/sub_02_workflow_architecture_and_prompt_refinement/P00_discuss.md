# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「`/plans/2026_10_17_1133_workflow_optimization` 中 sub-01 處理了一些基本的邏輯缺漏，現欲建立 sub 02，專注於提示詞、流程架構上的設計而不是邏輯運行層面」、「先進行調研，從一個業務流程分析師角度，拆解當前 agents workflow 所設計之流程架構，查漏補缺，評估是否有需優化處 (僅 assets 中之原始文件，不包含當前 .agents 中的編譯輸出後文件)」、「先對 R01 提出之各觀點，派送子代理驗證其真實性、修改之必要性」、「同意，進入 P01」。
- **核心目標**：以業務流程分析師（BPA）與提示詞架構師視角，針對 `ys_codebase/source/agents-workflow/assets/` 下原始資產文件進行端到端業務流程拆解與查漏補缺，經雙子代理獨立審計事實查核與工具鏈相容性驗證後，由「出口 ① 立即實作」原地升級為 Full Track 實作子計畫，完成流程閉環與提示詞優化。
- **邊界排除 (Explicitly Excluded)**：
  - 僅針對 `ys_codebase/source/agents-workflow/assets/` 內之原始資產文件（Standards、Skills、References、Templates）及對應測試驗收，不手動直接修改 `.agents/` 物化產物。
  - 剔除會造成常駐 Token 膨脹與雙重維護之過度設計（排除 `GAP-06` 新增 7 列工作流路由表、排除 `GAP-07` 於 `new-plan` 重寫步驟化長文、排除在 `P01`/`P03` 模板盲目新增必填 `##` 章節）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 先以調研計畫（Research Track）開立 `sub_02_workflow_architecture_and_prompt_refinement`，將 37 份 `assets/` 原始文件之業務流程拆解與 12 項缺口盤點（`GAP-01` ~ `GAP-12`）固化為 `R01_workflow_process_and_prompt_analysis.md`（狀態：`Concluded`），並執行 `/pause` 凍結交接現場。
- **[P00:DR-02]** 派送 2 位獨立調研子代理對 `R01` 之 `GAP-01` ~ `GAP-12` 進行真實性（對照 `scanner.py` / `verifier.py` / `archiver.py` / `roadmap.py`）與修改必要性審計，確認由「出口 ① 立即實作」原地升級為 Full Track 子計畫：
  1. **必改納入（8 項）**：`GAP-09`（移除 `context-init` 殘留首行模型錨點指令）、`GAP-01`（`handoff.md` 消費後即刻刪除與子計畫路徑對齊，並同步確認歸檔清理）、`GAP-02`（Umbrella 主從狀態連動、補列主目錄 `changelog.md`、修正 `continue §3-U` 主目錄 `P00` 誤讀）、`GAP-03`（跨軌道升級舊產物刪除/回滾 SOP 與 Roadmap `Completed` 狀態閉環）、`GAP-04`（`P07` / `fast_track_plan` / `revision_log` 之 `plan verify` 結案守門時序調換）、`GAP-08`（`/discuss` 次要問題三大出口與完整回填清單）、`GAP-10`（`P04` 與 `P05` 任務清單去重、`P04` 與 `P07` 三層 5 列文檔表與 `<Category>` 對齊）、`GAP-12`（`/auto` P06 寫入合併與 `yscb-cli-guild` 三級權限定義及標籤對齊）。
  2. **精簡化納入（2 項）**：`GAP-05`（僅定義各階段檔案落檔預設標頭狀態，`P01~P04` 落檔即 `Confirmed`、`changelog.md` 固定 `Active`/`In Progress` 免結案回寫，零額外 I/O）、`GAP-11`（於 `P00`/`P01`/`P03` 既有章節內對齊欄位，**嚴禁新增必填 `##` 章節**以免觸發 `verifier` 強迫造假；移除 `P00 §3` 預設 `- [ ]`；通用化 `roadmap.md §1.2`）。
  3. **排除過度設計（2 項僅做單行微調）**：`GAP-06` 不在 `AgentsStandards.md §2` 新增 7 列（僅於 `development-sop` 欄括號附註一句）；`GAP-07` 維持 `new-plan/SKILL.md` 輕量入口（僅在 §1 補單行跳轉 `phase_00_discuss.md` 指針）。

---

## 3. 開放議題與確認紀錄

- [x] **Q1 調研出口與範疇確認**：經子代理獨立驗證後，採納上述精簡後範疇（`[P00:DR-02]`），由「出口 ① 立即實作」原地升級為 Full Track 進入 `P01`。
- [x] **Q2 `handoff.md` 消費後生命週期（GAP-01）**：確認採用「消費後即刻刪除 (`Consume & Delete`)」，並明定 Umbrella 子計畫之 `handoff.md` 置於 `sub_XX/` 目錄下。
- [x] **Q3 Umbrella 主從狀態同步與主目錄產物（GAP-02）**：確認主目錄必備產物為 `umbrella_overview.md` + `changelog.md`（修正 `continue §3-U`），並補齊子計畫立項/結案回寫父目錄 `umbrella_overview.md` 與主目錄 `changelog.md` 之步驟。
- [x] **Q4 跨軌道升級舊產物處置（GAP-03）**：確認 Fast Track 升級 Full Track 時須刪除原 `fast_track_plan.md`；附掛於已結案計畫之 `revision_log.md` 觸發熔斷時須結算/回滾並另開新計畫或新 `sub_XX`。
- [x] **Q5 `P04` vs `P05` 任務清單去重與三層文檔表對齊（GAP-10 & GAP-11）**：確認將 `- [ ] TASK-XX` 唯一收歸 `P05_task.md`（`P04 §4` 改為無 Checkbox 之檔案變更與順序預排），統一 `P04 §2` 與 `P07 §4.1` 為三層 5 列文檔表與 `<Category>` 命名，且 `P00/P01/P03` 於既有章節內對齊而不新增必填 `##` 標題。

