# 技術路線圖：Dev 測試集純化、碎片檔收斂與沙盒／發布管線路徑補盲 (`dev_test_suite_purification_roadmap`) (Roadmap)

> 主題：Dev 測試集純化、碎片檔收斂與沙盒／發布管線路徑補盲 (`dev_test_suite_purification_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
對 `ys-codebase / module:dev`（`v1.1.0.2`）下的 `tests/` 目錄（共 **10 個測試檔案、2,380 行程式碼、92 個頂層 `test_*` 測試方法**）執行六維度測試體檢後，發現現有測試集存在 **5 大類結構性病灶（`DT-01` ～ `DT-05`）**，這也是導致 `D-01`（`op-test` 子進程 `-k`/`-v`/`-q` 失真）、`D-02`（跨三元組版本回退漏攔截與 `git commit` 失敗吞沒）與 `D-03`（`UNKNOWN` 測試假性放行）在測試全綠下潛伏未覺的根本原因：

1. **`DT-01` 虛假測驗、被測方法自我 Mock 與寬容放行（Vacuous, Self-Mocked & Lenient-Pass Tests，共 5 處）**：
   - **`test_case.py::TestCaseSandboxLifecycleTest.test_cleanup_shared_sandbox_safe`（L84–95）**：Docstring 宣稱「驗證 `cleanup_shared_sandbox` 重置 `_shared_sandbox_ctx` 並刪除目錄」，但測試內**完全未呼叫 `YSCBTestCase.cleanup_shared_sandbox()`**，僅呼叫 `create_sandbox()` 後斷言 `os.path.isdir(sb_dir)` 為 `True`，不僅是 0% 測試目標邏輯的空殼測試，還在磁碟上洩漏了一座未清理的虛擬沙盒。
   - **`test_release_pipeline.py::TestReleasePipeline.test_release_check_gates`（L44–50）**：呼叫 `passed, errors = self.releaser.release_check("mock_gate_mod")` 後，僅斷言 `self.assertTrue(isinstance(passed, bool))` 與 `self.assertTrue(isinstance(errors, list))`——無論 `release_check` 通過或失敗皆 100% 綠燈放行。
   - **`test_tester.py::TestDevTesterThrottle.test_tester_quiet_flag_and_silence_op_test`（L272–278）**：Docstring 宣稱「驗證 `_run_op_test` 支援 `--quiet` 與 `-q`，抑制進度文字並調用 `format_throttled`」，實際卻用 `patch.object(self.tester, "_run_op_test", return_value=0)` **把被測目標 `_run_op_test` 自身整個 Mock 掉**。
   - **`test_tester.py::TestDevTesterThrottle.test_ai_guidelines_alignment`（L280–291）**：在沙盒環境下尋找 `project://source/dev/assets/skills/yscb-module-dev/SKILL.md`，並將唯一斷言包在 `if os.path.isfile(skill_path):` 內；因沙盒 `project://` 指向空的 `mock_downstream_project`，條件永遠為 `False` 而 **100% 靜默跳過放行**（且若真讀到 `SKILL.md` 反而會失敗，因 `SKILL.md` 內寫的是 `-q` 而非 `--quiet`）。
   - **`test_sandbox.py::TestSandboxArchitecture.test_third_party_host_module_inheritance`（L201–214）**：將核心斷言包在 `if os.path.isdir(uri.resolve("module://core")):` 條件塊內，具備靜默跳過風險。
2. **`DT-02` 歷史任務碎片檔、跨檔重複測試與頂層夾具雙重跑測（Fragment Files & Duplicate Execution，共 3 個碎片檔 ＋ 6 組重複／錯置）**：
   - **3 個任務導向碎片檔（Plan-Named Fragment Files）**：
     - `test_cli_compliance.py`（126 行，4 個測試）：單獨測試 `Checker._check_cli_compliance`，應歸入 `test_checker.py`。
     - `test_output_purification.py`（285 行，6 個測試）：過往單次輸出純化任務留下的碎片檔，其中 5 個測試屬 `Tester`（應歸入 `test_tester.py`），1 個測試屬 `YSCBTestCase`（應歸入 `test_case.py`）。
     - `test_pip_adaptation.py`（275 行，6 個測試）：過往單次 Pip 適配任務留下的碎片檔，其中 5 個測試屬 `SandboxProvisioner`（應歸入 `test_sandbox.py`），1 個測試屬 `Checker._check_pip_dependencies`（應歸入 `test_checker.py`）。
   - **6 組跨檔重複與職責錯置**：
     - `test_release_pipeline.py::test_builder_dev_build_and_release_package`（L23–41）與 `test_builder.py` 的前兩個測試 **100% 重複**。
     - `test_output_purification.py::test_sandbox_path_validation_blocks_leak` Case A（L231–236）與 `test_case.py::test_security_error_when_direct_host_run`（L110–125）**100% 重複**。
     - `test_sandbox.py::test_op_test_in_place_execution`（L65–69）與 `test_tester.py::test_tester_contract_only_cli`（L35–39）**逐行 100% 重複**。
     - `test_sandbox.py` 內含 `test_type_filter_and_recursive_pattern_filter`（L92）與 `test_filter_suite_taxonomy_and_target`（L298）兩組重複的 `filter_suite` 測試，且 `test_sandbox.py` 後半部共 8 個測試實為測試 `runner.py` 與 `tester.py`。
     - **`test_case.py` 頂層 `DummySharedTestCase` 與 `DummySharedTestCaseB`（L13–42）遭雙重發現與重複執行**：因定義於模組頂層且繼承 `YSCBTestCase`，`TestLoader.discover()` 會先將其作為獨立測試執行一輪（含額外建立一座 `ISOLATED_SANDBOX`），隨後又在 `test_shared_and_isolated_sandbox_dispatch`（L63–70）中被手動加入 `TestSuite` 再跑第二輪。
3. **`DT-03` 過時 `process(args)` 契約測試與歷史墓碑斷言（Obsolete Contract & Tombstone Tests，共 4 處）**：
   - `test_scaffold.py::test_scaffold_cli_format`（L56）、`test_cli_compliance.py`（L37–68）與 `test_checker.py` 全數以已日落（Hard Sunset）的 `def process(args):` 作為合法 CLI 測試範本，尚未驗證新版 `CmdBags` 契約函式與 `contributes/core.json` 1:1 對稱性（對應 `D-04`、`D-05`）。
   - `test_sandbox.py::test_dev_sandbox_hook_convergence`（L152）包含歷史墓碑斷言 `self.assertFalse(hasattr(SandboxProvisioner, "_dispatch_test_hooks"))`。
4. **`DT-04` 暫存目錄洩漏與共享沙盒狀態污染（Temp Dir & Shared Sandbox Pollution，共 4 處）**：
   - `test_output_purification.py`（L60, L113, L176, L266）在 4 個測試中呼叫 `tempfile.mkdtemp()` 並同時 `patch` 掉 `cleanup_sandbox`，且未在 `tearDown` 刪除，每次跑測固定在系統暫存區洩漏 4 個目錄。
   - `test_case.py::test_cleanup_shared_sandbox_safe`（L87）建立真實沙盒卻未清理。
   - `test_builder.py` 與 `test_release_pipeline.py` 在共享沙盒的 `module.source://`、`module.build://`、`module.release://` 建立 8 個 `mock_*` 模組卻未在 `tearDown` 清理，污染後續測試。
   - `test_pip_adaptation.py`（L83）修改全域 `SandboxProvisioner._ADAPTED_SPECS` 集合未還原。
5. **`DT-05` 高風險真實路徑漏測（Critical Coverage Gaps，共 5 大區塊，對應 `D-01` ～ `D-08`）**：
   - **`scripts/cli.py` 所有指令入口（`create`, `check`, `build`, `release`, `release_check`, `release_git`, `bump_*`, `test`, `op_mksb`, `op_test`）為 0 覆蓋**：從未測試 `bump-major/minor/patch/revision`、`check --json`、`_normalize_bags` 以及 `-k`/`-v`/`-q`/`--sequential` 的 CLI 派發（導致 `D-01` 漏網）。
   - **`Releaser` 關鍵防線漏測**：未測試跨三元組版本回退攔截（如在庫 `1.1.0.2` 時退回 `1.0.0.6` 或 `0.9.0.0`）、未測試 `release_all()` 的 Kahn DAG 拓撲排序與循環依賴 `CyclicDependencyError`、未測試上游失敗阻斷下游、未測試 `release_git` 在 `git commit` 失敗時中止打 Tag（導致 `D-02` 漏網）。
   - **測試引擎三態守門與異常保留漏測**：未測試存在 `UNKNOWN` 測試時返回 Exit Code `1` 且 `custom_passed` 扣除 `unknown`、未測試 `_FailedTest` 在 `--type=env/workflow/perf` 下不被濾除、未測試 `@require(Requirement.NETWORK)` 在預設跑測離線時自動觸發 `SkipTest`（導致 `D-03` 漏網）。
   - **`Checker._check_custom_rules` 跨模組載入與源碼 Schema 優先讀取漏測**（導致 `D-04` 漏網）。
   - **`SandboxProvisioner` 多位數 SemVer（`1.9.0` vs `1.10.0`）排序選包、`YSCBTestCase` CWD 漂移自動還原、`Builder.build_module(clean=False)` 與 `contributes/*.json` Schema 合規驗證漏測**（對應 `D-06`、`D-08`）。

### 1.2 現況與影響範圍評估
- **架構定調：裁撤 3 個歷史任務碎片檔，將 `dev/tests/` 由 10 檔收斂為 7 個子系統 1:1 對齊的高內聚測試檔，修復 5 處虛假測試與 4 處資源洩漏，並補齊 `D-01` ～ `D-08` 全鏈路回歸測試**：
  1. **一子系統一測試檔（10 檔 $\rightarrow$ 7 檔）**：將 `test_cli_compliance.py`、`test_output_purification.py` 與 `test_pip_adaptation.py` 無損併入 `test_checker.py`、`test_sandbox.py`、`test_case.py` 與 `test_tester.py`。
  2. **消除雙重發現與資源洩漏**：將 `DummySharedTestCase` 移入測試方法局部作用域（減少 4 次冗餘測試與 1 次冗餘沙盒建置），並確保所有暫存目錄與 `mock_*` 模組於 `tearDown` 100% 清零。
  3. **100% 實質斷言與 CLI 全覆蓋**：補齊 `scripts/cli.py`、`Releaser` DAG／跨三元組防回退、`Tester` `UNKNOWN` 阻斷與 `Checker` 自訂規則之完整正負向測試。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：維持現有 10 檔結構，僅修補 `process(args)` 字串** | 配合 `D-05` 替換測試中的 `process(args)`，不動碎片檔與虛假斷言 | 改動最小 | 3 個碎片檔、6 組重複測試、4 個暫存目錄洩漏與 `test_cleanup_shared_sandbox_safe` 空殼測試依舊留存 | ⭐️⭐️ |
| **方案 2：將所有測試合併為單一 `test_dev_all.py`** | 將 10 個測試檔全部塞進單一檔案 | 檔案數最少 | 超過 2,000 行難以局部跑測與維護，違反子系統 1:1 歸戶原則 | ⭐️⭐️ |
| **方案 3：子系統 1:1 對齊收斂（10 檔 $\rightarrow$ 7 檔）＋ 去重防漏 ＋ 補齊 `D-01`～`D-08` 回歸測試（推薦採納）** | 1. 裁撤 `test_cli_compliance.py`、`test_output_purification.py`、`test_pip_adaptation.py` 3 個碎片檔，歸戶至 7 個子系統主測試檔。<br/>2. 消除 6 組重複測試與 `DummySharedTestCase` 頂層雙重跑測。<br/>3. 修復 5 處虛假測試、4 處資源洩漏並補齊 5 大高風險漏測區塊。 | 1. 與 `dev` 子系統 1:1 清晰對應<br/>2. 減少冗餘沙盒建置與 I/O，根除 `/tmp` 暫存洩漏<br/>3. 100% 守住 CLI 契約、3-Gate 防回退與三態測試引擎 | 需重構整併 3 個碎片檔並更新過時 `process(args)` 測試範本 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：僅替換 `process(args)` | 方案 2：單一巨型測試檔 | 方案 3：7 檔子系統對齊 ＋ 去重純化 ＋ 補盲（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高**（與 `testing-sop` 六大鐵律 100% 契合） |
| **後續維護難度 (Maintenance)** | 高（職責散落多檔） | 高（單檔過大） | **極低**（`scaffold`, `checker`, `builder`, `releaser`, `sandbox`, `case`, `tester` 七大領域一目了然） |
| **缺陷攔截可靠性 (Reliability)** | 低（空殼斷言與 CLI 0 覆蓋仍在） | 中 | **極高**（完整覆蓋 `D-01` ～ `D-08` 所有邊界與錯誤攔截） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（可與 `dev_toolchain_and_sandbox_hardening_roadmap.md` Stage 1~3 同步落地） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 測試集檔案結構收斂映射表（10 檔 $\rightarrow$ 7 檔）

| 序號 | 檔案名稱 | 處置動作與職責定位 |
| :---: | :--- | :--- |
| **1** | `test_cli_compliance.py` | **【裁撤併入 `test_checker.py`】** 將 CLI AST 合規檢查測試併入 `test_checker.py`，並升級為驗證 `contributes/core.json` 命令節點與 `scripts/cli.py` `CmdBags` 函式之對稱性。 |
| **2** | `test_output_purification.py` | **【裁撤拆併入 `test_tester.py` ＆ `test_case.py`】** 將 `Tester` 輸出節流、JSON IPC、警告摺疊、`op-test` 宿主守門與崩潰尾部擷取併入 `test_tester.py`（並補齊 `tempfile.mkdtemp` 清理）；將 `YSCBTestCase` 非法沙盒路徑攔截併入 `test_case.py`（消除與 `test_security_error_when_direct_host_run` 的重複）。 |
| **3** | `test_pip_adaptation.py` | **【裁撤拆併入 `test_sandbox.py` ＆ `test_checker.py`】** 將 `adapt_build_pip_dependencies`、`_project_venv`、`.pth` 降級與 `_unlink_projected_venv` 併入 `test_sandbox.py`；將 `_check_pip_dependencies` 併入 `test_checker.py`。 |
| **4** | `test_scaffold.py` | **【現代化＋擴充】** 統管 `Scaffolder` 與 `scripts/cli.py:create`；更新 `test_scaffold_cli_format` 驗證新生成模組具備 `def hello(cmd_bags: CmdBags)`、無字面 `\\n` 污染，且直接通過 `Checker.check_module()`（0 FAIL, 0 WARN）與生成的 `test_basic.py` 測試。 |
| **5** | `test_checker.py` | **【吸收合併＋補盲】** 統管 `Checker` 8 步檢核管線與 `scripts/cli.py:check`（含 `--json`）；吸收 `test_cli_compliance.py` 與 `pip_dependencies` 測試；新增 `_check_custom_rules` 跨模組載入與異常轉 `WARN` 測試、`_check_core_injection` 優先讀取 `module.source://` Schema 測試、以及 CLI 葉節點誤用 `leaf_fn` 攔截測試（`D-04`）。 |
| **6** | `test_builder.py` | **【加固清理＋補盲】** 統管 `Builder` 與 `scripts/cli.py:build`；於 `tearDown` 自動清理測試建立的 `mock_*` 模組；新增 `build_module(clean=False)` 保留既有檔案測試（`D-06`）與 `.yscbignore` 規則測試。 |
| **7** | `test_release_pipeline.py` | **【修復虛假測試＋補齊 DAG 與防回退】** 統管 `Releaser` 與 `scripts/cli.py:release / release_check / release_git / bump_*`；移除與 `test_builder.py` 重複的 `test_builder_dev_build_and_release_package`；重寫 `test_release_check_gates`；新增跨三元組版本回退攔截測試、`release_all()` Kahn DAG 拓撲排序與 `CyclicDependencyError` 測試、上游失敗阻斷下游測試、以及 `release_git` 在 `git commit` 失敗時中止打 Tag 測試（`D-02`）。 |
| **8** | `test_sandbox.py` | **【純化職責＋移除墓碑＋補盲】** 專注統管 `SandboxProvisioner` 與 `SandboxContext`（將原檔內屬 `runner.py` 與 `tester.py` 的 8 個測試移交 `test_tester.py`）；移除 `_dispatch_test_hooks` 墓碑斷言与 `if os.path.isdir` 條件包裝；新增多位數 SemVer（`1.9.0` vs `1.10.0`）選包排序測試與 `create_mock_package` 合規驗證（`D-05`、`D-06`）。 |
| **9** | `test_case.py` | **【修復空殼測試＋消除雙重跑測＋補盲】** 統管 `YSCBTestCase`、`Requirement` 與 `BaseModuleContractTestCase`；將 `DummySharedTestCase` 與 `DummySharedTestCaseB` 移入測試方法內部避免被 `TestLoader` 頂層重複發現執行；重寫 `test_cleanup_shared_sandbox_safe` 真實呼叫 `cleanup_shared_sandbox()` 並驗證目錄刪除；新增 `setUp/tearDown` 自動還原 `os.getcwd()` 漂移測試（`D-06`）。 |
| **10** | `test_tester.py` | **【整合 Runner／CLI 測試＋修復自我 Mock】** 統管 `Tester`、`TestDiscovery`、`TestRunner`、`ASCIIReportFormatter` 與 `scripts/cli.py:test / op_test / op_mksb`；重寫 `test_tester_quiet_flag_and_silence_op_test` 真實執行 `_run_op_test`；刪除靜態文檔 grep `test_ai_guidelines_alignment`；新增 `-k <pat>` / `-v` / `-q` / `--sequential` 跨子進程參數傳遞測試（`D-01`）、`UNKNOWN > 0` 剛性阻斷與 `custom_passed` 扣減測試、`@require(Requirement.NETWORK)` 離線 `SkipTest` 統計測試、`_FailedTest` 在 `--type=env` 下保留不漏報測試（`D-03`），以及 `contributes/*.json` Schema 合規測試（`D-08`）。 |

### 4.2 5 處虛假／自我 Mock 測試 (`DT-01`) 重寫規格
1. **重寫 `test_case.py::test_cleanup_shared_sandbox_safe`（含 `finally` 兜底清理保護）**：
   - 建立 `mock_sb = SandboxProvisioner.create_sandbox()` 並賦值予 `YSCBTestCase._shared_sandbox_ctx`。
   - 於 `try...finally` 內暫時清除 `YSCB_TEST_SANDBOX` 與 `YSCB_TEST_KEEP_SANDBOX` 環境變數後，**真實呼叫 `YSCBTestCase.cleanup_shared_sandbox()`**，明確斷言 `self.assertIsNone(YSCBTestCase._shared_sandbox_ctx)` 且 `self.assertFalse(os.path.exists(mock_sb.sandbox_dir))`；並於 `finally:` 區塊除了還原 `_shared_sandbox_ctx` 與環境變數外，加上兜底 `if os.path.exists(mock_sb.sandbox_dir): SandboxProvisioner.cleanup_sandbox(mock_sb)`，確保即使斷言失敗也 100% 零殘留。
2. **重寫 `test_release_pipeline.py::test_release_check_gates`**：
   - 對新建立的合規模組 `mock_gate_mod@1.0.0.0` 執行 `passed, errors = self.releaser.release_check("mock_gate_mod")`，剛性斷言 `self.assertTrue(passed, f"Expected pass, got: {errors}")` 與 `self.assertEqual(errors, [])`。
   - 接著打包 `1.0.0.0.zip` 與 `1.1.0.0.zip`，將 `manifest.json` 改為 `1.0.0.5`（跨三元組回退），再次呼叫 `release_check("mock_gate_mod", force=True)`，剛性斷言 `self.assertFalse(passed)` 且錯誤訊息包含 `"Gate 3 Failed (Monotonicity)"`。
3. **重寫 `test_tester.py::test_tester_quiet_flag_and_silence_op_test`**：
   - 不再 `patch` `_run_op_test`，而是透過 `StringIO` 攔截 `sys.stdout`，直接呼叫 `ret = self.tester._run_op_test(["core", "--contract-only", "-q"])`。
   - 斷言 `ret == 0`，且 `stdout` 僅輸出單行節流格式 `"Pass: 3(100.0%), Fail: 0, Skip: 0"`，不包含 `"begin test in"` 或 `"test finish in"` 進度洗版文字。

### 4.3 5 大高風險漏測路徑 (`DT-05`) 補盲規格
1. **`scripts/cli.py` 與 `op-test` 參數重組端到端測試（於 `test_tester.py` ＆ `test_release_pipeline.py`，對應 `D-01`）**：
   - 測試 `cli.bump_major / bump_minor / bump_patch / bump_revision` 對 `manifest.json` 版號之精確遞增。
   - 測試 `cli.test(CmdBags(command="test", args=["core"], options={"pattern": CmdOption("pattern", "manifest"), "quiet": CmdOption("quiet", True)}))` 與列表輸入 `cli.test(["core", "-k", "manifest", "-q", "--no-build"])`，驗證子進程 `op-test` 正確依 `-k manifest` 過濾（僅跑匹配的測試案例）且未將 `"manifest"` 誤判為 `target_mod`。
2. **`Releaser` DAG 拓撲排序、循環依賴與 `release_git` 錯誤阻斷測試（於 `test_release_pipeline.py`，對應 `D-02`）**：
   - 建立 `mod_c`（依賴 `mod_b`）、`mod_b`（依賴 `mod_a`）、`mod_a`（僅依賴 `core`），驗證 `releaser.release_all()` 嚴格依 `mod_a -> mod_b -> mod_c` 順序執行；若 `mod_a` 失敗，`mod_b` 與 `mod_c` 自動標記跳過失敗。
   - 建立互相依賴的 `cycle_a <-> cycle_b`，驗證 `releaser.release_all()` 拋出 `CyclicDependencyError`。
   - 模擬 `_run_git_cmd` 在 `commit` 時回傳 `(128, "", "fatal: unable to auto-detect email address")`，驗證 `releaser.release_git()` 回傳 `False` 且不執行 `git tag`。
3. **`UNKNOWN` 測試剛性失敗、`_FailedTest` 保留與 `NETWORK` 自動 `SkipTest` 測試（於 `test_tester.py`，對應 `D-03`，含 AST 靜態掃描防呆）**：
   - **AST 靜態檢核防呆**：由於 `dev check dev` 的 `Checker._check_test_classes` 會以 `ast.walk()` 掃描 `dev/tests/*.py` 內所有 `ClassDef` 確認是否呼叫 `self.mark_passed()`，因此在測試 `UNKNOWN` 與 `SyntaxError` 時，**必須透過 `self.create_mock_source_module("mock_unknown", files={"tests/test_bad.py": "..."})` 以字串寫入沙盒暫存模組檔案中**，嚴禁直接在 `test_tester.py` AST 內定義未呼叫 `self.mark_passed()` 的測試類別。
   - 針對含漏寫 `self.mark_passed()` 測試方法的沙盒 Mock 模組執行 `_run_op_test`，驗證回傳碼為 `1`、`custom_passed == 0`、`unknown == 1` 且報表狀態為 `FAILED`。
   - 針對含 `SyntaxError` 測試檔的沙盒 Mock 模組執行 `_run_op_test(["mock_broken", "--type=env"])`，驗證 `_FailedTest` 未被濾除且回傳碼為 `1`。
   - 在模擬 `is_network_available() -> False` 下執行含 `@require(Requirement.NETWORK)` 測試之套件，驗證預設 `filter_suite` 保留該測試並在執行時觸發 `SkipTest` 計入 `Skipped: 1`。
4. **`Checker._check_custom_rules` 與源碼 Schema 優先讀取測試（於 `test_checker.py`，對應 `D-04`）**：
   - Mock `core.contributes.get("dev", "custom_checks")` 回傳指向沙盒模組檢查函式的規則（支援 `code.func://` 與 `mod:func`），驗證 `check_module` 成功載入並寫入自訂 `CheckIssue`。
5. **沙盒多位數 SemVer 選包與 `YSCBTestCase` CWD 還原測試（於 `test_sandbox.py` ＆ `test_case.py`，對應 `D-06`）**：
   - 在 `module.build://mock_semver/` 同時放置 `1.2.0.build.zip`、`1.9.0.build.zip` 與 `1.10.0.build.zip`，驗證 `SandboxProvisioner.create_sandbox` 與 `adapt_build_pip_dependencies` 正確挑選 `1.10.0.build.zip` 而非 `1.9.0.build.zip`。
   - 在測試方法內執行 `os.chdir(temp_dir)`，驗證 `tearDown()` 後 `os.getcwd()` 自動還原為初始沙盒目錄。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- **雙路線圖強制綁定／合併立項建議**：由於本測試純化路線圖之 `DT-03`（升級 `process(args)` 測試範本為 `CmdBags`）與 `DT-05`（補測 `D-01` ～ `D-08` CLI 傳遞、3-Gate 防回退、`UNKNOWN` 阻斷與自訂規則載入）與 `dev_toolchain_and_sandbox_hardening_roadmap.md` 100% 共生，**立項時應將兩份 `dev` 路線圖合併為單一 `dev` 升級計畫（Full Track）同步交付**。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：裁撤 3 個任務碎片檔、消除 6 組重複測試與 `DummySharedTestCase` 雙重跑測（`DT-02`、`DT-03`）**
   - 將 `test_cli_compliance.py`、`test_output_purification.py` 與 `test_pip_adaptation.py` 無損拆併入 `test_checker.py`、`test_sandbox.py`、`test_case.py` 與 `test_tester.py` 後刪除。
   - 將 `test_sandbox.py` 中的 `runner/tester` 測試移交 `test_tester.py`，將 `DummySharedTestCase` 移入方法局部作用域，並升級所有 `process(args)` 舊範本為 `CmdBags` 合約函式。
2. **Stage 2：修復 5 處虛假／自我 Mock 測試與清零暫存目錄／沙盒狀態洩漏（`DT-01`、`DT-04`）**
   - 重寫 `test_cleanup_shared_sandbox_safe`、`test_release_check_gates` 與 `test_tester_quiet_flag_and_silence_op_test`，刪除 `test_ai_guidelines_alignment` 靜態 grep。
   - 為 `test_tester.py`、`test_builder.py`、`test_release_pipeline.py` 與 `test_sandbox.py` 補齊 `tearDown` 資源清理與 `_ADAPTED_SPECS` 狀態還原。
3. **Stage 3：補齊 `D-01` ～ `D-08` 五大高風險回歸測試並全量驗收（`DT-05`）**
   - 新增 `scripts/cli.py` 與 `op-test` `-k/-v/-q` 傳遞測試、`Releaser` DAG／跨三元組防回退／Git Commit 失敗攔截測試、`UNKNOWN` 阻斷與 `_FailedTest` 保留測試、`Checker` 自訂規則測試，以及 SemVer 排序與 CWD 還原測試，執行 `python yscb.py dev test dev` 確保 7 個測試檔 100% 綠燈通過且環境零殘留。
