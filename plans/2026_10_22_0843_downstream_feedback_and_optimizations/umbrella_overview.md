# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_22_0843_downstream_feedback_and_optimizations  
> 建立日期：2026-10-22  
> 計畫狀態：In Progress  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：統籌處理下游專案實戰使用回饋報告與系統各模組體驗/準確度優化，以增量演進模式滾動開立子計畫並逐項閉環驗收。
- **架構邊界**：涵蓋 `knowledge-db`（多語言 AST 調用圖譜解析、`callers` / `impact` 準確度與 CLI 輸出規格）及後續增量回饋所涉及之 YSCB 生態系模組，嚴守 `source/` 唯一 SSOT 與沙盒測試 100% 守門。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_knowledge_db_callers_and_parsers_remediation` | Full Track | `Completed` | 修復 `uitk.net` 回報之 `callers --json` `'caller_symbol'` 崩潰、C# 呼叫點大量漏報、`callers`/`impact` 混入 Markdown 文字提及與 `impact` 低估問題，並全面體檢及一併修復其他語言解析器（Tree-sitter queries / AST drivers）之同類調用圖譜提取缺陷。 |
| **sub_02** | `sub_02_cross_platform_git_dirty_remediation` | Full Track | `Completed` | 修復跨平台（Linux / Windows）交替執行 YSCB 指令時自動改寫 `.vscode/settings.json` 與 `.yscb/storage/agents-workflow/release_manifest.json` 導致 Git Working Tree Dirty 之 ping-pong diff 問題。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `knowledge-db` 跨語言解析器調用鏈提取完整性、`callers` / `impact` 非代碼過濾與 `--json` 序列化穩定性修復。
- [x] **里程碑 2 (`sub_02`)**：完成 `core` (`IdeProjector`, `installer`) 與 `agents-workflow` (`ReleasePublisher`) 跨平台 Git Working Tree 零污染與狀態檔隔離修復。

