# Phase 6: 測試驗證與品質驗收 (P06 Test Guide)

本手冊定義 Phase 6 測試執行、回填規範、UX 驗收 Checkpoint 守門、業務測試與表層修訂分界引導及盲目修補阻斷鐵律。

```markdown
Phase 06 執行檢核表：
- [ ] 1. [!] 強制觸發 testing-sop 技能手冊與 CodeQualityStandards.md，落實六大測試鐵律與代碼品質自檢
- [ ] 2. 守門 ①（子系統回歸全綠）：執行新增測試與被修改子系統之全量回歸套件（100% 通過）
- [ ] 3. 守門 ②（測試反模式與增量 Diff 微觀無損收斂自檢）：無計畫名碎片檔、無空殼斷言、無歷史墓碑、無 S2 殘留轉發殼或 FR/DR 工單註解、跑測後 git status 零殘留
- [ ] 4. 將實測數據與通過狀態客觀回填至 P06_test_plan.md，標頭狀態設為 Passed
- [ ] 5. 更新 changelog.md，呈遞 P06 測試驗證回報卡並立即 End Turn 等待開發者驗收
```

---

## 1. 核心定位與職責

- **強制觸發 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與遵循 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`)**：執行 Phase 06 驗證前，強制精讀並遵循 `testing-sop` 之六大測試鐵律與 `CodeQualityStandards.md` 之結構衛生規範。
- **雙重驗收守門機制（Dual Acceptance Gates）**：
  1. **守門 ①（子系統回歸全綠）**：除本次新增案例外，強制跑過被修改子系統之完整回歸測試（100% Passed）。
  2. **守門 ②（新增測試反模式自檢與增量 Diff 微觀無損收斂 — Red-Green-Refactor）**：嚴查無碎片測試檔、無虛假空殼斷言、無歷史墓碑、工作區零污染；並在全綠測試保護傘下，依 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`) 對本次 `git diff` 變更範圍執行快速微觀收斂（消除本次新增之結構重複 `S3`、壓平深層巢狀 `S4`、拔除 1 行轉發殼 `S2` 與工單編號註解）。
- **專注業務功能與邏輯正確性測試**：100% 依據 `P06_test_plan.md` 執行自動化測試與回歸測試，驗證核心業務邏輯、API 契約與邊界條件 (`FT/ET/RT`)，客觀回填測試日誌。
- **人工 / UX 驗收守門**：若包含人機介面、CLI 輸出或終端交互變更，強制等待開發者驗收確認。
- **業務功能測試 vs. 表層修訂主動分流引導**：當核心業務功能已無問題，而反饋轉向非業務邏輯微調時，主動引導先完成 P07 結案再開啟 `revision_log.md` 修訂。
- **阻斷盲目修補**：測試失敗時遵守排查階層與 5-Whys 根因溯源。

---

## 2. 測試執行與回填鐵律

1. **自動化測試與回歸驗證**：
   - 實機執行專案定義之單元測試、邊界測試與全量回歸測試套件。
2. **測試紀錄客觀回填**：
   - 在 `P06_test_plan.md` 之「測試執行紀錄表」如實填寫執行狀態（`Passed` / `Failed`）、執行時間與關鍵日誌摘要。
3. **部署/構建後免重複測試鐵律**：
   - 通過測試並完成本地部署或物化同步後，**嚴禁無意義重複調用相同測試套件跑測**。
