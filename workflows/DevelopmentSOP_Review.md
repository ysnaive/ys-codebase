---
description: 開發完成後品質與細節審查工作流
---

# 開發完成後審查工作流 (DevelopmentSOP Review)

本工作流用於功能實作完成後，進行獨立且嚴格的品質稽核、文檔同步檢查與 Commit 訊息驗證。

---

## 審查 Checklist

### 1. 程式碼品質與清潔度
- [ ] **無殘留 Debug 代碼**：所有臨時性的 print/log 已清除。
- [ ] **無死代碼**：無大段被註解掉的廢棄代碼。
- [ ] **命名與封裝**：命名符合專案 `coding-standards.md`，成員變數封裝完備。
- [ ] **物理/數學單位**：具體物理或數學變數顯式標註 `_{unit}` 單位後綴，且無同名覆蓋中轉。

### 2. 日誌完整性
- [ ] **關鍵進入點與重要狀態**：核心介面有適當的 Info / Debug 日誌。
- [ ] **錯誤與異常處置**：錯誤邊界有 Warning / Error 日誌並附帶上下文資訊。

### 3. 知識庫與文檔同步 (Knowledge Base Sync)
- [ ] 依專案 `docs/` 鏡像規則，更新受影響模組的 `README.md`、`[topic].md` 或 `DESIGN_NOTES.md`。
- [ ] 全域 `CHANGELOG.md` 最上方已追加本次 Plan 之變更摘要。

### 4. 驗證與測試覆蓋
- [ ] 自動化測試或 CLI 編譯 100% 通過（附帶日誌紀錄）。
- [ ] 人工 / UX / 實機驗證已獲得開發者明確確認。

### 5. Commit 訊息規範
- [ ] 採用 Conventional Commits 格式：`<type>(<scope>): <標題>`，簡潔且資訊完整。
