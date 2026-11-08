---
target: "AST"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/ast/ast_engine/__init__.py"
  - "yscb://source/ast/ast_engine/schema.py"
  - "yscb://source/ast/ast_engine/engine.py"
  - "yscb://source/ast/ast_engine/bundler.py"
  - "yscb://source/ast/ast_engine/resolver.py"
  - "yscb://source/ast/ast_engine/provisioner.py"
  - "yscb://source/ast/ast_engine/parsers/treesitter.py"
  - "yscb://source/ast/ast_engine/parsers/registry.py"
related_docs:
  - "./README.md"
  - "../file-space/DESIGN_NOTES.md"
  - "../knowledge-db/DESIGN_NOTES.md"
last_updated: "2026-11-08"
---

# ast 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`ast`  
> 職責定位：記錄 `module:ast` 中屬於「維度 ⑤ 工程妥協與防坑」之非直覺設計、標準庫 `ast` 命名空間防遮蔽、雙層分部符號儲存、同名異載群組定址、按需 Grammar 離線圍欄與多 `.scm` 交換律合流不變量。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :---: | :--- | :--- | :---: |
| **DN-AST-01** | 內部套件命名為 `ast_engine`（且模組根目錄不設 `__init__.py`）以防遮蔽 Python 標準庫 `import ast` | `ast_engine/*` | 🚨 CRITICAL |
| **DN-AST-02** | C# `partial class` 雙層無損儲存 (`children` vs `metadata["_own_*"]`) 與 `outline` 姊妹檔提示 | `bundler.py`, `engine.py` | 🚨 CRITICAL |
| **DN-AST-03** | 無 BM25 確定性符號定位器：同父型別 Overload 群組展開 vs 跨父型別結構化歧義攔截 | `resolver.py`, `linker.py` | ⚠️ WARNING |
| **DN-AST-04** | `GrammarProvisioner` 標準錯誤流 (`stderr`) 強制隔離與會話級離線負快取 | `provisioner.py` | ⚠️ WARNING |
| **DN-AST-05** | 多 `.scm` 以 `@name` 物理座標為錨點之交換律合流與 `core.space` 規則範圍綁定 | `schema.py`, `treesitter.py`, `registry.py` | ⚠️ WARNING |

---

## 詳細設計決策與防坑邊界

### [DN-AST-01] 內部套件命名為 `ast_engine`（且模組根目錄不設 `__init__.py`）以防遮蔽 Python 標準庫 `import ast`

- **背景與根因**：
  CLI 與模組註冊名稱為 `ast`（`ys_codebase/source/ast/` 與 `.modules/ast/`），當測試框架或 `server` Warm Worker 將 `.modules` 或 `ys_codebase/source/ast` 加入 `sys.path` 時，若其下存在名為 `ast/` 的子目錄，或 `.modules/ast/` 根目錄存在 `__init__.py`，將使 `.modules/ast` 成為名為 `ast` 的頂層 Python package，直接遮蔽 Python 標準庫內建的 `import ast`（導致 `dataclasses` -> `inspect` -> `import ast` 循環匯入崩潰）。
- **工程妥協與解法**：
  將 `ys_codebase/source/ast/` 內部的實作套件命名為 `ast_engine/`（於 `ast_engine/__init__.py` 匯出公開門面 API），且模組根目錄不放置 `__init__.py`。如此既滿足 `yscb.py ast` 與 `module://ast` 模組規範，又 100% 保護 Python 標準庫 `import ast` 不被污染。

> [!CAUTION]
> **嚴禁在 `ys_codebase/source/ast/` 下建立名為 `ast/` 的子套件目錄或根目錄 `__init__.py`！** 所有內部模組與公開 API 匯出請一律置於 `ast_engine/` 下。

---

### [DN-AST-02] C# `partial class` 雙層無損儲存 (`children` vs `metadata["_own_*"]`) 與 `outline` 姊妹檔提示

- **背景與根因**：
  1. 在重度使用 C# `partial class` 的專案中，呼叫圖譜消歧（`TopologyLinker`）需要看到跨所有分部檔案合併後的完整方法與欄位表；但單檔大綱（`yscb ast outline <file>`）與下游全文檢索（`knowledge-db` BM25 倒排索引）若直接索引合併後的 `members`，會導致單檔大綱混入其他檔案的行號，且造成 $N$ 個分部重複索引全量成員的 $N^2$ 膨脹。
- **工程妥協與解法**：
  1. **雙層無損儲存**：`aggregate_partial_symbols()` 合併前先透過 `_extract_unaggregated_partial_state()` 將單一物理檔案的原始成員保存於 `symbol.metadata["_own_members"]`（及 `_own_base_types`、`_own_field_types`、`_own_docstring`），再將跨檔合併後的完整成員寫入 `symbol.children` / `symbol.members` 與 `symbol.metadata["partial_files"]`。
  2. **`outline` 預設本檔成員 + `[Partial Siblings]` 提示**：`ASTEngine.outline()` 在 `merged=False`（預設）時，針對 `is_partial` 型別僅渲染 `_own_members`，並自動從空間快照提取其餘同 FQN 分部檔產生 `partial_siblings` 提示。

