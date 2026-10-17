# Fast Track 敏捷開發計畫 (Fast Track Plan)

`__@{PHASEXX_HEADER}__`

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [ ] **修改行數守門**：代碼修改行數預估 $\le 100$ 行。
- [ ] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [ ] **依賴邊界守門**：零跨模組新依賴引入。
- [ ] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
- **影響範圍**：

### 1.3 實作任務與測試規劃
- [ ] **TASK-01**：
- **測試案例清冊**：
  - [ ] **FT-01**：[測試案例驗證目標與斷言]
  - [ ] **RT-01**：全模組既有單元測試 100% 回歸通過

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
- **實機測試日誌**：

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [ ] **SOP Review 品質矩陣**：三層文檔對齊（`__${workflow.docs://}__` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [ ] **日誌與發布交付**：追加 `__${project://CHANGELOG.md}__` 發布摘要。
- [ ] **結構與註解檢核**：實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- [ ] **標頭狀態更新**：完成上述審查後，將頂部標頭 `> 狀態：` 更新為 `Completed` 結案。
