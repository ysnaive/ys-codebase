---
name: roadmap
description: 掃描 `__${workflow.roadmap://}__` 宏觀技術儲備庫並比對專案現況成熟度，產出高契合度立項推薦卡、將跨模組新技術提案寫入儲備庫檔案 ({topic}.md)，或透過 roadmap promote 執行儲備消耗立項 (Consume-on-Promote)。觸發情境：輸入 /roadmap 或 /Roadmap、詢問「接下來有哪些長期規劃可做」、將宏觀調研成果轉入技術儲備或晉升路線圖立項 (manage/recommend/promote roadmap items)。排除情境：單一檔案微調或局部技術債速記（改用 todo）、直接開立需求已明確的單一短期開發任務（改用 new-plan）、接續進行中計畫（改用 continue）。
---

# 技術路線圖探索與智能推薦工作流 (Roadmap)

本工作流用於管理與掃描專案之長期技術儲備庫 (`__${workflow.roadmap://}__/{topic}.md`)，結合目前專案架構進度與模組狀態，客觀推薦最適合當前啟動之路線圖主題，或於立項時透過 `roadmap promote` 物理遷入計畫目錄（`Consume-on-Promote`）。輕量待辦請改用 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`)。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心原則

1. **CLI 優先掃描 (CLI-First Scan)**：優先調用 `python __${yscb.host://yscb.py}__ agents-workflow roadmap [list] [--status <Backlog|Proposed|Ready|Deferred>]` 獲取結構化元數據與問題背景，嚴禁盲目逐檔全讀。
2. **立項即物理遷入 (`Consume-on-Promote`)**：路線圖立項時不再採用原地修改 `In Progress / Completed` 狀態，而是調用 `roadmap promote <topic> [--model "<ModelName>"]` 將 `__${workflow.roadmap://}__/{topic}.md` **物理搬移 (`shutil.move`)** 至新計畫目錄下命名為 `roadmap.md`（並自動初始化 `changelog.md`），使 `__${workflow.roadmap://}__` 永遠維持 100% 純淨未立項狀態。
3. **主動推薦、開發者定奪**：Agent 僅負責客觀篩選並呈遞依據，絕對禁止擅自代開發者啟動任何 Roadmap 計畫。

---

## 執行步驟

開始執行時，請依序遵循以下檢核步驟：

```markdown
/Roadmap 執行檢核表：
- [ ] 步驟 1：透過 CLI (`roadmap list [--status Ready]`) 調取 `__${workflow.roadmap://}__` 儲備庫清單
- [ ] 步驟 2：比對當前專案架構與前置解鎖條件，篩選 1~2 個最佳推薦啟動項（或依模板新增儲備檔）
- [ ] 步驟 3：呈遞極簡路線圖推薦卡並立即 End Turn 等待指示
- [ ] 步驟 4：獲授權立項後，執行 `roadmap promote <topic>` 物理遷入，並於該 Seeded 目錄原地建立初始計畫文件
```

### 步驟 1：調取 Roadmap 儲備庫摘要
- **執行指令**：
  ```bash
  python __${yscb.host://yscb.py}__ agents-workflow roadmap list [--status <Backlog|Proposed|Ready|Deferred>]
  ```
- **檢查結果**：
  - 若無待啟動條目，直接向開發者回報並結束對話。
  - 若存在儲備條目，提取各條目之主題、狀態、目標範疇、前置解鎖條件與核心問題背景。
  - *(分支情境：若本次任務為「將調研成果或新提案存入 Roadmap」，則讀取 [`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`) 模板，填寫標頭（含 `> 目標範疇：`、`> 前置解鎖條件：` 與 `> 模型：`）後於 `__${workflow.roadmap://}__/{topic}.md` 建立儲備檔並回報完成。)*

---

### 步驟 2：情境比對與推薦評估
檢視目前專案狀態：
1. 是否有進行中計畫？（`python __${yscb.host://yscb.py}__ agents-workflow plan status`）
2. 各主題之 `> 前置解鎖條件：` 是否已成熟？
3. 篩選出 1~2 個客觀匹配當前情境之主題。

---

### 步驟 3：呈遞極精簡推薦卡並等待指示 (強制 End Turn)

對話 Session **嚴禁逐檔全文傾倒或冗長主觀論述**，強制僅呈遞以下極簡推薦卡，並**立即 End Turn 等待指示**：

```markdown
### [ROADMAP] /Roadmap 路線圖推薦卡
- **儲備庫現況**：共掃描到 `[count]` 項技術儲備
- **推薦啟動項**：[{topic}.md](__${workflow.roadmap://}__/{topic}.md)（狀態：`[Backlog | Proposed | Ready | Deferred]`）
- **核心效益**：[1 行客觀效益說明]
- **匹配理由**：[1 行當前專案相容或前置解鎖條件已成熟之客觀依據]
- **待確認事項**：請問是否授權執行 `roadmap promote {topic}` 立項並轉入 [/new-plan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)？
```

---

### 步驟 4：流轉立項與物理遷入 (`Consume-on-Promote`)

當開發者確認啟動時：
1. **執行物理遷入指令**：
   ```bash
   # 建立新 Seeded 計畫目錄並將 {topic}.md 搬移為 roadmap.md
   python __${yscb.host://yscb.py}__ agents-workflow roadmap promote <topic> --model "<ModelName>"

   # 或遷入既有主計畫／子計畫目錄
   python __${yscb.host://yscb.py}__ agents-workflow roadmap promote <topic> --plan <existing_plan_or_subpath> --model "<ModelName>"
   ```
2. **[!] `Seeded` 目錄原地復用鐵律**：`roadmap promote` 已預先建立 `__${project://plans}__/YYYY_MM_DD_HHMM_{topic}/`（內含 `roadmap.md` 與 `changelog.md`）。接續進入 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 時，**必須直接在該既有 `Seeded` 目錄內建立 `P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md`，嚴禁重複新建第二個時間戳資料夾**！

---

## 常見踩坑指南 (Gotchas)

- **切勿在立項後將 `{topic}.md` 留在 `__${workflow.roadmap://}__` 原地改狀態**：一律透過 `roadmap promote` 物理搬移進計畫資料夾，結案時隨 `plan archive` 自然封存，彻底杜絕殭屍檔案。
- **切勿從舊 `{topic}.md` 抄錄歷史模型名稱至新計畫**：`roadmap promote` 與新計畫文件的 `--model` / `> 模型：` 必須填寫當輪平台宣告之模型（或 `Unknown`）。
