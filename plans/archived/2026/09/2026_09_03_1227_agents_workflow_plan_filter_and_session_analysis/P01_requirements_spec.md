# 需求規格說明書 (Requirements Specification)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 計畫目錄識別正則收斂 | 在 `PlanVerifier.verify_all_plans()`、`PlanScanner.scan_active_plans()` 與 `PlanSearcher.find_all_plans()` 中，全面收斂以 `r"^\d{4}_\d{2}_\d{2}"` 判定合法計畫目錄，排除 `roadmap`、`archived` 與任意非時間戳資源目錄。 | P0 | [P00:DR-01] |
| **FR-02** | 工作流更名 SessionAnalysis | 將 `assets/workflows/Retro.md` 重命名為 `SessionAnalysis.md`，Slash Command 映射為 `/SessionAnalysis`，更新 `contributes/agents-workflow.json` 之 workflow 導出項目與說明。 | P0 | [P00:DR-02] |
| **FR-03** | 佔位符與錨點重命名 | 將尾部特化佔位符 `WORKFLOW_RETRO` 更名為 `WORKFLOW_SESSIONANALYSIS`；將模組自檢注入錨點 `RETRO_CHECK_ITEMS` 更名為 `SESSION_ANALYSIS_CHECK_ITEMS`。 | P0 | [P00:DR-02] |
| **FR-04** | 雙核心分析體系實作 | `SessionAnalysis` 涵蓋「流程自檢」（異常過濾呈遞模式、三大核心公理、單 Turn 與 Checkpoint 守門、除錯範疇保護、文檔根因溯源）與「四大維度分析」（Skills、Workflows、CLI 含讀寫、Other；觸發時機正確性與 Token 預估模型，計算總量與佔比）。 | P0 | [P00:DR-03] |
| **FR-05** | 下游使用者視角與過度修飾去除 | 工作流與各模組注入片段全面去除主觀過度形容詞與開發環境特化資訊，確保對任何下游被管理專案具備普適性。 | P1 | [P00:DR-04] |
| **FR-06** | core 模組移除 CLI 合規審查 | `source/core/contributes/agents-workflow.json` 移除 `RETRO_CHECK_ITEMS` 注入；清理廢棄之 `source/core/assets/retro_check.md`。 | P1 | [P00:DR-05] |
| **FR-07** | knowledge-db 注入對齊與優化 | `source/knowledge-db/contributes/agents-workflow.json` 改向 `SESSION_ANALYSIS_CHECK_ITEMS` 注入 `session_analysis_check.md`，專注於工具調用次數、情境合理性與效益對比。 | P1 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `plans/` 下存在任意非時間戳開頭目錄 (如 `roadmap/`, `archived/`, `resources/`) | 全量掃描/檢核 (`verify_all_plans`, `scan_active_plans`, `find_all_plans`) 安全略過，不誤報任何結構錯誤或損毀。 |
| **EC-02** | 使用者顯式指定非時間戳目錄執行 `plan verify <target>` | 若目錄不存在拋出 `PlanNotFoundError`；若目錄存在但格式非時間戳，依 `verify_plan` 檢測並回報時間戳格式警告或錯誤。 |
| **EC-03** | 對話 Session 中某維度調用次數為 0 (如未調用任何 CLI 或未觸發特定模組工具) | 四大維度分析與模組自檢應優雅呈現 0 次調用與 0 Token 估算，不引發除以零或統計錯誤。 |
| **EC-04** | 投影目標存在舊 `Retro.md` 產物 | 重新發布時覆蓋編譯，並確保 IDE 與 CLI 辨識最新的 `/SessionAnalysis` 工作流。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 | 100% Python 標準庫實作，不引入外部計量或解析庫。 |
| **NFR-02** | 執行效能 | 計畫目錄正則過濾耗時 $< 5\text{ms}$，無感知零負擔。 |
| **NFR-03** | 回歸測試覆蓋 | 全模組單元測試 305+ 項保持 100% 通過，並為 Bug Fix 與 SessionAnalysis 新增專屬測試案例。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`PlanScanner` 先前採取硬編碼名單排除 `archived` 與 `roadmap`，而 `PlanVerifier` 僅排除 `archived`，導致規則分裂。本次統一以正則 `r"^\d{4}_\d{2}_\d{2}"` 作為 SSOT 解決根本原因。
- **`[!CAUTION]`**：重命名 Token 錨點時，必須同步更新 Donor 模組（`knowledge-db`）與主模組（`agents-workflow`），避免出現未解算的懸空佔位符（`__@{...}__`）。
