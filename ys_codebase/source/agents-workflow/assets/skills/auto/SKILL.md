---
name: auto
description: 針對已確認需求之計畫自動連續產出規格、完成代碼實作並推進至測試驗收守門。僅於顯式輸入 /auto 時觸發，嚴禁主動觸發。
---

# 自動連續推進工作流 (Auto — Lean Context Fast-Path)

本工作流用於 Full Track 或 Umbrella 子計畫處於 Phase 00 (`Confirmed`) 或 Phase 01 ~ 05 時，跳過中間人工等待點，以最小 Context 開銷連續推進至 Phase 6 手動/UX 驗證守門點。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

```markdown
/auto 精實連續推進檢核表：
- [ ] 步驟 1：定位目標計畫當前已確認階段，判定本次 `/auto` 自動生成之起始階段 `XX`（產出單一綜合檔 `P{XX}-05_auto.md`）
- [ ] 步驟 2（批次 A）：即時讀取 `PXX-05_auto.md` 模板（免讀 `phase_01~05.md`），立即寫出 `P{XX}-05_auto.md` (`In Progress`；完成 §1~§4 規格與 §5 待辦拆解 `[ ]`，中間嚴禁穿插源碼讀取工具呼叫），並於動刀前依 `BlindSubagentStandards.md` 完成 `Pre-Code Analyze Gate`（全新功能/模組或跨範疇變更優先派發盲審 Subagent 核對 `[P00:DR-XX]` 溯源、查重與專案憲法紅線）
- [ ] 步驟 3：完成源碼與單元測試實作 (`testing-sop`；全新功能/模組或橫跨多模組/多類別正交變更時，依 `BlindSubagentStandards.md` §1~§3 委派實作 Subagent)
- [ ] 步驟 4（批次 B）：即時讀取 `P06_test_plan.md` 模板，將 `P{XX}-05_auto.md` 更新為 `Completed` (勾選 `[x]` 與填寫偏差表) 並一次寫出 `P06_test_plan.md` (`Passed`)，執行單次 `plan verify` 與支柱三 Pre-UX 審查（依影響範圍門檻內聯自檢或委派盲審），輸出卡片並 End Turn
```

---

## 1. 適用情境、熔斷防線與 `P{XX}-05_auto.md` 動態區段合並鐵律

- **適用與排除邊界**：僅適用於已具 `P00_discuss.md` (`Confirmed`) 或處於 `P01`~`P05` 之 Full Track / Umbrella 子計畫；`P00` 尚在 `Discussing` 或屬 `Fast Track` 計畫時嚴禁觸發（若僅需恢復中斷現場請改用 [continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)）。
- **三大熔斷防線**：
  1. **零臆測熔斷**：需求語意或邊界存在歧義時，嚴禁腦補，立即暫停提問。
  2. **偏差熔斷**：實作或測試遭遇 Major/Critical 偏差或連續 2 次失敗時，立即轉入 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)。
  3. **P06 手動/UX 驗證絕對阻斷**：通過自動化測試與 Pre-UX 盲審後，強制停步等待開發者驗收，嚴禁自行標記 `Completed` 或進入 Phase 7。
- **[!] `/auto` 動態區段綜合產物命名鐵律 (`P{XX}-05_auto.md` Consolidated Range Rule)**：
  - 凡於 `/auto` 過程中由 Agent **自動連續生成之 `Phase {XX}` ~ `Phase 05` 規格與任務**，一律收斂為單一綜合檔案 **`P{XX}-05_auto.md`**（Agent 必須將 `XX` 替換為開始 `/auto` 之階段編號）：
    - **自 `P00` (`Confirmed`) 啟動 `/auto`**：直接產出單一 **`P01-05_auto.md`**（涵蓋 `§1 (P01)` ~ `§5 (P05)` 完整五節）。
    - **自中途階段（如人工討論至 `P02` 定案後）啟動 `/auto`**：已人工定案之 `P00`~`P02` 保持原名（`P01_requirements_spec.md`、`P02_architecture_plan.md`），後續由 `/auto` 自動生成之階段收斂為 **`P03-05_auto.md`**（僅需填寫 `§3 (P03)` ~ `§5 (P05)` 章節）。
    - **`P06_test_plan.md`**：作為人工 / UX 驗收 Checkpoint 報告，統一使用獨立檔案 `P06_test_plan.md`<!-- yscb:ignore:begin -->（`plans` 工具鏈原生相容 `P{XX}-05_auto.md`、傳統 `P01_requirements_spec_auto.md`~`P05_task_auto.md` 與標準檔名）<!-- yscb:ignore:end -->。

