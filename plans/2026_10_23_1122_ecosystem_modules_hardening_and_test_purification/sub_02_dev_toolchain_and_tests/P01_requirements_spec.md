# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev test` / `op-test` / `op-mksb` CLI 選項契約對齊與無損傳遞 (`D-01`) | 1. 於 `contributes/core.json` 為 `test`、`op-test`、`op-mksb` 補齊完整 `options` 宣告（含 `sequential`/`no-parallel`、`pattern`/`k`、`contract-only`、`logical`/`env`/`workflow`/`perf`/`all-types`、`report-json`、`quiet-report`、`dir`），並修正 `--sync` 描述。<br/>2. 強化 `scripts/cli.py:_normalize_bags` 支援帶值短/長選項與別名正規化；於 `Tester._run_test` 將子進程 `op_test_args` 正規化為 `--pattern=<val>`、`--quiet`、`--verbose`，確保 `-k <pat>` 不再覆寫 `target_mod`，且 `-v`/`-q`/`--sequential` 在沙盒子進程內 100% 生效。 | P0 | 核心目標 1 |
| **FR-02** | `Releaser` Gate 3 全庫最高版本防回退與發布流水線加固 (`D-02`) | 1. 升級 `Releaser.release_check` Gate 3 為全庫最高版本 (`global_highest`) 單調遞增校驗：未帶 `force` 時要求 `target > global_highest`，帶 `force=True` 時僅容許 `target == global_highest` 覆蓋，嚴禁跨三元組版本回退（`target < global_highest`）。<br/>2. `release_all` 依模組名字母序穩定初始化 Kahn DAG 佇列，且上游模組發布失敗時自動跳過並標記所有下游依賴模組失敗。<br/>3. `release_git` 傳遞 `_skip_check=True` 消除重複預檢，並檢查 `git commit` 非零退出碼：僅容忍 `nothing to commit` / `working tree clean`，其餘錯誤立即回傳 `False` 並中止打 Tag。<br/>4. `scripts/cli.py:release_check` 支援無參數預設全模組，並過濾不含 `manifest.json` 之目錄。 | P0 | 核心目標 2 |
| **FR-03** | 測試引擎 `UNKNOWN > 0` 剛性阻斷、`NETWORK` 正交發現與 `_FailedTest` 保留 (`D-03`) | 1. 修正 `Tester._run_op_test` 與 `runner.py` 中 `custom_passed = max(0, custom_total - custom_failed - custom_skipped - mod_unknown)`；當 `mod_unknown > 0` 時強制將 `all_passed` 與 `mod_info["passed"]` 設為 `False`、回傳 Exit Code `1`，並列出漏呼叫 `self.mark_passed()` 之測試方法。<br/>2. 於 `VALID_TYPES` 與 `filter_suite` 預設 `resolved_types` 納入 `"network"`，使 `@require(Requirement.NETWORK)` 測試在離線環境正常觸發 `SkipTest` 計入 `Skipped`。<br/>3. `filter_suite` 對 `_FailedTest`（語法錯誤或匯入失敗）在任何 `--type` 下強制保留不濾除。 | P0 | 核心目標 3 |
| **FR-04** | `Checker` 跨模組自訂規則載入、源碼 Schema 優先讀取與 CLI 對稱檢核 (`D-04`) | 1. `_check_custom_rules` 支援 `code.func://<donor>/<path>:<func>`、`mod:func` 與 `mod.func` 語法，載入前僅將 `uri.resolve(f"module://{donor}")` 臨時加入 `sys.path`（嚴守 `[P00:DR-02]` 絕不注入 `module.source://`），且載入/執行異常轉為 `CheckSeverity.WARN` 不再靜默吞沒。<br/>2. `_check_core_injection` 優先讀取 `module.source://<target>/contributes/_format.json`，不存在時方回退 `core.contributes.get_format(target)`。<br/>3. `_check_cli_compliance` 嚴格對齊 `[P00:DR-01]`，葉節點命令合法候選函式限定為 `candidates = {full_fn, primary_fn}`，移除無效之 `leaf_fn` 與 `cmd_*`。 | P0 | 核心目標 4, [P00:DR-01], [P00:DR-02] |
| **FR-05** | 腳手架與沙盒 Mock 產生器 `CmdBags` 現代化 (`D-05`) | 1. `Scaffolder` 生成之 `scripts/cli.py` 改為 `def hello(cmd_bags: CmdBags) -> int:`（移除 `def process(args)` 與手動 `sys.path.insert`），修正 `tests/__init__.py` 字面 `\\n` 殘留，並使生成的 `tests/test_basic.py` 實質呼叫 `hello()`。<br/>2. `SandboxProvisioner.create_mock_package` 與 `YSCBTestCase.create_mock_source_module` 預設生成合規 `def hello(cmd_bags): return 0`、`contributes/core.json` 與 `contributes/_manifest.md`，使預設 Mock 模組 0 Error / 0 Warning 通過 `Checker.check_module()`。 | P0 | 核心目標 4 |
| **FR-06** | 沙盒 SemVer 排序、`YSCBTestCase` CWD 還原與 `Builder` `clean` 參數修復 (`D-06`) | 1. `SandboxProvisioner` 在挑選 `.build/<mod>/*.zip` 與排序 `index.json` 版本時改用 `core.semver.compare_semver` 取代字典序 `sorted()`，並對損毀 `.build` zip 加上 `BadZipFile` 防護。<br/>2. `YSCBTestCase.setUp` 記錄 `self._orig_cwd = os.getcwd()` 並於 `tearDown` 自動還原。<br/>3. `Builder.build_module(name, clean=True)` 僅於 `clean=True` 時清空 `real_build_dir`。 | P1 | 核心目標 4 |
| **FR-07** | `yscb-module-dev` 技能手冊、`contributes` 事件宣告與 PEP 562 延遲載入同步 (`D-07`, `D-08`) | 1. 修正 `assets/skills/yscb-module-dev/references/cli_and_commands.md` 中 `CmdBags` 存取範例（`cmd_bags.args[0]`、`cmd_bags.get_option_value()`、`cmd_bags.raw_cmd`）、預設版號 `0.1.0.0`、`.build` 產物路徑與 3-Gate 說明，並同步更新 `README.md`、`contributes/_manifest.md` 與 `docs/dev/DESIGN_NOTES.md` (`[DN-DEV-04]`)。<br/>2. 於 `contributes/core.json` 頂層註冊 `events`（`on_test_setup`、`on_test_teardown`）。<br/>3. 於 `dev/__init__.py` 補匯出 `Releaser` 並實作 PEP 562 `__getattr__` 延遲載入；`scripts/cli.py` 改為函式內按需匯入。 | P1 | 核心目標 1, 4 |
| **FR-08** | `dev/tests/` 10 檔收斂為 7 檔、消除雙重跑測與資源洩漏 (`DT-01`~`DT-04`) | 1. 裁撤 `test_cli_compliance.py`、`test_output_purification.py`、`test_pip_adaptation.py` 3 個碎片檔，無損拆併入 7 個子系統測試檔（`test_scaffold.py`, `test_checker.py`, `test_builder.py`, `test_release_pipeline.py`, `test_sandbox.py`, `test_case.py`, `test_tester.py`），並將 `test_sandbox.py` 內屬 `runner/tester` 之測試移交 `test_tester.py`。<br/>2. 將 `DummySharedTestCase` 移入測試方法局部作用域消除頂層雙重發現；移除 `_dispatch_test_hooks` 墓碑斷言與 `test_ai_guidelines_alignment` 靜態 grep；重寫 `test_cleanup_shared_sandbox_safe`、`test_release_check_gates` 與 `test_tester_quiet_flag_and_silence_op_test`。<br/>3. 補齊所有 `tempfile.mkdtemp()`、`mock_*` 模組與 `_ADAPTED_SPECS` 之 `tearDown` / `try...finally` 清理。 | P0 | 核心目標 5 |
| **FR-09** | 補齊 `D-01`~`D-08` 五大高風險路徑回歸測試 (`DT-05`) | 1. 補齊 `scripts/cli.py`（`bump_*`、`test -k/-q`）與 `op-test` 參數重組測試。<br/>2. 補齊 `Releaser` 跨三元組版本回退攔截、`release_all` Kahn DAG 拓撲排序、`CyclicDependencyError`、上游失敗阻斷下游與 `release_git` `git commit` 失敗攔截測試。<br/>3. 遵循 `[P00:DR-03]` 以動態檔案字串測試 `UNKNOWN > 0` 剛性失敗、`_FailedTest` 保留與 `@require(Requirement.NETWORK)` 離線 `SkipTest`。<br/>4. 補齊 `Checker._check_custom_rules` 跨模組載入、源碼 Schema 優先讀取、多位數 SemVer（`1.9.0` vs `1.10.0`）選包排序與 `YSCBTestCase` CWD 漂移自動還原測試。 | P0 | 核心目標 5, [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `dev test <mod> -k <pat>` 子進程 `op-test` 參數重組 | `-k <pat>` 正規化為 `--pattern=<pat>` 傳遞，子進程絕不將 `<pat>` 誤判為位置參數 `target_mod`。 |
| **EC-02** | `Releaser.release_check` 跨三元組版本回退（如在庫 `1.1.0.0`，目標 `1.0.0.5`） | 即使傳入 `force=True`，仍因 `1.0.0.5 < global_highest (1.1.0.0)` 被 Gate 3 剛性阻斷。 |
| **EC-03** | `Releaser.release_git` 遭遇 `git commit` 真實錯誤（非 `nothing to commit`） | 立即回傳 `(False, error_msg)` 並中止後續 `git tag` 操作，防止在舊 Commit 上誤打新版本 Tag。 |
| **EC-04** | `Releaser.release_all` 遭遇循環依賴或上游依賴模組發布失敗 | 循環依賴拋出 `CyclicDependencyError`；上游模組失敗時，下游依賴模組自動標記 `Skipped because dependency '...' failed release.` 而不執行打包。 |
| **EC-05** | 測試方法未呼叫 `self.mark_passed()`（狀態為 `UNKNOWN`）或測試檔含 `SyntaxError`（產生 `_FailedTest`） | `UNKNOWN > 0` 時強制判定測試失敗（Exit Code `1`）並從 `custom_passed` 扣除；`_FailedTest` 在任何 `--type` 過濾下均強制保留並觸發失敗。 |
| **EC-06** | `Checker._check_custom_rules` 目標函式不存在或執行時拋出例外 | 捕獲例外並轉換為 `CheckSeverity.WARN`（`category="CONTRIBUTES"`）寫入報表，且 `finally` 確保臨時加入之 `module://<donor>` 從 `sys.path` 移除。 |
| **EC-07** | 沙盒 `.build/<mod>/` 內含多位數版本（`1.9.0.build.zip` vs `1.10.0.build.zip`）或損毀 Zip | 以 `semver.compare_semver` 正確選出 `1.10.0.build.zip`；若遇 `BadZipFile` 則安全捕獲略過或回退，不崩潰。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 運行時隔離與延遲載入 | 嚴守 `.modules/` 運行時剛性隔離（嚴禁向 `sys.path` 注入 `module.source://`）；`dev/__init__.py` 落實 PEP 562 按需延遲載入。 |
| **NFR-02** | 測試收斂與零殘留 | `ys_codebase/source/dev/tests/` 收斂為 7 個子系統測試檔，執行 `python yscb.py dev check dev` 與 `python yscb.py dev test dev -q` 100% 通過（0 Fail, 0 Unknown），且宿主與 `/tmp` 零暫存目錄殘留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` [DN-DEV-02] 沙盒微環境 3-Tier 零拷貝投影與 `shutil.rmtree` 前強制斷開防護**：任何清理沙盒之路徑必須統一經由 `SandboxProvisioner.cleanup_sandbox()`（先執行 `_unlink_projected_venv`），嚴禁直接對沙盒根目錄呼叫 `shutil.rmtree` 導致穿透刪除宿主 `.venv`。
- **`[!CAUTION]` [DN-DEV-03] 宿主環境防穿透三道剛性守門鎖**：嚴禁在 `YSCBTestCase.setUp` 中回退至 `os.getcwd()`；新增之 CWD 備份與還原僅在合法沙盒啟動後保存 `self._orig_cwd` 並於 `tearDown` 還原。
- **`[!WARNING]` [DN-DEV-01] & [P00:DR-03] AST 靜態檢查防呆**：`Checker._check_test_classes` 會靜態掃描 `dev/tests/*.py` 內所有測試類別是否呼叫 `self.mark_passed()`；因此測試 `UNKNOWN` 與 `SyntaxError` 行為時，必須透過 `create_mock_source_module` 將受測代碼以字串寫入沙盒暫存模組，不得直接寫在 `dev/tests/test_tester.py` AST 中。

