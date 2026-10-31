# 技術調研報告：`dev` 模組五維度靜態診斷與 Mode A 無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：sub_02_dev_code_optimization (`dev` 模組五維度靜態診斷與 Mode A 無損重構處方)  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **巨型單體類別與深層巢狀控制流（`D1` / `D3`）**：`ys_codebase/source/dev/dev/checker.py`（1,136 LOC）將 8 大靜態合規檢查步驟全部耦合於單一 `Checker` 類別，其中 `_check_test_classes`（`L813-921`）混雜 AST 繼承圖走訪與正則退避，巢狀深度高達 8~11 層；`tester.py`（778 LOC）之 `_run_op_test`（299 LOC）與 `_run_test`（218 LOC）控制流膨脹且重複。
  2. **跨層重複管線與樣板代碼（`D2` / `D3`）**：`builder.py` 的 `build_module` 與 `build_to_mirror` 重複實作 Zip 打包與過濾迴圈；`tester.py` 將 CLI 旗標先在 `_run_test` 轉為字串陣列、又在 `_run_op_test` 重新解析並重複組裝單一/平行子進程；`scripts/cli.py:_normalize_bags` 手刻 68 行參數正規化，與 `core.commands` 標準 `CmdBags` 管線脫節；`dev` 內多達 42 處混用 `uri.<io>` 轉發層且直接存取 `core.uri` 私有方法（`uri._get_yscb_root()`、`uri._get_host_config()`）。
  3. **資源生命週期與並發鎖對稱缺口（`D4`）**：`SandboxProvisioner.create_sandbox`（`sandbox.py:553, 581`）在 `try...except` 回滾區塊外才註冊 `_ACTIVE_SANDBOXES`，若建置中途失敗將遺留孤兒沙盒；`cleanup_all_sandboxes`（`L244`）遍歷並修改 `_ACTIVE_SANDBOXES` 時未持有 `_SANDBOX_LOCK`；`builder.py` 寫入 `.zip.tmp` 缺乏 `try...finally` 異常清理；`builder.py`、`sandbox.py`、`checker.py` 多處以 `except Exception: pass` 靜默吞沒錯誤。
  4. **過渡別名、殭屍參數與死分支殘留（`D2` / `D5`）**：殘留 `ReleasePipeline = Releaser`、`CheckReport.__iter__/__getitem__/__len__` 三元組解包相容介面、`Requirement.{HOST_CLI,PERFORMANCE,STRESS}` 雙重枚舉別名、`ReleaseVersionExistsError`/`VersionRollbackError` 0 調用例外，以及 `author`/`desc`/`skip_tests`/`quiet`/`active_types` 等殭屍參數與 `def process(args)`/`ISOLATE_SANDBOX` 死分支。
- **調研目標**：
  - 鎖定 **範圍 = 單一模組（`ys_codebase/source/dev/`，含 `dev/` 12 檔與 `scripts/cli.py` 1 檔，共 13 檔 / 4,813 LOC）** 與 **生命週期 = `Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`**。
  - 融合雙子代理（Auditor A / Auditor B）獨立盲測結果，建立完整基線盤點、`Mode A` 破壞性清除清冊（12 大項）、`D1~D5` 分級問題單（`P0/P1/P2`）與 `S1~S6` 無損重構處方。

### 1.1 `dev` 模組基線盤點表 (13 檔 / 4,813 LOC)

