# 修訂紀錄書 (Revision Log)

`__@{PHASEXX_HEADER}__`

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] [修訂主題簡述]
- **修訂類別**：[UI/UX/DX | Parameter | Docs]
- **涉及檔案**：
  - `[檔案路徑]`
- **修訂摘要**：
- **驗證結果**：

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [ ] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [ ] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `__${workflow.docs://}__` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `__${project://CHANGELOG.md}__`。
- [ ] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [ ] **結構合規檢核（最終守門）**：最後實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

