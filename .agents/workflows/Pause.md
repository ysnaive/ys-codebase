---
description: 暫停開發與無縫交接工作流 (Pause) — 現場狀態凍結、生成 handoff.md 達成零斷層接手
---

> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下（核心來源規範：[Pause.md](../../modules/agents-workflow/workflows/commands/Pause.md)）：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | `./` | `[ACTIVE]` |
> | **`plans://`** | `./plans` | `[ACTIVE]` |
> | **`archive://`** | `./archive_plans` | `[ACTIVE]` |
> | **`docs://`** | `./docs` | `[ACTIVE]` |
> | **`sop_ext://`** | `./extensions` | `[ACTIVE]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb_cli.py uri resolve <uri>`（例：`python yscb_cli.py uri resolve project://AGENTS.md`）

# 暫停開發與無縫交接工作流 (Pause)

本 Workflow 用於開發者需要中斷工作、結束當前 Session 或切換任務時，將現場狀態、未提交進度、踩坑注意事項與下一步動作進行**「即時上下文凍結 (Context Freeze)」**。

---

## 🎯 核心目標：零斷層、零疑問

確保未來的自己、接手開發者或新開 Session 的 Agent，**光看計畫目錄下的 `handoff.md` 就能在 3 秒內無縫接軌**，不需要耗費大量 Token 重新猜測與探勘程式碼。

---

## 🚀 執行步驟

### 步驟 1：定位當前活躍 Dev Plan 目錄
- 定位當前正在進行的計畫目錄（如 `plans://{YYYY_MM_DD_HHMM_xxx}/`）。

---

### 步驟 2：生成暫停交接快照 (`handoff.md`)
- 依據 `workflows/templates/handoff.md` 模板，在該計畫目錄下建立 `handoff.md`：
  ```markdown
  # 📌 當前進度與暫停交接現場 (Handoff Context)

  > 暫停時間：YYYY-MM-DD HH:MM
  > 所屬計畫：[計畫名稱]
  > 當前所在階段：[Phase X / FT-Y (狀態: Implementing / In Progress)]
  > 模板版本：v1.0

  ---

  ## 1. 現場已完成事項
  - [x] [已完成的類別/函式/測試項目]
  - [x] [已解決的邊界問題]

  ## 2. 現場未完成 / 進行中待辦
  - [ ] [具體檔案與函式名：目前做到哪裡、下一步要寫什麼]
  - [ ] [尚未編寫或尚未通過之驗證項目]

  ## 3. 踩坑與注意事項 (Gotchas & Blockers)
  - ⚠️ [關鍵坑點/特殊時序/未解問題/本次討論達成的口頭共識]

  ## 4. 下一次接手時的第 1 步 (Immediate Next Action)
  - 🚀 [極精確的重啟行動指引，例如「從 MyElement.cpp 的 render() 函式繼續實作，完成後執行 build 驗證」]
  ```

---

### 步驟 3：呈遞交接摘要卡並結束對話
- 向開發者呈遞簡短的交接摘要卡，標註 `handoff.md` 已儲存與下次重啟第 1 步。
- **立即 End Turn 等待下次喚醒**。