| 檔案路徑 (`ys_codebase/source/dev/...`) | 行數 (LOC) | 核心職責與主要類別/函式 | 入向耦合 (`dev` 內 / 跨模組) | 診斷熱點等級 |
| :--- | :---: | :--- | :--- | :---: |
| `dev/checker.py` | 1,136 | `Checker`、`CheckReport`：8 步模組靜態合規檢查與 AST 分析 | `builder`、`releaser`、`contract`、`cli`、`tests/` | **P0 / P1** |
| `dev/tester.py` | 778 | `Tester`：沙盒測試編排、平行/單一進程派發、JUnit XML 彙整 | `releaser`、`cli`、`tests/` | **P0 / P1** |
| `dev/testing/sandbox.py` | 584 | `SandboxProvisioner`：隔離沙盒環境建置、模組部署、Junction/Symlink 與清理 | `tester`、`case`、`tests/` | **P0 / P1** |
| `dev/testing/contract.py` | 483 | `ModuleContractTestMixin`、`BaseModuleContractTestCase`：6 項標準合約測試 | 全生態系模組 `tests/test_contract.py` | **P1 / P2** |
| `scripts/cli.py` | 462 | `dev` CLI 路由入口（`create`/`check`/`build`/`test`/`release`/`clean`） | `core.dispatcher`、`tests/` | **P1** |
| `dev/builder.py` | 369 | `Builder`：模組打包、`@build` 本地安裝與 `.mirror` 歸檔 | `releaser`、`sandbox`、`cli`、`tests/` | **P0 / P1** |
| `dev/releaser.py` | 299 | `Releaser`：單模組與全生態系拓撲排序發布管線 | `cli`、`tests/` | **P1** |
| `dev/scaffold.py` | 262 | `Scaffolder`：新模組標準骨架與模板生成 | `cli`、`tests/` | **P1 / P2** |
| `dev/testing/case.py` | 228 | `YSCBTestCase`：沙盒生命週期整合與 CLI 測試輔助斷言 | 全生態系模組 `tests/` | **P1 / P2** |
| `dev/testing/runner.py` | 150 | `XMLTestRunner`、`_XMLTestResult`、`filter_suite`：測試過濾與 XML 輸出 | `tester`、`tests/` | **P1** |
| `dev/testing/requirement.py` | 35 | `Requirement`、`requires`：測試環境需求標記枚舉與裝飾器 | `case`、`runner`、`tester`、`tests/` | **P1** |
| `dev/testing/__init__.py` | 19 | `dev.testing` 公開匯出門面 | 全生態系模組 `tests/` | **P2** |
| `dev/__init__.py` | 8 | `dev` 頂層套件標記 | `dev` | Clean |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：`Mode A` 全面破壞性收斂 + 結構拆解**<br/>*(Recommended — Full Track)* | 徹底移除 `ReleasePipeline`、`CheckReport` tuple 解包介面、`Requirement` 舊枚舉別名、`def process(args)` 分支與所有殭屍參數；將 `Checker` 拆分為獨立規則驗證器、合併 `Tester` 與 `Builder` 重複管線、補齊 `SandboxProvisioner` 鎖與回滾保證，並將 `dev` 內 42 處 `uri.<io>` 全面遷移至 `vfs.<io>`。 | 100% 消除歷史相容負債與資源洩漏風險，預計淨減 ~500 LOC，大幅降低 `checker.py` 與 `tester.py` 維護成本。 | 需同步更新 `dev/tests/` 中依賴舊別名或 tuple 解包的斷言（約 6 處測試檔）。 | ⭐⭐⭐⭐⭐ **(推薦)** |
| **方案 B：保守局部重構（保留相容別名與舊分支）** | 僅拆分內部私有長函式，保留 `ReleasePipeline`、`CheckReport.__iter__`、`Requirement` 別名與 `_normalize_bags`。 | 不需修改既有測試案例。 | 違背 `Mode A` 原則，雙軌別名與死代碼持續污染語意空間。 | ⭐⭐ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `Mode A` 公開入口收斂、薄轉發層、相容別名與死代碼清除清冊 (`S5`)

