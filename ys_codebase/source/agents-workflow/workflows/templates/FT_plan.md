<!--
=== AGENT_GUIDANCE: Fast Track 變更計畫 (FT_plan) 填寫規範 ===
1. 定位與目的：
   - 適用於 Level 0 (Fast Track) 輕量修改（修改檔案數 <= 2、不影響 Public API、不引入新跨模組依賴）。
2. Agent 行為鐵律：
   - 剛性追溯：FT-1 必須引用 P00 核心語意，嚴禁無語意依據空降實作。
   - 升級防線：若發現影響 Public API 或跨模組依賴，立即暫停並建議升級為 Full Track。
   - DR 類型規範：
     - [TRADEOFF]：結論、理由、排除方案
     - [NEW]：結論、理由
     - [IMPROVE]：改進點、動機
3. 產出約束：
   - Agent 生成目標文件時，嚴禁輸出本 HTML 註解區塊。
============================================================
-->
# Fast Track 變更計畫 (Fast Track Plan)

> 功能名稱：[填入功能名稱]  
> 建立日期：[YYYY-MM-DD]  
> 所屬主計畫：[填入主計畫目錄名稱 / 無]  
> 依據 P00：[連結至 P00_semantic_requirements.md]  
> 狀態：Planning / Implementing / Reviewing / Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## FT-1：變更說明

### P00 語意需求摘要（引用自 P00）

- **計畫類型**：[Feature / Refactor / Bug Fix / Performance / Docs / 自訂類型]
- **核心訴求**：[一句話概述 P00 的核心需求或問題]
- **P00 關鍵情境 / 復現步驟摘要**：[從 P00 直接引用關鍵段落]

### 修改動機

[為什麼要做這個修改？]

### 修改內容

[要修改什麼？一段話概述。]


### 受影響的檔案和函式

| 檔案路徑 | 影響範圍 | 說明 |
|---------|---------|------|
| [[path/to/file]] | [函式名 / 類別名] | [修改什麼] |

### 專案擴充特化判定矩陣 (Extension Specialization Matrix)

> 執行 `python yscb_cli.py agents-workflow ext list` 盤點 `sop_ext://` 下所有可用擴充，評估本計畫之適用性：

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `[擴充名稱 1]` | `always` / `on_demand` | ✅ 納入 (Included) / ❌ 排除 (Excluded) | [說明為何需要或為何不涉及] |

> **標頭同步**：凡判定為「✅ 納入」之項目，宣告於頂部 Header `> 擴充項目：`；若全數排除則標記 `> 擴充項目：none (已評估排除)`。

### Decision Records

> ID 格式：`[FT:DR-XX]`，並附加決策類型分類標籤（`[TRADEOFF]` / `[NEW]` / `[IMPROVE]`）。

---

**[FT:DR-XX] `[TRADEOFF]` 標題**
- 結論：[最終選擇]
- 理由：[為什麼選這個]
- 排除方案：[被排除的方案及原因]

**[FT:DR-XX] `[NEW]` 標題**
- 結論：[確立的規範或約束]
- 理由：[為什麼需要這個規範]

**[FT:DR-XX] `[IMPROVE]` 標題**
- 改進點：[具體補充或澄清的內容]
- 動機：[為什麼需要這個改進]

### 閉合確認 (Closing Confirmation)

> **[Agent 執行紀律]** 在觸發 Checkpoint 前，Agent **必須**明確詢問開發者：
> 「目前已討論的所有議題是否完整？是否還有其他想法、方向或尚未提出的約束？」
> 並等待開發者明確回覆「無其他議題」後，才能進入 Checkpoint。

- [ ] 開發者已確認：目前討論已完整，無其他新議題

---

## FT-2：實作清單

> 以下清單兼任進度追蹤。標記規則：`[ ]` 未開始、`[/]` 進行中、`[x]` 已完成。

- [ ] [實作項目 1]
- [ ] [實作項目 2]
- [ ] [實作項目 3]

### 偏差記錄

> 實作過程中的任何偏差記錄在此。偏差處理規則同 Full Track Phase 5。

| 等級 | 偏差內容 | 處理方式 |
|------|---------|---------|
| | | |

---

## FT-3：品質與 UX 審查

### 代碼清理

- [ ] 移除所有 debug 輸出、未使用的變數、被註解掉的死代碼

### 測試與 UX 驗證

- [ ] Agent CLI 自動化測試結果：已實機完成自動化測試 (例 `pytest` / `dotnet test` / `npm test` / `cargo test` 等) 並無 Error/Warning
- [ ] 開發者 UX / 手動測試確認：開發者回覆「UX 驗證通過」或指示免測

### 命名規範

- [ ] 所有新增/修改的命名符合專案命名規範

### 文檔與知識庫同步 (詳見 DocumentationStandards.md)

> **[Agent 執行紀律]** 每個 Checklist 項目必須在執行後才勾選，並在「→ 操作」欄位明確描述具體執行內容。若該項確認為不適用，寫明「N/A：[原因]」。嚴禁空勾。

- [ ] 新增或修改的 public API 已加上標準文檔註解 (XML doc / JSDoc / Docstring / Doxygen 等)
  → 操作：[填入：已更新 X 個函式/方法 / N/A：無 public API 變更]
- [ ] 涉及的模組/命名空間/套件對應之 `docs/` 文件已更新（README.md / 主題文件）
  → 操作：[填入：已更新 docs/[path]/README.md，修改內容：...]
- [ ] 根目錄 `CHANGELOG.md` 已按 `global_changelog.md` 模板追加本次 Plan 之高階變更摘要（無條件必做）
  → 操作：[填入：已追加 ## YYYY_MM_DD_HHMM_功能名稱 區塊]
- [ ] `docs/README.md` 根層知識地圖已同步更新（無條件必做）
  → 操作：[填入：已新增 / 更新 / 確認無需修改，說明：...]
- [ ] 若發現坑點或工程妥協，已紀錄至對應模組之 `DESIGN_NOTES.md`
  → 操作：[填入：已記錄 / N/A：無坑點]

### Commit 訊息

> 格式：`<type>(<scope>): <簡短標題>` （常用 type: `feat`, `fix`, `refactor`, `docs`, `perf`, `test`, `chore`）

```text
<type>(<scope>): <標題：一句話概述>

- <要點 1>
- <要點 2>
```

### 變更摘要

[一段話概述本次修改完成了什麼。]

### Workflow 回顧

> 預設執行。開發者可明確說「跳過回顧」來省略此區塊。

- **本次流程是否順暢**：[回答]
- **是否應該升級為 Full Track**：[回答]
