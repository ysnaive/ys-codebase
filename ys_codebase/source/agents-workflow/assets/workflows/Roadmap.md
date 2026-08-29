`__@{DYNAMIC_CONTEXT_MAP}__`

# 技術路線圖探索與智能推薦工作流 (Roadmap)

本 Workflow 用於主動掃描、探索與檢視專案之長期技術儲備庫 (`__${workflow.roadmap://}__`)，並依據目前專案架構進度、模組狀態與開發痛點，智能推薦最適合當前啟動的技術路線圖主題。所有階段的執行規範請嚴格遵循 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 核心原則

1. **零 Token 負擔 (CLI-First Scan)**：優先調用 `python __${yscb.host://yscb.py}__ agents-workflow roadmap` 獲取結構化 Header 元數據與問題背景摘要，嚴禁盲目逐檔全讀。
2. **客觀事實匹配 (Context-Aware Matching)**：結合專案當前 `plan status` 與最新 `CHANGELOG.md` 演進，評估各儲備主題的先決條件是否已成熟。
3. **主動推薦、開發者定奪**：Agent 僅負責客觀篩選與呈遞推薦理由，絕對禁止擅自代開發者啟動任何 Roadmap 計畫。

---

## 🚀 執行步驟

### 步驟 1：調取 Roadmap 儲備庫摘要
- **執行指令**：`python __${yscb.host://yscb.py}__ agents-workflow roadmap`
- **檢查結果**：
  - 若輸出「目前無任何待啟動之 Roadmap 技術儲備」，直接向開發者回報，結束對話。
  - 若存在儲備條目，提取各條目之主題、狀態與核心問題背景摘要。

---

### 步驟 2：情境比對與推薦評估
- 檢視目前專案狀態：
  1. 目前是否有未完結之進行中計畫？（透過 `python __${yscb.host://yscb.py}__ agents-workflow plan status`）
  2. 當前架構演進重點是什麼？
  3. 各 Roadmap 主題之先決條件是否已滿足（例如模組版本、發布管道或重構前置作業）？
- 篩選出 **1 ~ 2 個最適合在當前或近期啟動的主題**。

---

### 步驟 3：呈遞 Roadmap 推薦卡並等待指示

向開發者呈遞結構化推薦摘要卡：

```markdown
# 🗺️ 技術路線圖儲備掃描報告 (Roadmap Assessment)

已掃描長期技術儲備庫，目前共有 X 個技術路線圖條目：

### 🌟 推薦啟動主題：[主題名稱]
- **路線圖檔案**：[檔名.md](`__${workflow.roadmap://}__`/[檔名.md])
- **儲備狀態**：`Backlog` (更新於 YYYY-MM-DD)
- **核心痛點與效益**：[簡述痛點與預期效益]
- **推薦啟動理由**：[說明為何當前時機點適合啟動]

---

**🤖 請問是否要針對上述主題正式立項開發（轉入 /NewPlan），或檢視其他 Roadmap 主題？**
```

- **🚨 立即 End Turn 等待回覆**。

---

### 步驟 4：流轉立項 (Promotion to Dev Plan)

- 當開發者回覆「確認啟動 [主題]」或「針對 [主題] 開立計畫」時：
  1. 引導進入 `/NewPlan` 流程。
  2. 新計畫將自動讀取該 Roadmap 檔案，直接將「問題背景」、「方案對比」與「SOP」繼承為新計畫之基礎，達成零斷層立項開發。

`__@{WORKFLOW_ROADMAP}__`
