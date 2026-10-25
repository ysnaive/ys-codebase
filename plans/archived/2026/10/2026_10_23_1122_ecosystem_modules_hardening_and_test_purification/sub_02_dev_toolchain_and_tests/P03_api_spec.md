# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `dev` PEP 562 Facade | `source/dev/dev/__init__.py` | Public | 匯出 `Scaffolder`, `Checker`, `Builder`, `Tester`, `Releaser`, `testing` 並以 `__getattr__` 延遲載入 |
| `Tester._run_test` / `_run_op_test` | `source/dev/dev/tester.py` | Internal / CLI | 跨沙盒子進程參數長選項正規化 (`--pattern=<pat>`)，`UNKNOWN > 0` 剛性阻斷與統計修正 |
| `runner.filter_suite` | `source/dev/dev/testing/runner.py` | Internal | 保留 `_FailedTest` 不被過濾，將 `Requirement.NETWORK` 納入預設發現 |
| `Releaser.release_check` | `source/dev/dev/releaser.py` | Public | Gate 3 全庫最高版本 (`global_highest`) 雙重單調遞增防回退校驗 |
| `Releaser.release_all` | `source/dev/dev/releaser.py` | Public | 穩定字母序初始化 Kahn DAG 拓撲排序，上游失敗跳過下游依賴 |
| `Releaser.release_git` | `source/dev/dev/releaser.py` | Public | 消除重複預檢 (`_skip_check=True`)，攔截 `git commit` 非零且非 clean 之致命錯誤 |
| `Checker._check_custom_rules` | `source/dev/dev/checker.py` | Internal | 支援 `code.func://` 語法，僅將 `module://<donor>` 臨時注入 `sys.path`，例外轉 `WARN` |
| `Checker._check_cli_compliance` | `source/dev/dev/checker.py` | Internal | 嚴格對齊 `candidates = {full_fn, primary_fn}`，移除無效 `leaf_fn` 與 `cmd_*` |
| `Scaffolder.create_module` | `source/dev/dev/scaffold.py` | Public | 生成合規 `def hello(cmd_bags)` 範本，修正 `tests/__init__.py` 字面 `\\n` |
| `SandboxProvisioner._sort_zip_filenames_by_semver` | `source/dev/dev/testing/sandbox.py` | Internal | 依數值 SemVer 排序選包，防護多位數版號與損毀 Zip |
| `YSCBTestCase.setUp` / `tearDown` | `source/dev/dev/testing/case.py` | Public | 自動記錄 `self._orig_cwd = os.getcwd()` 並於 `tearDown` 安全還原 |
| `Builder.build_module` | `source/dev/dev/builder.py` | Public | 支援 `clean: bool = True`，僅在 `clean=True` 時清空 `real_build_dir` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. dev/__init__.py PEP 562 延遲載入
__all__ = ["Scaffolder", "Checker", "Builder", "Tester", "Releaser", "testing"]
def __getattr__(name: str) -> Any: ...

# 2. Releaser 3-Gate 與 DAG 加固
class Releaser:
    def release_check(self, module_name: str, force: bool = False) -> Tuple[bool, List[str]]:
        """
        Gate 1: Checker 合規檢驗 (0 Fail, 0 Warn)
        Gate 2: 發布包不可變性校驗
        Gate 3: 單調遞增校驗 (target_version > global_highest; 若 force=True 僅允許 target_version == global_highest)
        """
        ...

    def release_all(self, force: bool = False, skip_tests: bool = False) -> Dict[str, Tuple[bool, str]]:
        """
        按字母序穩定初始化佇列執行 Kahn DAG 拓撲排序發布。
        若偵測到循環依賴拋出 CyclicDependencyError；若上游失敗則下游標記跳過。
        """
        ...

    def release_git(self, module_name: str, commit_msg: str, force: bool = False) -> Tuple[bool, str]:
        """
        調用 release_module(..., _skip_check=True) 避免重複檢核；
        執行 git commit，非零退出碼若非 'nothing to commit' / 'working tree clean' 則失敗阻斷打 Tag。
        """
        ...

