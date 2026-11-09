# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：AST 模組正交化重構與全倉符號 SSOT 架構  
> 建立日期：2026-11-08  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：將 `module:ast` 從早期耦合於 `knowledge-db` 檢索切片的過渡設計，重構為對齊 `core.space` 微內核哲學的正交全倉符號 SSOT 基座。確立「單一遞迴同構 `SymbolNode` + 多部位無損座標 `parts: Dict[str, Span]` + 通用有向邊 `RelationEdge` + 來源追蹤 `provenance`」四大內核原子結構、多 `.scm`（原生相容 Tree-sitter 官方 `queries/tags.scm`）全平權交換律合流與 `spaces` 範圍綁定、四階段確定性跨檔連結流水線（4-Pass Deterministic Linking Pipeline），以及 L0 無狀態單檔原語（`parse_file`、`outline`、`slice_part`）與 L1 全倉圖譜原語（`resolve`、`select_nodes`、`traverse_edges`），完整支撐下游 `knowledge-db` 與全生態系工具鏈。
- **架構邊界**：
  - **第一方影響模組**：`ys_codebase/source/ast/`（核心重構目標）、`ys_codebase/source/knowledge-db/`（下游符號索引與圖譜查詢對接遷移）與相關模組之 `contributes/ast.json` 宣告契約。
  - **正交依賴邊界**：檔案集合過濾與增量變更游標 100% 委派 `core.space`（`contributes/ast.json` 僅透過選填 `spaces?: list[str]` 引用空間，預設 `project://` 全掃描，不在 `ast` 內重複定義 `include`/`exclude`）；遵守全倉 `A1`~`F13` 執行期隔離與 `@dataclass(frozen=True)` 不可變規範。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_atomic_schema_and_commutative_extractor` | Full Track | `Completed` | **R01 落地**：實作四大不可變內核原子結構（`Span`, `ProvenanceStep`, `SymbolNode`, `RelationEdge`）與單檔 `FileSymbolGraph`；升級 `contributes/_format.json` 支援 `spaces?: list[str]` 引用 `core.space`；實作原生相容官方 `queries/tags.scm` 之多 `.scm` 平權提取器、`@name` 物理座標交換律合流（Commutative Merge）、`Span` 包含堆疊父子樹組裝與平權 `SymbolProcessor` 管線。 |
| **sub_02** | `sub_02_deterministic_linker_and_workspace_graph` | Full Track | `Completed` | **R02 落地**：實作 `WorkspaceSymbolGraph` 與四階段確定性跨檔連結流水線（Pass 1 全域索引與跨檔同體折疊 $\to$ Pass 2 `FileImportTable` 匯入邊解析 $\to$ Pass 3 型別繼承與實作 DAG 建構 $\to$ Pass 4 四階確定性作用域查找消歧）；廢除啟發式模糊打分，確立 `resolved` / `overload_group` / `ambiguous` / `external` 四態與平權 `ModulePathResolver` / `EdgeRefiner` 注入契約。 |
| **sub_03** | `sub_03_l0_l1_primitives_cache_and_kdb_migration` | Full Track | `Completed` | **R03 落地**：實作基於不可變 `FileSymbolGraph` 之單次掃描（Single-Pass）二進位快取與 $O(|\text{Dirty}|)$ 零污染增量熱修補（拔除 `_own_members` 還原與重複解析）；落地 L0 無狀態單檔原語（`parse_file`, `outline`, `slice_part`）與 L1 全倉圖譜原語（`resolve`, `select_nodes`, `traverse_edges` 及 CLI 對齊）；完成下游 `knowledge-db` 與全倉測試無縫對接遷移。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成內核四大不可變原子結構、官方 `tags.scm` 相容平權提取器、`@name` 交換律合流與 `core.space` 規則範圍綁定驗證。
- [x] **里程碑 2 (`sub_02`)**：完成四階段確定性跨檔連結流水線（4-Pass Linker）、四階作用域查找與零幽靈邊消歧狀態機驗證。
- [x] **里程碑 3 (`sub_03`)**：完成 `FileSymbolGraph` 增量快取、L0/L1 六大操作原語（含 `slice_part` 與 `traverse_edges`）、CLI 升級與 `knowledge-db` 下游消費遷移驗收。
