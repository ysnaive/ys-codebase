# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_ast_engine_and_parsers_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將全倉深度審計報告（[`R01_full_codebase_deep_audit_report.md`](../R01_full_codebase_deep_audit_report.md)）中針對 `Unit 03` 與 `Unit 04` 檢出之全部 **16 項問題（`AST-AUD-01` ~ `AST-AUD-16`：1 P0, 7 P1, 5 P2, 3 P3）**，以及架構與演進技術債審計報告（[`R02_architecture_and_evolutionary_debt_audit.md`](../R02_architecture_and_evolutionary_debt_audit.md)）之 **`ARCH-AST-01` ~ `ARCH-AST-08` 與根因重構手術 `S3`（AST 雙軌圖譜合流、單次解析派發與鎖保護游標提交）** 全量轉化為 `sub_02` 實作與驗證閉環。
- **核心目標**：
  1. **根除 1 項 P0 跨執行緒 90 秒全域凍結與鎖順序反轉（`AST-AUD-01`）**：
     - 重構 [`ast/ast_engine/provisioner.py:L143-L232`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) 之 `GrammarProvisioner.load_language`，採用「鎖內快取查表 $\to$ 釋放 `cls._LOCK` 執行 `_try_pip_install`（含 60s 跨行程鎖與 30s `pip install`）+ `per-language Event` 單飛去重 $\to$ 重取 `cls._LOCK` 寫回快取」三階段設計，消除鎖順序反轉與 90 秒全域執行緒凍結。
  2. **落實手術 `S3` 與 `ARCH-AST-01` ~ `ARCH-AST-08` 架構收斂**：
     - **單次解析派發 (`ARCH-AST-02`, `AST-AUD-15`)**：在 `TreeSitterDriver` 實作單次 `_get_parsed_unit` 快取（涵蓋 `raw_items`、`merged_items`、`dialect_imports`、`file_graph_by_space`、`symbols_by_space`），並在 `BaseParser` / `ParserRegistry` / `PythonASTParser` 建立單通解析快取，使 `_parse_file_full` 不再對同一檔案重複解析 4 次。
     - **雙軌圖譜查詢合流與緊湊序列化 (`ARCH-AST-01`, `ARCH-AST-03`, `AST-AUD-09`, `AST-AUD-14`)**：保留 `graph.py` 內建 `_StdlibDiGraph` 零依賴退避；在 `resolver.py`（`query_callers`/`query_callees`/`query_impact`）支援直接或備援查詢 `WorkspaceSymbolGraph` 邊集合；在 `FileSymbolGraph` 與 `WorkspaceSymbolGraph` 之 `to_dict()` / `from_dict()` 消除重複節點表序列化並自動重建索引映射。
     - **鎖保護事務游標提交與分部符號深拷貝隔離 (`ARCH-AST-04`, `ARCH-AST-06`, `ARCH-AST-07`)**：在 `engine.py:ensure_jit_synced` 與 `scripts/hook.core.py:on_file_space_changed` 以 `engine._lock` 及 `ExitStack` 包裹 `consume_diff` 與 `hot_patch_index`，確保熱修補失敗時絕不推進 `"ast"` 游標；在 `bundler.py:restore_unaggregated_partial_symbol` 實作深拷貝還原；移除 `bundler.py` 對 `knowledge-db` 組態之反向硬編碼依賴。
  3. **修復 7 項 P1 重載切片錯位、跨命名空間契約斷裂、多根空間熱修補誤刪、多進程組態遺失與無 `tree_sitter` 降級失敗（`AST-AUD-02` ~ `AST-AUD-08`）及全部 P2/P3 Parser 邊界問題（`AST-AUD-09` ~ `AST-AUD-16`）**。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `GrammarProvisioner._provision_lock`、`PythonASTParser`、`MarkdownParser`、`_StdlibDiGraph` 與 `InterProcessLock`。
- **邊界排除 (Explicitly Excluded)**：不變動 `ast` CLI 子命令、MCP 工具名稱與 `ast_engine.__all__`（維持 72 個公開導出項 100% 向下相容）。
- **架構影響範圍**：`ys_codebase/source/ast/ast_engine/{provisioner,engine,linker,bundler,schema,resolver,io_utils}.py`、`ast_engine/parsers/{treesitter,registry,base,python_ast,html_parser,css_parser,spice_parser,markdown}.py`、`ast_engine/dialects/{base,cpp}.py`、`scripts/hook.core.py` 及 `ast/tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `GrammarProvisioner.load_language` Per-Language `threading.Event` 單飛鎖分離 (`AST-AUD-01`)**：`cls._LOCK` 僅保護記憶體字典讀寫（耗時 $< 1\text{ ms}$）；當某語言需執行 `_try_pip_install` 時，於 `cls._LOCK` 內登記 `_INFLIGHT_EVENTS[lang] = threading.Event()` 後立即釋放 `cls._LOCK`，讓其他已快取語言與 `get_warnings()` 零阻塞並行，安裝完成後再重取 `cls._LOCK` 更新 `_LANGUAGE_CACHE` 並 `event.set()`。
- **[P00:DR-02] 標準庫 Fallback Parser 自動掛載保障 (`AST-AUD-07`, `ARCH-AST-08`)**：當 `GrammarProvisioner.load_language("python")` 或 `"markdown"` 返回 `None` 時，`ParserRegistry.get_parser` 自動退回標準庫 `PythonASTParser` 與 `MarkdownParser`，且 `PythonASTParser` 支援巢狀函式/類別、類別欄位與任意深度屬性呼叫鏈提取。
- **[P00:DR-03] 單通解析快取與鎖保護游標提交 (`ARCH-AST-02`, `ARCH-AST-04`, `S3`)**：`TreeSitterDriver._get_parsed_unit` 與 `BaseParser._last_base_extract_cache` 將單檔 4 次 AST 解析收斂為 1 次；`ensure_jit_synced` 與 `on_file_space_changed` 將 `hot_patch_index` 置於 `consume_diff` 上下文內並受 `engine._lock` 保護。

---

## 3. 開放議題與確認紀錄

- 全部 16 項 `AST-AUD-01` ~ `AST-AUD-16` 與 8 項 `ARCH-AST-01` ~ `ARCH-AST-08`（Surgery `S3`）修復方案均已確認定案並實作驗證完成。
