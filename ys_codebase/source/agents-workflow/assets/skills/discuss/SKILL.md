---
name: discuss
description: 針對實作或測試異常、範疇越界與契約衝突，執行 5-Whys 根因分析並產出候選修復方案討論卡。觸發情境：輸入 /discuss、同一錯誤或測試連續 2 次修復失敗、修改觸及非目標模組或破壞 Public API。
---

# 深度歸因與防淺層修復工作流 (Discuss)

本工作流為開發過程（特別是 Phase 5 實作與 Phase 6 測試）遇非預期錯誤、測試失敗或範疇越界時的**強制停手與深度歸因機制**，杜絕盲目試錯與淺層敷衍修補（Shallow Patching）。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 觸發條件與排除邊界

- **強制自動觸發條件（滿足任一即刻停手轉入本流程）**：
  1. **範疇越界（Scope Creep / Boundary Breach）**：排查時發現需修改非當前計畫承諾範圍之檔案或模組，或偏離 `P01` / `P02` 原定架構。
  2. **連續修復失敗（Two-Strike Circuit Breaker）**：針對同一報錯或測試缺陷，連續 2 次修復嘗試未通過。
  3. **破壞性變更（Breaking Change）**：修復方案將破壞 Public API 契約、既有架構或引入非預期跨模組依賴。
- **顯式觸發條件**：開發者主動輸入 `/discuss` 要求針對當前問題進行根因探討。
- **排除情境（負向邊界）**：
  - 初次遇到語法錯誤或明確的單行 Typo 且可立即精準修復時，無需觸發本流程。
  - 若為全新功能之初期 Phase 00 需求訪談，請依 [`new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 與 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`) 之 `Phase 00` 執行。

---

## [GUARD] 排查優先級：由近及遠、本體優先

排查時強制遵循以下三層優先級由近及遠排查（在未排除本體嫌疑前嚴禁越級懷疑底層框架或外部套件）：

```text
優先級 1：當前本體組件 (組件內部狀態、計算邏輯、型別轉型與邊界防護)
   ⬇ (確認本體正確後)
優先級 2：呼叫端傳參與時序 (傳遞給外部之參數、格式、單位與生命週期時序)
   ⬇ (確認傳參與時序正確後，方可懷疑外部)
優先級 3：下游/外部組件 (外部模組確有缺陷) -> 附上重現證據觸發本討論向開發者報告！
```

---

## 執行步驟

觸發本工作流時，請依序執行以下檢核步驟：

```markdown
/discuss 深度歸因檢核表：
- [ ] 步驟 1：立即停止修改程式碼，依「由近及遠」原則收集異常現場與執行 5-Whys 根因分析
- [ ] 步驟 2：擬定 2~3 種修復候選方案（含影響範疇與 Trade-off），輸出極簡討論卡並 End Turn
- [ ] 步驟 3：獲開發者決策授權後，同步更新對應計畫文件與 changelog.md，再恢復代碼實作
```

### 步驟 1：現場呈遞與 5-Whys 根因歸因 (含 Subagent 支柱一委派協定)
1. **現場證據**：立即凍結當前無效的嘗試修改，客觀記錄報錯摘要、發生檔案位置與傳參呼叫現場。
2. **5-Whys 根因**：依「本體 -> 傳參 -> 外部」順序分析架構、時序或資料狀態為何流入該錯誤分支，追溯本質根因而非表面現象。
3. **[!] 支柱一：唯讀探索隔離 (Pillar 1 Delegation)**：
   - 若排查涉及深入多模組呼叫鏈或調試日誌繁雜，可派發唯讀 Subagent 進行檔案檢索與上下文抽絲剝繭。
   - 子代理回傳嚴格限制為 150~300 Tokens（根因線索、檔案行號與證據摘要），主視窗保留純淨 Context 擬定修復方案；無子代理環境自動降級為由主視窗內聯排查。

### 步驟 2：呈遞修復方案矩陣與討論卡 (強制 End Turn)
呈遞 2~3 種具體修復方案（分析各自影響範圍與 Trade-offs）。若觸發原因為「次要衍生問題 / 範疇越界」，候選方案須對接 `AgentsStandards.md` 核心原則 3「次要衍生問題處置鐵律」之三大範疇裁定出口：① 擴充當前計畫範疇進行標準修復、② 維持當前範疇並另闢新計畫 / 子計畫、③ 登錄至 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`) 輕量待辦帳本（微觀技術債/局部打磨，獲開發者拍板後以 `todo add` 單行盲寫追加）或 [`/roadmap`](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`) 長期技術儲備（跨模組架構演進）。
對話 Session **嚴禁代碼傾倒、日誌全文傾倒或冗長論述**，強制僅呈遞以下極簡討論卡，並**立即 End Turn 等待開發者決策**：

```markdown
### [!] /discuss 深度歸因與討論卡
- **觸發原因**：[範疇越界 / 連續 2 次修復失敗 / 破壞性變更 / 開發者調用]
- **異常現場**：[錯誤訊息摘要 / 發生檔案位置]
- **5-Whys 根因**：[1~2 行客觀架構/時序根因分析]
- **修復候選方案**：
  1. **方案 A (推薦)**：[方案簡述]（影響範疇：[小/中/大]，Trade-off：[簡述]）
  2. **方案 B**：[方案簡述]（影響範疇：[小/中/大]，Trade-off：[簡述]）
- **待確認事項**：請確認採取方案 A、方案 B 或有其他指引？
```

### 步驟 3：決策固化與恢復執行
獲得開發者指示後：
1. **決策記錄**：於當前計畫之 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`) 或對應 Phase 文件登載標準 `[{Phase}:DR-XX]` 決策記錄。
2. **產物回填**：依決策影響層級同步回填完整溯源鏈：需求邊界 → `P00` / [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)；架構與 API → [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) / [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)；實作與測試 → [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) / [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) / [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)；Fast Track → [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)。
3. **恢復執行**：依共識方案恢復實作或測試推進。

---

## 常見踩坑指南 (Gotchas)

- **嚴禁以 Try-Except 吞掉例外或註解掉失敗測試來偽裝通過**：這違反「零淺層敷衍公理」，任何透過隱藏錯誤換取的表面綠燈都會在結案審查時被退回。
- **未獲開發者回覆前嚴禁偷偷先改代碼**：輸出討論卡後必須立即停手（End Turn），等待開發者選定方案 A 或 B。
