# `module:ast` 上游生產與下游消費雙視角盲眼架構分析報告 (Upstream & Downstream Blind Architecture Audit)

> 調研主題：語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`) 上下游雙視角盲眼分析
> 所屬主計畫：2026_11_02_1009_ast_topology_engine_modularization
> 建立日期：2026-11-02
> 調研狀態：Concluded
> 模型：Gemini 4 Argon (Low)
> 模板版本：v1.2

---

## 1. 背景與調研目標 (Background & Objectives)

依據《語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`)》路線圖提案與下游實戰專案 (`uitk.net`) 回饋之 4 項工程邊界建議，本報告透過 `/blind-subagent`（原型 ① 無假設探索）分別派發兩名獨立盲眼子代理：
- **視角 A（上游生產：`Upstream AST Producer Analyst`）**：聚焦 `module:file-space` $\to$ `module:ast` 之語法樹解析、`dialects/<lang>` 方言隔離、C# `partial class` 雙層無損聚合、`contributes` 語言擴充、`CallGraph` 雙向呼叫拓撲與 `uitk.net` 邊界 ①~③。
- **視角 B（下游消費：`Downstream KDB & Workflow Analyst`）**：聚焦 `module:ast` $\to$ `module:knowledge-db` 之單次解析符號共享（Single-Parse Symbol Sharing）、BM25/ONNX 混合檢索解耦、邊界 ④ Pull-Based JIT 三階水位線連鎖自癒，以及 `agents-workflow` 技能與 CLI 路由遷移。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 視角 A：上游生產分析（`module:file-space` $\to$ `module:ast`）

#### (1) 現有 `knowledge-db` 必須 100% 無損遷移至 `module:ast` 之功能資產盤點

| 核心資產類別 | 現有實作座標 | 關鍵行為與不變量（嚴禁退化） |
| :--- | :--- | :--- |
| **統一符號與圖譜模型** | `knowledge_db/schema.py:13-253, 387-424` | `SymbolKind`、`LanguageType`、`MemberInfo`、`LanguageConfig` (`mode="tree_sitter"\|"custom"`)、`UnifiedSymbol`（含 `compute_id`、`children/members` 雙向同步、`spaces` 標籤）與 `SymbolCallSite`。 |
| **Tree-sitter 通用驅動與語言特化** | `knowledge_db/parsers/treesitter.py:30-802`、`assets/queries/*.scm` | ① Docstring 與 `///` XML tag 清理 (`L30-59, 144-160`)；② `base_list`/`base_class_clause`/`class_heritage` 泛型清理與基底提取 (`L161-202`)；③ 多語言 Visibility 推導（Python `__`/`_`、C# `private protected` 與容器預設可見度、C++ `access_specifier` 向前兄弟節點繼承、TS/JS `#` private，`L203-270`）；④ 3 階段 AST 物化（含 C/C++ `::` 分隔符、C++ 類別外方法 `ClassName::method` 反推 `parent_scope` `L452-456`、Markdown 標題/表格切分）；⑤ 調用點（`this/base/super` 正規化、泛型 `<T>()` 剝離、最小行距外包符號歸屬）與檔頭 Import/Using/Include 提取 (`L573-802`)。 |
| **C# `partial class` 雙層無損跨分部聚合** | `knowledge_db/bundler.py:29-189`、`retrieval.py:350-363, 501-560` | `_extract_unaggregated_partial_state` 與 `restore_unaggregated_partial_symbol` 保留單檔原始 `_own_members`、`_own_base_types`、`_own_field_types`、`_own_docstring`；`aggregate_partial_symbols` 按 `(spaces, kind, fqn)` 合併跨檔成員與 `partial_files` 並選舉 `is_primary_partial`，同時保留 `metadata["_own_*"]` 供下游倒排索引去重（消除 $N^2$ 膨脹）。增量熱修補時自動撈出同群組存活分部還原後重聚合。 |
| **`contributes` 宣告式語言擴充** | `knowledge_db/parsers/registry.py:78-229`、`spice/html/css_parser.py` | 支援 `tree_sitter`（掛載自訂 `.scm`）與 `custom`（動態載入 `module.path:Class` 或 `project://`/`module://` 腳本）雙模式，動態綁定 `SUPPORTED_EXTENSIONS`；內建 SPICE、HTML、CSS 解析器。 |
| **四階消歧連結器與雙向圖譜增量重連** | `knowledge_db/linker.py:175-393`、`graph.py:20-244`、`pipeline.py:489-529` | `TopologyLinker` 四階消歧（Tier 1 `self/cls/base` + 繼承鏈 BFS、Tier 2 檔頭 Import + FQN、Tier 3 欄位型別 `_class_fields` + 同空間匹配、Tier 4 全域候選打分）；`CallGraphIndex` 熱修補時透過 `get_external_incoming_edges` 保存外部入度邊並於重解析後重新縫合。 |

