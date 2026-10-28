---
name: auto
description: 針對已確認需求之計畫自動連續執行規格產出、代碼實作與測試驗證。僅於顯式輸入 /auto 或明確指示自動連續推進計畫時觸發。
---

# 自動連續推進工作流 (Auto — Lean Context Fast-Path)

本工作流用於 Full Track 或 Umbrella 子計畫處於 Phase 00 (`Confirmed`) 或 Phase 01 ~ 05 時，跳過中間人工等待點，以最小 Context 開銷連續推進至 Phase 6 手動/UX 驗證守門點。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

```markdown
/Auto 精實連續推進檢核表：
- [ ] 步驟 1：定位目標計畫當前已確認階段，判定本次 `/auto` 自動生成之起訖階段 (附加 `_auto.md` 後綴)
- [ ] 步驟 2：批次 A 即時讀取 `P01`~`P04` 模板 (免讀 `phase_01~05.md`)，單次到位寫出 `P01`~`P04` (`*_auto.md`)
- [ ] 步驟 3：完成源碼與單元測試實作 (`testing-sop`；符合規模門檻時委派實作 Subagent)
- [ ] 步驟 4：批次 B 即時讀取 `P05` & `P06` 模板，一次寫出 `P05_task_auto.md` (`Completed`) 與 `P06_test_plan.md` (`Passed`)，執行單次 `plan verify` 與支柱三 Pre-UX 盲審，輸出卡片並 End Turn
```

---

## 1. 適用情境、熔斷防線與 `_auto.md` 專屬命名鐵律

- **適用與排除邊界**：僅適用於已具 `P00_discuss.md` (`Confirmed`) 或處於 `P01`~`P05` 之 Full Track / Umbrella 子計畫；`P00` 尚在 `Discussing` 或屬 `Fast Track` 計畫時嚴禁觸發（若僅需恢復中斷現場請改用 [continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)）。
- **三大熔斷防線**：
  1. **零臆測熔斷**：需求語意或邊界存在歧義時，嚴禁腦補，立即暫停提問。
  2. **偏差熔斷**：實作或測試遭遇 Major/Critical 偏差或連續 2 次失敗時，立即轉入 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)。
  3. **P06 手動/UX 驗證絕對阻斷**：通過自動化測試與 Pre-UX 盲審後，強制停步等待開發者驗收，嚴禁自行標記 `Completed` 或進入 Phase 7。
- **[!] `/auto` 一次寫入產物專屬後綴命名鐵律 (`PXX_YYYY_auto.md` Provenance Rule)**：
  - 凡於 `/auto` 過程中由 Agent **自動連續生成之 `Phase 01` ~ `Phase 05` 規格與任務檔**，檔名強制附加 `_auto` 後綴，以明確區隔「人工逐步定案文件 (`PXX_YYYY.md`)」與「自動連續產出文件 (`PXX_YYYY_auto.md`)」：
    - **自 `P00` (`Confirmed`) 啟動 `/auto`**：`P01`~`P05` 全數命名為 `P01_requirements_spec_auto.md`、`P02_architecture_plan_auto.md`、`P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`。
    - **自中途階段（如人工討論至 `P02` 定案後）啟動 `/auto`**：已人工定案之 `P00`~`P02` 保持原名，後續由 `/auto` 自動生成之階段命名為 `P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`。
    - **`P06_test_plan.md`**：作為人工 / UX 驗收 Checkpoint 報告，統一使用 `P06_test_plan.md`（`plans` 工具鏈原生雙軌相容原名與 `_auto.md` 後綴）。

---

## 2. Context 精實化與兩階段 JIT 讀模板四大鐵律 (Lean & Two-Stage JIT Rules)

