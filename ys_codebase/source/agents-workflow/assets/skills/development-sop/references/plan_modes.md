# 6 大計畫分支模式詳解 (Plan Modes & Archetypes)

本手冊詳細定義專案 6 大計畫分支的判定標準、生命週期流程、升降級守門、路徑語意規範與極精簡 Session 回覆格式。

---

## 1. 標準開發計畫 (Full Track)

- **適用場景**：單一功能重構、新增複雜模組能力、涉及 Public API 介面變更，或代碼修改行數預估 $> 100$ 行。
- **生命週期**：完整經歷 Phase 0 ➔ Phase 7 八大階段。
- **產出檔案清單**：
  - `P00_discuss.md` ➔ `P01_requirements_spec.md` ➔ `P02_architecture_plan.md` ➔ `P03_api_spec.md` ➔ `P04_implementation_plan.md` ➔ `P05_task.md` ➔ `P06_test_plan.md` ➔ `P07_walkthrough.md`
  - 微觀日誌：`changelog.md`（隨建檔初始化並逐 Phase 登記）。
- **剛性要求**：嚴禁跳過任何 Phase（除獲授權執行 [/Auto](`__#{module://agents-workflow/assets/workflows/Auto.md}__`) 連續推進外）；產出各階段文檔後，**強制僅呈遞專屬極簡卡片（嚴禁對話全文重複或傾倒）**，並立即 End Turn 等待確認。

---

## 2. 迅捷開發計畫 (Fast Track)

- **適用場景**：極小範圍修改、純內部優化或局部 Bug 修復。
- **4 大剛性守門條件（必須同時滿足）**：
  1. 代碼修改行數 $\le 100$ 行。
  2. Public API 簽名契約 0 變更（無破壞性與新增導出）。
  3. 零跨模組新依賴引入。
  4. 既有單元測試套件 100% 覆蓋守門。
- **生命週期與極精簡回覆卡**：
  - **FT-1 (規劃階段)**：確認 4 大守門清單，定義修改範圍與驗證指令，產出 `fast_track_plan.md`。
    ```markdown
    ### 📄 FT-1 迅捷計畫已落檔
    - **產出文件**：[fast_track_plan.md](__${project://plans/}__/{plan_name}/fast_track_plan.md)
    - **變更清單**：[預計修改檔案計 N 個 / 守門條件全部合規]
    - **待確認事項**：請確認 4 大守門條件無誤，是否授權進入 FT-2（編碼與驗證）？
    ```
  - **FT-2 (實作階段)**：直接編碼實作，執行單元測試並回填結果。
    ```markdown
    ### 📄 FT-2 實作與測試通過
    - **產出文件**：[fast_track_plan.md](__${project://plans/}__/{plan_name}/fast_track_plan.md)
    - **驗證摘要**：[測試 100% 通過 / 實際修改 N 行 ($\le 100$ 行)]
    - **待確認事項**：請問是否推進至 FT-3（結案交付）？
    ```
  - **FT-3 (結案階段)**：確認測試 100% 通過，追加 [`__${project://CHANGELOG.md}__`](`__${project://CHANGELOG.md}__`)，結案交付。
    ```markdown
    ### 📄 FT-3 迅捷開發已結案
    - **產出文件**：[fast_track_plan.md](__${project://plans/}__/{plan_name}/fast_track_plan.md)、[CHANGELOG.md](__${project://CHANGELOG.md}__)
    - **結案摘要**：[高階成果摘要 / 測試 100% 通過]
    - **推薦 Commit**：`[type(scope): brief message]`
    - **後續動作**：[任務已圓滿完成，可依需求執行 commit 或進行下一項任務]
    ```
- 🚨 **強制升級機制**：實作中若代碼超標（$> 100$ 行）或意外觸碰 Public API 變更，強制中斷並升級為 Full Track！

---

## 3. 修訂計畫 (Revision Plan - 短循環)

