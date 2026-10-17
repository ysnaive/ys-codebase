# 6 大計畫分支模式詳解 (Plan Modes & Archetypes)

本手冊詳細定義專案 6 大計畫分支的判定標準、生命週期流程、升降級守門、路徑語意規範與極精簡 Session 回覆格式。

---

## 1. 標準開發計畫 (Full Track)

- **適用場景**：單一功能重構、新增複雜模組能力、涉及 Public API 介面變更，或代碼修改行數預估 $> 100$ 行。
- **生命週期**：完整經歷 Phase 0 -> Phase 7 八大階段。
- **產出檔案清單**：
  - `P00_discuss.md` -> `P01_requirements_spec.md` -> `P02_architecture_plan.md` -> `P03_api_spec.md` -> `P04_implementation_plan.md` -> `P05_task.md` -> `P06_test_plan.md` -> `P07_walkthrough.md`
  - 微觀日誌：`changelog.md`（隨建檔初始化並逐 Phase 登記）。
- **剛性要求**：嚴禁跳過任何 Phase（除獲授權執行 [/auto](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`) 連續推進外）；產出各階段文檔後，**強制僅呈遞專屬極簡卡片（嚴禁對話全文重複或傾倒）**，並立即 End Turn 等待確認。

---

## 2. 迅捷開發計畫 (Fast Track)

- **適用場景**：極小範圍修改、純內部優化或局部 Bug 修復。
- **4 大剛性守門條件（必須同時滿足）**：
  1. 代碼修改行數 $\le 100$ 行。
  2. Public API 簽名契約 0 變更（無破壞性與新增導出）。
  3. 零跨模組新依賴引入。
  4. 既有單元測試套件 100% 覆蓋守門。
- **生命週期與極精簡回覆卡**：
  - **FP-01 (快速規劃階段)**：確認 4 大守門清單，定義修改範圍與驗證指令，產出 `fast_track_plan.md`。
    ```markdown
    ###  FP-01 迅捷計畫已落檔
    - **產出文件**：[fast_track_plan.md](__${project://plans/}__/{plan_name}/fast_track_plan.md)
    - **變更清單**：[預計修改檔案計 N 個 / 守門條件全部合規]
    - **待確認事項**：請確認 4 大守門條件無誤，是否授權進入 FP-02（編碼與驗證）？
    ```
  - **FP-02 (實作與測試階段)**：直接編碼實作，執行單元測試並回填結果。
    ```markdown
    ###  FP-02 實作與測試通過
    - **產出文件**：[fast_track_plan.md](__${project://plans/}__/{plan_name}/fast_track_plan.md)
    - **驗證摘要**：[測試 100% 通過 / 實際修改 N 行 ($\le 100$ 行)]
    - **下一步**：實作驗證完成，進入 FP-03 結案階段（包含 SOP Review 三層文檔與合規審查）
    ```
  - **FP-03 (SOP 審查與結案階段)**：執行三層文檔核驗（CHANGELOG、docs、微觀註解）、測試 100% 通過、實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 合規檢核通過，回填結案紀錄至 `fast_track_plan.md`，追加 [`__${project://CHANGELOG.md}__`](`__#{project://CHANGELOG.md}__`)，結案交付。
    ```markdown
    ###  FP-03 迅捷開發已結案
    - **產出文件**：[fast_track_plan.md](__${project://plans}__/{plan_name}/fast_track_plan.md)、[CHANGELOG.md](__${project://CHANGELOG.md}__)
    - **結案摘要**：[高階成果摘要 / 通過 SOP 審查與合規檢核 / 測試 100% 通過]
    - **推薦 Commit**：`[type(scope): brief message]`
    - **後續動作**：[任務已圓滿完成，可依需求執行 commit 或進行下一項任務]
    ```
- [!] **強制升級機制**：實作中若代碼超標（$> 100$ 行）或意外觸碰 Public API 變更，強制中斷並升級為 Full Track！

---

## 3. 修訂計畫 (Revision Plan - 正交修訂與留檔)

- **適用場景**：**不牽涉核心業務與控制流邏輯**之變更，包含：
  1. **UI / UX / DX 表層微調**：視覺排版優化、CLI/介面提示文案潤飾、互動回饋打磨。
  2. **靜態參數與常數調整**：Timeout 閾值、預設組態常數、靜態路徑與設定微調（零 Schema 與狀態機變更）。
  3. **文檔與註解調整**：知識庫手冊校訂、程式碼註解同步、勘誤修正。
- **[!] 4 大熔斷條件與 Bug Fix 排除原則**：
  - **4 大強制升級熔斷**：修訂過程中若觸發以下任一條件，**強制立即中斷修訂**並向開發者請示升級為 Fast Track 或 Full Track：
    1. 修改牽涉核心控制流、業務判斷或狀態機邏輯。
    2. 變更或擴充 Public API 簽名契約。
    3. 引入跨模組新依賴。
    4. 代碼修改行數超過 50 行。
  - **Bug Fix 剛性排除**：凡涉及邏輯錯誤修復 (Bug Fix)，不論代碼行數多寡，**嚴禁採用 Revision 模式**，必須開立 Fast Track 或 Full Track。
- **正交雙軌存在型態（強制實體留檔，禁止無留檔修改）**：
  1. **獨立修訂計畫（無衍生來源）**：
     - 開立獨立計畫目錄 `__${project://plans/}__/{plan_name}/`，產出 `revision_log.md` 與 `changelog.md`（若有前置討論或調研，可伴隨 `P00_discuss.md` 及/或 `R{NN}_{topic}.md`）。
     - 於 `plan status` 中 Track 模式識別為 `Revision`。
  2. **衍生/附掛於既有計畫（Full Track / Fast Track / Umbrella 主計畫或 `sub_XX` 子計畫）**：
     - 主功能完成（如進入 P07 結案後）衍生出後續微調需求時，**直接於該計畫（或子計畫）目錄內建立 `revision_log.md`**。
     - 附掛之 `revision_log.md` 隨發隨改，不干擾原計畫在 `plan status` 中的主狀態判定；在 `plan verify` 檢驗主計畫時不強制阻塞，僅於 `plan archive` 歸檔時強制檢核其已完成 (`Completed`)，確保結案無遺漏。
- **`revision_log.md` 紀錄、收斂與重開鐵律**：
  - 採用 `### [REV-01] [修訂主題簡述]` 條目結構追加。
  - **同條目多輪收斂**：若針對同一修訂主題進行多輪來回微調（例如反覆調整某表格視覺排版），**直接原地更新該 `[REV-XX]` 條目為最終變更摘要**，嚴禁將每次微調過程重複刊載為流水帳。
  - **重開與追加修訂**：已標記為 `Completed` 之既有附掛 `revision_log.md` 若後續需要再次進行修訂，允許直接重開：將標頭狀態改回 `In Progress`，追加新修訂條目 `[REV-XX]` 並記錄於計畫 `changelog.md`，完成後重新標記為 `Completed`。
- **生命週期與極精簡回覆格式**：
  1. 原地精確修改目標檔案，並建立或更新計畫目錄下之 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`) 與 `changelog.md`。
  2. 實機執行相關測試或靜態檢查驗證，並執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 確認合規。
  3. **極精簡 Session 回覆格式**：
     ```markdown
     ###  Revision 修訂紀錄已更新
     - **產出文件**：[revision_log.md](__${project://plans/}__/{plan_name}/revision_log.md)、[changelog.md](__${project://plans/}__/{plan_name}/changelog.md)
     - **修訂摘要**：[[REV-XX] 1~2 行變更說明 / 驗證與合規檢核通過]
     - **推薦 Commit**：`[type(scope): brief message]`
     - **待確認事項**：修訂已完成，請問是否繼續其他修訂或將 `revision_log.md` 標記為 `Completed` 結案？
     ```

---

## 4. 調研計畫 (Research Plan - 調研 Track)

- **適用場景**：高複雜度未知技術探索、多候選方案選型評估、跨平台 API 可行性驗證。
- **生命週期與產出**：
  - `P00_discuss.md` -> `R{NN}_{topic}.md` -> `changelog.md`。
- **R01 極精簡 Session 回覆格式**：
  ```markdown
  ###  R01 調研報告已落檔
  - **產出文件**：[R01_{topic}.md](__${project://plans/}__/{plan_name}/R01_{topic}.md)、[changelog.md](__${project://plans/}__/{plan_name}/changelog.md)
  - **調研結論**：[1~2 行方案選型評估結論 / 推薦採納方案]
  - **推薦出口**：[出口 ① 立即實作 (升級 P01) | 出口 ② 路線圖儲備 | 出口 ③ 結案存檔]
  - **待確認事項**：請問是否採納此結論，並選擇何種流轉出口？
  ```
- **三大無痛出口轉化機制**：
  - **出口 ① 立即實作**：調研結論明確可行，原地追加 `P01~P07` 升級為實作計畫。
  - **出口 ② 技術儲備**：結論可行但當前無即時需求，轉化為 `__${workflow.roadmap://}__/{topic}.md` 長期路線圖儲備。
  - **出口 ③ 放棄結案**：方案不可行或成本過高，記錄原因後於調研報告標記 `Concluded` 登記結案。

---

## 5. 分類型主計畫 (Umbrella)

- **適用場景**：大型系統重構或跨模組史詩級任務，需拆解為多個 Full Track 顆粒度之子計畫進行滾動推進。
- **兩大統籌模式**：
  - **預先規劃型 (Pre-planned Blueprint)**：立項時已能明確拆分出全部子計畫清單（`sub_01`、`sub_02`...）。
  - **增量演進型 (Incremental Evolutionary)**：探索型大任務，先立項 `sub_01`，其餘子計畫隨開發動態滾動開立與驗收。
- **目錄結構與產出檔案**：
  - 主目錄：`__${project://plans/}__/{plan_name}/umbrella_overview.md`
  - 各子計畫目錄：`sub_01_{name}/`、`sub_02_{name}/`（各自具備獨立的 `P00~P07` 與 `changelog.md`）。
- **極精簡 Session 回覆格式**：
  ```markdown
  ###  Umbrella 主計畫已開立
  - **產出文件**：[umbrella_overview.md](__${project://plans/}__/{plan_name}/umbrella_overview.md)
  - **藍圖摘要**：[規劃子計畫計 N 個 / 執行模式 (Pre-planned/Incremental)]
  - **待確認事項**：請問是否同意主計畫藍圖，並授權啟動首個子計畫？
  ```
- [!] **最多兩層約束**：主計畫 -> 子計畫，**絕對禁止三層或更多層嵌套**。

---

## 6. 長期路線圖 (Roadmap - 策略資產庫)

- **適用場景**：全專案層級的長期技術願景、架構儲備庫與探索主題清單。
- **實體位置**：`__${workflow.roadmap://}__`（每個主題一檔 `{topic}.md`）。
- **流轉機制**：
  - 平時持續沉澱與維護技術想法。
  - 開發者調用 [/roadmap](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`) 時，Agent 智慧探索當前代碼脈絡並推薦最適合當前專案情境之主題。
  - 獲選主題可一鍵流轉立項為 Full Track、Research 或 Umbrella 開發計畫。
