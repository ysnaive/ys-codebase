# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_ast_engine_and_parsers_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `GrammarProvisioner.load_language` 在慢速 `_try_pip_install` 期間不阻塞其他語言 `load_language` 與 `get_warnings()`，且同語言並發請求透過 `_INFLIGHT_EVENTS` 僅觸發單次安裝 (`EC-01`, `NFR-01`) | FR-01, EC-01, NFR-01 | `python3 -W error::ResourceWarning yscb.py dev test --target=ast:TestProvisionerAndJit` |
| **FT-02** | 單元測試 | 驗證重載方法 `slice_part` 精準定位各重載定義、限定名基底型別 (`pkg.Base`) 繼承解析、`expand_contract_symbol_ids` 雙軌 ID 映射、多根同名 `sub/mod.py` 熱修補消歧 (`EC-02`)、游標異常回滾、分部深拷貝還原與多跳 Barrel Re-export 傳遞鏈 | FR-02, FR-03, EC-02 | `python3 -W error::ResourceWarning yscb.py dev test --target=ast:TestOverloadAndTopology` |
| **ET-01** | 邊界測試 | 驗證 C++ `Outer::Inner::compute` 類外作用域保留、Python `self.x` 重複賦值不產生偽重載、`tree_sitter` 缺失時自動降級 `PythonASTParser`/`MarkdownParser` (`EC-03`)、多行簽名與 UTF-8 多位元組列號，以及 HTML/CSS/SPICE/Markdown 邊界解析 | FR-04, EC-03 | `python3 -W error::ResourceWarning yscb.py dev test --target=ast:TestDialectsAndParsers` |
| **RT-01** | 回歸與效能測試 | 驗證 `SymbolNode` 巢狀 `facets` 深度凍結與 JSON 序列化、快照雙檔 `InterProcessLock`、合流交換律、`SymbolSelector.parse` 泛型選擇器、`FileSymbolGraph`/`WorkspaceSymbolGraph` 序列化去重 (`NFR-02`)、`PythonASTParser` 巢狀函式提取，以及 `knowledge-db` 下游相容性 | FR-05, NFR-02 | `python3 -W error::ResourceWarning yscb.py dev check && python3 -W error::ResourceWarning yscb.py dev test --m ast && python3 -W error::ResourceWarning yscb.py dev test --m knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestProvisionerAndJit` 6/6 測試全數通過，驗證雙執行緒並發請求同一缺失語法套件僅執行 1 次 `_try_pip_install`，且 `hot_patch_index` 拋出例外時游標不提交並於下次 `ensure_jit_synced` 自動重試恢復。 | 2026-11-09 |
| **FT-02** | `Passed` | `TestOverloadAndTopology` 與 `TestDeterministicLinker` 全數通過，驗證同名重載 `slice_part("parameters")` 精確返回各自參數、多跳 Barrel Re-export 與字母序無關（`ws_fwd.to_dict() == ws_rev.to_dict()`）、多根空間 `sub/mod.py` 依 `mtime` 與 `known_indexed_files` 精準消歧。 | 2026-11-09 |
| **ET-01** | `Passed` | `TestDialectsAndParsers` 全數通過，驗證 `Outer::Inner::compute` 拆解出 `Outer::Inner` 父作用域、`super()._svc.` 正規化為 `self._svc`、`PythonASTParser` 提取巢狀 `_format_msg` 與 `self.logger.client`、以及 HTML/CSS/SPICE/Markdown 註解與未閉合區塊防護。 | 2026-11-09 |
| **RT-01** | `Passed` | `dev check` 9/9 模組 PASS（0 Warnings, 0 Errors）；`dev test --m ast` 52/52 通過（3 Contract + 49 Custom，耗時 3.94s，0 `ResourceWarning`）；`dev test --m knowledge-db` 113/113 通過（3 Contract + 110 Custom，耗時 3.92s，0 `ResourceWarning`）。 | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python3 -W error::ResourceWarning yscb.py dev check`、`dev test --m ast` 與 `dev test --m knowledge-db`，確認 0 違規、0 `ResourceWarning` 且全部 165 項單元測試 100% 通過 | `[測試通過]` | 沙盒實機驗證 9/9 模組 Check PASS，`ast` (52/52) 與 `knowledge-db` (113/113) 100% 通過 |
