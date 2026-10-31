# 迅捷開發計畫作業手冊 (Fast Track Plan)

本手冊定義迅捷開發計畫（`Fast Track`）的適用場景、4 大剛性守門條件、3-Step 敏捷閉環生命週期、極精簡回覆卡與強制升級機制。

---

## 1. 適用場景與 4 大剛性守門條件

- **適用場景**：極小範圍修改、純內部優化或局部 Bug 修復。
- **4 大剛性守門條件（必須同時滿足）**：
  1. 代碼修改行數 $\le 100$ 行。
  2. Public API 簽名契約 0 變更（無破壞性與新增導出）。
  3. 零跨模組新依賴引入。
  4. 既有單元測試套件 100% 覆蓋守門。

---

## 2. 生命週期與極精簡回覆卡 (FP-01 ~ FP-03)

- **FP-01 (快速規劃階段)**：確認 4 大守門清單，定義修改範圍與驗證指令，產出 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)。
  ```markdown
  ###  FP-01 迅捷計畫已落檔
  - **產出文件**：[fast_track_plan.md](`__${project://plans}__/{plan_name}/fast_track_plan.md`)
  - **變更清單**：[預計修改檔案計 N 個 / 守門條件全部合規]
  - **待確認事項**：請確認 4 大守門條件無誤，是否授權進入 FP-02（編碼與驗證）？
  ```
- **FP-02 (實作與測試階段)**：**強制觸發並遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`)**（落實主幹階段管線化、零轉發殼層且嚴禁留存工單編號註解），直接編碼實作，執行單元測試並回填結果。
  ```markdown
  ###  FP-02 實作與測試通過
  - **產出文件**：[fast_track_plan.md](`__${project://plans}__/{plan_name}/fast_track_plan.md`)
  - **驗證摘要**：[測試 100% 通過 / 實際修改 N 行 ($\le 100$ 行)]
  - **下一步**：實作驗證完成，進入 FP-03 結案階段（包含 SOP Review 三層文檔與合規審查）
  ```
- **FP-03 (SOP 審查與結案階段)**：執行三層文檔核驗（CHANGELOG、docs、微觀註解）、測試 100% 通過、實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 合規檢核通過，回填結案紀錄至 `fast_track_plan.md`，追加 [`__${project://CHANGELOG.md}__`](`__#{project://CHANGELOG.md}__`)，結案交付（若為 Umbrella 子計畫，同步回寫父目錄 `umbrella_overview.md` 與主目錄 `changelog.md`）。
  ```markdown
  ###  FP-03 迅捷開發已結案
  - **產出文件**：[fast_track_plan.md](`__${project://plans}__/{plan_name}/fast_track_plan.md`)、[CHANGELOG.md](`__${project://CHANGELOG.md}__`)
  - **結案摘要**：[高階成果摘要 / 通過 SOP 審查與合規檢核 / 測試 100% 通過]
  - **推薦 Commit**：`[type(scope): brief message]`
  - **後續動作**：[任務已圓滿完成，可依需求執行 commit 或進行下一項任務]
  ```

---

## 3. 強制升級機制 (Escalation Gate)

- [!] **強制升級機制**：實作中若代碼超標（$> 100$ 行）或意外觸碰 Public API 變更，強制中斷並升級為 Full Track：將已釐清需求轉入 `P00_discuss.md` / `P01_requirements_spec.md`，**強制刪除原 `fast_track_plan.md`**（避免 `plan status` 與 `/continue` 優先匹配誤判為 Fast Track），並記錄於 `changelog.md`！

