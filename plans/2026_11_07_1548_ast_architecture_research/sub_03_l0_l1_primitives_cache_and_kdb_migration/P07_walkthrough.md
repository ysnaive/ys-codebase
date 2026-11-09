# 成果展示與結案報告 (Walkthrough)

> 功能名稱：AST 單次掃描 FileSymbolGraph 快取、L0/L1 六大操作原語、CLI 升級與 KDB 下游對接遷移  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **單次掃描 `FileSymbolGraph` 快取與 $O(|\text{Dirty}|)$ 雙圖譜增量熱修補 (`FR-01`, `FR-02`, `EC-04`)**：擴充 `ASTSnapshot.file_graphs` 與 `CallGraphIndex.workspace_graph` 二進位持久化；升級 `SemanticBundler` 在單次讀檔中同時提取 `(symbols, call_sites, imports, file_graph)` 並緩存於 `_file_graphs_cache`，由 `ASTEngine.build_index` 與 `hot_patch_index` 直接針對異動檔案更新 `FileSymbolGraph` 並透過 `WorkspaceGraphLinker.link_workspace()` 重連 `WorkspaceSymbolGraph`（舊版磁碟快取缺欄位時自動按需升級並持久化）。
  2. **L0 無狀態單檔原語 (`parse_file`、`outline`、`slice_part`) (`FR-03`, `EC-01`, `EC-02`, `NFR-02`)**：於 `TreeSitterDriver` 自動填充 `parts["body"]` 與 `parts["signature"]` 位元組座標；於 `ASTEngine` 實作零全域索引依賴之 `parse_file(file_or_uri, *, content=None)`，以及基於 `Span.slice_text(raw_bytes)` 之 $O(1)$ UTF-8 位元組無損切片 `slice_part(symbol_or_id, part="outer", *, file_bytes=None)`（支援 `outer`、`name`、`signature`、`parameters`、`return_type`、`doc`、`body` 7 大結構槽位）。
  3. **L1 全倉語意圖譜原語 (`get_workspace_graph`、`resolve`、`select_nodes`、`traverse_edges`) 與 CLI `slice` / `traverse` (`FR-04`, `FR-05`, `EC-03`)**：於 `ast_engine/resolver.py` 與 `ASTEngine` 實作 `get_workspace_graph`、支援 `kinds` 過濾之 `resolve`、正交多維篩選 `select_nodes` 與通用有向圖多跳 BFS `traverse_edges`；於 `contributes/core.json`、`scripts/cli.py` 與 `ASTResultFormatter` 新增 `slice` 與 `traverse` 子命令，並保持下游 `knowledge-db` 100% 相容。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 於 `_extract_raw_definition_items` 自動提取 `parts["body"]` 與 `parts["signature"]` 位元組 Span |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 為 `SymbolNode` 新增 `.file_path` 屬性，並為 `ASTSnapshot` 新增 `file_graphs: Dict[str, FileSymbolGraph]` 欄位與序列化支援 |