# 3. Tester 與 Runner 參數傳遞與三態守門
class Tester:
    def _run_test(self, module_name: str, options: Dict[str, Any], ...) -> int:
        """
        組裝子進程 op-test 指令時，將 -k <pat> 正規化為 --pattern=<pat>，
        將 -q 轉為 --quiet，將 -v 轉為 --verbose。
        """
        ...

    def _run_op_test(self, raw_args: List[str]) -> int:
        """
        執行測試並收集結果。
        custom_passed = max(0, custom_total - custom_failed - custom_skipped - mod_unknown)
        若 mod_unknown > 0，將 all_passed 設為 False，回傳 Exit Code 1。
        """
        ...

# 4. Checker 自訂規則與 CLI 入口對稱檢核
class Checker:
    def _check_custom_rules(self, module_path: str, report: CheckReport) -> None:
        """
        載入 contributes["custom_checks"] 定義之函式。
        僅臨時將 uri.resolve(f"module://{donor}") 加入 sys.path；
        若載入/執行拋出例外，記錄為 CheckSeverity.WARN，不靜默吞噬。
        """
        ...

    def _check_cli_compliance(self, module_path: str, report: CheckReport) -> None:
        """
        比對 contributes/core.json 之 commands.cmd 與 scripts/cli.py。
        候選入口函式限定為 candidates = {full_fn, primary_fn}。
        """
        ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `CyclicDependencyError`：當 `release_all()` 遭遇跨模組循環依賴時拋出。
  - `CheckSeverity.WARN`：`Checker._check_custom_rules` 遭遇外部 donor 語法錯誤或執行例外時紀錄，維持檢核流程不崩潰。
  - Exit Code `1`：`Tester` 遭遇 `UNKNOWN > 0`、`_FailedTest` 或測試失敗時回傳。
- **階段決策紀錄**：
  - `[P03:DR-01]`：`Tester._run_test` 組裝子進程參數時一律產出單一 Token（`--pattern=<val>`），徹底杜絕分離參數被子進程誤拆為位置參數。
  - `[P03:DR-02]`：`Releaser.release_module` 增設內部參數 `_skip_check: bool = False`，讓已在前置步驟跑過 `release_check` 的 `release_git` 免去重複靜態檢查。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
+---------------------------------------------------------------------------------+
| Step 1: contributes/core.json 契約宣告 ＋ dev/__init__.py PEP 562 延遲載入 (基礎契約) |
+---------------------------------------------------------------------------------+
                                       │
                                       ▼
+---------------------------------------------------------------------------------+
| Step 2: scripts/cli.py 選項正規化 ＋ Tester/Runner 長選項傳遞與 UNKNOWN 阻斷 (測試引擎)  |
+---------------------------------------------------------------------------------+
                                       │
                                       ▼
+---------------------------------------------------------------------------------+
| Step 3: Releaser 3-Gate 全庫防回退 ＋ 字母序 DAG ＋ release_git 錯誤攔截 (發布流水線) |
+---------------------------------------------------------------------------------+
                                       │
                                       ▼
+---------------------------------------------------------------------------------+
| Step 4: Checker 自訂規則運行時隔離 ＋ 源碼 Schema 優先 ＋ CLI 入口精確對稱 (檢核管線)   |
+---------------------------------------------------------------------------------+
                                       │
                                       ▼
+---------------------------------------------------------------------------------+
| Step 5: Scaffolder/Sandbox/Case/Builder 現代化 (CmdBags / SemVer / CWD / clean) |
+---------------------------------------------------------------------------------+
                                       │
                                       ▼
+---------------------------------------------------------------------------------+
| Step 6: dev/tests/ 10 檔收斂為 7 檔 ＋ 虛假測驗重寫 ＋ D-01~D-08 補盲驗收 (測試純化) |
+---------------------------------------------------------------------------------+
```

