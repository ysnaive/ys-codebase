---
name: roadmap
description: 管理 `__${workflow.roadmap://}__` 宏觀技術儲備庫 ({topic}.md)，執行成熟度比對推薦、長期提案入庫與 roadmap promote 儲備晉升立項。觸發情境：輸入 /roadmap、詢問長期規劃建議或晉升路線圖項目。
---

# 技術路線圖探索與智能推薦工作流 (Roadmap)

本工作流用於管理與掃描專案之長期技術儲備庫 (`__${workflow.roadmap://}__/{topic}.md`)，結合目前專案架構進度與模組狀態，客觀推薦最適合當前啟動之路線圖主題，或於立項時透過 `roadmap promote` 物理遷入計畫目錄（`Consume-on-Promote`）。輕量待辦請改用 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`)；直接開立需求已明確的短期開發任務請改走 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)；接續進行中計畫請改走 [`/continue`](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心原則

1. **時序與顆粒度分流（近期歸 `/todo`，遠期歸 `/roadmap`）**：凡近期可執行、涉及具體檔案或短期技術債之任務一律歸入 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`)；`__${workflow.roadmap://}__` **專責收錄不會在近期執行的中長期跨模組演進與抽象架構藍圖**。
2. **強制類 `P00` 抽象敘述，嚴禁混雜技術現況與硬湊陪跑方案**：
   - **去現況耦合（Zero Current-State Coupling）**：撰寫 `{topic}.md` 必須以**高階抽象概念、語意目標與架構不變量（類 `P00` 層級）**敘述；**嚴禁混入當前程式碼之暫態實作現況**（如具體檔案行號、暫時性缺失旗標、內部私有實作細節，除非屬強耦合必要之核心基礎契約），避免因近期代碼演進導致路線圖過時腐敗。
   - **拒絕硬湊多方案（No Strawman Alternatives）**：直接聚焦闡述核心架構原則與概念機制，**嚴禁為填表而虛構無用的陪跑候選方案**。
3. **CLI 優先掃描 (CLI-First Scan)**：優先調用 `python __${yscb.host://yscb.py}__ agents-workflow roadmap [list] [--status <Backlog|Proposed|Ready|Deferred>]` 獲取結構化元數據與背景摘要，嚴禁盲目逐檔全讀。
4. **立項即物理遷入 (`Consume-on-Promote`)**：路線圖立項時不再採用原地修改 `In Progress / Completed` 狀態，而是調用 `roadmap promote <topic> [--model "<ModelName>"]` 將 `__${workflow.roadmap://}__/{topic}.md` **物理搬移 (`shutil.move`)** 至新計畫目錄下命名為 `roadmap.md`（並自動初始化 `changelog.md`），使 `__${workflow.roadmap://}__` 永遠維持 100% 純淨未立項狀態。
5. **主動推薦、開發者定奪**：Agent 僅負責客觀篩選並呈遞依據，絕對禁止擅自代開發者啟動任何 Roadmap 計畫。

---

## 執行步驟

開始執行時，請依序遵循以下檢核步驟：

```markdown
/roadmap 執行檢核表：
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
  - *(分支情境：若本次任務為「將調研成果或新提案存入 Roadmap」，則讀取 [`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`) 模板，填寫標頭（含 `> 目標範疇：`、`> 前置解鎖條件：` 與 `> 模型：`），並嚴格遵循「核心原則 2：類 `P00` 抽象概念敘述、抽離非強耦合之當前技術現況、不硬湊陪跑方案」於 `__${workflow.roadmap://}__/{topic}.md` 建立儲備檔並回報完成。)*

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
### [ROADMAP] /roadmap 路線圖推薦卡
- **儲備庫現況**：共掃描到 `[count]` 項技術儲備
- **推薦啟動項**：[{topic}.md](`__${workflow.roadmap://}__/{topic}.md`)（狀態：`[Backlog | Proposed | Ready | Deferred]`）
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

- **切勿在 Roadmap 混入當前暫態代碼細節或硬湊多方案對比表**：Roadmap 探討的是遠期概念藍圖，若塞入當前檔案行號、暫態 Bug 或虛構的陪跑方案，不僅浪費 Token 更會隨日常重構迅速失效；近期具體任務請一律改走 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`)。
- **切勿在立項後將 `{topic}.md` 留在 `__${workflow.roadmap://}__` 原地改狀態**：一律透過 `roadmap promote` 物理搬移進計畫資料夾，結案時隨 `plan archive` 自然封存，徹底杜絕殭屍檔案。
- **切勿從舊 `{topic}.md` 抄錄歷史模型名稱至新計畫**：`roadmap promote` 與新計畫文件的 `--model` / `> 模型：` 必須填寫當輪平台宣告之模型（或 `Unknown`）。