---

## 2. Context 精實化與兩階段 JIT 讀模板四大鐵律 (Lean & Two-Stage JIT Rules)

1. **兩階段寫檔前即時讀模板 (`Two-Stage JIT Template Read`) 與免讀 `phase_01~05.md`**：
   - 處於 `/auto` 模式時，**免除讀取 `phase_01~05.md`**（省去無效的單階段 End Turn 說明），改採**兩階段寫檔前即時讀取權威模板**以兼顧零記憶衰減與 100% 結構合規：
     - **批次 A（寫 `P{XX}-05_auto.md` 規格前與動刀前 `Pre-Code Analyze Gate`）**：即時讀取 [`PXX-05_auto.md`](`__#{module://agents-workflow/assets/templates/PXX-05_auto.md}__`) 模板<!-- yscb:ignore:begin -->（相容既有分檔模板 [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)、[`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)、[`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)、[`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)、[`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)）<!-- yscb:ignore:end -->。**讀取模板後必須立即寫出 `P{XX}-05_auto.md`（狀態標記為 `> 狀態：In Progress`，完成 `§1`~`§4` 規格契約與 `§5` 待辦任務拆解 `- [ ]`），中間嚴禁穿插源碼讀取工具呼叫**（防止中途觸發 Context Compaction 洗掉模板結構記憶導致退件重寫）。若涉及修改既有公開 API 簽名，撰寫受影響檔案清單前**必須先執行 `knowledge-db callers <Symbol>`** 確保 100% 涵蓋所有跨空間呼叫端。**寫完 `P{XX}-05_auto.md` 後、動手修改業務源碼前，強制執行一次 `Pre-Code Analyze Gate`**：凡屬**全新功能開發 (`Feature`)、新建模組／組件（非明確之局部 Bug 修復）**或**跨模組／跨 Class 正交變更**，優先遵循 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) 原型 ② / ③（套用 `§5.2` 盲眼派發模板，僅傳遞計畫目錄與規範路徑；明確局部 Bug 修復或無子代理環境則由主代理 Inline 執行）獨立核對所有 `[P00:DR-XX]` 與排除邊界皆已對齊 `§1~§5`、無重複造輪子且未違反 `AGENTS.md`（含專案特化工程規範）與 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`) 剛性紅線（若檢出憲法級衝突立即觸發熔斷修正規格或轉入 `/discuss`）。
     - **批次 B（實作與測試完成後，收尾 `P{XX}-05_auto.md` 與寫 `P06` 前）**：即時讀取 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) 模板，將 `P{XX}-05_auto.md` 狀態更新為 `Completed`（勾選 `- [x]` 並填寫實作偏差紀錄表），並一次寫出 `P06_test_plan.md` (`Passed`)。
     - **同對話跨子計畫模板免重讀豁免 (`Same-Session Template Cache Reuse`)**：若於同一對話 Session 中連續推進 Umbrella 旗下多個 `sub_XX` 子計畫，且前序子計畫已讀取過 `PXX-05_auto.md` 與 `P06_test_plan.md` 模板、中間未發生 Context Compaction 失憶，後續子計畫可直接沿用已載入 Context 之模板結構落檔，**無須於每個子計畫重複調用原生檔案讀取工具重讀階段模板**。
   - 撰寫業務源碼、測試與執行 `Phase 06` 驗證時，強制遵循 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`)、[`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 [`phase_06_test.md`](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_06_test.md}__`)（含增量微觀收斂與支柱三 Pre-UX 唯讀盲審）。
