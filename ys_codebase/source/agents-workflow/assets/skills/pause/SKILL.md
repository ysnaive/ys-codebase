---
name: pause
description: 凍結當前開發進度與斷點並於計畫目錄產出 handoff.md 交接快照。僅於顯式輸入 /pause 或明確指示暫停並交接當前進度時觸發。
---

# 暫停開發與無縫交接工作流 (Pause)

本工作流用於中斷工作、結束當前 Session 或切換任務時，將現場狀態、未提交進度、踩坑注意事項與下一步動作進行**即時上下文凍結 (Context Freeze)**，完整固化至實體檔案 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心目標：零斷層、零疑問

確保未來的自己、接手開發者或新開 Session 的 Agent，光看計畫目錄下的 `handoff.md` 即可在 10 秒內無縫接軌，無需耗費 Token 重新探勘程式碼：
1. 目前做到哪個 Phase 或哪個具體 `[TASK-XX]`？
2. 哪些檔案已經改完、哪些改到一半？
3. 剛剛踩了什麼坑、有什麼絕對不能誤觸的陷阱？
4. 下次重啟後的第一個具體動作（精確到檔案與指令）是什麼？

---

## 執行步驟

當開發者輸入 `/pause`（或 `/Pause`）時，請依序執行以下檢核步驟：

```markdown
/Pause 現場凍結檢核表：
- [ ] 步驟 1：定位 `__${project://plans}__` 中當前正在進行的計畫目錄
- [ ] 步驟 2：讀取 handoff.md 模板，完整寫入現場狀態並驗證「重啟第 1 步」具體可執行
- [ ] 步驟 3：輸出極簡交接狀態卡並立即 End Turn
```

### 步驟 1：定位當前進行中計畫
1. 檢視 `__${project://plans}__`，定位目標計畫目錄 `__${project://plans}__/{YYYY_MM_DD_HHMM_功能名稱}/`。
2. 若當前對話未綁定特定計畫且存在多個進行中計畫，先向開發者確認欲凍結哪一個計畫。

---

### 步驟 2：生成暫停交接快照 (`handoff.md`) 並自我驗證
讀取標準模板 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)（工作區根目錄路徑：`.agents/.yscb/templates/handoff.md`），完整填寫標頭（含 `> 模型：`，依模型紀錄規則填平台宣告名稱或 `Unknown`）後落檔於計畫目錄（若為 Umbrella 子計畫則落檔於 `sub_{編號}_{名稱}/handoff.md`），客觀記錄：
1. **現場已完成事項**：具體完成之函式、邊界處理或測試。
2. **進行中待辦**：精確記錄當前實作中斷點與待續邏輯。
3. **踩坑與注意事項**：關鍵坑點、特殊時序或口頭共識。
4. **下一次接手第 1 步**：極精確的重啟行動指引（寫明接手後第一個要讀取的檔案或執行的命令，嚴禁僅寫「繼續寫程式碼」等模糊字眼）。

---

### 步驟 3：呈遞極精簡交接卡並結束對話 (強制 End Turn)

對話 Session **嚴禁全文重複、代碼傾倒或冗長轉述**，強制僅呈遞以下極簡卡片，並**立即 End Turn**：

```markdown
### [PAUSE] /Pause 現場上下文凍結完成
- **交接檔案**：[handoff.md](__${project://plans}__/{plan_name}/handoff.md)
- **所屬計畫**：[{plan_name}](__${project://plans}__/{plan_name}/)
- **凍結斷點**：[Phase X 或 FP-0Y (狀態)]
- **重啟第 1 步**：[極精確的重啟行動指引]
- **下次接手**：輸入 [/Continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`) 即可無縫接續
```

---

## 常見踩坑指南 (Gotchas)

- **切勿在 `/pause` 時擅自推進未完成的代碼變更**：`/pause` 的職責是「如實記錄並安全凍結現場」，不要為了湊齊進度而倉促寫入未驗證的半成品程式碼。