| `ys_codebase/source/ast/ast_engine/graph.py` | Modify | 為 `CallGraphIndex` 新增 `workspace_graph: Optional[WorkspaceSymbolGraph]` 屬性與二進位持久化序列化 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 升級 `_parse_file_task_worker` 單次讀檔提取 `FileSymbolGraph`，新增 `_file_graphs_cache`、`extract_all_file_graphs` 與 `extract_dirty_file_graphs` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 為 `DeterministicSymbolResolver.resolve` 新增 `kinds` 過濾，並實作 `select_workspace_nodes` 與 `traverse_workspace_edges` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 升級 `build_index` / `hot_patch_index` 整合 `FileSymbolGraph` 與 `WorkspaceSymbolGraph`，實作 L0 (`parse_file`, `slice_part`) 與 L1 (`get_workspace_graph`, `resolve`, `select_nodes`, `traverse_edges`) 原語 |
| `ys_codebase/source/ast/ast_engine/formatter.py` | Modify | 新增 `format_slice_output` 與 `format_traverse_output` 終端與 JSON 格式化方法 |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 新增 `slice` 與 `traverse` CLI 子命令契約與正交選項群組宣告 |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 新增 `slice` 與 `traverse` CLI 處理函式並註冊至 `dispatch_cli` |
| `ys_codebase/source/ast/ast_engine/__init__.py` | Modify | 匯出 `VALID_SLICE_PARTS`、`select_workspace_nodes`、`traverse_workspace_edges`（共 72 個公開符號） |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 同步更新 PEP 562 公開匯出符號數量驗證（72 個符號） |
| `ys_codebase/source/ast/tests/test_l0_l1_primitives_and_cache.py` | New | 新增 `TestL0L1PrimitivesAndCache` 涵蓋 `FT-01` ~ `FT-05` 與 `EC-01` ~ `EC-04` 單元與邊界測試 |
| `docs/ast/README.md` | Modify | 同步更新 L0/L1 原語與 `slice` / `traverse` CLI 快速上手及 SDK 範例 |
| `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `[DN-AST-07]` 記錄 L0/L1 圖譜查詢原語、UTF-8 Byte Span 結構化切片與單次解析雙圖譜持久化守則 |
| `CHANGELOG.md` | Modify | 新增 `sub_03_l0_l1_primitives_cache_and_kdb_migration` 結案變更紀錄並將主計畫標記為 `Completed` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - 靶向單元與邊界測試（`TestL0L1PrimitivesAndCache` `FT-01` ~ `FT-05`）：`5 Total, 5 Passed, 0 Failed`
  - 靜態合規檢核（`python yscb.py dev check ast`）：`PASSED`（0 Warnings, 0 Errors）
  - `ast` 全模組回歸測試（`python yscb.py dev test ast -q`）：`Pass: 50(100.0%), Fail: 0, Skip: 0`
  - `knowledge-db` 全模組回歸測試（`python yscb.py dev test knowledge-db -q`）：`Pass: 113(100.0%), Fail: 0, Skip: 0`
  - Pre-Code 與 Pre-UX 雙重唯讀冷眼靜態審查：`REVIEW_STATUS: PASSED`
- **實機 UX / 人工驗證**：
  - `UX-01`（`[測試通過]`）：完成 `ast@build` 熱部署，針對 `slice`、`traverse`、`outline`、`callers` 各執行 10 組不同符號/檔案（共 40 次 CLI 調用）全數 100% 通過（中位數耗時：`slice` `259.7 ms`、`traverse` `256.3 ms`、`outline` `229.4 ms`、`callers` `222.3 ms`）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 記錄 `sub_03_l0_l1_primitives_cache_and_kdb_migration` 結案亮點與變更摘要 |
| **中觀 (Meso)** | `docs/ast/README.md` | 已交付 | 補充 L0/L1 原語與 `slice` / `traverse` CLI 及 SDK 說明 |
| **中觀 (Meso)** | `docs/ast/[topic].md` | 免更 | 由 `docs/ast/README.md` 與 `docs/ast/DESIGN_NOTES.md` 完整涵蓋 |
| **中觀 (Meso)** | `docs/ast/DESIGN_NOTES.md` | 已交付 | 新增 `[DN-AST-07]` 記錄 UTF-8 Byte Span 切片與雙圖譜持久化守則 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | `engine.py`、`bundler.py`、`resolver.py`、`formatter.py`、`cli.py` Docstring 完整且無工單編號殘留 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(ast): implement single-pass FileSymbolGraph cache, L0/L1 primitives, and slice/traverse CLI (sub_03)

- Persist FileSymbolGraph map in ASTSnapshot and WorkspaceSymbolGraph in CallGraphIndex with O(|Dirty|) hot-patching
- Add L0 stateless single-file primitives parse_file and O(1) UTF-8 byte-span slice_part (outer/name/signature/parameters/return_type/doc/body)
- Add L1 workspace graph primitives get_workspace_graph, resolve(kinds=...), select_nodes, and multi-hop BFS traverse_edges
- Expose `yscb.py ast slice` and `yscb.py ast traverse` CLI subcommands and add TestL0L1PrimitivesAndCache suite
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_07_1548_ast_architecture_research/sub_03_l0_l1_primitives_cache_and_kdb_migration` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
