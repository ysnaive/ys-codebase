# Phase 5: 任務實作與編碼紀律 (P05 Task Guide)

本手冊定義 Phase 5 編碼實作階段之任務編排、空間隔離鐵律、代碼註解規範與實作偏差處置標準。

```markdown
Phase 05 執行檢核表：
- [ ] 1. 讀取 P05_task.md 模板，依 P04 建立 [TASK-XX] 實作任務清單
- [ ] 2. 依序完成源碼實作、補齊 Docstring 與單元測試，每完成一項即勾選 P05_task.md 對應任務
- [ ] 3. 如實記錄任何 Minor 偏差（若遇 Major/Critical 偏差立即依矩陣暫停或轉 /discuss）
- [ ] 4. 將 P05_task.md 狀態更新為 Completed、更新 changelog.md，呈遞狀態卡並立即 End Turn
```

---

## 1. 核心定位與職責

- **依序實作**：依據 `P04` 依賴拓撲建立 `P05_task.md`，並逐一實作代碼與測試。
- **文檔同步交付**：將中觀手冊與微觀註解列為一等公民任務同步交付，嚴禁後補。
- **偏差即時留痕**：任何與原計畫不符的改動必須嚴格分級處置。

---

## 2. 空間隔離與代碼規範鐵律

1. **源碼空間唯一 SSOT**：
   - 所有代碼修改 **100% 必須在專案源碼空間進行**，嚴禁手動直接修改部署運行端、第三方依賴目錄或編譯中介產物。
2. **公開介面註解保護 (Docstring Preservation)**：
   - 重構或新增 Public API 時，**嚴禁刪減或破壞標準介面註解結構**（說明、傳參、回傳與例外規範）。
3. **意圖導向行內註解 (Why-Driven Comments)**：
   - 凡涉及非直觀演算法、邊界補償或特定常數，行內註解必須記錄「為什麼這樣做 (Why)」，嚴禁僅複述語法操作 (What)。
4. **動作前置技能調用與測試連鎖觸發**：
   - 編輯源碼、執行測試或維護文檔前，須依專案規範調用對應之專屬技能，不可省略。
   - **撰寫或修改自動化測試腳本前，強制先觸發並遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)**，嚴格落實實質副作用斷言與 `tearDown` / `try...finally` 沙盒零殘留清理。
5. **Subagent 支柱二委派協定（受限讀寫實作隔離）**：
   - **門檻判定**：當處於 `/auto` 模式進入 Phase 05/06，或 `P05_task.md` 含 $\ge 3$ 個跨模組獨立任務組時，依耦合度按「單一任務或高內聚任務組（Cohesive Task Group）」**強制每次僅序列派發 1 個 Subagent**（嚴禁平行改碼；`Fast Track`、`Revision` 或 $\le 2$ 個簡單任務維持主視窗直行以規避 Token 入場稅；若運行環境不支援子代理則自動降級為主視窗內聯執行）。
   - **路徑傳址（Pass-by-Reference）**：主視窗傳遞 `P03_api_spec.md`、`P04_implementation_plan.md`、`P05_task.md` 目標 `[TASK-XX]` 與必讀 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 路徑指針。
   - **二振失敗熔斷（2-Strike Limit）**：Subagent 內部跑測遇錯最多自主嘗試修復 2 次，第 2 次仍失敗立即停手回傳 `STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)` 交主視窗轉入 `/discuss`。
   - **Single-Writer 鐵律與 5 行結構化回傳格式**：Subagent 嚴禁建立或修改 `plans/` 下任何檔案（嚴守單層星型拓撲，禁止遞迴派發子代理），僅回傳 150~300 Tokens 之 5 行結構化狀態摘要（`STATUS: <COMPLETED | MINOR_DEVIATION | MAJOR_BLOCKER | CRITICAL_BLOCKER>`、`TASK`、`MODIFIED_FILES`、`TEST_OUTCOME`、`DEVIATION_OR_BLOCKER_NOTE`），由主視窗統一更新 `P05_task.md` 與 `changelog.md`。

---

## [WARN] 3. 實作偏差三級處置矩陣 (Deviation Matrix)

| 偏差等級 | 判定條件 | 處置行動 |
| :--- | :--- | :--- |
| [!] **Critical** | 需求越界、架構翻盤、破壞全域相容性 | **強制中斷實作**，發起 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`) 進行 5-Whys 根因分析，退回 P00/P01 重新定稿。 |
| [WARN] **Major** | 局部 API 簽名微調、新增模組內部依賴 | **暫停推進**，於當前 Turn 呈報開發者確認同意後再行修改。 |
| ℹ️ **Minor** | 內部區域變數重命名、演算法非介面層微調 | 自主修正，並於 `P05_task.md` 之「實作偏差紀錄表」登記備查。 |

`__@{PHASE05_AGENTS_GUIDE}__`

---

## [!] 4. Phase 5 結束 Checkpoint

- 所有 `TASK-XX` 與 `TASK-DOC` 均標記為完成 `[x]` 並通過專案語法與靜態合規檢查。
- **極精簡 Session 回覆格式**：產出 `P05_task.md` 並更新 `changelog.md` 後，對話中**嚴禁全文重複、代碼傾倒或冗長轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ###  P05 任務實作已完成
  - **產出文件**：[P05_task.md](__${project://plans/}__/{plan_name}/P05_task.md)
  - **實作摘要**：[完成 TASK 計 N 項、文檔同步 N 項 / 靜態檢查通過 / 偏差處置說明]
  - **待確認事項**：實作已完成，請問是否推進至 Phase 6（測試驗證）？
  ```
- **立即 End Turn 等待確認**：嚴禁跨階段連續產出。

