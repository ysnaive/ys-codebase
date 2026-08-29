`__@{DYNAMIC_CONTEXT_MAP}__`

# 開發完成後審查工作流 (Review)

本工作流用於功能實作完成後（通常於 Phase 7 Walkthrough 結束後或發布/結案前），進行獨立且嚴格的品質稽核、五維度品質矩陣驗收與即時修復閉環。所有階段的執行規範請嚴格遵循 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🚀 執行步驟

### 步驟 1：五維度品質與規範審查矩陣 (Five Quality Pillars)

#### 1. 程式碼品質與清潔度
- [ ] **無殘留 Debug 代碼**：所有臨時性的 print/console/debug log 已清除。
- [ ] **無死代碼**：無大段被註解掉的廢棄代碼。
- [ ] **命名與封裝**：命名符合專案規範，封裝邊界清楚。
- [ ] **物理/數學單位**：具體物理或數學變數顯式標註 `_{unit}` 單位後綴，且無同名覆蓋中轉。

#### 2. 日誌與安全性
- [ ] **關鍵進入點與重要狀態**：核心介面有適當的 Info / Debug 日誌。
- [ ] **錯誤與異常處置**：錯誤邊界有 Warning / Error 日誌並附帶上下文資訊。
- [ ] **高頻防衛**：嚴禁在每影格循環項目 (Update / Render / Calculate) 頻繁記錄日誌。

#### 3. 知識庫 1:1 交付與文檔審查 (Knowledge Base Delivery Audit)
- [ ] **三維錨點對齊**：對照 [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)、[`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) 與 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)，確認所有公開介面、協同機制、狀態機、資料管線與工程妥協已全數覆蓋。
- [ ] **中觀專題手冊 (Topic Docs)**：若涉及 3 個以上狀態轉移、通訊封包、資料管線或並發同步，已建立獨立 `workflow.docs://<Module>/[topic].md`（垂直 Mermaid TD + 轉移矩陣）。
- [ ] **工程妥協登記**：若實作包含非直觀設計或 Workaround，已於 `workflow.docs://<Module>/DESIGN_NOTES.md` 登記 `DN-XX` 與 `[!CAUTION]`。
- [ ] **模組 README 同步**：`workflow.docs://<Module>/README.md` 已補齊最新 API 簽名與快速上手範例。
- [ ] **全域發布日誌**：專案根目錄 [CHANGELOG.md](`__#{project://CHANGELOG.md}__`) 最上方已追加本次變更摘要。

#### 4. 驗證與測試覆蓋
- [ ] 自動化測試或 CLI 編譯 100% 通過（附帶日誌紀錄）。
- [ ] 人工 / UX / 實機驗證已獲得開發者明確確認。
- [ ] **計畫合規性檢核**：已實機調用 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>`，確認計畫所有文件結構完整、無殘留 HTML 註解且標頭狀態合法。

#### 5. Commit 訊息規範
- [ ] 採用 Conventional Commits 格式：`<type>(<scope>): <標題>`，簡潔且資訊完整。

---

### 步驟 2：即時互動修復與回填閉環 (Interactive Resolution Loop)

- **非單純報錯**：若審查中發現任何代碼瑕疵、文檔缺漏或規範偏差，Agent **絕對禁止僅僅列出問題就結束**！
- **即時修復**：Agent 必須呈遞具體修復方案，與開發者即時討論並動手修正。
- **回填閉環**：修復完成後，將審查結論與偏差紀錄同步寫入 [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) 與 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)。

---

`__@{WORKFLOW_REVIEW}__`
