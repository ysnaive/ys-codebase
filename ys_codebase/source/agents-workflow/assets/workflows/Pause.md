# 暫停開發與無縫交接工作流 (Pause)

本工作流用於中斷工作、結束當前 Session 或切換任務時，將現場狀態、未提交進度、踩坑注意事項與下一步動作進行**即時上下文凍結 (Context Freeze)**。執行規範遵循 [NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 核心目標：零斷層、零疑問

確保未來的自己、接手開發者或新開 Session 的 Agent，光看計畫目錄下的 `handoff.md` 即可無縫接軌，無需耗費 Token 重新探勘程式碼。

---

## 🚀 執行步驟

### 步驟 1：定位當前進行中計畫
檢視 `__${project://plans/}__`，定位目標計畫目錄 `__${project://plans/}__/{YYYY_MM_DD_HHMM_功能名稱}/`。

---

### 步驟 2：生成暫停交接快照 (`handoff.md`)
讀取標準模板 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)，徹底移除導引註解後落檔於計畫目錄，客觀記錄：
1. **現場已完成事項**：具體完成之函式、邊界處理或測試。
2. **進行中待辦**：精確記錄當前實作中斷點與待續邏輯。
3. **踩坑與注意事項**：關鍵坑點、特殊時序或口頭共識。
4. **下一次接手第 1 步**：極精確的重啟行動指引。

---

### 步驟 3：呈遞極精簡交接卡並結束對話

對話 Session **嚴禁全文重複、代碼傾倒或冗長轉述**，強制僅呈遞以下極簡卡片，並**立即 End Turn**：

```markdown
### ⏸️ /Pause 現場上下文凍結完成
- **交接檔案**：[handoff.md](__${project://plans/}__/{plan_name}/handoff.md)
- **所屬計畫**：[{plan_name}](__${project://plans/}__/{plan_name}/)
- **凍結斷點**：[Phase X 或 FT-Y (狀態)]
- **重啟第 1 步**：[極精確的重啟行動指引]
- **下次接手**：輸入 [/Continue](`__#{module://agents-workflow/assets/workflows/Continue.md}__`) 即可無縫接續
```

---

`__@{WORKFLOW_PAUSE}__`
