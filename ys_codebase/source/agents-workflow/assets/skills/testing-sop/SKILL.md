---
name: testing-sop
description: 規劃、撰寫、執行與審查專案自動化測試 (單元測試、邊界測試、整合與回歸測試)，以及對既有測試集 (tests/) 執行六維度體檢、去重與純化重構。觸發情境：定稿 P06_test_plan.md (Phase 04)、撰寫或修改測試代碼 (Phase 05 / Fast Track)、執行 Phase 06 測試驗證與回歸守門、或應開發者要求健檢與純化既有測試集。排除情境：純業務生產源碼架構設計 (改用 development-sop) 或非測試類系統知識庫文檔撰寫 (改用 documentation)。
---

# 自動化測試建置與回歸品質規範指南 (Testing SOP)

本指南定義專案自動化測試建置必遵的「六大測試鐵律」、Phase 06 品質守門清單與專案測試流程嫁接錨點。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 1. 六大自動化測試建置與回歸鐵律 (Core Test Invariants)

1. **鐵律 1：子系統 1:1 歸戶（Subsystem Alignment over Plan-Named Files）**：
   - 新增或修改測試案例時，強制依被測子系統職責歸入既有的 `test_<subsystem>.*` 擴充；**嚴禁以「單次開發計畫名稱、Bug 編號或臨時話題（如 `test_fix_xxx.py`）」新建碎片測試檔**（僅在專案新增全新獨立子系統時，方允許建立對應的子系統測試檔）。
2. **鐵律 2：實質副作用與正負雙向斷言（Substance & Negative Assertions）**：
   - **嚴禁虛假空殼測驗**：禁止將「待測目標函式自身」Mock 掉、禁止僅斷言 `assertIsNotNone(obj)` / `assertIn(rc, (0, 1))`、禁止以 `if found:` 包覆關鍵斷言在缺少檔案時靜默放行。
   - **正負雙向驗證**：每個測試必須驗證「具體輸入 $\to$ 真實邏輯調用 $\to$ 可觀測副作用（回傳值、寫盤內容、狀態遷移或底層依賴呼叫參數）」；核心功能除正向 Happy Path 外，必須包含**負向錯誤攔截測試（驗證非法輸入、損毀資料或越界存取時必定拋出預期異常或返回非零錯誤碼）**。
3. **鐵律 3：管線實機產出驗證取代靜態文檔搜尋（Pipeline Execution over Static Doc Grep）**：
   - 驗證**程式碼邏輯、CLI、編譯器、驗證器或業務管線**時，必須呼叫真實生成／編譯／檢驗函式或管線並檢查產出結構，**嚴禁在單元測試中用字串搜尋（grep）外部靜態 Markdown 規範檔取代實機執行**（*註：專門檢驗倉庫內 Markdown 資產／計畫檔標頭格式與 Frontmatter 合規性之 Meta-Linter 測試不在此限*）。
4. **鐵律 4：零歷史墓碑與舊測同步清理（Zero Tombstone & Obsolete Purge）**：
   - 重構或移除舊有 API 時，必須同步刪除或改寫對應舊測試；**嚴禁留下「僅斷言某舊方法已被刪除（如 `assertFalse(hasattr(cls, 'old_api'))`）」的歷史墓碑測試**，亦嚴禁保留測試死代碼的過時測試檔。
5. **鐵律 5：100% 狀態隔離與 `tearDown` / `try...finally` 零殘留（Zero Workspace Pollution）**：
   - 凡涉及檔案系統、設定檔、註冊表或環境變數變更之測試，必須於隔離沙盒或暫存目錄中進行，並將清理邏輯包入 `tearDown` 或 `try...finally`，確保即使斷言中途失敗，工作區與 `git status` 依然 100% 零殘留。
6. **鐵律 6：本體獨立性與零跨層反向耦合（Zero Upper-Layer Coupling）**：
   - 底層或核心模組之單元測試必須可在獨立環境下 100% 通過，嚴禁反向匯入、讀取或 `patch` 上層選配業務模組。

---

## 2. 雙情境分流工作流 (Context Routing)

- **情境 A（日常增量測試開發與 Phase 06 驗收守門）**：
  遵循上述六大鐵律與下方 Phase 06 自檢清單，於既有子系統測試檔擴充測試案例。
- **情境 B（存量測試集健檢、去重與純化大掃除）**：
  當開發者要求對既有 `tests/` 進行整體體檢、碎片檔整併或純化重構時，強制按需精讀 [references/test_suite_audit_and_purification.md](./references/test_suite_audit_and_purification.md)，依循「六大病灶掃描（`T-01`~`T-06`）$\to$ 產出歸戶映射表 Gate $\to$ 無損整併與實機全綠回歸」推進。

---

## 3. Phase 06 測試品質自檢清單 (Test Hygiene Gate)

將 `P06_test_plan.md` 標記為 `Passed` 前，強制逐項自檢確認：
- [ ] **無碎片測試檔**：本次修改與新增之測試案例皆依子系統 1:1 歸戶，無以計畫名稱或 Bug ID 命名之碎片檔案。
- [ ] **無虛假斷言**：核心斷言皆具實質副作用驗證，無空殼 `assertIsNotNone`、無 `if found:` 靜默放行、涵蓋負向異常攔截。
- [ ] **無歷史墓碑**：重構刪除的舊 API 已同步清理舊測，無殘留墓碑斷言。
- [ ] **沙盒零殘留**：跑測完畢後，`git status` 無任何暫存檔案、殘留設定目錄或未清理快取。

---

## 4. 專案特化測試流程與注意事項 (Project Testing Standards)

`__@{TESTING_SOP_STANDARDS}__`

---

## 常見踩坑指南 (Gotchas)

- **嚴禁以單次計畫名稱新建碎片測試檔**：所有新增案例必須依被測子系統職責歸戶至既有 `test_<subsystem>.*`。
- **嚴禁為求測試全綠而吞掉底層例外或降低斷言約束**：這嚴重違反「核心原則 3：零淺層敷衍公理」，將於 Phase 07 結案審查時被嚴格駁回。

