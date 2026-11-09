# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 四大不可變內核原子結構、平權交換律提取器與 core.space 規則範圍綁定  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 `R01_atomic_symbol_definition_and_contributes_boundary.md` 定案結論，啟動首個子計畫 `sub_01_atomic_schema_and_commutative_extractor`，落地 `module:ast` 的四大不可變內核原子結構（`Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge`）與單檔局部圖（`FileSymbolGraph`），升級 `contributes/_format.json` 支援多查詢檔與 `spaces?: list[str]` 引用 `core.space` 定義，並實作原生相容 Tree-sitter 官方 `queries/tags.scm` 標準之平權交換律合流（Commutative Merge）提取器與 `SymbolProcessor` 管線。
- **核心目標**：
  1. 在 `ast_engine/schema.py` 建立 `@dataclass(frozen=True)` 之 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge` 與 `FileSymbolGraph`（內部字典/集合正規化為 `frozenset`、`tuple`、`MappingProxyType`），提供與 `space` 及行號解耦之穩定語意 URI（`{canonical_path}::{fqn}`，同名異載附加確定性參數簽名後綴）。
  2. 擴充 `ys_codebase/source/ast/contributes/_format.json` 與 `LanguageConfig` / 規則配置模型，支援 `query_files: list[uri]?`、選填 `spaces: list[str]?`（透過 `core.space.match_path` 綁定空間範圍，未指定預設 `project://` 全掃描）與選填 `processors: list[str]?` 平權注入。
  3. 實作原生相容 Tree-sitter 官方 `queries/tags.scm`（`@definition.<kind>`、`@name`、`@doc`、`@reference.<kind>`）與擴充部位/邊捕獲標籤（`@def.<kind>`、`@part.<slot>`、`@facet.<key>`、`@edge.<kind>`）之單次掃描（Single-Pass）提取器，以 `@name` / `@part.name` 物理 `Span(start_byte, end_byte)` 為錨點執行五大欄位交換律聯集（`kinds`、`span` Bounding Box、`parts`、`facets`、`provenance`），並透過 `Span` 包含關係堆疊（Containment Stack）組裝無限層級遞迴 `SymbolNode.children` 樹與 `outgoing_edges`。
  4. 建立 `SymbolProcessor` 介面與既有 `DialectAdapter` 之相容橋接，並在 `sub_01`~`sub_02` 過渡期間保留既有 `UnifiedSymbol` / `MemberInfo` / `SymbolCallSite` 相容門面，確保在 `sub_03` 全面切換前全倉既有測試 100% 綠燈無中斷。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `ast_engine/provisioner.py:GrammarProvisioner` 進行 Tree-sitter C Grammar 載入與 stderr 隔離。
  - 復用 `core.space`（`get_default_registry().match_path`）判定檔案是否命中規則宣告之 `spaces`，不在 `ast` 中自建 `include`/`exclude` glob 匹配器。
  - 復用 `core.loader.load_module_from_path` 載入動態註冊之 `SymbolProcessor` 或自訂 Parser。
  - 復用並收編 `ast_engine/dialects/*` 既有各語言可見度推導、修飾符提取、C++ out-of-line 作用域拆解與註解清理邏輯為標準 `SymbolProcessor`。
- **邊界排除 (Explicitly Excluded)**：
  - **跨檔四階段連結器（4-Pass Deterministic Linker）與 `WorkspaceSymbolGraph`**：歸屬 `sub_02_deterministic_linker_and_workspace_graph`，本子計畫產出之 `FileSymbolGraph.outgoing_edges` 預設 `resolution_status="unresolved"`、`resolved_target_ids=()`。
  - **`ASTEngine` 持久化二進位快取替換、L0/L1 六大公開原語與 `knowledge-db` 下游遷移**：歸屬 `sub_03_l0_l1_primitives_cache_and_kdb_migration`。
- **架構影響範圍**：
  - `ys_codebase/source/ast/contributes/_format.json`
  - `ys_codebase/source/ast/ast_engine/schema.py`
  - `ys_codebase/source/ast/ast_engine/parsers/{base.py,treesitter.py,registry.py,markdown.py,html_parser.py,css_parser.py,spice_parser.py}`
  - `ys_codebase/source/ast/ast_engine/dialects/*`
  - `ys_codebase/source/ast/assets/queries/*.scm`
  - `ys_codebase/source/ast/tests/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 軸一（既有組件復用与過渡期相容門面）**：
  - 直接在 `ast_engine/schema.py` 擴充新增 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge` 與 `FileSymbolGraph`；同時保留既有 `UnifiedSymbol`、`MemberInfo`、`SymbolCallSite` 與 `BaseParser.parse()` 相容方法（可由 `extract_file_graph()` 投影衍生或雙軌並存），確保 `sub_01` 獨立交付時不破壞 `bundler.py`、`engine.py` 與 `knowledge-db` 既有呼叫端。
- **[P00:DR-02] 軸二（預設值與 `spaces` 隱性副作用防呆）**：
  - 規則未宣告 `spaces`（預設 `spaces=()`）時，代表對工作區所有符合 `extensions` 之檔案生效，L0 單檔解析時無須強制觸發全倉 `core.space` 掃描；唯有當規則顯式宣告非空 `spaces: ("core/contributes", ...)` 時，才透過 `core.space` 註冊表執行 `match_path` 檢查，確保無頭單檔測試與記憶體內解析零額外 I/O 副作用。
- **[P00:DR-03] 軸三（生命週期、快取隔離與異常逆向路徑）**：
  - 所有新增資料結構（`Span`, `ProvenanceStep`, `SymbolNode`, `RelationEdge`, `FileSymbolGraph`）100% 標註 `@dataclass(frozen=True)`，內部 `parts` 與 `facets` 於 `__post_init__` 封裝為不可變映射或正規化結構，遵循 `dev check` 之 `C8`/`C9` 靜態守門；當單一擴充 `.scm` 或 `SymbolProcessor` 語法損毀時，記錄 `log_warn(..., stream="stderr")` 與 `load_errors` 並隔離該故障規則，不阻斷同檔案其餘有效規則的提取。
- **[P00:DR-04] 軸四（全局座標、穩定 ID 與交換律不變量）**：
  - `Span` 統一採用 0-based `start_byte` / `end_byte`（與 `source_bytes[start_byte:end_byte]` 完全一致）及 1-based `start_line` / `end_line`、0-based `start_col` / `end_col`；`SymbolNode.id` 格式固定為 `"{canonical_path}::{fqn}"`（若同作用域存在同名多載則附加 `({param_types})` 簽名區分），徹底剔除 `space:` 前綴與行號耦合；多 `.scm` 捕獲以 `@name` / `@part.name` 的 `(start_byte, end_byte)` 為唯一合流錨點，保證 `ProvenanceStep` 按 `(provider_id, action, rule_or_hook)` 字典序穩定排序，滿足嚴格交換律 $A \cup B = B \cup A$。
- **[P00:DR-05] 軸五（顯式排除與階段邊界鎖定）**：
  - `sub_01` 嚴格鎖定於單檔原子結構定義、平權 `.scm` 提取器、交換律合流與 `core.space` 規則範圍匹配；跨檔 4-Pass 連結演算法留待 `sub_02`，全倉快取與 KDB 下游整合留待 `sub_03`。

---

## 3. 開放議題與確認紀錄

- **[已確認] 議題 1**：`R01` 架構規格與五維度邊界均已收斂確認，無開放未決問題。
