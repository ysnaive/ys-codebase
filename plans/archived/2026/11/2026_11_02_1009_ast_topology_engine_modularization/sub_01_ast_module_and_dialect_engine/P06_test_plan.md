# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：建立 `module:ast@1.0.0.0` 靜態語法樹、方言隔離、雙層分部符號與呼叫拓撲核心引擎  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `get_dialect()` 針對 `python`、`c_sharp`、`cpp`、`c`、`javascript`、`typescript`、`markdown` 返回專屬 `DialectAdapter` 子類別與預期 `scope_separator` / `supports_partial_aggregation` 屬性 | FR-01 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_ft_01_dialect_factory_and_language_properties` |
| **FT-02** | 單元測試 | 驗證 Python（含 `__init__` public 特例）、C#、C++ 與 JS/TS 方言之可見度提取與 `import` / `using` 匯入映射解析 | FR-01 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_ft_02_dialect_visibility_and_imports_extraction` |
| **FT-03** | 單元測試 | 驗證通用 `TreeSitterDriver` 結合 `DialectAdapter` 解析 Python（裝飾器、型別標註、呼叫點）、C#（`partial class`、基底型別、欄位與多載方法）及 C++（存取修飾符狀態機與 Out-of-line `Class::Method` 定義） | FR-01 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_ft_03_treesitter_driver_python_csharp_cpp_parsing` |
| **FT-04** | 單元測試 | 驗證領域與獨立解析器（`MarkdownParser` 標題與文件連結引用提取、`SpiceParser` `.subckt` 與 `X*` 實例化呼叫、`HtmlParser` 單行多標籤與 `#id`、`CssParser` 選擇器、`PythonASTParser` 標準庫 `ast` 防遮蔽回退） | FR-01, NFR-01 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_ft_04_domain_and_standalone_parsers` |
| **FT-05** | 邊界測試 | 驗證 `ParserRegistry` 支援宣告式 `languages` 擴充註冊，並優雅攔截無效自訂解析器路徑記入 `load_errors` | FR-01 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_et_01_parser_registry_custom_contributes_and_invalid_inputs` |
| **FT-06** | 單元測試 | 驗證 `aggregate_partial_symbols()` 跨檔案合併 C# `partial class` 成員、基底與欄位型別，同時於 `metadata["_own_members"]` 無損保留單檔物理成員，並支援 `restore_unaggregated_partial_symbol()` 退化還原 | FR-02 | `python yscb.py dev test --target=ast:TestPartialAndOutline.test_ft_01_csharp_partial_two_tier_aggregation_and_restoration` |
| **FT-07** | 整合與邊界測試 | 驗證 `ASTEngine.outline()` 預設僅顯示單一物理分部檔之 `_own_members` 並自動附帶 `[Partial Siblings]` 姊妹檔提示，`merged=True` 展開跨檔合併成員，支援 `visibility` / `binding` / `member_kind` 三維度正交過濾（`[REV-01]`），且對不存在檔案回傳結構化錯誤（`EC-03`） | FR-04, EC-03, NFR-02, [REV-01] | `python yscb.py dev test --target=ast:TestPartialAndOutline.test_ft_02_outline_single_file_default_vs_merged_partial_siblings` / `test_ft_03_outline_orthogonal_filters_visibility_binding_and_member_kind` / `test_et_01_outline_missing_file_returns_structured_error` |
| **FT-08** | 單元測試 | 驗證 `ensure_unique_overload_ids()` 與 `TopologyLinker._by_fqn` 完整保留同類別下多個同名異載（Method Overloads）而不互相覆蓋 | FR-03 | `python yscb.py dev test --target=ast:TestOverloadAndTopology.test_ft_01_linker_preserves_all_overloads_in_by_fqn` |
| **FT-09** | 單元與邊界測試 | 驗證 `DeterministicSymbolResolver` 對同父型別 `Window.Open` 自動群組化展開 (`status="overload_group"`) 並聯集 `callers`/`callees`/`impact`，且支援 `Window.Open(string, int, int)` 參數簽名精確過濾（`EC-01`） | FR-03, EC-01 | `python yscb.py dev test --target=ast:TestOverloadAndTopology.test_ft_02_resolver_overload_group_vs_parameter_filtered_match` |
| **FT-10** | 邊界測試 | 驗證查詢短名 `Open` 橫跨 `UI.Window.Open` 與 `IO.File.Open` 不同父型別時拒絕盲猜，返回 `status="ambiguous"` 結構化候選清單與不存在符號錯誤提示（`EC-02`） | FR-03, EC-02 | `python yscb.py dev test --target=ast:TestOverloadAndTopology.test_et_01_resolver_cross_type_homonym_returns_ambiguous_candidates` |
| **FT-11** | 邊界測試 | 驗證 `GrammarProvisioner` 將動態 `pip install` 輸出 100% 導向 `sys.stderr`，且離線失敗時寫入 `_FAILED_PACKAGES` 會話級負快取不重複重試，保持 `stdout` 100% 純淨（`EC-04`） | FR-05, EC-04 | `python yscb.py dev test --target=ast:TestProvisionerAndJit.test_ft_01_provisioner_stderr_redirection_and_negative_cache` |
| **FT-12** | 整合與邊界測試 | 驗證 `ASTEngine.ensure_jit_synced()` 與 `hot_patch_index()` 在修改/刪除 C# 分部檔後自動剔除已刪分部成員、保留外部未變動檔案入度呼叫邊 (`ProcessCheckout -> Charge`) 並遞增 `ast_generation`（`EC-05`） | FR-02, FR-06, EC-05 | `python yscb.py dev test --target=ast:TestProvisionerAndJit.test_ft_02_ast_engine_jit_sync_hot_patch_and_external_edge_preservation` |
| **FT-13** | 整合測試 | 驗證 `scripts/hook.file-space.py` (`on_file_space_changed`) 自動消費 `file-space` diff、執行增量熱修補並向事件匯流排廣播 `on_ast_index_updated` | FR-06 | `python yscb.py dev test --target=ast:TestProvisionerAndJit.test_et_01_file_space_hook_handles_events_and_graceful_errors` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-13** | `Passed` | `python yscb.py dev check ast` (`[PASS]`) 與 `python yscb.py dev test ast` 全數通過：`18 Total, 18 Passed, 0 Failed`（含 3 項 Auto-Contract Suite 與 15 項 Custom Tests，含 `[REV-01]` 正交過濾測試）；實機安裝 `ast@build` 後執行 `yscb ast outline`（含 `--public --methods` / `--static` 正交過濾）與 `yscb ast status` 驗證通過。 | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py ast outline ys_codebase/source/core/core/uri.py`（含 `--public --methods` / `--protected` / `--static` / `--types` 等正交過濾）與 `python yscb.py ast status`，確認單檔結構大綱（含可見度、`[static]`、簽名、起訖行號）與 10 種已註冊語言解析器正常輸出 | `[測試通過]` | 開發者確認驗收通過 |
| **UX-02** | 執行 `python yscb.py dev test ast` 確認 18/18 測試案例（含 C# `partial class` `[Partial Siblings]`、`outline` 正交過濾、Method Overloads 群組展開與 `GrammarProvisioner` 離線圍欄）100% 通過 | `[測試通過]` | 開發者確認驗收通過 |

