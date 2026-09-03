# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Confirmed  
> 計畫類型：Bug Fix / Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. **BUG**：驗證 cli cmd 中，錯誤的將 "plans://" 中的所有子資料夾都視為計畫，應只有符合 YYYY_MM_DD 開頭的才能視為計畫，其餘可能為資源資料夾，例如 roadmap, archived。
  2. **重構**：
     - Retro 工作流將重新命名為 SessionAnalysis。
     - agents-workflow 提供的主要分析項目為：
       1. 流程自檢 (現有 Retro 之分析內容)。
       2. 以四大維度 (Skills / Workflows / CLI 外部工具 / Other) 分析：Skills 與 Workflows 在那些時機觸發了？觸發的正確嗎？預估本次 session 總 token 消耗，並分析四大維度 token 占比（調用 CLI 的讀寫算在 CLI 中）。
       3. knowledge-db 注入：一樣專注於分析 knowledge-db 工具使用率 & 使用情境。
       4. core 不再注入 CLI 合規審查。
       5. 將現有 Retro 之工作流進行過度形容詞去除 & 語意聚合（注意：於各模組間之產出提示詞，必須以下游使用者角度考量，切勿加入本開發環境之特化資訊）。
     - 註：需同時重命名佔位符 WORKFLOW_RETRO。
- **核心目標**：
  - 修復 CLI 計畫掃描與檢核邊界，僅以時間戳格式判定合法計畫，解除非計畫資源目錄（如 `plans/roadmap`）之誤報。
  - 將 `Retro` 工作流全面演進為 `SessionAnalysis`，建立精準客觀、以下游專案使用者為中心的流程自檢與四大維度 Token / 行為分析體系，並對齊跨模組 Contributes 注入與佔位符命名。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `plans/roadmap` 內部檔案結構或既有路線圖儲備邏輯。
  - 不變更其他 10 個標準工作流（如 `NewPlan`, `Auto`, `Review`, `Discuss` 等）之執行行為。
  - 不引入外部計費或 Token 計量第三方相依套件，Token 分析維持純原生啟發式預估模型。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 計畫目錄識別正則收斂**：在 `PlanVerifier.verify_all_plans()`、`PlanScanner.scan_active_plans()` 與 `PlanSearcher.find_all_plans()` 統一收斂為 `r"^\d{4}_\d{2}_\d{2}"`，嚴格將 `roadmap/`、`archived/` 及任何非時間戳開頭資料夾判定為非計畫資源排除。
- **[P00:DR-02] Retro 重新命名為 SessionAnalysis**：工作流檔名改為 `SessionAnalysis.md`，Slash Command 映射為 `/SessionAnalysis`，尾部佔位符更名為 `WORKFLOW_SESSIONANALYSIS`，模組自檢注入錨點更名為 `SESSION_ANALYSIS_CHECK_ITEMS`。
- **[P00:DR-03] SessionAnalysis 雙核心分析體系**：
  1. 流程自檢：保持既有異常過濾呈遞與文檔 5-Whys 根因溯源原則。
  2. 四大維度分析：Skills、Workflows、CLI（包含命令輸入與輸出切片讀寫）、Other，評估觸發時機正確性並估算 Session 總 Token 消耗與四維度百分比。
- **[P00:DR-04] 提示詞下游使用者視角化與過度修飾去除**：工作流指令與注入片段全面剔除開發環境特化假設與主觀形容詞，以乾淨、專業、客觀語言呈現。
- **[P00:DR-05] 跨模組 Contributes 職責解耦**：`core` 徹底移除 `retro_check.md`，不再注入 CLI 查核；`knowledge-db` 更新注入錨點並優化為 `session_analysis_check.md`。

---

## 3. 開放議題與確認紀錄

- [x] 計畫分流判定：經評估變更跨 `agents-workflow`、`core`、`knowledge-db` 三大模組且重構工作流契約，確認採 **Full Track (標準開發計畫)**。
- [x] 佔位符命名一致性：確認使用 `WORKFLOW_SESSIONANALYSIS` 與 `SESSION_ANALYSIS_CHECK_ITEMS`。
- [x] core 模組注入策略：確認 core 完全退出 `SessionAnalysis` 注入，刪除廢棄之 `retro_check.md`。
- [x] 語意風格：下游使用者視角，去除過度修飾與本地特化資訊。
