# 開發完成後審查工作流 (Review)

本工作流用於功能實作完成後（通常於 Phase 7 Walkthrough 結案前），進行具體可驗證的品質稽核（文檔交付、測試覆蓋、計畫合規與 Commit 規範）與即時修復閉環。執行規範遵循 [NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🚀 執行步驟

### 步驟 1：品質與合規審查矩陣 (Quality & Compliance Matrix)

#### 1. 三層文檔交付審查 (Documentation Delivery Audit)
- [ ] **宏觀發布日誌**：專案根目錄 [`CHANGELOG.md`](`__${project://CHANGELOG.md}__`) 最上方已追加本次高階變更摘要。
- [ ] **中觀模組與專題手冊**：`__${project://docs/}__<Category>/` 模組手冊、專題手冊已同步更新；若有工程妥協已於 `DESIGN_NOTES.md` 登記 `DN-XX`。
- [ ] **微觀代碼註解契約**：本次修改之 Public API 註解結構完整，複雜演算法具備 Why-Driven 動機註解。

#### 2. 測試與計畫合規檢核 (Verification & Plan Compliance)
- [ ] **自動化測試**：執行專案定義之自動化測試指令全數通過。
- [ ] **手動 / UX 驗證**：若有待手動驗證項，已獲開發者明確確認。
- [ ] **計畫合規性檢核**：執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>`，確認計畫文件結構完整、無殘留 HTML 註解且標頭狀態合法。

#### 3. Commit 訊息規範 (Commit Convention)
- [ ] 採用 Conventional Commits 格式：`<type>(<scope>): <標題>`。

---

### 步驟 2：即時互動修復與回填閉環 (Interactive Resolution Loop)

- **即時修復**：審查中發現任何文檔缺漏、測試未過或計畫合規偏差，禁止僅列出問題，必須呈遞修復方案並立即動手修正。
- **回填閉環**：修復完成後，將審查結論記錄於 [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) 與 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)。

---

### 步驟 3：極精簡 Session 回覆格式 (Review Verdict Card)

完成審查與即時修復後，對話 Session **嚴禁傾倒全部 Checkbox 清單**，強制僅呈遞以下極簡卡片並結束當前 Turn：

```markdown
### 📋 /Review 審查結果
- **審查結論**：[✅ 全數通過 / ⚠️ 發現 N 項偏差已即時修復閉環]
- **核驗摘要**：
  - 文檔對齊：[CHANGELOG、docs 知識庫、代碼註解對齊完成]
  - 測試與計畫：[自動化測試 100% 通過 / 計畫合規性檢核通過]
  - 推薦 Commit：`[type(scope): brief message]`
- **回填產物**：[P07_walkthrough.md](__${project://plans/}__/{plan_name}/P07_walkthrough.md)、[changelog.md](__${project://plans/}__/{plan_name}/changelog.md)
- **待確認事項**：審查已完成，請問是否同意結果並進行結案 Commit？
```

---

`__@{WORKFLOW_REVIEW}__`