| 編號 | 檔案與行號座標 | 冗餘轉發 / 相容別名 / 死代碼 | 調用方盤點（`dev` 內部 / 跨模組 / `tests/`） | `Mode A` 物理清除與收斂處方 (`S5`) |
| :---: | :--- | :--- | :--- | :--- |
| **M-01** | `dev/releaser.py:298` | `ReleasePipeline = Releaser` 類別別名 | 生產代碼 **0 callers**；僅 `dev/tests/test_release_pipeline.py:7, 29, 36, 46` 引用 | 物理刪除 `ReleasePipeline = Releaser`；將 `test_release_pipeline.py` 統一改用正統名稱 `Releaser`。 |
| **M-02** | `dev/releaser.py:22-28` | `ReleaseVersionExistsError`、`VersionRollbackError` 死例外類別 | 全倉 **0 callers**（連 `releaser.py` 自身皆未 `raise`） | 直接物理刪除 `releaser.py:22-28`（保留實際使用之 `ReleaseError`）。 |
| **M-03** | `dev/checker.py:79-87` | `CheckReport.__iter__`、`__getitem__`、`__len__` 舊式 3-tuple `(passed, warnings, errors)` 解包相容魔術方法 | `builder.py:186`、`releaser.py:76`、`contract.py:29`、`test_dev_pipeline.py:42`、`test_checker.py` | 物理刪除 `CheckReport` 3 個序列魔術方法；所有調用端統一改為存取具名屬性 `report.passed`、`report.warnings`、`report.errors`。 |
| **M-04** | `dev/testing/requirement.py:19, 23, 24`<br/>`dev/tester.py:171`<br/>`dev/testing/runner.py:31, 38-39` | `Requirement.HOST_CLI` (`= CORE_CLI`)、`PERFORMANCE` (`= BENCHMARK`)、`STRESS` (`= BENCHMARK`) 枚舉別名，與 `tester.py` / `runner.py` 內的 `"host_cli"` / `"performance"` 字串特判 | 跨模組 **0 callers**；僅 `dev/tests/test_tester.py:28`、`test_case.py:118-119` 引用 | 物理刪除 3 個枚舉別名與 `"host_cli"` / `"performance"` 字串分支；正統枚舉收斂為 `CLEAN_ENV`、`ISOLATED_SANDBOX`、`CORE_CLI`、`BENCHMARK`、`NETWORK`。 |
| **M-05** | `scripts/cli.py:16-83` | `_normalize_bags(args_or_bags)` 68 行手刻參數解析器與全數 `cmd_*` 函式頂部樣板 | 生產環境由 `core.dispatcher` 直接傳入 `CmdBags`；僅 `test_cli.py` 傳入 `list` | 移除手刻解析迴圈，改為若非 `CmdBags` 則直接委派 `core.commands.parse_cli_args_to_bags`（或於測試統一傳入 `CmdBags`）。 |
| **M-06** | `dev/scaffold.py:13, 24` | `Scaffolder.create_module(self, name, description="", author="YSCB Developer", desc=None)` 之未使用參數 `author` 與重複別名參數 `desc` | `scripts/cli.py:92` 傳入 `description`；僅 `test_dev_pipeline.py:33` 傳入 `desc=` | 物理移除 `author` 與 `desc` 參數，簽名收斂為 `create_module(self, name: str, description: str = "") -> str`，並更新 `test_dev_pipeline.py:33`。 |
| **M-07** | `dev/releaser.py:149` | `Releaser.release_all(self, bump=None, dry_run=False, skip_tests=False)` 之未使用參數 `skip_tests` | 全倉 **0 callers** 傳入 `skip_tests`，且函式體完全未讀取 | 物理移除 `skip_tests: bool = False` 參數。 |
| **M-08** | `dev/testing/sandbox.py:266-269` | `adapt_build_pip_dependencies(yscb_dir, mod_name, target_dir, quiet=False)` 之未使用參數 `quiet` | `tester.py:645`、`sandbox.py:445`、`test_sandbox.py:261, 265` | 物理移除未使用的 `quiet` 參數並同步更新 4 處調用點。 |
| **M-09** | `dev/testing/runner.py:15-20, 28` | `filter_suite(..., active_types: Optional[set] = None)` 之 0 調用參數與分支 | 全倉 **0 callers** 傳入 `active_types` | 物理移除 `active_types` 參數與 `L28` 過濾分支。 |
| **M-10** | `dev/testing/case.py:60-63, 181`<br/>`dev/testing/__init__.py:7, 17`<br/>`scaffold.py:10`、`checker.py:91`、`tester.py:43` | `YSCBTestCase.tearDownClass` 空方法（`pass`）、3 個無狀態類別之空 `__init__`、`case.py:181` 過時 3 碼預設版號 `"1.0.0"`、以及 `__init__.py` 未列入 `__all__` 之內部類別 `BaseModuleContractTestCase` | 內部無狀態實例化與合約測試繼承 | 刪除空 `tearDownClass` 與空 `__init__`；將 `case.py:181` 預設版號改為符合 4 碼規範之 `"1.0.0.0"`；移除 `testing/__init__.py` 對內部 `BaseModuleContractTestCase` 的多餘匯入。 |
| **M-11** | `dev/checker.py:590, 602-603, 676-685, 838`<br/>`dev/builder.py:86-88, 134-135, 268-270`<br/>`scripts/cli.py:349` | `checker.py` 舊版 `def process(args)` 簽名相容分支与 `"ISOLATE_SANDBOX"` 拼字容錯分支；`builder.py` 舊版 `.mirror/<mod>/<ver>/` 非壓縮目錄清理代碼；`cli.py:349` 單次使用卻暴露為公開名稱之 `alias_map_skip` | 全倉已無 `def process(args)` 或非壓縮 mirror 目錄 | 物理刪除上述歷史過渡分支；將 `alias_map_skip` 內聯或改為私有常數 `_SKIP_REQ_MAP`。 |
| **M-12** | 7 支檔案頂部與局部匯入 | 未引用之死匯入：`scaffold.py:4` (`Path`)、`builder.py:9,15` (` tempfile`, `Tuple`)、`releaser.py:11-12` (`Set`, ` Optional`)、`tester.py:13` (` Optional`)、`case.py:9-10` (` Optional`, `Callable`)、`runner.py:6` (` Optional`)、`cli.py:8` (` Optional`)，以及 `checker.py:638, 1045` 與 `sandbox.py:110-111, 131-132` 函式內重複 `import` | **0 references** | 物理清除所有未引用匯入，並將局部重複 `import` 提升至模組頂層。 |

