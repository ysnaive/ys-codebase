# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`) 與三階單向 DAG 架構重構  
> 建立日期：2026-11-02  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  1. 建立與 `module:file-space`（Layer 1：檔案空間與指紋底座）及 `module:knowledge-db`（Layer 3：跨空間全文與向量混合檢索）嚴格正交的 **`module:ast`（Layer 2：靜態語法樹、雙層分部符號與呼叫拓撲核心模組）**，落實「單次解析共享（Single-Parse Symbol Sharing）」。
  2. 100% 無損保留並強化既有 AST 解析特性、C# `partial class` 跨分部聚合品質與 `contributes` 宣告式語言可擴充性，同時完整落地 `uitk.net` 下游實戰回饋之 4 大工程邊界（同名多載群組定址、`outline` 跨分部姊妹檔提示、按需 Grammar 自舉之 `stderr`/離線圍欄、`file-space -> ast -> knowledge-db` Pull-Based JIT 水位線連鎖自癒）。
- **架構邊界**：
  - **納入本主計畫**：`ys_codebase/source/ast/` 新模組建置、`ys_codebase/source/knowledge-db/` 轉型為純檢索消費者、`ys_codebase/source/agents-workflow/` 技能與 CLI 對接 `yscb ast <outline|callers|callees|impact>`。
  - **明確排除**：不將個別程式語言拆為頂層獨立模組；`module:ast` 零 BM25/向量依賴。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | [`sub_01_ast_module_and_dialect_engine`](sub_01_ast_module_and_dialect_engine/P00_discuss.md) | Full Track | `Completed` | 建立 `module:ast@1.0.0.0`：實作 `dialects/<lang>` 官方方言隔離、`contributes` 外部語言擴充、按需 Grammar 自舉（`stderr`/離線圍欄）、雙層分部符號模型（物理符號 + 邏輯聚合視圖）、確定性符號定位器（含同名多載群組展開）、`CallGraph` 雙向呼叫拓撲與 `yscb ast <outline|callers|callees|impact|status|clean>` CLI（含 `[Partial Siblings]` 提示與三維度正交過濾） |
| **sub_02** | [`sub_02_knowledge_db_ast_consumer_migration`](sub_02_knowledge_db_ast_consumer_migration/P00_discuss.md) | Full Track | `Completed` | `module:knowledge-db` 轉型為 Layer 3 純混合檢索消費者：移除重複 AST 解析與圖譜基建，透過 Pull-Based JIT 水位線協議（`file-space -> ast -> knowledge-db`）直接消費 `module:ast` 符號快照（Single-Parse Symbol Sharing）建立 BM25 與向量索引 |
| **sub_03** | [`sub_03_agents_workflow_ast_routing`](sub_03_agents_workflow_ast_routing/P00_discuss.md) | Full Track | `Completed` | `module:agents-workflow` 與系統知識庫對接：更新 `knowledge-db-search` 等技能手冊、CLI 路由規範與 `docs/` 架構文檔，全面對接 `yscb ast <outline|callers|callees|impact>` |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0（雙盲眼子代理上下游深度架構分析）**：完成「上游生產（`file-space` / `ast`）」與「下游消費（`knowledge-db` / `agents-workflow`）」雙視角盲眼調研報告 (`R01`) 與 `sub_01` ~ `sub_03` 介面契約定案。
- [x] **里程碑 1（`sub_01` `module:ast` 核心引擎與 CLI 落成）**：完成 `module:ast@1.0.0.0` 研發、方言隔離、雙層分部符號、重載群組定址、`outline` 姊妹檔提示與測試驗證。
- [x] **里程碑 2（`sub_02` `knowledge-db` 單次解析共享與三階 JIT 自癒收斂）**：完成 `knowledge-db` 轉型消費 `module:ast` 快照與三階連鎖熱自癒驗證。
- [x] **里程碑 3（`sub_03` 工作流技能對接與全倉結案驗收）**：完成 `agents-workflow` 技能與 `docs/` 文檔同步及全生態系聯合驗收。