> [!CAUTION]
> **嚴禁在增量熱修補 (`hot_patch_index`) 重聚合分部類別前省略 `restore_unaggregated_partial_symbol()`！** 若未先還原存活分部的 `_own_*` 狀態即再次聚合，已刪除或已修改分部的舊成員將殘留於存活分部中無法清除。

---

### [DN-AST-03] 無 BM25 確定性符號定位器：同父型別 Overload 群組展開 vs 跨父型別結構化歧義攔截

- **背景與根因**：
  `module:ast` 不含 BM25 模糊搜尋引擎。在 C# / C++ 中，同一類別常有多個同名異載方法（Method Overloads，如 `Window.Open(string)` 與 `Window.Open(string, int)`）。若未加參數括號即一律報「歧義錯誤」拒絕查詢，會迫使 AI Agent 多花一輪對話重查；但若對不同類別的同名方法（如 `Window.Open` 與 `File.Open`）盲猜第一個，又會給出錯誤拓撲。
- **工程妥協與解法**：
  1. `TopologyLinker._by_fqn` 採用 `Dict[str, List[UnifiedSymbol]]` 保存同 FQN 下所有重載符號。
  2. `DeterministicSymbolResolver.resolve()` 在命中多個符號時檢查其 `(spaces, parent_fqn, name)`：若全數隸屬**同一父型別**，判定為 `status="overload_group"` 並一併展開所有重載的簽名與聯集拓撲；若橫跨**多個不同父型別**，則判定為 `status="ambiguous"` 並回傳結構化候選清單，支援使用者以 `Class.Method(param_types)` 精確定址。

---

### [DN-AST-04] `GrammarProvisioner` 標準錯誤流 (`stderr`) 強制隔離與會話級離線負快取

- **背景與根因**：
  若在首次執行 `yscb ast outline <file> --json` 時觸發動態 `pip install tree-sitter-<lang>`，一旦 `pip` 輸出寫入 `stdout` 將直接破壞 JSON 結構；且在斷網沙盒中若每次解析檔案皆重複嘗試連線安裝，將造成嚴重超時卡頓。
- **工程妥協與解法**：
  `GrammarProvisioner` 執行 `subprocess.run` 時強制指定 `stdout=sys.stderr, stderr=sys.stderr`，並維護進程級 `_FAILED_PACKAGES` 負快取；一旦安裝失敗或離線，當次進程不再重試該套件，僅向 `stderr` 發出結構化 Warning 並優雅跳過該語言解析。

---

### [DN-AST-05] 多 `.scm` 以 `@name` 物理座標為錨點之交換律合流與 `core.space` 規則範圍綁定

- **背景與根因**：
  1. 當官方 `tags.scm` 與外部模組掛載之領域 `.scm`（例如擷取裝飾器/CLI 路由或型別槽位的伴隨查詢）同時作用於同一來源檔時，兩組 `.scm` 所捕獲的外層 CST 節點範圍（如含裝飾器的 `decorated_definition` vs 內層 `function_definition`）往往不一致。若以外層定義節點之 `(start_byte, end_byte)` 去重，將導致同一函式分裂為兩個重複符號；若依賴載入順序覆蓋，又會破壞多來源規則之確定性。
  2. 此外，針對通用副檔名（如 `.json` 或 `.yaml`）掛載領域專屬提取器時，若對全工作區所有同副檔名檔案無差別執行，會污染無關配置檔。
- **工程妥協與解法**：
  1. **以 `@name` / `@part.name` 物理 `Span(start_byte, end_byte)` 為唯一合流錨點**：`TreeSitterDriver._commutatively_merge_raw_items()` 將同檔案內凡 `@name` 槽位座標完全相同的捕獲項自動歸併為單一符號，對 `kinds`（集合聯集）、外層 `span`（Bounding Box 聯集）、`parts`（依槽位名聯集）、`facets`（確定性字典/集合聯集）與 `provenance`（依 `(provider_id, action, rule_or_hook, detail)` 字典序排序聯集）執行交換律合併，保證 $A \cup B = B \cup A$。
  2. **`core.space` 規則範圍短路與過濾**：`LanguageConfig.spaces` 預設為空 tuple `()`（短路直接放行，零額外 I/O）；唯有顯式配置非空 `spaces: ["core/contributes", ...]` 時，`ParserRegistry._matches_configured_spaces()` 才調用 `core.space.get_default_registry().match_path(file_path, list(spaces))` 驗證檔案是否隸屬目標空間。

> [!CAUTION]
> **嚴禁在 `.scm` 合流邏輯中依賴 `query_files` 列表順序決定最終屬性覆蓋結果，亦嚴禁在 `SymbolNode` / `FileSymbolGraph` 中儲存可變 `dict` 或 `list`！** 所有內部映射必須於 `__post_init__` 封裝為 `MappingProxyType` 並將容器欄位標註 `hash=False`，以同時滿足 `dev check` `C9` 不可變規範與 `hash(node)` 雜湊契約。


