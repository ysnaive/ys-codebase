# 開發標準規範與工作流指南 (Development Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性規則、工作流程引導與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

Agent 必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，都必須與開發者釐清後才能推進。禁止自行假設需求、猜測 API 行為或臆測解法。
2. **可追溯 (Traceability)**：從需求到程式碼的每一步決策，都必須有文件記錄可回溯（P00 語意 ➔ P01 FR/EC ➔ [{Phase}:DR-XX] ➔ API 簽名 ➔ 程式碼 ➔ 測試）。
3. **分級管控 (Graduated Control)**：完整 Phase 0 語意化討論後，依三大分流層級矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 分類型主計畫模式)。

### 🚨 執行紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予對該階段的「確認/同意/推進」指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋** ➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令** ➔ 只有接收到此類明確信號（如「確認」、「通過」、「進入 Phase X」），Agent 才能推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **除錯排查與範疇保護鐵律 (Scope-Bound Debugging)**：
  - **「由近及遠、本體優先」**：優先徹底排查當前組件本體內部邏輯與傳參配置。未 100% 排除自身問題前，禁止跨模組修改。
  - **修改範疇越界阻斷**：超出本次 Dev Plan 承諾範圍的外部模組，嚴禁擅自修改。
  - **阻斷盲目淺層修補**：同一問題連續 2 次修復失敗，必須強制停手進行 5-Whys 根因分析。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段一併剛性定稿 (Confirmed)。
- **Phase 6 UX / 手動測試 Checkpoint 強制等待關卡**：CLI 自動化測試通過後，必須呈遞測試結果並明確等待開發者完成 UX 驗證或指示免測後，方可推進至 Phase 7。

---

## 2. 標準生命週期 SOP 0~7 與三大分流 (Lifecycle & Tracks)

### 2.1 三大分流矩陣
- **Level 0 (Fast Track)**：單一檔案/輕量功能/微型修復，採用 `FT_plan.md`（FT-1 規格與計畫 ➔ FT-2 實作與驗證 ➔ FT-3 結案）。
- **Level 1 (Full Track)**：完整功能/中大型模組，標準執行 Phase 0 ~ Phase 7（P00~P07）。
- **Level 2 (Umbrella 主計畫)**：大型複合主題/跨模組重構，以 `umbrella_overview.md` 統籌，拆分多個 `sub_XX` 子計畫。

### 2.2 Phase 0~7 階段定義
- **Phase 0 (語意需求)**：釐清原始意圖與邊界，產出 `P00_semantic_requirements.md`。
- **Phase 1 (需求規格)**：轉譯 FR、EC、NFR，產出 `P01_requirements_spec.md`。
- **Phase 2 (架構設計)**：分層架構、資料流、受影響清單，產出 `P02_architecture_plan.md` 並初始化 `P06_test_plan.md` (Draft)。
- **Phase 3 (API 規格)**：介面簽名、錯誤契約、實作拓撲，產出 `P03_api_spec.md`。
- **Phase 4 (審查定稿)**：文檔衝擊盤點、靈魂拷問、任務分解，定稿 `P04_implementation_plan.md` 與 `P06_test_plan.md` (Confirmed)。
- **Phase 5 (依序實作)**：依拓撲順序實作程式碼，維護 `P05_task.md`。
- **Phase 6 (測試驗證)**：實機執行測試並回填日誌，等待 UX 驗證關卡確認。
- **Phase 7 (展示結案)**：成果展示、1:1 文檔交付驗收，產出 `P07_walkthrough.md`。

---

__@{PROJECT_SPECIFIC_STANDARDS}__
