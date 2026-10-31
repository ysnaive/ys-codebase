# 修訂計畫作業手冊 (Revision Plan - 正交修訂與留檔)

本手冊定義修訂計畫（`Revision Plan`）的適用場景、4 大強制升級熔斷條件、正交雙軌存在型態、`revision_log.md` 收斂與重開鐵律，以及極精簡回覆格式。

---

## 1. 適用場景與 4 大熔斷條件

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
  - **熔斷後舊產物雙軌處置**：
    - **獨立修訂計畫**：將內容轉入同目錄新軌道檔案，刪除未完成之 `revision_log.md` 或將已完成項標記 `Completed` 結算。
    - **附掛於既有已結案計畫之修訂觸發熔斷**：嚴禁在原已結案目錄塞入 `fast_track_plan.md` 或 `P01~P07`；須將已完成表層微調於 `revision_log.md` 標記 `Completed` 結算或回滾刪除，再另開新計畫或新 `sub_XX`。
  - **Bug Fix 剛性排除**：凡涉及邏輯錯誤修復 (Bug Fix)，不論代碼行數多寡，**嚴禁採用 Revision 模式**，必須開立 Fast Track 或 Full Track。

---

## 2. 正交雙軌存在型態與紀錄鐵律

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

---

## 3. 生命週期與極精簡回覆格式

1. 原地精確修改目標檔案，並建立或更新計畫目錄下之 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`) 與 `changelog.md`。
2. 實機執行相關測試或靜態檢查驗證，並執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 確認合規。
3. **極精簡 Session 回覆格式**：
   ```markdown
   ###  Revision 修訂紀錄已更新
   - **產出文件**：[revision_log.md](`__${project://plans}__/{plan_name}/revision_log.md`)、[changelog.md](`__${project://plans}__/{plan_name}/changelog.md`)
   - **修訂摘要**：[[REV-XX] 1~2 行變更說明 / 驗證與合規檢核通過]
   - **推薦 Commit**：`[type(scope): brief message]`
   - **待確認事項**：修訂已完成，請問是否繼續其他修訂或將 `revision_log.md` 標記為 `Completed` 結案？
   ```

