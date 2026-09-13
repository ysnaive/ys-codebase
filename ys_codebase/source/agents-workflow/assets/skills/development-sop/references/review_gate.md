# SOP 結案審查規範手冊 (Review Gate Guide)

本手冊定義專案開發流程中的標準結案品質審查閘門（Review Gate）。位處 **P06 測試驗證** 與 **P07 成果展示** 之間（迅捷開發位處 **FT-2 實作驗證** 與 **FT-3 結案交付** 之間），為確保文檔交付、測試覆蓋與計畫合規的強制必經步驟。

---

## 1. 核心定位與觸發節點

1. **SOP 標準必經步驟**：本步驟為 SOP 標準生命週期的獨立品質閘門，非可選動作。
2. **強制連鎖觸發時機**：
   - **Full Track**：P06 自動化測試 100% 通過，且手動/UX 驗證項已與開發者確認並標註為 `[測試通過]` 或 `[跳過/免測]` 後，**強制立即進入 Review 步驟**。
   - **Fast Track**：FT-2 實作與測試通過後，**強制立即進入 Review 步驟**。
3. **[!] 守門禁令**：未完成 Review 審查並呈遞 `Review Verdict Card` 前，**絕對禁止直接產出 `P07_walkthrough.md` 或宣稱任務結案**！

---

## 2. 品質與合規審查矩陣 (Quality & Compliance Matrix)

### 2.1 三層文檔交付審查 (Documentation Delivery Audit)
- [!] **文檔更新前強制觸發技能**：在執行 Review Gate 之三層文檔核驗與更新前，**強制必須先觸發並精讀 [`documentation`](`__#{module://agents-workflow/assets/skills/documentation/SKILL.md}__`) 技能手冊**，嚴格對齊專案知識庫 7 大知識維度與作者指引。
- [ ] **宏觀發布日誌**：專案根目錄 [`CHANGELOG.md`](`__${project://CHANGELOG.md}__`) 最上方預擬或追加本次高階變更摘要。
- [ ] **中觀模組與專題手冊 (優先更新載體，嚴防 DN 膨脹)**：
  - **優先更新載體**：更新文檔時應優先從 `docs/<Category>/README.md` 模組手冊或專題手冊 (`docs/<Category>/[topic].md`) 下手更新架構、流程與功能資訊，嚴禁在 DN 一直增量！
  - **Design Notes 邊界防膨脹守門 (DN Anti-Bloat Axiom)**：`DESIGN_NOTES.md` (`DN-XX`) 僅限存放「真正高度特例、非直觀工程妥協、或從架構/專題設計文檔無法直觀看出的非直覺設計與防坑坑點」，不得作為一般架構描述、普通功能介紹或日常變更紀錄的傾倒處。
- [ ] **微觀代碼註解契約**：本次修改之 Public API 註解結構完整，複雜演算法具備 Why-Driven 動機註解。

### 2.2 測試與計畫合規檢核 (Verification & Plan Compliance)
- [ ] **自動化測試**：執行專案定義之自動化測試指令（`python __${yscb.host://yscb.py}__ dev test <mod> --quiet`）全數通過。
- [ ] **手動 / UX 驗證**：手動驗證項已獲開發者明確確認，並於 `P06_test_plan.md` 獨立標註為 `[測試通過]` 或 `[跳過/免測]`（嚴禁未測標記為已測）。
- [ ] **計畫合規性檢核**：執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>`，確認計畫文件結構完整、無殘留 HTML 註解且標頭狀態合法。

### 2.3 Commit 訊息規範 (Commit Convention)
- [ ] 採用 Conventional Commits 格式：`<type>(<scope>): <標題>`。

---

## [TOOL] 3. 即時修復與回填閉環 (Interactive Resolution Loop)

- **即時修復原則**：審查中發現任何文檔缺漏、測試未過或計畫合規偏差，**禁止僅口頭列出問題**，必須呈遞具體修復方案並立即動手修正。
- **回填閉環**：修復完成後，將審查結論與修復項目記錄於微觀日誌 [`changelog.md`](`__${project://plans/}__/{plan_name}/changelog.md`)，並供後續 P07 / FT-3 結案引用。

---

## [!] 4. SOP Review 結束 Checkpoint (Review Verdict Card)

完成審查與即時修復後，對話 Session **嚴禁傾倒全部 Checkbox 清單**，強制僅呈遞以下極簡卡片：

```markdown
### SOP Review 審查結果
- **審查結論**：[[PASS] 全數通過 / [WARN] 發現 N 項偏差已即時修復閉環]
- **核驗摘要**：
  - 文檔對齊：[CHANGELOG、docs 知識庫、代碼註解對齊完成]
  - 測試與計畫：[自動化測試 100% 通過 / UX 驗收標註完成 / 計畫合規性檢核通過]
  - 推薦 Commit：`[type(scope): brief message]`
- **下一步**：審查已通過，請問是否確認推進至 Phase 7 (P07 成果展示與結案)？
```

**立即 End Turn 等待開發者確認推進**。