---

### 3.2 五維度靜態診斷問題單 (`D1~D5` × `P0/P1/P2`)

| 編號 | 維度 | 嚴重度 | 座標 (`file:line`) | 病徵描述與根因剖析 | 對應重構策略 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | **D4** | **P0** | `dev/testing/sandbox.py:244` & `L447-583` | **沙盒註冊時序漏洞與並發鎖缺失 (`Scoped Resource Lifecycle`)**：`create_sandbox` 在 `L553` 的 `try...except` 回滾區塊結束後才於 `L581` 將路徑加入 `_ACTIVE_SANDBOXES`；且 `cleanup_all_sandboxes` (`L244`) 在未持有 `_SANDBOX_LOCK` 的情況下遍歷與 `.discard()` 全域集合，多執行緒下存在 `RuntimeError: Set changed size during iteration` 風險。 | **S4**（進入建置即在鎖保護下註冊，清理全程加鎖） |
| **F-02** | **D3 / D4** | **P0** | `dev/builder.py:172-308` | **雙重 Zip 打包管線重複與 `.zip.tmp` 異常殘留**：`build_module` (`L196-205`) 與 `build_to_mirror` (`L283-303`) 各自重複實作 `os.walk` + `_should_exclude` + `zipfile.ZipFile` 壓縮迴圈；且寫入 `.zip.tmp` 時未使用 `try...finally` 確保壓縮失敗時清除臨時檔。 | **S1 + S2 + S4**（抽取 `_create_module_archive_atomic`） |
| **F-03** | **D1 / D3** | **P0** | `dev/tester.py:192-710` | **CLI 參數雙重序列化與測試執行管線重複 (`_run_test` 218 LOC + `_run_op_test` 299 LOC)**：`_run_test` 將旗標轉為 `cmd_args` 字串陣列後傳給同進程的 `_run_op_test` 重新迴圈解析；且 `_run_test` 與 `_run_op_test` 重複實作 `failures`/`errors` 格式化迴圈，`_run_op_test` 內單一模組與 `ThreadPoolExecutor` 平行分支又重複實作沙盒建置與子進程調用。 | **S1 + S2 + S3**（引入 `_TestRunOptions` 與 `_execute_module_in_sandbox`） |
| **F-04** | **D1 / D3** | **P0** | `dev/checker.py:90-1136` | **`Checker` 1,136 行單體巨獸與 11 層深層巢狀**：`Checker` 無任何實例狀態卻塞入 8 大檢查步驟；`_check_test_classes` (`L813-921`) 在單一函式內混雜多檔 AST 繼承圖走訪與正則退避，巢狀達 8~11 層；`_check_cli_scripts` (`L579-702`) 混雜多種 AST 訪問職責。 | **S1 + S2 + S3**（詳見 §3.3） |
| **F-05** | **D4** | **P0** | `dev/builder.py:216-249`<br/>`dev/testing/sandbox.py:201-235`<br/>`dev/checker.py:861, 882` | **大面積 `except Exception: pass` 靜默吞噬異常**：`builder.py` 安裝 `@build` 失敗時吞掉 `AtomicEngine` 例外並回傳 `True`；`sandbox.py` 失敗時靜默吞掉備份還原與刪除錯誤；`checker.py` 吞掉語法解析例外卻未在報告留下診斷訊息。 | **S4**（改為精確捕獲 `OSError`/`SyntaxError` 並顯式記錄警告或拋出） |
| **F-06** | **D2** | **P1** | `dev/builder.py:23, 326`<br/>`dev/testing/sandbox.py:143`<br/>`dev/testing/case.py:55`<br/>全模組 42 處 `uri.<io>` | **跨模組穿透 `core.uri` 私有 API 與混用 `uri.<io>` 薄轉發層**：`builder.py` 與 `sandbox.py` 直接呼叫 `uri._get_yscb_root()` / `uri._get_host_config()`，`case.py` 直接讀寫 `uri._active_workspace_root` 等 3 個私有全域變數；且全模組有 42 處呼叫 `uri.exists`/`uri.read_json` 等轉發函式。 | **S5 + S6**（全面改用 `vfs.<io>` 與 `uri` 公開 Context API） |
| **F-07** | **D2 / D3** | **P1** | `dev/builder.py:157-170`<br/>`dev/releaser.py:194-224`<br/>`dev/testing/sandbox.py:390-416` | **3 處重複實作 `manifest.json` 依賴提取與拓撲排序**：`builder.extract_dependencies_from_manifest`、`releaser._topological_sort_modules` 與 `sandbox._resolve_dependency_order` 各自解析 `dependencies` 字典/陣列並執行 Kahn 演算法拓撲排序。 | **S2 + S3**（抽取共用純函式 `resolve_module_dependency_order`） |
| **F-08** | **D3** | **P1** | `dev/testing/contract.py:84-465` | **`contract.py` 5 處重複的專案根目錄與模組源碼路徑推導**：`test_02`~`test_06` 各自重複呼叫 `os.path.dirname` 鏈與 `uri.resolve("project://source/...")` 推導 `mod_dir`，且 `test_02_contributes_schema_validation` 長達 121 行、巢狀 7 層。 | **S1 + S3**（抽取 `self._get_module_source_path()` 並拆解 `test_02`） |
| **F-09** | **D3 / D4** | **P2** | `dev/checker.py:345`<br/>`dev/testing/contract.py:372`<br/>`dev/tester.py:331` | **檢查規則雙重維護與常數重複**：標準頂層目錄白名單在 `checker.py` 與 `contract.py` 重複硬編碼（`contract.py` 還多出過時的 `"workflows"`）；`tester.py` 多處重複組裝 `[sys.executable, yscb_bin]`。 | **S3 + S5**（統一引用 `Checker.ALLOWED_TOP_LEVEL_DIRS` 單一常數） |

