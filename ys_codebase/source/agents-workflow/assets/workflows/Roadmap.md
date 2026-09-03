# 技術路線圖探索與智能推薦工作流 (Roadmap)

本工作流用於掃描專案之長期技術儲備庫 (`__${workflow.roadmap://}__`)，結合目前專案架構進度與模組狀態，客觀推薦最適合當前啟動之路線圖主題。執行規範遵循 [NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 核心原則

1. **CLI 優先掃描 (CLI-First Scan)**：優先調用 `python __${yscb.host://yscb.py}__ agents-workflow roadmap` 獲取結構化元數據與問題背景，嚴禁盲目逐檔全讀。
2. **客觀事實匹配 (Context-Aware Matching)**：結合專案當前 `plan status` 與最新 `CHANGELOG.md`，客觀評估各主題先決條件是否成熟，嚴禁主觀臆測。
3. **主動推薦、開發者定奪**：Agent 僅負責客觀篩選並呈遞依據，絕對禁止擅自代開發者啟動任何 Roadmap 計畫。

---

## 🚀 執行步驟

### 步驟 1：調取 Roadmap 儲備庫摘要
- **執行指令**：`python __${yscb.host://yscb.py}__ agents-workflow roadmap`
- **檢查結果**：
  - 若無待啟動條目，直接向開發者回報並結束對話。
  - 若存在儲備條目，提取各條目之主題、狀態與核心問題背景。

---

### 步驟 2：情境比對與推薦評估
檢視目前專案狀態：
1. 是否有進行中計畫？（`python __${yscb.host://yscb.py}__ agents-workflow plan status`）
2. 各主題先決條件是否已成熟（模組版本、依賴或重構前置作業）？
3. 篩選出 1~2 個客觀匹配當前情境之主題。

---

### 步驟 3：呈遞極精簡推薦卡並等待指示

對話 Session **嚴禁逐檔全文傾倒或冗長主觀論述**，強制僅呈遞以下極簡推薦卡，並**立即 End Turn 等待指示**：

```markdown
### 🗺️ /Roadmap 路線圖推薦卡
- **儲備庫現況**：共掃描到 `[count]` 項技術儲備
- **推薦啟動項**：[{topic}.md](__${workflow.roadmap://}__{topic}.md)（狀態：`[Backlog / Ready]`）
- **核心效益**：[1 行客觀效益說明]
- **匹配理由**：[1 行當前專案相容或前置條件已成熟之客觀依據]
- **待確認事項**：請問是否針對此主題正式轉入 [/NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`) 開立計畫？
```

---

### 步驟 4：流轉立項 (Promotion to Dev Plan)

當開發者確認啟動時：
1. 引導進入 [/NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`) 流程。
2. 新計畫自動讀取該 Roadmap 檔案，直接將問題背景、方案對比與 SOP 繼承為新計畫之基礎，達成無縫立項。

---

`__@{WORKFLOW_ROADMAP}__`
