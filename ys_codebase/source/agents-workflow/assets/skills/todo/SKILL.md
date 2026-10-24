---
name: todo
description: 管理 `__${workflow.roadmap://TODO.md}__` 輕量級待辦與微觀技術債帳本，執行單行免讀盲寫追加 (todo add)、待辦清單檢索過濾 (todo list) 與單筆/多筆打包立項消耗 (todo promote)。觸發情境：輸入 /todo 或 /Todo、開發途中順手記錄微觀技術債/打磨點子/文檔微調、或檢視並打包提取待辦條目轉入 Fast Track / Revision / Full Track 計畫。排除情境：跨模組架構重構或需多階段推進之長期藍圖（改用 roadmap）、直接開立已明確之開發計畫（改用 new-plan）。
---

# 輕量待辦與技術債帳本工作流 (TODO Ledger)

本工作流管理專案戰術級輕量待辦與技術債帳本（`__${workflow.roadmap://}__/TODO.md`），提供零 Context 污染之單行免讀盲寫登記（`todo add`）、範圍過濾檢索（`todo list`）與單筆／多筆原子剪切立項（`todo promote`）。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 核心原則

1. **單行免讀盲寫 (`Zero-Read Blind Append`)**：登記輕量待辦時，一律直接調用 `todo add` CLI 指令，**嚴禁手動讀取或編輯 `TODO.md`**，由 Python 自動維護頂部 `> 最後分配編號：N` 單調遞增計數器並追加結構化區塊，100% 保護當前任務注意力。
2. **範疇保護與防敷衍守門（對齊 `AgentsStandards.md` 核心原則 3）**：實作或測試中途遭遇非當前範疇之次要衍生問題時，必須先向開發者請示或透過 [`/discuss`](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`) 裁定；**獲開發者確認轉入待辦後**，方可用 `todo add` 秒速登記並無縫回到原任務，**嚴禁未經請示私自將 Bug 塞入 `todo add` 逃避修復**。
3. **立項即原子拔除遷入 (`Pop & Promote`)**：當待辦事項準備啟動開發時，透過 `todo promote` 將目標 `[TODO-XX]` 自 `TODO.md` 原子剪切拔除，遷入新計畫目錄存為 `todo.md`，確保 `TODO.md` 永遠只保留尚未立項的活躍待辦。

---

## 執行步驟與 CLI 指令速查

```markdown
/Todo 執行檢核表：
- [ ] 1. 新增待辦：調用 `todo add "<標題>" --scope "<範疇>" --note "<備忘>" --model "<ModelName>"` 免讀盲寫登記
- [ ] 2. 檢視待辦：調用 `todo list [--scope "<keyword>"]` 檢索並呈遞推薦或清單
- [ ] 3. 立項遷入：獲授權立項時調用 `todo promote <TODO-ID...> --slug <ascii_slug> --model "<ModelName>"`，並於該 Seeded 目錄原地建立初始計畫文件
```

### 1. 單行免讀盲寫登記 (`todo add`)
```bash
python __${yscb.host://yscb.py}__ agents-workflow todo add "<簡短動作標題>" --scope "<模組或檔案路徑>" --note "<單行解法備忘或觸發條件>" --model "<ModelName>"
```
- **引號防呆**：雙引號包裹之參數內文**嚴禁夾帶雙引號 `"` 或反引號 `` ` ``**，一律改用單引號 `'...'` 或方括號 `[...]`。

### 2. 檢索與盤點待辦 (`todo list`)
```bash
python __${yscb.host://yscb.py}__ agents-workflow todo list [--scope "<keyword>"]
```

### 3. 單筆／多筆打包原子拔除立項 (`todo promote`)
```bash
# 新建 Seeded 計畫目錄並遷入 1~N 筆待辦
python __${yscb.host://yscb.py}__ agents-workflow todo promote TODO-01 [TODO-02 ...] --slug <ascii_plan_slug> --model "<ModelName>"

# 或遷入既有計畫／子計畫目錄
python __${yscb.host://yscb.py}__ agents-workflow todo promote TODO-01 --plan <existing_plan_or_subpath> --model "<ModelName>"
```
- **[!] `Seeded` 目錄原地復用鐵律**：執行 `todo promote` 建立 `__${project://plans}__/YYYY_MM_DD_HHMM_{slug}/`（內含 `todo.md` 與 `changelog.md`）後，接續進入 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 定稿時，**必須直接在該既有 `Seeded` 目錄內建立 `P00_discuss.md`、`fast_track_plan.md` 或 `revision_log.md`，嚴禁重複新建第二個時間戳資料夾**！

---

## 常見踩坑指南 (Gotchas)

- **切勿為小型局部修繕建立獨立 `{topic}.md` 路線圖**：單一檔案修繕、待補邊界測試或局部技術債請用 `todo add` 記入 `TODO.md`；跨模組架構演進或多候選方案權衡才使用 [`/roadmap`](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`)。
- **切勿手動重置 `> 最後分配編號：N`**：該欄位用於防止條目被 `todo promote` 拔除後發生歷史編號碰撞，請交由 CLI 自動維護。
