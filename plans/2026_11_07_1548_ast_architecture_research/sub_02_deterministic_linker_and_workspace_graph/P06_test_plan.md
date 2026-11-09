# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：AST 四階段確定性跨檔連結流水線 (4-Pass Linker)、四階作用域查找與全倉圖譜組裝  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `FileImportBinding`、`FileImportTable`、`WorkspaceSymbolGraph` 之 `@dataclass(frozen=True)` 與 `MappingProxyType` 不可變性、`to_dict()` / `from_dict()` 雙向無損序列化，以及非法 `resolution_status` 或空白必填欄位時拋出 `SchemaValidationError` | FR-01 | `python yscb.py dev test --target=ast:TestDeterministicLinker.test_ft01_workspace_symbol_graph_and_import_table_contracts` |
| **FT-02** | 單元測試 / 邊界測試 | 驗證 `LanguageConfig`（`receiver_aliases`、`symbol_folding`、`module_resolver`、`edge_refiners`）與 `ParserRegistry` 自訂 `ModulePathResolver` / `EdgeRefiner` 註冊載入、端到端解算，以及損毀外掛路徑自動記錄 `load_errors` 並優雅降級 | FR-02, EC-05 | `python yscb.py dev test --target=ast:TestDeterministicLinker.test_ft02_language_config_and_plugin_registry_extensions` |
| **FT-03** | 單元測試 / 邊界測試 | 驗證 Pass 1 跨檔案符號摺疊（C# `partial class` `merges_with` 與 C++ `.hpp`/`.cpp` `declares` 配對，且不竄改輸入之 `FileSymbolGraph`）及 Pass 2 `FileImportTable` 解算（Python 相對匯入、`__init__.py` 重匯出、萬用字元 `from .core import *` 與外部標準庫 `os` 標記為 `external`） | FR-03, EC-04 | `python yscb.py dev test --target=ast:TestDeterministicLinker.test_ft03_pass1_symbol_folding_and_pass2_import_table_resolution` |
| **FT-04** | 單元測試 / 邊界測試 | 驗證 Pass 3 結合 `FileImportTable` 消除跨模組同名基底型別 `BaseRunner` 碰撞、無環繼承 DAG 剪枝（防禦 `CycleA(CycleB)` / `CycleB(CycleA)` 循環繼承）、欄位型別分派 `self.helper.assist()`，以及 `expand_contract_symbol_ids(ws_graph, ...)` 多型展開 | FR-04, EC-01 | `python yscb.py dev test --target=ast:TestDeterministicLinker.test_ft04_pass3_inheritance_dag_and_field_dispatch` |
| **FT-05** | 單元測試 / 邊界測試 | 驗證 Pass 4 四階確定性作用域瀑布流（`Tier1_LexicalScope`、`Tier2_ClassAndBaseDAG`、`Tier3_FileImportTable`、`Tier4_WorkspaceFQN`）、同名多載參數數量收斂 vs `overload_group`、鴨子型別跨類別 `ambiguous` 狀態、Markdown `documents` 邊連結，以及輸入順序無關性 $G([f_1, \dots, f_n]) == G([f_n, \dots, f_1])$ | FR-05, EC-02, EC-03, NFR-02 | `python yscb.py dev test --target=ast:TestDeterministicLinker.test_ft05_pass4_scope_cascade_overloads_ambiguity_markdown_and_determinism` |
| **RT-01** | 靜態合規與全量回歸 | 驗證 `python yscb.py dev check ast`（`A1`~`F13` 靜態守門 0 違規）與 `python yscb.py dev test ast -q` 全模組 45 項測試案例 100% 通過 | NFR-01 | `python yscb.py dev check ast && python yscb.py dev test ast -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `1 Total, 1 Passed, 0 Failed` — `FileImportBinding`、`FileImportTable`、`WorkspaceSymbolGraph` 凍結不可變性、雙向序列化與負向 `SchemaValidationError` 驗證通過 | 2026-11-09 |
| **FT-02** | `Passed` | `1 Total, 1 Passed, 0 Failed` — `LanguageConfig` 擴充欄位、自訂 `_CustomPrefixModuleResolver` / `_CustomEventBusRefiner` 端到端收斂與故障外掛降級驗證通過 | 2026-11-09 |
| **FT-03** | `Passed` | `1 Total, 1 Passed, 0 Failed` — Pass 1 C# `partial` 與 C++ `.hpp`/`.cpp` 摺疊邊（單檔 `FileSymbolGraph` 零變異）及 Pass 2 相對/重匯出/萬用/外部匯入驗證通過 | 2026-11-09 |
| **FT-04** | `Passed` | `1 Total, 1 Passed, 0 Failed` — Pass 3 跨模組同名 `BaseRunner` 精確消歧、循環繼承無環剪枝、欄位型別分派與 `expand_contract_symbol_ids` 驗證通過 | 2026-11-09 |
| **FT-05** | `Passed` | `1 Total, 1 Passed, 0 Failed` — Pass 4 四階作用域瀑布流、`overload_group` vs `ambiguous` 判定、Markdown `documents` 邊與正反序輸入完全一致驗證通過 | 2026-11-09 |
| **RT-01** | `Passed` | `dev check ast: PASSED`；`dev test ast -q: Pass: 45(100.0%), Fail: 0, Skip: 0` | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev test --target=ast:TestDeterministicLinker`、`python yscb.py dev check ast` 與 `ast@build` 自部署實機耗時測試（`outline`、`callers`、`callees`、`impact` 各 10 組不同目標），確認 4-Pass `WorkspaceGraphLinker` 與 `WorkspaceSymbolGraph` 契約測試及靜態守門 100% 通過 | `[測試通過]` | 開發者確認 `ast@build` 自部署與各指令 10 組符號耗時驗證通過 |