#### (2) `module:ast` 內部架構與 `uitk.net` 邊界 ①~③ 設計

1. **`ast/dialects/<lang>.py` 官方方言隔離 (`DialectAdapter`)**：
   - 定義標準 `DialectAdapter` 基底介面：`clean_docstring()`、`extract_visibility()`、`post_process_raw_item()`、`resolve_out_of_line_scope()`、`extract_imports()`、`normalize_call_receiver()`、`supports_partial_aggregation`。
   - 將 `python`、`c_sharp`、`cpp`、`c`、`javascript`、`typescript`、`markdown` 各自封裝於 `ast/dialects/<lang>.py`，使 `TreeSitterDriver` 成為 100% 零語言名稱 `if/elif` 分支的純淨引擎。
   - `ParserRegistry` 優先讀取 `contributes.get("ast", "languages")`，並自動向下相容合併 `contributes.get("knowledge-db", "languages")`。
2. **工程邊界 ①：無 BM25 確定性符號定位器與同名異載（Method Overloads）群組定址**：
   - **移除 BM25 依賴**：移除原 `TopologyQueryService.find_target_symbol` 尾端的 `bm25_engine.search` 模糊回退，改為純確定性三階定位器（精確 `SymbolSelector` $\to$ 精確 FQN / 尾綴 `.Name` / `::Name` / 短名查表 $\to$ 大小寫不敏感前後綴確定性匹配）。
   - **支援參數簽名過濾與同型別 Overload 群組化**：
     - 擴充 `SymbolSelector` 支援可選參數型別簽名：`[kind] [scope.]name[(param_types...)]`（如 `Window.Open(string, int)`）；
     - 修正 `TopologyLinker._by_fqn` 為 `Dict[str, List[UnifiedSymbol]]`（解決現行 `linker.py:58` 同 FQN 重載互相覆蓋問題）；
     - 當查詢 `Class.Method`（不含括號）命中多個符號時：若全部屬於**同一父型別 `(space, parent_fqn)` 下的同名重載（Overloads）**，預設視為同一邏輯群組一併展開（分別標註各重載之完整簽名、`file:line` 及聯集 `callers/callees/impact`）；唯有命中**跨不同父型別**（如 `Window.Open` vs `File.Open`）時，才返回結構化歧義清單提示。
3. **工程邊界 ②：`yscb ast outline <file_or_uri> [--merged] [--json]` 與 `[Partial Siblings]` 提示**：
   - 支援對任意受管或單一檔案即時生成結構化符號大綱（類別、方法/函式簽名、可見度、起訖行號 `Lxx-Lyy`）。
   - 當檢測到檔案內型別具有跨分部群組（`is_partial=True` 且於空間快照中存在其他同 FQN 分部檔）時：預設僅列出該物理檔案自身定義之 `_own_members`（保持單檔大綱精準對應本檔行號），並自動附帶 `[Partial Siblings]` 提示區塊列出其餘分部檔案路徑與成員數摘要（加 `--merged` 則展開跨分部完整邏輯視圖）。
4. **工程邊界 ③：按需語法依賴自舉（On-Demand Grammar Provisioning）之 `stderr` 純淨度與離線圍欄**：
   - `GrammarProvisioner` 於偵測到缺失 `tree-sitter-<lang>` 套件時，所有安裝輸出強制導向 `sys.stderr` 或日誌檔，**嚴禁寫入 `sys.stdout`**，確保 `yscb ast outline --json` 等指令在任何情況下 100% 輸出合法 JSON。
   - 內建單次會話失敗記憶與離線圍欄：若處於無網路沙盒或安裝失敗，輸出結構化 Warning 至 `stderr`（及 JSON `warnings` 欄位）並優雅略過該語言 AST 解析，絕不拋出未捕獲異常阻斷管線。

---

### 2.2 視角 B：下游消費分析（`module:ast` $\to$ `module:knowledge-db` & `agents-workflow`）

#### (1) `knowledge-db` 解耦轉型與 Single-Parse Symbol Sharing 快照契約

1. **移除 `knowledge-db` 內部重複 AST 基建**：
   - 自 `knowledge-db` 移除 `parsers/`、`bundler.py`、`linker.py`、`graph.py`、`topology_query.py` 與 `callers/callees/impact` 拓撲實作，使 `knowledge-db` 專注於 `InvertedIndex` (BM25)、`VectorIndex` (ONNX Embedding)、`HybridSearchEngine` 與 `KnowledgeDBServiceWorker`。
