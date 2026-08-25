---
description: 開發完成後品質與細節審查工作流 (Review) — 包含 verify 定式掃描、全量 Extension 雙重稽核與即時修復閉環
---

# 開發完成後審查工作流 (Review)

本工作流用於功能實作完成後（通常於 Phase 7 Walkthrough 結束後或發布/歸檔前），進行獨立且嚴格的品質稽核、定式腳本驗收、全量 Extension 深度稽核與即時修復閉環。

---

## 🚀 執行步驟

### 步驟 1：執行定式計畫驗收工具 (Deterministic Tooling)

優先呼叫專案定式驗證工具，秒級完成 Header 元數據與 Extension 格式合規性掃描：
```bash
python yscb_cli.py agents-workflow verify
```
- 若腳本回報格式錯誤（例如 Header 欄位缺失、`> 擴充項目：` 遺漏），優先進行修復。

---

### 步驟 2：全量 Extension 雙重深度稽核 (Extension Deep Audit)

Agent 主動呼叫定式指令或遍歷擴充目錄（`sop_ext://` 或 `yscb://source/agents-workflow/workflows/extensions/`）：
```bash
# 檢視專案所有可用 Extension 清單與觸發模式
python yscb_cli.py agents-workflow ext list

# 檢視指定 Extension 完整內容與 Checklist
python yscb_cli.py agents-workflow ext show <extension_name>
```

執行雙重比對：
1. **常態觸發 (`trigger: always`) 檢查**：
   - 檢查對應 Phase 的 Header `> 擴充項目：` 是否已宣告該 extension 名稱。
   - 檢查正文是否包含該 extension 的執行結果表格。
2. **語意化觸發 (`trigger: on_demand`) 檢驗**：
   - 檢視本次 Dev Plan 的實作範疇（例如：是否修改了通訊協定、持久化層、渲染底層或日誌系統）。
   - 判斷是否踩中任何 on-demand extension 的語意條件；若符合但先前遺漏執行，**立即在此階段攔截並補做該 Checklist**。

---

### 步驟 3：五維度品質與規範審查矩陣 (Five Quality Pillars)

#### 1. 程式碼品質與清潔度
- [ ] **無殘留 Debug 代碼**：所有臨時性的 print/log 已清除。
- [ ] **無死代碼**：無大段被註解掉的廢棄代碼。
- [ ] **命名與封裝**：命名符合專案 [docs://_project/STANDARDS.md](docs://_project/STANDARDS.md)，成員變數 `m_`/`s_`/`k_` 前綴完備。
- [ ] **物理/數學單位**：具體物理或數學變數顯式標註 `_{unit}` 單位後綴，且無同名覆蓋中轉。

#### 2. 日誌與安全性
- [ ] **關鍵進入點與重要狀態**：核心介面有適當的 Info / Debug 日誌。
- [ ] **錯誤與異常處置**：錯誤邊界有 Warning / Error 日誌並附帶上下文資訊。
- [ ] **高頻防衛**：嚴禁在每影格循環項目 (Update / Render / Calculate) 記錄日誌。

#### 3. 知識庫 1:1 交付與文檔審查 (Knowledge Base Delivery Audit)
> 💡 **自動化檢查提示**：可優先執行知識庫定式巡檢工具，自動排查死鏈與 Frontmatter 語法：
> ```bash
> python yscb_cli.py agents-workflow docs audit
> ```
- [ ] **三維錨點對齊**：對照 P03 (API)、P05 (Tasks) 與 P06 (Tests)，確認所有公開介面、協同機制、狀態機、資料管線與工程妥協已全數覆蓋。
- [ ] **中觀專題手冊 (Topic Docs)**：若涉及 3 個以上狀態轉移、通訊封包、資料管線或並發同步，已建立獨立 `docs/<Module>/[topic].md`（垂直 Mermaid TD + 轉移矩陣）。
- [ ] **工程妥協登記**：若實作包含非直觀設計或 Workaround，已於 `docs/<Module>/DESIGN_NOTES.md` 登記 `DN-XX` 與 `[!CAUTION]`。
- [ ] **模組 README 同步**：`docs/<Module>/README.md` 已補齊最新 API 簽名與快速上手範例。
- [ ] **全域地圖與 CHANGELOG**：`docs/README.md` 知識地圖與全域 [project://CHANGELOG.md](project://CHANGELOG.md) 最上方已追加本次變更摘要。

#### 4. 驗證與測試覆蓋
- [ ] 自動化測試或 CLI 編譯 100% 通過（附帶日誌紀錄）。
- [ ] 人工 / UX / 實機驗證已獲得開發者明確確認。

#### 5. Commit 訊息規範
- [ ] 採用 Conventional Commits 格式：`<type>(<scope>): <標題>`，簡潔且資訊完整。

---

### 步驟 4：即時互動修復與回填閉環 (Interactive Resolution Loop)

- **非單純報錯**：若審查中發現任何代碼瑕疵、文檔缺漏、未執行的 ext 或規範偏差，Agent **絕對禁止僅僅列出問題就結束**！
- **即時修復**：Agent 必須呈遞具體修復方案，與開發者即時討論並動手修正。
- **回填閉環**：修復完成後，將審查結論與偏差紀錄同步寫入 `P07_walkthrough.md` 與 `changelog.md`。