- **適用場景**：文檔校閱、極小註解同步、錯誤路徑修正、單純常數定義微調等極小範圍修訂。
- **核心優勢**：**免開立實體計畫目錄**，零額外 Markdown 文件負擔，最大化節省 Token 與專案空間。
- **生命週期與交付要求**：
  1. 原地精確修改代碼或文檔。
  2. 實機執行相關單元測試驗證（`dev test <mod> --quiet`）。
  3. 執行 `@build` 安裝與熱發布（若涉及生態系模組）。
  4. **極精簡 Session 回覆格式**：
     ```markdown
     ### 📄 Revision 修訂完成回報
     - **修改檔案**：[檔案 1](__${project://...}__)、[檔案 2](__${project://...}__)
     - **修訂摘要**：[1~2 行變更說明 / 測試驗證通過]
     - **推薦 Commit**：`[type(scope): brief message]`
     - **待確認事項**：修訂已完成，請問是否確認並進行下一項任務？
     ```

---

## 4. 調研計畫 (Research Plan - 調研 Track)

- **適用場景**：高複雜度未知技術探索、多候選方案選型評估、跨平台 API 可行性驗證。
- **生命週期與產出**：
  - `P00_discuss.md` ➔ `R01_{topic}_research.md` ➔ `changelog.md`。
- **R01 極精簡 Session 回覆格式**：
  ```markdown
  ### 📄 R01 調研報告已落檔
  - **產出文件**：[R01_{topic}_research.md](__${project://plans/}__/{plan_name}/R01_{topic}_research.md)、[changelog.md](__${project://plans/}__/{plan_name}/changelog.md)
  - **調研結論**：[1~2 行方案選型評估結論 / 推薦採納方案]
  - **推薦出口**：[出口 ① 立即實作 (升級 P01) | 出口 ② 路線圖儲備 | 出口 ③ 結案存檔]
  - **待確認事項**：請問是否採納此結論，並選擇何種流轉出口？
  ```
- **三大無痛出口轉化機制**：
  - **出口 ① 立即實作**：調研結論明確可行，原地追加 `P01~P07` 升級為實作計畫。
  - **出口 ② 技術儲備**：結論可行但當前無即時需求，轉化為 `roadmap.md` 長期路線圖儲備。
  - **出口 ③ 放棄結案**：方案不可行或成本過高，記錄原因後於 `R01` 登記結案。

---

## 5. 分類型主計畫 (Umbrella)

- **適用場景**：大型系統重構或跨模組史詩級任務，需拆解為多個 Full Track 顆粒度之子計畫進行滾動推進。
- **兩大統籌模式**：
  - **模式 A (預先規劃型 Blueprint)**：立項時已能明確拆分出全部子計畫清單（`sub_01`、`sub_02`...）。
  - **模式 B (增量演進型 Evolutionary)**：探索型大任務，先立項 `sub_01`，其餘子計畫隨開發動態滾動開立與驗收。
- **目錄結構與產出檔案**：
  - 主目錄：`__${project://plans/}__/{plan_name}/umbrella_overview.md`
  - 各子計畫目錄：`sub_01_{name}/`、`sub_02_{name}/`（各自具備獨立的 `P00~P07` 與 `changelog.md`）。
- **極精簡 Session 回覆格式**：
  ```markdown
  ### 📄 Umbrella 主計畫已開立
  - **產出文件**：[umbrella_overview.md](__${project://plans/}__/{plan_name}/umbrella_overview.md)
  - **藍圖摘要**：[規劃子計畫計 N 個 / 執行模式 (Blueprint/Evolutionary)]
  - **待確認事項**：請問是否同意主計畫藍圖，並授權啟動首個子計畫？
  ```
- 🚨 **最多兩層約束**：主計畫 ➔ 子計畫，**絕對禁止三層或更多層嵌套**。

---

## 6. 長期路線圖 (Roadmap - 策略資產庫)

- **適用場景**：全專案層級的長期技術願景、架構儲備庫與探索主題清單。
- **實體位置**：`__${workflow.roadmap://}__`（實體路徑 `__${project://plans/roadmap/roadmap.md}__`）。
- **流轉機制**：
  - 平時持續沉澱與維護技術想法。
  - 開發者調用 [/Roadmap](`__#{module://agents-workflow/assets/workflows/Roadmap.md}__`) 時，Agent 智慧探索當前代碼脈絡並推薦最適合當前專案情境之主題。
  - 獲選主題可一鍵流轉立項為 Full Track、Research 或 Umbrella 開發計畫。
