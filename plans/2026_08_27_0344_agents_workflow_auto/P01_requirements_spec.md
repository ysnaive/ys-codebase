# 需求規格說明書 (Requirements Specification)

> 功能名稱：Agents-Workflow 模組新增 Auto 工作流 (Add Auto Workflow to Agents-Workflow)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Auto.md` 工作流資產建立 | 於 `source/agents-workflow/assets/workflows/Auto.md` 建立 Auto 工作流指引文檔，定義觸發條件、執行邊界、連續推進生命週期與三大熔斷機制。 | P0 | [P00:DR-02] |
| **FR-02** | `manifest.json` 導出與發布註冊 | 於 `source/agents-workflow/manifest.json` 之 `contributes["agents-workflow"]["export"]` 宣告註冊 `Auto.md`，使 `ReleasePublisher` 於發布時自動同步至發布目標 (如 `.agents/workflows/Auto.md`)。 | P0 | [P00:DR-03] |
| **FR-03** | 規範聯動與 Checkpoint 跳過授權定義 | 於標準手冊（如 `DevelopmentStandards.md`）補充說明 `/Auto` 指令的授權跳過機制、適用範圍（Full Track / Umbrella 子計畫）與三大絕對阻斷原則。 | P1 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | 完整階段產出 100% 保真機制 | 明確定義 Auto 工作流在連續推進期間，必須依序產出並嚴格鏡像標準模板之所有 Phase 產物（P01~P06、P05 task 清單、changelog 日誌），不可縮減或略過檔案產出。 | P0 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 於 Phase 0 討論階段觸發 `/Auto` | Phase 0 涉及原始需求收斂，嚴禁自動跳過。Agent 必須提示開發者：「Phase 0 討論必須由開發者確認定稿，P00 Confirmed 後方可啟用 `/Auto`」。 |
| **EC-02** | 於 Fast Track (Level 0) 計畫觸發 `/Auto` | Fast Track 無多階段等待需求。Agent 提示 Fast Track 不適用 `/Auto`，維持標準 FT-1 ➔ FT-2 ➔ FT-3 流程。 |
| **EC-03** | 自動推進中遭遇未確定之需求或技術疑問 | 觸發「零臆測熔斷 (Zero Speculation Gate)」：立即中斷自動推進，暫停並向開發者提出澄清問題。 |
| **EC-04** | 實作中遭遇 Major/Critical 架構或 API 偏差 | 觸發「偏差熔斷 (Deviation Gate)」：立即暫停實作，向開發者呈遞偏差評估或轉入 `/Discuss`，獲得確認後方可繼續。 |
| **EC-05** | 執行至 Phase 6 自動化測試完成 | 觸發「P06 手動/UX 驗證絕對阻斷 (Mandatory UX Gate)」：即使 CLI 跑測 100% Passed，絕對嚴禁自動通過 P06 或進入 Phase 7，必須停步呈遞測試報告等待開發者手動驗證。 |
| **EC-06** | 於 Umbrella (Level 2) 主計畫觸發 `/Auto` | 預設鎖定當前活躍/進行中之 `sub_XX` 子計畫目錄執行連續推進；若無活躍子計畫則提示開發者開立或指定子計畫。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 編譯相容性 | `Auto.md` 必須相容於 `ReleasePublisher` 與佔位符體系（`__@{...}__`, `__#{...}__`, `__${...}__`），無任何未解析之語法警告。 |
| **NFR-02** | 模組自閉環與測試 | 模組單元測試（`agents-workflow` tests）與全系統沙盒測試（`dev test agents-workflow`）100% 通過。 |
| **NFR-03** | 規範一致性 | 嚴格遵守 Dogfooding 三層空間隔離規範（所有源碼修改 100% 於 `source/agents-workflow/`）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` (Dogfooding 空間隔離)**：
  - 絕對禁止直接修改根目錄 `.agents/workflows/` 或 `modules/`；所有資產修改必須位於 `source/agents-workflow/`，發布與同步必須透過標準流水線完成。
- **`[!NOTE]` (三大佔位符體系引用規範)**：
  - 超連結引用請使用 `__#{uri}__`（如 `[NewPlan](__#{module://agents-workflow/assets/workflows/NewPlan.md}__)`）。
  - 代碼塊指令引用請使用 `__${uri}__`。

---

## 5. 核心決策紀錄 (Decisions)

- **[P01:DR-01] (FR/EC 完整映射收斂)**：
  - 1:1 映射 P00 核心語意，收斂出 4 大功能需求 (FR-01~04) 與 6 大邊界防禦情境 (EC-01~06)。