2. **規格先行兩階段落檔與單次彙總檢核 (`Spec-First & Single Batch Verify`)**：
   - **`P{XX}-05_auto.md`**：批次 A 實作前先以 `> 狀態：In Progress` 落盤鎖定規格與任務清單（`- [ ]`）；批次 B 實作完成後原地更新為 `> 狀態：Completed` 與全勾選 `- [x]`（嚴禁殘留 `[...]` 佔位符或 `<!-- ... -->` 註解）。
   - **`P06_test_plan.md`**：於測試 100% 通過後，直接以 `> 狀態：Passed` **一次建立並定稿**（§1 完整映射 `P01` 所有 `FR/EC/NFR` ID、§2 填實測 `Passed` 數據、§3 填 `UX-01` `Pending`）。
   - **單次彙總 `plan verify`**：取消 `P01`~`P05` 逐階段 CLI 檢核，於 `P06` 落檔後執行**單次**全量檢核與免讀日誌追加（確定性標頭缺漏會隨 `--log` 自動原地補齊）：
     ```bash
     python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name> --log "透過 /auto 完成 P01-05_auto.md 與 P06 規格、實作與測試驗證" --model "<ModelName>"
     ```
3. **跨節單點定義去重與禁預寫實作碼 (`DRY Spec Reference & Signature-Only`)**：
   - 於 `P{XX}-05_auto.md` 中：檔案清單單點定義於 `§2.2`；`§3.1` 僅寫 `def/class` 型別簽名與例外契約（**嚴禁預先貼入函式內部實作程式碼**）；任務拆解與勾選清單合一於 `§5.1`，免除跨節重複條列。
4. **Phase 5 實作子代理啟動界線 (`Orthogonal Scope & New Feature Subagent Gate`)**：
   - 嚴禁以硬編碼檔案數或行數常數作為機械門檻；當實作任務屬於明確之局部 Bug 修復或維持在單一模組／單一類別群組之單一職責軸線時，預設由主代理 Inline 執行。唯有當變更屬**全新功能或模組建立（非明確之局部 Bug 修復）**、或**橫跨多個模組／多個獨立類別（Classes）產生職責正交之結構性影響範圍**時，建議依據 [`phase_05_task.md`](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_05_task.md}__`) 與 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) `§1~§3`（套用 `§3.1` 標準派發訊息模板）委派 `self` 知情實作 Subagent 承擔高噪音編碼，保護主 Agent Context 預算。

---

## 3. 抵達 P06 手動/UX 驗證 Checkpoint（強制等待）

完成自動化測試、單次 `plan verify` 與支柱三 Pre-UX 唯讀冷眼盲審（`REVIEW_STATUS: PASSED`）後，對話僅呈遞以下極簡卡片並**立即 End Turn 等待確認**（後續驗收確認後唯一合法流轉節點為 [Phase 7 (P07 結案與 SOP 審查)](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_07_walkthrough.md}__`)；若轉向非業務微調則建議先 P07 結案再建 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)）：

```markdown
### 🚦 /auto 連續推進完成 (抵達 P06 驗證 Checkpoint)
- **產出文件**：[P06_test_plan.md](__${project://plans}__/{plan_name}/P06_test_plan.md) (`Passed` / 待驗收) 及 [P{XX}-05_auto.md](__${project://plans}__/{plan_name}/P{XX}-05_auto.md) (`Completed`)
- **推進摘要**：Phase {XX} ~ Phase 05 已依精實模式單次到位產出；自動化測試、單次 `plan verify` 與 Pre-UX 盲審 100% 通過
- **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
- **待確認事項**：[請確認驗收結果為 `[測試通過]` 或 `[跳過/免測]`；確認完成後將進入 Phase 7 (P07 成果展示與 SOP Review 結案)]
```

---

## 常見踩坑指南 (Gotchas)

- **切勿省略 JIT 模板讀取或未將 `XX` 替換為真實起始階段編號**：動筆寫 `P{XX}-05_auto.md`（例如 `P01-05_auto.md` 或 `P03-05_auto.md`）與 `P06_test_plan.md` 前務必即時讀取對應模板；若 `plan verify` 回報 `[TRIAGE: FULL_REWRITE]`，代表章節缺失率 $\ge 50\%$，請立即讀取提示之模板路徑並以原生檔案覆寫工具重寫。
- **切勿在 `§3` 預貼實作程式碼或重複建立 5 份零碎檔案**：嚴格落實 `Signature-Only` 與 `1-Write-Per-File`，避免無謂消耗 Output 與 Context Tokens。
