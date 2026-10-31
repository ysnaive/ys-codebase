# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_dev_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Mode A` 相容別名、死例外與薄轉發層清除 (`M-01` ~ `M-05`) | 1. 物理刪除 `releaser.py` 之 `ReleasePipeline = Releaser` 別名 (`M-01`) 與 `ReleaseVersionExistsError`、`VersionRollbackError` 死例外 (`M-02`)。<br/>2. 物理刪除 `CheckReport.__iter__`、`__getitem__`、`__len__` 三元組/二元組解包相容魔術方法 (`M-03`)，所有調用端統一存取 `report.passed`、`report.warnings`、`report.errors`。<br/>3. 物理刪除 `Requirement.HOST_CLI`、`PERFORMANCE`、`STRESS` 枚舉別名與 `tester.py` / `runner.py` 內的 `"host_cli"` / `"performance"` 字串特判 (`M-04`)。<br/>4. 精簡 `scripts/cli.py:_normalize_bags` 參數正規化並消除各 `cmd_*` 函式頂部重複旗標展開樣板 (`M-05`)。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `Mode A` 殭屍參數、歷史分支與未引用匯入清除 (`M-06` ~ `M-12`) | 1. 移除 `Scaffolder.create_module` 未使用參數 `author` 與重複別名參數 `desc` (`M-06`)。<br/>2. 移除 `Releaser.release_all` 未使用參數 `skip_tests` (`M-07`)、`adapt_build_pip_dependencies` 未使用參數 `quiet` (`M-08`)、`filter_suite` 未使用參數 `active_types` (`M-09`)。<br/>3. 移除 `YSCBTestCase.tearDownClass` 空方法、無狀態類別空 `__init__`、將 `case.py` `create_mock_package` 預設版號改為 `"1.0.0.0"`，並移除 `testing/__init__.py` 多餘匯入 (`M-10`)。<br/>4. 刪除 `checker.py` 舊版 `def process(args)` 與 `"ISOLATE_SANDBOX"` 相容分支、刪除 `builder.py` 非壓縮目錄清理代碼、將 `cli.py:alias_map_skip` 收斂為私有輔助 (`M-11`)，並清除全模組未引用匯入與局部重複匯入 (`M-12`)。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 全模組 `uri.<io>` 轉發層遷移至 `vfs.<io>` 與 Context API 收斂 (`F-06`) | 1. 將 `ys_codebase/source/dev/` 內所有透過 `uri.exists`、`uri.is_dir`、`uri.is_file`、`uri.read_json`、`uri.write_json`、`uri.read_text`、`uri.write_text`、`uri.makedirs`、`uri.listdir`、`uri.rmtree` 之 I/O 調用 100% 遷移至 `core.vfs`。<br/>2. `case.py` 保存與還原 URI 上下文改用公開 `uri.get_host_dir()` / `uri.set_host_dir()`、`uri.get_yscb_root()` / `uri.set_yscb_root()`、`uri.get_module_context()` / `uri.set_module_context()` API。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-04** | `SandboxProvisioner` 鎖競爭修復、回滾閉環與階段拆解 (`F-01`, `F-05`, `S1`, `S4`) | 1. `cleanup_all_sandboxes` 全程於 `with SandboxProvisioner._SANDBOX_LOCK:` 保護下快照 `_ACTIVE_SANDBOXES` 並執行清理。<br/>2. `create_sandbox` 於配置沙盒目錄並註冊 `_ACTIVE_SANDBOXES` 後，將後續建置步驟包入 `try...except` 回滾保護，若建置中途失敗立即調用 `cleanup_sandbox` 清除孤兒目錄再向上拋出。<br/>3. 將 `create_sandbox` 拆解為 `_allocate_sandbox_root`、`_provision_core_and_config`、`_deploy_target_and_dependency_modules`、`_link_virtual_environment` 四階段。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | `Builder` 原子 Zip 打包管線合一與臨時檔防護 (`F-02`, `F-05`, `S1`, `S2`, `S4`) | 1. 抽取模組級純函式 `_create_module_archive_atomic(source_dir, target_zip_path, ignores, manifest_data, target_version) -> int`，供 `build_module` 與 `package_release` 共用。<br/>2. 以 `try...finally` 確保寫入 `.zip.tmp` 發生任何異常時必定清除殘留 `.zip.tmp` 檔案。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-06** | `Tester` 執行管線收斂与結構化配置 (`F-03`, `S1`, `S2`, `S3`) | 1. 定義 `_TestRunConfig` 資料結構封裝測試參數，消除重複旗標解析邏輯。<br/>2. 抽取 `_execute_single_module_in_sandbox` 統一處理沙盒建置、子進程 `op-test` 調用、JSON 報告讀取與沙盒清理，供單一模組與平行測試共用。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-07** | `Checker` 模組級純函式剝離與深層 AST 巢狀扁平化 (`F-04`, `F-09`, `S1`, `S2`, `S3`) | 1. 將 `_check_cli_compliance` 拆解為 `_collect_declared_cli_commands`、`_audit_cli_script_ast` 等明確階段函式。<br/>2. 將 `_check_test_classes` 拆解為 `_build_test_class_ast_entries` 與 `_verify_test_class_isolation_and_marks`，將巢狀深度壓降至 $\le 3$ 層，並顯式處理 AST 解析異常。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-08** | 模組依賴拓撲排序共用化與 `contract.py` 瘦身 (`F-07`, `F-08`) | 1. 於 `releaser.py` 抽取純函式 `resolve_module_dependency_order(available_modules, dep_map) -> List[str]` 統一實作 Kahn 字母序穩定拓撲排序。<br/>2. 更新 `contract.py` 移除 `CheckReport` tuple 解包並提取共用輔助方法，同步更新 `dev/tests/` 下所有受影響之測試案例。 | P1 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `SandboxProvisioner.create_sandbox` 建置中途（如缺少 `yscb.py` 或複製失敗）拋出例外 | `try...except` 捕獲例外後立即執行 `cleanup_sandbox(ctx.sandbox_dir, force=True)` 移除 `_ACTIVE_SANDBOXES` 紀錄與半成品目錄，並將原例外重新 `raise`。 |
| **EC-02** | `Builder` 執行 `_create_module_archive_atomic` 壓縮過程遭遇 I/O 或權限失敗 | `try...finally` 區塊檢測若 `tmp_zip_path` 仍存在於磁碟則強制刪除，確保 `module.build://` 與 `module.release://` 不殘留 `.zip.tmp`。 |
| **EC-03** | 多執行緒並行測試時同時呼叫 `cleanup_all_sandboxes` 與 `create_sandbox` | 全程持有 `_SANDBOX_LOCK` 可重入鎖並對 `_ACTIVE_SANDBOXES` 取快照 (`set(SandboxProvisioner._ACTIVE_SANDBOXES)`)，杜絕 `RuntimeError: Set changed size during iteration`。 |
| **EC-04** | `Releaser.release_all` 遭遇模組間循環依賴 | `resolve_module_dependency_order` 偵測 `len(topo_order) != len(available_modules)` 時拋出 `CyclicDependencyError` 並列出受阻模組清單。 |
| **EC-05** | 測試檔案或 `scripts/cli.py` 包含語法錯誤 (`SyntaxError`) | `Checker` 捕獲 `SyntaxError` 後轉為結構化 `CheckIssue(CheckSeverity.FAIL, "SYNTAX", ...)` 記錄行號與原因，絕不以空白 `except Exception: pass` 吞沒。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴與標準庫純淨度 | 100% 使用 Python 標準庫與 `core` 公開 SDK（`core.vfs`、`core.uri`、`core.semver`、`core.commands`、`core.events`），零新增外部套件依賴。 |
| **NFR-02** | 複雜度與程式碼行數收斂 | `Checker._check_test_classes` 業務邏輯巢狀深度壓降至 $\le 3$ 層；100% 清除 `M-01`~`M-12` 歷史相容別名與死代碼。 |
| **NFR-03** | 並行工作區隔離安全 | 實體寫檔嚴格限制於 `ys_codebase/source/dev/` 與 `plans/2026_10_30_1641_code_optimize/sub_02_dev_code_optimization/`，零跨模組修改。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `CheckReport` 移除 `__iter__` 後，`dev` 內部所有 `passed, errors = self.checker.check_module(name)` 調用點（包含 `builder.py`、`releaser.py`、`contract.py`）必須同步改為 `report = self.checker.check_module(name)` 並檢查 `report.passed` 與 `report.errors`。
- **`[!CAUTION]`** `test_checker.py` 中原先使用 `def process(args): return 0` 作為假模組 `scripts/cli.py` 最小樣板，移除 `Checker` 的 `def process(args)` 歷史相容分支後，`Checker` 針對無 `contributes/core.json` 的模組仍需驗證 `scripts/cli.py` 至少宣告一個合規命令處理函式（如 `def hello(cmd_bags): ...`），且 `test_checker.py` 中的測試樣板須同步更新為標準 `CmdBags` 簽名。
