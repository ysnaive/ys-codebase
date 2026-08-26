# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Agents-Workflow 模組新增 Auto 工作流 (Add Auto Workflow to Agents-Workflow)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面與資產契約清單 (Interface Inventory)

| 介面 / 資產名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`Auto.md`** | `source/agents-workflow/assets/workflows/Auto.md` | Public Workflow | 定義 `/Auto` 工作流指引、四大執行步驟與三大熔斷防護規則。 |
| **`manifest.json export`** | `source/agents-workflow/manifest.json` | Schema Manifest | 向 `agents-workflow` 宣告導出 `Auto.md` 資產。 |
| **`DevelopmentStandards.md §4.4`** | `source/agents-workflow/assets/standards/DevelopmentStandards.md` | Public Standard | 補充 `/Auto` 自動連續推進模式之規範與授權定義。 |
| **`test_auto_workflow.py`** | `source/agents-workflow/tests/test_auto_workflow.py` | Internal Test | 測試驗證 Auto 工作流之資產齊備性、manifest 導出與編譯相容性。 |

---

## 2. 核心規格與詳細契約 (Contracts & Schema Specifications)

### 2.1 `Auto.md` 工作流契約結構
```markdown
__@{DYNAMIC_CONTEXT_MAP}__

# 自動連續推進工作流 (Auto)

本 Workflow 授權 Agent 在進行中的 Full Track 計畫（或 Umbrella 子計畫）於 **Phase 01 ~ Phase 05** 之間觸發時，在無未確定技術問題或爭議的前提下，跳過中間強制 Checkpoint 連續推進，直至 **Phase 6 手動/UX 驗證 Checkpoint** 前強制停步。

---

## 🚨 核心原則與三大熔斷機制 (Circuit Breakers)

1. **零臆測熔斷 (Zero Speculation Gate)**：若需求語意不明、API 行為未定或出現不可預期的技術阻礙，必須立即停止自動推進，向開發者提問釐清。
2. **偏差熔斷 (Deviation Gate)**：若實作過程遭遇 Major/Critical 架構或 API 偏差，必須立即暫停並轉入 `/Discuss`，獲得確認後方可繼續。
3. **P06 手動/UX 驗證絕對阻斷 (Mandatory UX Gate)**：抵達 Phase 6 且 CLI 自動化測試通過後，**絕對禁止**自動標記 Passed 或進入 Phase 7！必須停步呈遞測試報告，等待開發者手動驗證確認。
4. **規範與檔案 100% 保真**：連續推進期間，P01~P06、P05 任務清單與 changelog 日誌必須 100% 完整生成與記錄，嚴禁省略產物。

---

## 🚀 執行步驟

### 步驟 1：掃描目標計畫與斷點狀態
- 檢視 `workflow.plans://` 定位當前進行中之 Full Track 計畫（或 Umbrella 活躍子計畫）。
- 檢查當前處於 Phase 01 ~ Phase 05 之哪一階段。
- **邊界防禦**：
  - 若處於 Phase 0 ➔ 提示：「Phase 0 討論必須由開發者確認定稿，P00 Confirmed 後方可啟用 `/Auto`」。
  - 若處於 Fast Track ➔ 提示：「Fast Track (Level 0) 無多階段等待需求，不適用 `/Auto`」。

### 步驟 2：連續推進閉環 (Continuous Advancement Loop)
- 從當前斷點 Phase 依序執行至 Phase 5：
  - Phase 1 需求轉譯 (產出 P01_requirements_spec.md) ➔ 自動標記 Confirmed ➔
  - Phase 2 架構設計與 Test-First (產出 P02_architecture_plan.md & P06_test_plan.md Draft) ➔ 自動標記 Confirmed ➔
  - Phase 3 API 與介面規格 (產出 P03_api_spec.md) ➔ 自動標記 Confirmed ➔
  - Phase 4 實作計畫定稿與靈魂拷問 (產出 P04_implementation_plan.md & 定稿 P06 Confirmed) ➔ 自動標記 Confirmed ➔
  - Phase 5 依序實作 (產出 P05_task.md 並按拓撲實作程式碼)。
- 每一階段均同步寫入計畫內部 `changelog.md`。

### 步驟 3：Phase 6 自動化測試與日誌登載
- 實機執行 CLI 自動化測試（如 `python yscb.py dev test <module>`）。
- 將實機測試日誌回填至 `P06_test_plan.md`。

### 步驟 4：抵達 P06 UX/手動驗證 Checkpoint（強制等待）
- 向開發者呈遞測試執行結果，並明確詢問開發者進行實際互動/視覺/UX 驗證。
- **立即 End Turn 等待開發者回覆**（等待「UX 驗證通過/指示免測」指令）。
```

### 2.2 `manifest.json` 導出契約宣告
```json
{
  "type": "workflow",
  "source": "module://agents-workflow/assets/workflows/Auto.md",
  "description": "自動連續推進工作流 (Auto) — 支援 Phase 01~05 跳過中間 Checkpoint 連續執行直至 P06 手動驗證"
}
```

### 2.3 `DevelopmentStandards.md` §4.4 增補契約
```markdown
### 4.4 自動連續推進模式 (/Auto)
- **觸發時機**：於 Full Track (Level 1) 或 Umbrella (Level 2) 活躍子計畫之 Phase 01 ~ Phase 05 區間由開發者調用。
- **特權授權**：在無未確定技術疑問與無重大架構偏差前提下，Agent 獲授權連續推進各 Phase 文件產出與代碼實作，跳過中間強制 Checkpoint。
- **三大熔斷防線**：嚴格受「零臆測熔斷」、「偏差熔斷」與「P06 手動/UX 驗證絕對阻斷」約束。
```

---

## 3. 實作依賴拓撲順序 (Implementation Topology)

```text
[Step 1: 資產建立]
  └─ source/agents-workflow/assets/workflows/Auto.md
        │
        ▼
[Step 2: 規範增補]
  └─ source/agents-workflow/assets/standards/DevelopmentStandards.md
        │
        ▼
[Step 3: 模組宣告]
  └─ source/agents-workflow/manifest.json
        │
        ▼
[Step 4: 單元測試]
  └─ source/agents-workflow/tests/test_auto_workflow.py
```

---

## 4. 架構決策記錄 (Decisions)

- **[P03:DR-01] (規格契約與四大步驟標準化)**：
  - 確立 `Auto.md` 包含標準頭部、三大熔斷原則、步驟 1~4 執行規範與 EC-01~06 邊界防禦指引。