2. **`module:ast` 快照供給與 `_own_members` 防膨脹無損銜接**：
   - `module:ast` 以 `consumer_id="ast"` 消費 `file-space`，持久化 `cache://ast/indices/unified.symbols.bin.gz`（內含 `ast_generation: int`、`space_generations: Dict[str, int]`、`symbols: Dict[str, UnifiedSymbol]` 與 `file_to_symbol_ids: Dict[str, List[str]]`）及 `unified.graph.bin.gz`。
   - `module:ast` 產出之分部符號已預先填入 `metadata["_own_members"]`；`knowledge-db` 的 `InvertedIndex._extract_symbol_members_text()` (`retrieval.py:348-363`) 直接讀取 `metadata["_own_members"]` 建立 BM25 索引，零重複計算且 100% 維持防 $N^2$ Posting 膨脹保證。

#### (2) 工程邊界 ④：`file-space` $\to$ `ast` $\to$ `knowledge-db` Pull-Based JIT 水位線與常駐服務協同

```text
[CLI Pull-Based JIT 路徑]
  1. 呼叫 `yscb ast <outline|callers|callees|impact>`:
     ast.ensure_jit_synced() ──(consume_diff consumer="ast")──> file-space
     (僅更新符號與 CallGraph 快照，递增 ast_generation；0 BM25 / 0 ONNX 開銷)

  2. 呼叫 `yscb knowledge-db search`:
     kdb._ensure_jit_index_ready()
       ├─> 呼叫 ast.ensure_jit_synced() 確保 Layer 2 符號快照最新
       └─> 比對 kdb.acked_ast_generation < ast.head_generation
             └─> 拉取 ast 變更/刪除符號差集，熱修補 InvertedIndex (BM25) 與 VectorIndex (10 符號探針 / 3000ms 動態降級)

[Server Daemon Event-Driven 路徑]
  file-space-watcher (偵測磁碟變更，更新 YFP2 快照)
    └─(emit on_file_space_changed)─> ast/scripts/hook.file-space.py (熱修補 AST & CallGraph，遞增 ast_generation)
         └─(emit on_ast_index_updated)─> knowledge-db/scripts/hook.ast.py (喚醒 KnowledgeDBServiceWorker)
              ├─ Stage 1: 毫秒級同步 BM25 倒排索引並剔除變更符號舊向量
              └─ Stage 2: 32 筆微批次背景補齊 ONNX 向量嵌入
```

#### (3) `agents-workflow` 技能與全倉路由對接影響面

- **檢索與導航技能更新**：更新 `knowledge-db-search` 技能手冊與 `contributes/agents-workflow.json`（及 `research_guide.md`、`phase00_guide.md`、`usage_guide.md`、`code-optimizer`、`how-to-yscb`），建立清晰的分階檢索反射：
  - **未知座標（找檔案/找概念）**：`python yscb.py knowledge-db search <query>`
  - **已知檔案（看單檔結構大綱與行號）**：`python yscb.py ast outline <file>`
  - **已知符號（查呼叫拓撲與修改爆炸半徑）**：`python yscb.py ast <callers|callees|impact> <symbol>`
- **摩擦追蹤器更新**：`agents_workflow/plans/_trace_parser.py:472` 同步將 `yscb.py ast <outline|callers|callees|impact>` 納入合法檢索指令以重置連續盲讀計數。

---

## 3. 結論與已拍板架構決策 (Conclusion & Finalized Decisions)

雙盲眼分析確認 `file-space -> ast -> knowledge-db` 三階單向 DAG 架構完全可行，且能 100% 無損保留既有 AST 特性並落實 `uitk.net` 4 項工程邊界。經開發者拍板定案以下 3 項跨模組邊界決策：

1. **全解析器統一收斂於 `module:ast`（`knowledge-db` 零 Parser 殘留）**：`markdown`、`spice`、`html`、`css` 與所有 Tree-sitter / Python AST 解析器全數收斂於 `module:ast`，統一產出 `UnifiedSymbol` 快照與跨文檔引用追蹤，`knowledge-db` 不保留任何 Parser。
2. **CLI 與 `contributes` (`languages`) 徹底切分、完全解耦（不保留向下相容包袱）**：`module:ast` 獨佔 `yscb ast <outline|callers|callees|impact|status|clean>` 與 `contributes/ast.json` (`languages` 擴充點)；`module:knowledge-db` 徹底移除 `callers/callees/impact` CLI 與 `_format.json` 中的 `languages` 擴充點（宿主 `config/knowledge-db/contribute.json` 內之自訂語言同步遷移至 `config/ast/contribute.json`）。
3. **維持單一檢索與導航入口技能 (`knowledge-db-search`)**：於單一技能內整合「未知座標用 `knowledge-db search` $\to$ 已知檔案看結構用 `ast outline` $\to$ 已知符號查拓撲用 `ast callers/callees/impact`」三階工作流。