1. **兩階段寫檔前即時讀模板 (`Two-Stage JIT Template Read`) 與免讀 `phase_01~05.md`**：
   - 處於 `/auto` 模式時，**免除讀取 `phase_01~05.md`**（省去無效的單階段 End Turn 說明），改採**寫檔前最後一刻平行讀取權威模板**以兼顧零記憶衰減與 100% 結構合規：
     - **批次 A（寫 `P01`~`P04` 前即時平行讀取）**：動筆寫規格前，平行讀取 [P01](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)、[P02](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)、[P03](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)、[P04](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) 模板（僅需讀取本次尚未產出之階段）；**讀取模板後必須立即連續寫出 `P01`~`P04_auto.md`，中間嚴禁穿插源碼讀取工具呼叫**（防止中途觸發 Context Compaction 洗掉模板結構記憶導致退件重寫）。此外，若涉及修改既有公開 API 簽名，撰寫 `P02` §3 受影響檔案清單前**必須先執行 `knowledge-db callers <Symbol>`** 確保 100% 涵蓋所有跨空間呼叫端。
     - **批次 B（Phase 5 實作與測試通過後、寫 `P05` & `P06` 前即時平行讀取）**：完成源碼與自動化測試後，平行讀取 [P05](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) 與 [P06](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) 模板，隨即一次寫出 `P05_task_auto.md` 與 `P06_test_plan.md`。
     - **同對話跨子計畫模板免重讀豁免 (`Same-Session Template Cache Reuse`)**：若於同一對話 Session 中連續推進 Umbrella 旗下多個 `sub_XX` 子計畫，且前序子計畫已讀取過 `P01`~`P06` 模板、中間未發生 Context Compaction 失憶，後續子計畫可直接沿用已載入 Context 之模板結構落檔，**無須於每個子計畫重複調用原生檔案讀取工具重讀 `.agents/.yscb/templates/*`**。
   - 撰寫測試與執行 `Phase 06` 驗證時，強制遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 [`phase_06_test.md`](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_06_test.md}__`)（含支柱三 Pre-UX 唯讀盲審）。
2. **單檔單次到位寫入與單次彙總檢核 (`1-Write-Per-File & Single Batch Verify`)**：
   - **`P01`~`P04` (`*_auto.md`)**：直接以 `> 狀態：Confirmed` 一次建立並定稿（嚴禁殘留 `[...]` 佔位符或 `<!-- ... -->` 註解）。
   - **`P05_task_auto.md`**：完成實作後，直接以 `> 狀態：Completed` 與全勾選 `- [x]` **一次性寫入落檔**（嚴禁先寫 `In Progress` 再二次 Edit）。
   - **`P06_test_plan.md`**：於測試 100% 通過後，直接以 `> 狀態：Passed` **一次建立並定稿**（§1 完整映射 `P01` 所有 `FR/EC/NFR` ID、§2 填實測 `Passed` 數據、§3 填 `UX-01` `Pending`）。
   - **單次彙總 `plan verify`**：取消 `P01`~`P05` 逐階段 CLI 檢核，於 `P06` 落檔後執行**單次**全量檢核與免讀日誌追加（確定性標頭缺漏會隨 `--log` 自動原地補齊）：
     ```bash
     python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name> --log "透過 /auto 完成 P01~P06 規格、實作與測試驗證" --model "<ModelName>"
     ```
3. **跨檔單點定義去重與禁預寫實作碼 (`DRY Spec Reference & Signature-Only`)**：
   - 檔案清單單點定義於 `P02` §3；`P03` §2 僅寫 `def/class` 型別簽名與例外契約（**嚴禁在 `P03` 或 `P04` 預先貼入函式內部實作程式碼**）；任務拆解單點定義於 `P04` §4，`P05_task_auto.md` §1 每項僅寫 1 行指標（全文 $\le 25$ 行）。
4. **Phase 5 實作子代理量化啟動門檻 (`Implementation Subagent Threshold`)**：
   - 當 `P04` §4 實作任務滿足「**預估修改或整併 $\ge 5$ 個檔案**」或「**預估需展開閱讀與修改 $> 1,500$ 行源碼/測試**」時，建議依據 [`phase_05_task.md`](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_05_task.md}__`) 委派 `self` 實作 Subagent 承擔高噪音編碼與測試修補迴圈，保護主 Agent Context 預算。

---

## 3. 抵達 P06 手動/UX 驗證 Checkpoint（強制等待）

完成自動化測試、單次 `plan verify` 與支柱三 Pre-UX 唯讀冷眼盲審（`REVIEW_STATUS: PASSED`）後，對話僅呈遞以下極簡卡片並**立即 End Turn 等待確認**（後續驗收確認後唯一合法流轉節點為 [Phase 7 (P07 結案與 SOP 審查)](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_07_walkthrough.md}__`)；若轉向非業務微調則建議先 P07 結案再建 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)）：

```markdown
### 🚦 /Auto 連續推進完成 (抵達 P06 驗證 Checkpoint)
- **產出文件**：[P06_test_plan.md](__${project://plans}__/{plan_name}/P06_test_plan.md) (`Passed` / 待驗收) 及 `P01`~`P05` (`*_auto.md`)
- **推進摘要**：Phase 01 ~ Phase 05 已依精實模式單次到位產出；自動化測試、單次 `plan verify` 與 Pre-UX 盲審 100% 通過
- **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
- **待確認事項**：[請確認驗收結果為 `[測試通過]` 或 `[跳過/免測]`；確認完成後將進入 Phase 7 (P07 成果展示與 SOP Review 結案)]
```

---

## 常見踩坑指南 (Gotchas)

- **切勿省略兩階段 JIT 模板讀取或遺漏 `_auto.md` 後綴**：動筆寫 `P01`~`P04_auto.md` 與 `P05_task_auto.md`/`P06_test_plan.md` 前務必即時平行讀取對應模板；若 `plan verify` 回報 `[TRIAGE: FULL_REWRITE]`，代表章節缺失率 $\ge 50\%$，請立即讀取提示之模板路徑並以原生檔案覆寫工具重寫。
- **切勿在 `P03`/`P04` 預貼實作程式碼或對 `P05`/`P06` 重複寫檔**：嚴格落實 `Signature-Only` 與 `1-Write-Per-File`，避免無謂消耗 Output 與 Context Tokens。