---

### 3.3 `S1` 業務階段邏輯聚合與 `S2` 無狀態邏輯剝離藍圖（6 大核心檔案）

#### 1. `dev/checker.py` (`Checker`, 1,136 LOC $\to$ 預估 ~720 LOC)
* **`S2` 無狀態邏輯剝離**：`Checker` 本身不持有任何實例屬性，將底層 AST 與檔案檢查輔助函式剝離為模組級純函式（或 `@staticmethod`），並將 `ALLOWED_TOP_LEVEL_DIRS`、`LIFECYCLE_HOOK_SIGNATURES` 提升為模組級公開常數供 `contract.py` 共用。
* **`S1` 業務階段拆解**：
  - `_check_cli_scripts`（原 `L579-702`，124 LOC）$\to$ 拆為 `_collect_declared_cli_Uris(mod_dir)`、`_audit_cli_script_ast(script_path, func_name, report)`、`_verify_cli_main_dispatch(tree, script_path, report)`。
  - `_check_test_classes`（原 `L813-921`，109 LOC，8~11 層巢狀）$\to$ 拆為：
    1. `_build_test_class_inheritance_map(tests_dir) -> Dict[str, Tuple[List[str], List[str], str]]`（第一階段：單層 AST 掃描收集所有測試類別之基類與裝飾器）
    2. `_ verify_test_class_isolation_and_contract(class_map, mod_name, report)`（第二階段：扁平化檢查 `YSCBTestCase` 繼承鏈、需求裝飾器與 `BaseModuleContractTestCase` 覆蓋率，巢狀壓降至 $\le 3$ 層）

