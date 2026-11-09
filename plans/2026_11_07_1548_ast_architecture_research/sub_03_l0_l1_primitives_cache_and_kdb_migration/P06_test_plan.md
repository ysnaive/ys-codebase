# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：AST 單次掃描 FileSymbolGraph 快取、L0/L1 六大操作原語、CLI 升級與 KDB 下游對接遷移  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 / 邊界測試 | 驗證 `build_index` 單次掃描快取 `ASTSnapshot.file_graphs` 與 `CallGraphIndex.workspace_graph`，並從磁碟二進位快取反序列化重載（含舊版快取自動補齊相容 `EC-04`） | FR-01, EC-04 | `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache.test_ft01_single_pass_file_graph_cache_and_persistence` |
| **FT-02** | 單元測試 | 驗證 $O(\|\text{Dirty}\|)$ `hot_patch_index` 增量更新髒檔案 `FileSymbolGraph`、移除刪除檔案、重連 `WorkspaceSymbolGraph` 與 C# `partial class` 成員重聚合 | FR-02 | `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache.test_ft02_hot_patch_dirty_file_graphs_and_partial_classes` |
| **FT-03** | 單元測試 / 邊界測試 | 驗證 L0 無狀態單檔原語 `parse_file`（記憶體字串解析、零磁碟索引寫入）與 `slice_part`（對含中文 UTF-8 源碼之 `outer`/`name`/`signature`/`parameters`/`doc`/`body` $O(1)$ 位元組無損切片，以及缺失選填槽位回傳 `""`、非法部位/未知符號拋出 `ASTError`） | FR-03, EC-01, EC-02, NFR-02 | `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache.test_ft03_l0_stateless_primitives_parse_file_and_slice_part` |
| **FT-04** | 單元測試 / 邊界測試 | 驗證 L1 全倉圖譜原語 `resolve(..., kinds=...)`、`select_nodes`（依 `kinds`/`visibility`/`ftypes` 正交批次篩選）與 `traverse_edges`（跨 `inherits`、`documents`、`calls` 雙向多跳 BFS 遍歷、`depth=0` 與非法 `direction` 防護 `EC-03`） | FR-04, EC-03 | `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache.test_ft04_l1_workspace_primitives_resolve_select_and_traverse` |
| **FT-05** | 單元測試 | 驗證 CLI `slice` 與 `traverse` 子命令路由分派（`scripts/cli.py:dispatch_cli`）與 `--json` 結構化輸出契約 | FR-05 | `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache.test_ft05_cli_slice_and_traverse_commands` |
| **RT-01** | 靜態合規與雙模組全量回歸 | 驗證 `python yscb.py dev check ast`（`A1`~`F13` 靜態守門 0 違規）、`python yscb.py dev test ast -q`（全量 50 項測試）與下游 `python yscb.py dev test knowledge-db -q`（全量 113 項測試）100% 通過 | FR-05, NFR-01, NFR-03 | `python yscb.py dev check ast && python yscb.py dev test ast -q && python yscb.py dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `1 Total, 1 Passed, 0 Failed` — `ASTSnapshot.file_graphs` 與 `CallGraphIndex.workspace_graph` 單次建置與磁碟持久化重載驗證通過 | 2026-11-09 |
| **FT-02** | `Passed` | `1 Total, 1 Passed, 0 Failed` — `hot_patch_index` 髒檔案增量更新、C# `partial` 重聚合與檔案刪除淘汰驗證通過 | 2026-11-09 |
| **FT-03** | `Passed` | `1 Total, 1 Passed, 0 Failed` — L0 `parse_file` 零磁碟索引與 `slice_part` 多語系 UTF-8 Byte Span 無損切片及 `EC-01`/`EC-02` 邊界驗證通過 | 2026-11-09 |
| **FT-04** | `Passed` | `1 Total, 1 Passed, 0 Failed` — L1 `resolve`、`select_nodes` 與 `traverse_edges`（`inherits`/`documents`/`calls` 與 `EC-03` 邊界）驗證通過 | 2026-11-09 |
| **FT-05** | `Passed` | `1 Total, 1 Passed, 0 Failed` — CLI `slice` 與 `traverse` 子命令路由與 JSON 契約驗證通過 | 2026-11-09 |
| **RT-01** | `Passed` | `dev check ast: PASSED`；`dev test ast -q: Pass: 50(100.0%), Fail: 0`；`dev test knowledge-db -q: Pass: 113(100.0%), Fail: 0` | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev test --target=ast:TestL0L1PrimitivesAndCache`、`python yscb.py dev check ast` 與下游 `python yscb.py dev test knowledge-db -q`，或實機體驗 `python yscb.py ast slice` / `python yscb.py ast traverse`，確認 L0/L1 六大操作原語、單次掃描 `FileSymbolGraph` 快取與 KDB 對接符合預期 | `[測試通過]` | 開發者指示完成 `ast@build` 自部署與 `slice`/`traverse`/`outline`/`callers` 各 10 組符號實測（40/40 通過，中位數耗時 222~259 ms） |
