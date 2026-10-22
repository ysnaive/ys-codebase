---
name: roadmap
description: 掃描 `__${workflow.roadmap://}__` 長期技術儲備庫並比對專案現況成熟度，產出高契合度立項推薦卡，或將新技術提案寫入儲備庫檔案 ({topic}.md)。觸發情境：輸入 /roadmap 或 /Roadmap、詢問「接下來有哪些長期規劃可做」、或將調研成果與新構想轉入長期技術儲備 (manage/recommend roadmap items)。排除情境：直接開立需求已明確的單一短期開發任務（改用 new-plan）、接續進行中計畫（改用 continue）。
---

# 技術路線圖探索與智能推薦工作流 (Roadmap)

本工作流用於掃描專案之長期技術儲備庫 (`__${workflow.roadmap://}__`)，結合目前專案架構進度與模組狀態，客觀推薦最適合當前啟動之路線圖主題，或將暫不實作的技術提案標準化歸入儲備庫。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心原則

1. **CLI 優先掃描 (CLI-First Scan)**：優先調用 `python __${yscb.host://yscb.py}__ agents-workflow roadmap` 獲取結構化元數據與問題背景，嚴禁盲目逐檔全讀。
2. **客觀事實匹配 (Context-Aware Matching)**：結合專案當前 `plan status` 與最新 `CHANGELOG.md`，客觀評估各主題先決條件是否成熟，嚴禁主觀臆測。
3. **主動推薦、開發者定奪**：Agent 僅負責客觀篩選並呈遞依據，絕對禁止擅自代開發者啟動任何 Roadmap 計畫。

---

## 執行步驟

開始執行時，請依序遵循以下檢核步驟：

```markdown
/Roadmap 執行檢核表：
- [ ] 步驟 1：透過 CLI 調取 `__${workflow.roadmap://}__` 儲備庫清單
- [ ] 步驟 2：比對當前專案架構與依賴成熟度，篩選 1~2 個最佳推薦啟動項（或新增儲備檔）
- [ ] 步驟 3：呈遞極簡路線圖推薦卡並立即 End Turn 等待指示
- [ ] 步驟 4：獲授權立項後，轉入 /new-plan 繼承該 Roadmap 內容開立開發計畫并同步狀態閉環
```

### 步驟 1：調取 Roadmap 儲備庫摘要
- **執行指令**：`python __${yscb.host://yscb.py}__ agents-workflow roadmap`
- **檢查結果**：
  - 若無待啟動條目，直接向開發者回報並結束對話。
  - 若存在儲備條目，提取各條目之主題、狀態與核心問題背景。
  - *(分支情境：若本次任務為「將調研成果或新提案存入 Roadmap」，則讀取 [`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`) 模板，填寫標頭與 `> 模型：` 後於 `__${workflow.roadmap://}__/{topic}.md` 建立儲備檔並回報完成。)*

---

### 步驟 2：情境比對與推薦評估
檢視目前專案狀態：
1. 是否有進行中計畫？（`python __${yscb.host://yscb.py}__ agents-workflow plan status`）
2. 各主題先決條件是否已成熟（模組版本、依賴或重構前置作業）？
3. 篩選出 1~2 個客觀匹配當前情境之主題。

---

### 步驟 3：呈遞極精簡推薦卡並等待指示 (強制 End Turn)

對話 Session **嚴禁逐檔全文傾倒或冗長主觀論述**，強制僅呈遞以下極簡推薦卡，並**立即 End Turn 等待指示**：

```markdown
### [ROADMAP] /Roadmap 路線圖推薦卡
- **儲備庫現況**：共掃描到 `[count]` 項技術儲備
- **推薦啟動項**：[{topic}.md](__${workflow.roadmap://}__/{topic}.md)（狀態：`[Backlog | Proposed | Ready | Deferred | In Progress | Completed]`）
- **核心效益**：[1 行客觀效益說明]
- **匹配理由**：[1 行當前專案相容或前置條件已成熟之客觀依據]
- **待確認事項**：請問是否針對此主題正式轉入 [/new-plan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 開立計畫？
```

---

### 步驟 4：流轉立項 (Promotion to Dev Plan)

當開發者確認啟動時：
1. 引導進入 [/new-plan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 流程。
2. 新計畫自動讀取該 Roadmap 檔案，直接將問題背景、方案對比與 SOP 繼承為新計畫之基礎，達成無縫立項。
3. **狀態閉環**：立項時將該 Roadmap 檔案標頭狀態更新為 `In Progress`；對應開發計畫結案時更新為 `Completed`。

---

## 常見踩坑指南 (Gotchas)

- **切勿直接把 `__${workflow.roadmap://}__` 當成開發工作區**：Roadmap 僅存放長期願景與儲備提案；一旦決定動工實作，必須透過 `/new-plan` 在 `__${project://plans/}__` 建立正式開發計畫目錄，不可直接在 Roadmap 目錄內建立 `P01`~`P07`。