4. **支柱三：唯讀 Fresh-Eyes 冷眼盲審協定左移 (Pillar 3 Pre-UX Blind Review Delegation)**：
   - **審查左移時機**：在完成自動化跑測、**即將向開發者提出手動 / UX 測試驗證請求前**，強制派發無偏誤的 Reviewer Subagent 進行客觀審查，打破主視窗近因確認偏誤（球員兼裁判）。無子代理環境自動降級為由主視窗內聯冷靜自檢。
   - **零劇透盲審傳址鐵律 (Zero-Spoiler Blind Pass-by-Reference)**：**不應告知子代理本次計畫實作內容，僅可提供計畫路徑由子代理進行探索**。主視窗派發提示詞時，嚴禁摘要、提示或劇透已修改之檔案清單與實作細節，避免引發提示詞錨定偏誤（Confirmation Bias）。
   - **純靜態唯讀審查禁令 (Static Read-Only Inspection Only)**：**應明確告知子代理嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查**（嚴禁在子代理內重複執行測試指令、建置部署或啟動任何運行進程），且嚴守 Single-Writer 鐵律禁碰 `plans/` 下任何檔案。
   - **Untracked 新檔自主探索防護**：Reviewer 透過計畫路徑自行讀取 `P01`/`P03`/`P04` 規格文件，搭配版本控制狀態（如 `git status --short` 與 `git diff HEAD`），對未加入 index 之 `Untracked (??)` 新建檔案直接以唯讀工具檢視全文，杜絕漏審新建檔案。
   - **防吹毛求疵三類硬性審查契約**：Reviewer 僅允許回報違反下列三類硬性契約之具體缺失：
     1. 違反 `AGENTS.md` 核心原則 3 之淺層敷衍修補（如空白 `except` 吞錯誤、無意義 mock、放寬斷言）、違反 `testing-sop` 六大測試鐵律（如新建計畫名碎片測試檔、空殼斷言、歷史墓碑）或違反 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`) 之結構紅線（如殘留 `S2` 1 行轉發殼、`S3` 合併抹平 20% 邊界不變量、或生產代碼殘留 `FR/DR/EC` 工單編號註解）；
     2. `P01` 功能/邊界需求或 `P03` 介面契約未落實之遺漏；
     3. 程式碼 Docstring 或架構契約遺漏。
     *嚴禁回報主觀命名或排版微調；若無上述硬性缺失，強制直接回傳 `REVIEW_STATUS: PASSED`。*
   - **UX 請求守門**：必須在 Subagent 審查通過（`REVIEW_STATUS: PASSED`）或主視窗修正缺失後，方可向開發者呈遞 UX 驗證請求，確保代碼架構與測試在人工驗收前已 100% 健全，杜絕事後返工。

---

## [!] 3. 人工 / UX 驗證 Checkpoint 與「先結案、後修訂」主動分流引導

1. **人工驗證 (`UX-{XX}`) 守門**：
   - **嚴禁 Agent 自行標記為通過**。
   - Agent 必須呈遞驗證方法與預期效果，明確詢問開發者並 **立即 End Turn 等待回饋**。
   - **手動/UX 驗收狀態二元標記規範**：
     - 開發者回覆結果必須精確區分並於表格中獨立標記：
       1. **`[測試通過]`**：開發者完成實機/UX 操作且效果符合預期。
       2. **`[跳過/免測]`**：開發者指示免測、環境受限或非核心項目暫緩測試。
     - **防呆禁令**：**嚴禁將 `[跳過/免測]` 標記為 `[測試通過]` 或籠統標為 Passed**；兩者必須於文件與日誌中獨立清晰標記，杜絕未來查檔時誤判！
   - **意圖邊界約束**：開發者回覆「免測」或「驗收通過」**僅代表確認 P06 測試守門完成**，絕不包含「授權正式發布」之意圖。
2. **[!] 業務核心收斂 vs. 表層修訂 (`revision_log.md`) 主動提問鐵律**：
   - Phase 6 專注於**業務功能與邏輯行為驗證**。
   - 當開發者在 P06 期間**不再反饋邏輯 Bug、功能缺失或錯誤行為**，反而開始要求微調 **UI/UX/DX（如排版、提示文案）、靜態參數或文檔**等不牽涉核心業務邏輯的內容時：
     - **Agent 必須主動向開發者提問確認**：「請問核心業務功能是否已確認無問題？是否要先進入 Phase 7 (P07) 完成 SOP Review 與結案交付後，再於本計畫建立 `revision_log.md` 進行後續修訂？」
     - 藉此避免無止境的非業務微調卡住主功能結案管線，同時確保後續打磨透過 `revision_log.md` 結構化留檔。

---

## [GUARD] 4. 除錯排查與防淺層修復 (Anti-Blind Patching)

- **本體優先階層**：排查錯誤優先排查當前組件內部邏輯與傳參，未排除自身問題前禁止深入下游外部模組。
- **連續失敗阻斷**：同一問題連續 2 次修復失敗或破壞 API 簽名時，**強制停手發起 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`) 進行 5-Whys 根因分析**。

`__@{PHASE06_AGENTS_GUIDE}__`

---

## [!] 5. Phase 6 結束 Checkpoint

- 自動化測試 100% Passed，全系統回歸 100% Passed。
- `P06_test_plan.md` 狀態更新為 **`Passed`**（待手動/UX 驗收；待驗收確認完成後方轉為 `Completed`），並更新 `changelog.md`。
- **極精簡 Session 回覆格式**：對話中**嚴禁全文重複、日誌傾倒或冗長轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ###  P06 測試驗證回報
  - **產出文件**：[P06_test_plan.md](`__${project://plans}__/{plan_name}/P06_test_plan.md`) (Passed / 待驗收)
  - **測試摘要**：[單元/邊界測試 N 項 100% 通過 / 全量回歸 100% 通過]
  - **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
  - **待確認事項**：[若有 UX 項請確認結果為 [測試通過] 或 [跳過/免測]；確認後將進入 Phase 7 (P07 結案與 SOP Review 審查)]
  ```
- **立即 End Turn 等待確認**。
- **接續推進硬性約束**：P06 驗收確認後的唯一合法流轉節點為 **Phase 7 (P07 結案與 SOP 審查)**（請由 `development-sop/SKILL.md` §5 導航矩陣讀取對應手冊）。P07 內化三層文檔核驗與 plan verify 合規檢核，確認 100% Passed 後方可結案（若結案後有 UI/UX/DX、參數或文檔微調需求，則於同計畫建立 `revision_log.md` 接續修訂）！
