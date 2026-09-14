# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_09_14_0455_downstream_feedback_remediation  
> 建立日期：2026-09-14  
> 狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：針對下游專案 (`uitk.net`) 接入 YSCB 生態系回報的核心缺陷進行全面治理與品質修復，涵蓋 P0 致命選項解析失效、P1 `core contributes` 內部調用崩潰、P1 檢索選項互斥過嚴、以及 P2 向量模型離線韌性與預載指令（ISSUE-05 規範檔案命名屬下游專案應遵循之標準規範，移出主計畫）。
- **架構邊界**：
  - 修復涉及模組：`knowledge-db`、`core`。
  - 嚴格維持既有 Public API 契約與語意空間架構，確保向下與向上相容性。
  - 遵循零臆測、SSOT 與 CLI 權限守門原則，各子計畫均具備嚴密測試守門（Dev Check 0 警告 0 錯誤）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 | 對應反饋 |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **sub_01** | `sub_01_knowledge_db_cli_options_and_filtering` | Fast Track | `Completed` | 修復 `knowledge-db` CLI 選項值提取 (`get_option_value`)，並解開 `space` 與 `ftype` 互斥群組限制 | ISSUE-01, ISSUE-03 |
| **sub_02** | `sub_02_core_contributes_dispatcher_remediation` | Fast Track | `Completed` | 修復 `core` CLI `contributes()` 模組導入與未知子指令優雅分發處理，消除 `NameError` | ISSUE-02 |
| **sub_03** | `sub_03_knowledge_db_cli_consolidation_and_model_management` | Full Track | `Completed` | CLI 指令整併（移除 scan/bundle、整併入 status/index）、新增 model 管理群組、模型平滑降級與 Agent 防呆 | ISSUE-04 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (P0/P1 阻塞修復)**：完成 `sub_01` (CLI 選項與過濾) 與 `sub_02` (Contributes 分發)，消除下游致命檢索與執行崩潰
- [x] **里程碑 2 (體驗與韌性增強)**：完成 `sub_03` (向量模型離線平滑降級與預載指令)
- [x] **里程碑 3 (生態系驗收與發布)**：執行全模組回歸驗證、更新 CHANGELOG、版本晉升與成果交付
