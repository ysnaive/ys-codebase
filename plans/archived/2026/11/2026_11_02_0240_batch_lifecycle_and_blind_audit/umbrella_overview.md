# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_02_0240_batch_lifecycle_and_blind_audit  
> 建立日期：2026-11-02  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：一次性消化 `TODO-16` 與 `TODO-17` 兩項高 ROI 架構與工作流演進待辦——為 `agents-workflow` 的 `/session-audit` 技能引入盲眼子代理（`/blind-subagent`）客觀冷眼審計機制，防範當事主代理之防衛性合理化偏誤；同時將 `core` 模組生命週期 CLI（`install` / `update` / `remove`）升級為支援多模組參數與單次批次原子交易（Batch Transaction），消除多模組操作時重複依賴同步、建置與環境重載之開銷。
- **架構邊界**：
  - `sub_01_session_audit_blind_subagent`：聚焦於 `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md` 及相關文檔規範對齊（`Revision Plan`）。
  - `sub_02_core_batch_lifecycle_cli`：聚焦於 `ys_codebase/source/core/contributes/core.json`、`ys_codebase/source/core/scripts/cli.py`、`ys_codebase/source/core/core/installer.py` 與 `ys_codebase/source/core/core/engine.py`（`Full Track`）；`rollback` 維持單一環境快照參數不變。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_session_audit_blind_subagent` | Revision | `Completed` | 於 `/session-audit` 技能引入盲眼子代理（`BlindSubagentStandards.md` 原型 ②/①）執行 `session-trace` 客觀四象限根因解剖，防範主代理將 Type D 合理化為 Type C（`TODO-17`） |
| **sub_02** | `sub_02_core_batch_lifecycle_cli` | Full Track | `Completed` | 升級 `core` 之 `install` / `update` / `remove` 支援單次指令批次操作多個模組與單一原子事務（`TODO-16`） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `/session-audit` 盲眼子代理審計機制修訂、`agents-workflow` 測試驗證與 `@build` / `release` 物化同步。
- [x] **里程碑 2 (`sub_02`)**：完成 `core` 多模組批次生命週期 CLI 規格、實作、單元與邊界測試驗證及 `@build` 熱部署。

