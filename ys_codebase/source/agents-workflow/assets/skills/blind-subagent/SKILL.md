---
name: blind-subagent
description: 透過盲眼子代理執行無預設假設探索、冷眼靜態審查、反方辯護反向查驗與平行審計。僅於顯式輸入 /blind-subagent 或明確要求透過盲眼子代理執行任務時觸發。
---

# 盲眼子代理按需調度與去錨定轉譯工作流

本技能提供開發者「零前提溝通負擔」的顯式盲眼 Subagent 一鍵召喚機制。當觸發本技能時，主代理自動切換為**去錨定轉譯器與匯流驗證者**，載入 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`)，將開發者指令或當前卡關現場淨化為無偏見中立命題並套用專用派發訊息模板交由 Subagent 執行。

---

## 適用情境與觸發時機

- **適用情境**：當需消除主視窗的 Confirmation Bias 與 Recency Anchoring 時，委派盲眼 Subagent 執行 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) `§5.1` 定義之四大任務原型：**① 無假設盲眼探索／根因排查**、**② 基準對齊冷眼靜態審查**、**③ Devil's Advocate 反向事實查驗**、**④ 分區隔離平行盲審／獨立執行**。
- **觸發時機（`B-Assist` 契約）**：僅於開發者顯式輸入 `/blind-subagent`，或於對話中明確要求**「透過盲眼子代理執行任務」**時觸發；日常局部單一職責任務預設維持主代理 Inline 執行。

---

## 執行步驟

觸發本技能時，主代理必須嚴格依序執行以下三步去錨定調度檢核流程：

```markdown
/blind-subagent 三步去錨定調度檢核表：
- [ ] 步驟 1：讀取 BlindSubagentStandards.md，識別任務歸屬之「盲眼原型 (①~④)」與目標範圍邊界
- [ ] 步驟 2：依 BlindSubagentStandards.md §4 去錨定原則與 §5.2 專用派發模板組裝 Prompt 並派發 Subagent
- [ ] 步驟 3：接收 Subagent 濃縮回條（Mode I 摘要或 Mode II 落檔收據），由主代理完成跨邊界驗證並向開發者呈遞結果
```

### 步驟 1：載入盲眼標準與定錨四大任務原型

1. **[!] 強制前置讀取**：讀取 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`)。
2. **映射任務原型與邊界**：
   - 若開發者指令已明確指定審查／查驗／探索標的，直接鎖定對應之 **原型 ① ~ ④** 與目標路徑邊界（零過度反問，立即進入步驟 2）。
   - 若開發者僅輸入 `/blind-subagent` 而未指明標的，則簡短詢問本次欲委派的目標範圍與期望原型。

---

### 步驟 2：套用盲眼專用派發模板並派發

依據步驟 1 定錨之原型與範圍，直接套用 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) **`§5.2 主代理 -> 盲眼 Subagent 專用派發訊息模板`** 組裝 Prompt，並嚴格遵守該標準之去錨定淨化三原則（`§4.1`）、各原型隔離契約（`§4.2 ~ §4.4`）與平行批次上限（`§2.1`，無 Subagent 環境依規自動降級）。

---

### 步驟 3：匯流驗證與結構化結果呈遞

接收盲眼 Subagent 回傳之 `Mode I` 或 `Mode II` 回條後：
1. 若 Subagent 執行了平行分區修改或回報了問題座標，由主代理在主視窗統一執行跨邊界連動查證、實機驗證或測試守門。
2. 向開發者呈遞精煉之**盲眼 Subagent 執行報告**（包含：採用原型、盲眼獨立發現之核心結論／審查狀態、關鍵證據座標與後續行動建議）。

---

## 常見踩坑指南 (Gotchas)

- **切勿在未讀取 `BlindSubagentStandards.md` 前憑直覺自由發揮散文 Prompt**：必須先完成步驟 1 精讀標準並套用 `§5.2` 模板，確保黑盒禁讀清單、讀寫圍欄與回傳契約完整注入。
- **切勿在開發者未指明標的時盲目派發 Subagent**：若輸入指令未包含明確的目標範圍或意圖，必須先向開發者提問定錨，避免浪費 Subagent 冷啟動 Token。
- **切勿不經查證即全盤照單全收 Subagent 的破壞性修改建議**：盲眼 Subagent 雖具備零錨定優勢，但缺乏主對話的完整歷史脈絡；主代理在落地修改前，仍須核對是否符合當前任務的全域約束。