#### 2. `dev/tester.py` (`Tester`, 778 LOC $\to$ 預估 ~460 LOC)
* **`S1 + S2 + S3` 管線收斂**：
  - 定義不可變資料類別 `_TestRunConfig(target, level, enable_Set, skip_set, parallel, ...)`，消除 `_run_test` $\to$ `_run_op_test` 的 CLI 字串陣列二次反序列化。
  - 抽取 `_execute_single_module_in_sandbox(mod_name, config) -> Tuple[int, str, str]`，讓單一模組執行與 `ThreadPoolExecutor` 平行執行 100% 共用同一套沙盒建置、子進程啟動與清理閉環。
  - 抽取 `_print_suite_failure_details(results: List[Dict])`，消除 `_run_test` (`L354-365`) 與 `_run_op_test` (`L680-693`) 的重複錯誤列印迴圈。

#### 3. `dev/builder.py` (`Builder`, 369 LOC $\to$ 預估 ~240 LOC)
* **`S1 + S2 + S4` 原子打包抽取**：
  - 抽取模組級純函式 `_create_module_archive_atomic(source_dir: str, target_zip_path: str) -> None`：統一處理 `_should_exclude` 過濾、`.zip.tmp` 寫入、`os.replace` 原子替換，並以 `try...finally` 保證異常時清除 `.zip.tmp`，供 `build_module` 與 `build_to_mirror` 共用。
  - `build_module` 拆為 `_validate_module_before_build`、`_create_module_archive_atomic`、`_install_local_build_package` 三階段，並移除吞噬安裝異常的 `except Exception: pass`。

#### 4. `dev/testing/sandbox.py` (`SandboxProvisioner`, 584 LOC $\to$ 預估 ~450 LOC)
* **`S1 + S4` 資源安全與階段拆解**：
  - `cleanup_all_sandboxes` 全程於 `with _SANDBOX_LOCK:` 保護下複製並清理 `_ACTIVE_SANDBOXES`。
  - `create_sandbox`（原 `L447-583`，137 LOC）於建立臨時目錄當下即納入 `try...except` 回滾保護與 `_ACTIVE_SANDBOXES` 註冊，並拆解為 `_allocate_sandbox_root`、`_provision_core_and_config`、`_deploy_target_and_dependency_modules`、`_link_virtual_environment` 四個明確階段。

#### 5. `dev/releaser.py` & `dev/testing/contract.py`
* **`S2 + S3` 拓撲排序與合約測試瘦身**：
  - 將模組依賴提取與 Kahn 拓撲排序統一收斂為共用純函式，消除 `builder.py`、`releaser.py`、`sandbox.py` 三處重複實作。
  - `contract.py` 提取 `_get_module_source_root()` 消除 5 處路徑推導樣板，並將 `test_02_contributes_schema_validation` (121 LOC) 拆解為 Schema 載入、Donor 驗證與 Locale 驗證三個輔助方法，同時移除 `test_05` 中過時的 `"workflows"` 目錄白名單。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  - 採納 **方案 A（`Mode A` 全面破壞性收斂 + 結構拆解）**，於後續啟動實作時將本子計畫 `sub_02_dev_code_optimization` 原地升級為 **標準開發計畫 (`Full Track`, `P01~P07`)**。
  - **預估量化收益**：
    1. 物理清除 **12 大類歷史別名、死例外、殭屍參數、舊版分支與未引用匯入**，合併重複打包/測試/拓撲排序管線，預計淨減約 **450~550 LOC**。
    2. 徹底修復 `SandboxProvisioner` 鎖競爭與異常回滾缺口、`Builder` `.zip.tmp` 殘留風險，以及多處 `except Exception: pass` 靜默吞錯問題。
    3. 將 `Checker._check_test_classes` 巢狀深度由 **11 層** 壓降至 **$\le 3$ 層**，將 `Tester._run_op_test` 由 **299 LOC** 壓降至 **$\le 60$ LOC**。
- **後續行動與 P00 銜接（Step 3 三大流轉出口）**：
  1. **出口 ① 立即/後續升級實作（推薦）**：將 `R01_code_optimization_audit.md` 標記為 `Concluded`，並於 `sub_02_dev_code_optimization` 原地追加 `P01~P07` 升級為 `Full Track` 實作計畫。
  2. **出口 ② 轉入長期技術儲備**：轉入 `/roadmap` 或 `/todo` 分批排程。
  3. **出口 ③ 結案存檔**：僅保留調研診斷報告備查。
