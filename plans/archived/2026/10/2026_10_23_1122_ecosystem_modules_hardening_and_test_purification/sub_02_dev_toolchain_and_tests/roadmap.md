# 技術路線圖：開發工具鏈契約對齊、發布預檢閉環與測試沙盒引擎加固 (`dev_toolchain_and_sandbox_hardening_roadmap`) (Roadmap)

> 主題：開發工具鏈契約對齊、發布預檢閉環與測試沙盒引擎加固 (`dev_toolchain_and_sandbox_hardening_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在對 `ys-codebase / module:dev`（`v1.1.0.2`）進行全模組功能性與架構邊界審查後，確認存在 **8 項功能缺陷與契約一致性問題（`D-01` ～ `D-08`）**：

1. **`D-01` [Critical] `dev test` / `op-test` / `op-mksb` CLI 選項契約脫鉤與參數重組失真（導致 `-k <pattern>`、`-v`、`-q`、`--sequential` 失效或誤判目標模組）**：
   - **子進程 `op-test` 與 `op-mksb` 漏宣告 `options`（`contributes/core.json` L405, L422）**：`op-test` 在 `core.json` 的 `options` 為空 `{}`。當 `Tester._run_test` 衍生沙盒內子進程呼叫 `python yscb.py dev op-test ...`（或測試直接傳入 `["test", "core", "-k", "test_foo"]`、`-v`、`-q`）時，子進程的 `OptionResolver` 因不知 `-k` 需帶值，將 `-k` 視為布林旗標（轉為 `--k`）、將 `"test_foo"` 視為位置參數塞入 `bags.args`，進而在 `Tester._run_op_test`（L168）中把 `"test_foo"` **覆寫為 `target_mod = "test_foo"`**，直接報錯 `Module 'test_foo' not found in source/.`；同理，短旗標 `-v` / `-q` 經 `op_test()` 重組為 `--v` / `--q` 後，`_run_op_test`（L137, L143）僅比對 `-v`/`--verbose` 與 `-q`/`--quiet`，導致 `-v` 在子進程內 100% 失效。
   - **`dev test` 漏宣告多項實作與文檔已公開之選項（`contributes/core.json` L126–198）**：`tester.py` 與 `README.md` 支援的 `--sequential` / `--no-parallel`、`--logical`、`--env`、`--workflow`、`--perf` / `--stress`、`--all-types`、`--pattern`、`--contract-only` 均未在 `core.json` 宣告；且 `_normalize_bags()`（`scripts/cli.py` L25–43）對列表輸入未處理短選項別名與帶值選項（`-k pat`、`-j 4`）。
   - **`--sync` 選項語意在 `core.json` 與 `tester.py` 完全衝突**：`contributes/core.json`（L181–183）將 `sync` 描述為 `"Run tests synchronously in main process"`（置於 `execution` 群組），但 `tester.py`（L85, L392, L816）實作卻是「測試通過後自動執行 `python yscb.py install <mod>@build --force` 覆寫宿主環境」。
2. **`D-02` [High] `Releaser` 發布預檢與 Git 發布流水線漏洞（跨三元組版本回退漏攔截、`git commit` 失敗靜默吞沒與 `release --all` 斷鏈續跑）**：
   - **Gate 3 單調遞增預檢僅比對同三元組（`same_triplet_versions`），漏攔截跨三元組版本回退（`dev/releaser.py` L101–128）**：`release_check` 僅收集 `item_tuple.triplet == target_tuple.triplet` 的版本。若在庫最高版本已達 `1.1.0.2` 或 `2.0.0.0`，而將 `manifest.json` 退回 `1.0.0.6` 或 `0.9.0.0`（不同三元組），Gate 3 因比對集合為空（或僅看到舊的 `1.0.0.5`）而 **100% 放行舊版本回退發布**。
   - **`release_git` 無條件吞沒 `git commit` 錯誤並重複跑 3 次 `Checker`（`dev/releaser.py` L240–278）**：L269–272 對 `git commit -m` 的任何非零退出碼一律 `pass`（原意僅為容忍 `nothing to commit`），若因未設定 Git `user.name`/`email` 或 Hook 失敗導致 Commit 失敗，程式仍會直接把舊 `HEAD` 打上新版本 Tag 並回傳成功；且單次 `release_git` 重複執行了 3 次 `Checker.check_module()`（Step 1 `test`、Step 2 `release_check`、Step 3 `release_module`）。
   - **`release_all` 拓撲排序順序不固定且上游失敗未阻斷下游（`dev/releaser.py` L161, L191, L207）**：`available_modules` 使用無序 `set`，導致平級模組發布順序隨機變動；且當上游依賴模組發布失敗時，仍繼續發布依賴它的下游模組。
   - **`scripts/cli.py:release_check --all` 未過濾非模組目錄且缺省參數行為與 `check/build/release` 不一致（`scripts/cli.py` L226–252）**：`release_check --all` 未檢查子目錄是否存在 `manifest.json`，且省略模組名時未預設檢查全模組。
3. **`D-03` [High] 測試引擎 `UNKNOWN` 狀態假性放行、`@require(Requirement.NETWORK)` 預設消失與 `_FailedTest` 過濾漏洞（`dev/tester.py`, `dev/testing/runner.py`）**：
   - **`UNKNOWN` 測試未阻斷通過且模組小計數字矛盾（`tester.py` L256, L267, L344, `runner.py` L351）**：規範明定未呼叫 `self.mark_passed()` 之測試為 `UNKNOWN`（無法完成驗收），但 `tester.py` 僅以 `mod_failed == 0` 判定 `all_passed = True` 與 `PASSED (100% Ready)`（Exit Code `0`）；且 `custom_passed`（L267）未扣除 `mod_unknown`，導致模組樹顯示 `Custom Tests (5/5) [Unknown: 5]`、總結卻顯示 `0 Passed, 5 Unknown`。
   - **`@require(Requirement.NETWORK)` 測試在預設跑測時被靜默剔除而非顯示 `Skipped`（`runner.py` L45, L86；`tester.py` L171, L288）**：`Requirement.NETWORK` 的設計初衷是在離線環境自動觸發 `SkipTest`（顯示於 `Skipped: N`），但 `filter_suite` 將預設 `resolved_types` 設為 `{"logic", "env"}` 且把 `NETWORK` 獨立為優先於 `ENV` 的第 5 類，導致標註 `@require(Requirement.NETWORK)` 或 `@require(Requirement.ENV | Requirement.NETWORK)` 的測試在預設跑測時 **100% 被過濾隱藏**。
   - **匯入失敗的 `_FailedTest` 在指定 `--type=env/workflow/perf` 或 `-k` 時被靜默濾除（`runner.py` L47–96）**：當測試檔發生 `SyntaxError` 或 `ImportError` 產生 `unittest.loader._FailedTest` 時，`filter_suite` 將其歸為 `"logic"`，在 `--type=env/workflow/perf` 下會被直接濾除並回傳綠燈通過。
4. **`D-04` [High] `Checker` 靜態檢核器盲區：`custom_checks` 跨模組匯入必敗、`_check_core_injection` 讀取過期 `.modules` Schema 與 CLI 葉節點誤放行（`dev/checker.py`）**：
   - **`_check_custom_rules` 無法載入其他模組註冊之檢查函式且吞沒所有異常（`checker.py` L979–1001）**：執行 `dev check` 時 `sys.path` 僅有 `.modules/core` 與 `.modules/dev`，其他模組註冊於 `custom_checks` 的 `checker_func` 在 `importlib.import_module` 時因 `.modules/<donor>` 不在 `sys.path` 而 100% 拋出 `ModuleNotFoundError` 並被 `except Exception: pass` 靜默吞掉；且未支援 `mod:func` 或 `code.func://` 語法。
   - **`_check_core_injection` 優先讀取舊版 `.modules/<target>/contributes/_format.json`（`checker.py` L399）**：直接呼叫 `core_contrib.get_format(target)` 會先讀已安裝之 `.modules/`，導致在 `source/` 新增或修改擴充點 Schema 時，`dev check` 拿舊版 `.modules/` Schema 檢驗新版 `source/` 而誤報失敗。
   - **`_check_cli_compliance` 誤將 `leaf_fn` 與 `cmd_*` 視為合法入口（`checker.py` L613）**：`core.commands.dispatcher` 僅支援平鋪全名 `full_fn`（如 `config_list`）或頂層群組路由 `primary_cmd`（如 `config`），從不呼叫單獨葉節點名 `leaf_fn`（如 `list`）或 `cmd_*`；但 `checker.py` 卻將 `{full_fn, f"cmd_{full_fn}", leaf_fn, f"cmd_{leaf_fn}"}` 全部放行。
5. **`D-05` [Medium] `Scaffolder`、Mock 生成器與 `Checker` 仍殘留已日落（Hard Sunset）之 `def process(args)` 與非法 `def main(argv)` 範本（`scaffold.py`, `sandbox.py`, `case.py`, `checker.py`）**：
   - `core/commands/dispatcher.py`（L401）已徹底移除 `process(args)` fallback（EC-05 Hard Sunset），但：
     - `dev/scaffold.py`（L56–73）建立新模組時仍在 `scripts/cli.py` 生成過時的 `def process(args)` 與 `sys.path.insert`，且 L86 寫入 `'"""\\nTest package.\\n"""\\n'` 造成字面 `\n` 殘留，L95 生成 `self.assertTrue(True)` 空殼測試。
     - `dev/testing/sandbox.py:create_mock_package`（L55）生成的 `scripts/cli.py` 寫成 `def main(argv):`（直接違反 `checker.py` 嚴禁 `def main` 的紅線，且無法被 `dispatcher` 呼叫）。
     - `dev/testing/case.py:create_mock_source_module`（L211）預設僅生成 `def process(args)` 且未生成 `contributes/core.json`，導致每次建立 Mock 源碼模組執行 `dev check` 都會觸發 `WARN: Module lacks 'contributes/core.json'`。
     - `dev/checker.py:_check_cli_compliance`（L524, L635, L646）錯誤訊息仍要求模組宣告 `def process(args)`。
6. **`D-06` [Medium] 沙盒生命週期與 `YSCBTestCase` 狀態隔離缺陷：版本字典序誤排、CWD 漂移未還原與 `Builder.build_module(clean=False)` 參數無效（`sandbox.py`, `case.py`, `builder.py`）**：
   - **`sandbox.py` 以字典序 `sorted()` 挑選最新版本（L78, L243, L429）**：在挑選 `.build/<mod>/*.zip` 與排序 `mock_provider` 的 `index.json` 版本時使用字串 `sorted()`，當版本號超過個位數（如 `1.9.0.build.zip` vs `1.10.0.build.zip`）時會選錯舊包。
   - **`YSCBTestCase.setUp / tearDown` 未備份與還原 `os.getcwd()`（`case.py` L86, L131）**：`tearDown` 僅還原 `sys.path` 與 `os.environ`，若任一測試呼叫 `os.chdir()`，後續同進程共用沙盒之測試會因 CWD 漂移或目錄刪除而連鎖崩潰。
   - **`Builder.build_module(name, clean=True)` 忽略 `clean` 參數（`builder.py` L172, L202）**：無論傳入 `clean=True` 或 `clean=False`，L202 皆無條件清空 `real_build_dir`。
7. **`D-07` [Medium] `yscb-module-dev` 技能手冊存在致命 API 誤導（`CmdBags` 錯誤範例導致 `AttributeError`）與文檔／清冊脫鉤（`cli_and_commands.md`, `README.md`, `_manifest.md`）**：
   - **`assets/skills/yscb-module-dev/references/cli_and_commands.md`（§1.2 L28–42 & §2 L58）誤導 Agent**：
     - 手冊教導寫 `target = cmd_bags.args.get("target")`，但 `CmdBags.args` 實為 `List[str]`，呼叫 `.get()` 必拋 `AttributeError`。
     - 手冊教導寫 `tier = cmd_bags.get_option("tier")` 取值，但 `get_option()` 回傳的是 `CmdOption` 物件，取值應呼叫 `cmd_bags.get_option_value("tier")`。
     - 手冊教導寫 `extra_args = cmd_bags.raw_args`，但 `CmdBags` 僅有 `raw_cmd: str`，無 `raw_args` 屬性。
   - **打包路徑與版本描述不一致**：`README.md`（L139）與 `cli_and_commands.md`（L120, L124, L145, L173）記載之預設版號 `0.1.0`、`.build` 產物路徑與 `release-check` 3-Gate 定義，與實作（預設版號 `0.1.0.0`、產物 `.build/<mod>/<major>.<minor>.<patch>.build.zip`、3-Gate 為「合規、不可變性、單調性」）不一致。
   - **`contributes/_manifest.md`（L19–20）過時**：仍描述向 `AGENTS_STANDARDS` 注入，實際 `contributes/agents-workflow.json` 為匯出 `yscb-module-dev` 技能並注入 `AGENTS_SKILL_ROUTING`。
8. **`D-08` [Low] `contributes/core.json` 漏註冊 `events`（`on_test_setup` / `on_test_teardown`）且 `dev/__init__.py` 漏匯出 `Releaser` 並違反自身 PEP 562 延遲載入規範**：
   - `sandbox.py` 廣播了 `on_test_setup` 與 `on_test_teardown` 事件，但 `dev/contributes/core.json` 未宣告 `"events"` 清冊，導致 `python yscb.py event list` 無法查閱。
   - `dev/__init__.py` 漏匯出 `Releaser`，且 `dev/__init__.py` 與 `scripts/cli.py` 頂層皆直接匯入所有重型子模組，違反自身 `cli_and_commands.md` §4 的 PEP 562 延遲載入規範。

### 1.2 現況與影響範圍評估
- **架構定調：打通 `dev` CLI 強型別契約與沙盒 `op-test` 參數無損傳遞、加固 3-Gate 全庫版本單調性與 `UNKNOWN` 測試守門、全面汰除 `process(args)` 遺留範本，並修正 `yscb-module-dev` 技能手冊**：
  1. **CLI 與沙盒測試參數 100% 對稱保真**：補齊 `contributes/core.json` 中 `test`、`op-test`、`op-mksb` 的選項契約，確保 `-k <pattern>`、`-v`、`-q`、`--sequential` 在主進程與沙盒子進程間零失真傳遞。
  2. **嚴密品質與發布守門（Zero Unknown Pass & Global Monotonicity）**：將 `UNKNOWN` 測試與 `_FailedTest` 納為剛性阻斷條件，並使 `Releaser` Gate 3 同時防禦同三元組與跨三元組版本回退。
  3. **全面對齊 `CmdBags` 活躍執行契約**：從 `Scaffolder`、`Checker`、沙盒 Mock 產生器到 `yscb-module-dev` 技能參考手冊，100% 統一為 `CmdBags` 標準介面。

---

## 2. 候選架構方案對比 (Candidate Solutions)

針對 `D-01`（`dev test` 與沙盒內 `op-test` 選項傳遞失真）與 `D-03`（`UNKNOWN` 測試與 `NETWORK` 分類守門），對比以下三種架構方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：僅在 `tester.py` 手寫更多 `--q`、`--v` 特例修補** | 不改 `contributes/core.json`，僅在 `_run_op_test` 增加 `elif a == "--v":` 等補丁 | 改動行數最少 | 治標不治本：`-k test_foo` 在 `op-test` 仍會被 `OptionResolver` 拆成位置參數覆寫 `target_mod`，且 `--help` 依舊漏列選項 | ⭐️⭐️ |
| **方案 2：繞過 `yscb.py` 直接在子進程呼叫 `python -m dev.tester`** | 讓 `_run_test` 不走 `sandbox_yscb dev op-test`，改為直接呼叫內部模組 | 避開二次 `OptionResolver` 解析 | 破壞沙盒透過 `yscb.py` 驗證微內核 Bootstrap 與環境變數載入的端到端保真度 | ⭐️⭐️⭐️ |
| **方案 3：補齊 `core.json` 全選項契約 ＋ 正規化 `--key=val` 子進程傳遞 ＋ 剛性阻斷 `UNKNOWN` 與 `_FailedTest`（推薦採納）** | 1. 在 `contributes/core.json` 完整宣告 `test`、`op-test`、`op-mksb` 之所有選項與別名，並修正 `--sync` 描述。<br/>2. 在 `scripts/cli.py` 與 `Tester._run_test` 組裝 `op_test_args` 時統一正規化為標準長選項（`--pattern=<val>`、`--quiet`、`--verbose`）。<br/>3. 將 `UNKNOWN > 0` 視為測試未通過（返回 `1`），保留 `_FailedTest` 不被濾除，並將 `NETWORK` 作為正交能力標籤納入預設發現。 | 1. 徹底根除 `-k` 誤判模組名與 `-v/-q` 吃字問題<br/>2. 保持 100% 真實 `yscb.py` 沙盒啟動鏈路<br/>3. 落實 `mark_passed()` 三態契約與離線 `SkipTest` 可觀測性 | 需同步更新 `contributes/core.json`、`scripts/cli.py`、`tester.py` 與 `runner.py` | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：局部特例補丁 | 方案 2：繞過 `yscb.py` 入口 | 方案 3：契約補齊 ＋ 標準化傳遞 ＋ 剛性守門（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高**（完全符合 `core.commands` 設計規範） |
| **CLI 與文檔對稱性** | 低（`core.json` 與實作仍脫鉤） | 低 | **極高**（`core.json`、`cli.py`、`tester.py`、`README.md` 四方 100% 對齊） |
| **測試與發布守門可靠性** | 低（`UNKNOWN` 與版本回退仍放行） | 中 | **極高**（100% 攔截漏寫 `mark_passed()`、語法錯誤測試檔與跨三元組版本回退） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（聚焦於 `dev` 模組內部檔案之精準修正） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 `D-01` & `D-08` CLI 選項契約對齊、參數無損傳遞與 PEP 562 延遲載入 (`contributes/core.json`, `scripts/cli.py`, `dev/__init__.py`)
1. **補齊 `contributes/core.json` 選項與 `events` 宣告**：
   - 於頂層新增 `"events"` 區塊，正式宣告 `on_test_setup` 與 `on_test_teardown` 兩個沙盒測試生命週期事件。
   - 於 `commands.cmd.test.options`：
     - `parallel` 群組新增 `sequential`（別名 `["no-parallel"]`，描述：`"Disable parallel execution and run sequentially"`）。
     - `filter` 群組將 `k` 正規化為 `pattern`（別名 `["k"]`，帶 `args.pattern`）並新增 `contract-only`（描述：`"Run only auto-synthesized contract tests"`）。
     - `type` 群組除 `type`（帶參數）外，補齊快捷旗標 `logical`、`env`、`workflow`、`perf`（別名 `["stress"]`）、`all-types`。
     - `execution` 群組將 `sync` 描述修正為 `"Auto-install local @build package into host environment after 100% test pass"`。
   - 於 `commands.cmd.op-mksb.options` 補齊 `dir`（帶 `args.path`）；於 `commands.cmd.op-test.options` 同步配置與 `test` 一致的過濾與輸出選項，並加上內部通訊選項 `report-json`（帶 `args.path`）與 `quiet-report`。
2. **強化 `scripts/cli.py` 的 `_normalize_bags` 與選項轉譯**：
   - 在 `_normalize_bags()` 中支援解析帶空白之已知帶值短/長選項（如 `["-k", "pat"]`、`["-j", "4"]`、`["--target", "spec"]`、`["--type", "logic"]`、`["--desc", "text"]`、`["-m", "msg"]`），並將短別名（`q -> quiet`, `v -> verbose`, `a -> all`, `f -> force`, `j -> jobs`, `k -> pattern`）正規化為標準選項名。
   - 在 `Tester._run_test()` 與 `_run_op_test()` 中統一識別 `--pattern=` / `-k=` / `-k`、`--quiet` / `-q` / `--q`、`--verbose` / `-v` / `--v`，並在組裝 `op_test_args` 時將 `-k <pat>` 轉為單一 Token `--pattern=<pat>`，徹底杜絕子進程位置參數漂移。
3. **落實 PEP 562 延遲載入並匯出 `Releaser`（`D-08`）**：
   - 於 `dev/__init__.py` 將 `__all__` 擴充為 `["Scaffolder", "Checker", "Builder", "Tester", "Releaser", "testing"]`，並以 `__getattr__(name)` 按需延遲載入各子模組。
   - 於 `scripts/cli.py` 將 `Scaffolder`、`Checker`、`Builder`、`Tester`、`Releaser` 移至各對應命令函式內按需匯入。

### 4.2 `D-02` `Releaser` 3-Gate 跨三元組防回退、拓撲阻斷與 `release_git` 加固 (`dev/releaser.py`, `scripts/cli.py`)
1. **升級 Gate 3 為全庫＋同三元組雙重單調遞增校驗（`dev/releaser.py` L96–129）**：
   - 掃描 `real_rel_dir` 下所有合法 `<ver>.zip` 解析為 `all_released_versions`，並取 `global_highest = max(all_released_versions)`：
     - 若 `not force` 且 `target_tuple <= global_highest`：攔截報錯 `Gate 3 Failed (Monotonicity): Target version '{target_version}' must be strictly greater than the highest existing version '{global_highest}'.`。
     - 若 `force=True` 且 `target_tuple < global_highest`：攔截報錯 `Gate 3 Failed (Monotonicity): Version rollback below highest existing version '{global_highest}' is forbidden even with --force.`（僅在 `force=True` 且 `target_tuple == global_highest` 時放行同最高版本覆蓋打包）。
2. **加固 `release_all` 確定性拓撲排序與上游失敗阻斷（`dev/releaser.py` L161–210）**：
   - 將初始 `queue` 與每次入列節點按模組名稱字母序排序（` sorted(...)`），確保拓撲發布順序 100% 確定可重現。
   - 若某模組 `m` 在 `release_module(m)` 失敗，將其所有下游依賴模組標記為 `(False, f"Skipped because dependency '{m}' failed release.")`，防止在基底模組失敗時發布不一致的上層模組。
3. **修復 `release_git` 錯誤處理與消除重複 `Checker` 呼叫（`dev/releaser.py` L235–280）**：
   - 於 `release_module()` 新增可選內部參數 `_skip_check: bool = False`，使 `release_git()` 在通過 Step 2 `release_check()` 後呼叫 `release_module(..., _skip_check=True)` 免除重複預檢。
   - 執行 `git commit -m commit_msg` 時，當 `c_code != 0` 檢查 `c_out + c_err` 是否包含 `"nothing to commit"` 或 `"working tree clean"`；若非此情況（如缺少 Git user.name/email 或 Hook 失敗），立即回傳 `False, f"Git commit failed during release-git: {c_err or c_out}"` 並中止打 Tag。
4. **統一 `scripts/cli.py:release_check` 行為（`scripts/cli.py` L226–252）**：
   - 將 `check_all = bags.has_option("all") or bags.has_option("a") or not bags.args` 與 `check / build / release` 對齊，且掃描 `src_root` 時僅納入包含 `manifest.json` 之合法模組目錄。

### 4.3 `D-03` 測試引擎 `UNKNOWN` 剛性守門、`NETWORK` 正交分類與 `_FailedTest` 保留 (`dev/tester.py`, `dev/testing/runner.py`)
1. **修復 `custom_passed` 計算與 `UNKNOWN` 阻斷邏輯（`dev/tester.py` L256–299, L342–363；`runner.py` L351）**：
   - 將 `custom_passed` 修正為 `max(0, custom_total - custom_failed - custom_skipped - mod_unknown)`，確保模組樹顯示的 `(custom_passed/custom_total)` 與下方 `Summary` 的 `Passed` 數量完全一致。
   - 當 `mod_unknown > 0` 時，將 `mod_info["passed"]` 設為 `False`、`all_passed` 設為 `False`，並在 `mod_info["errors"]` 與 `failures_list` 附加明確提示（列出未呼叫 `self.mark_passed()` 之測試方法名稱與快速重跑指令），使 `Status` 顯示 `FAILED` 並返回 Exit Code `1`。
2. **將 `Requirement.NETWORK` 作為正交能力標籤納入預設發現（`dev/testing/runner.py` L28–96；`dev/tester.py` L171, L288）**：
   - 於 `tester.py:VALID_TYPES` 補入 `"network"`，並於 `runner.py:filter_suite` 將預設 `resolved_types` 設為 `{"logic", "env", "network"}`；同時在 `get_test_category` 與 `_matches` 中，若測試同時標註 `ENV | NETWORK` 則歸入 `"env"`（或獨立計入 `network_passed` 並顯示 `Network: N`），讓離線環境下 `@require(Requirement.NETWORK)` 測試能正常進入 Runner 並觸發 `SkipTest` 計入 `Skipped`。
3. **強制保留 `_FailedTest` 不被分類過濾剔除（`dev/testing/runner.py` L47–65）**：
   - 在 `filter_suite` 的 `_matches(test_case)` 開頭加入：若 `test_case.__class__.__name__ == "_FailedTest"`，除非使用者指定了不匹配的 `--target` 或 `-k`，否則在任何 `--type` 下**一律回傳 `True`**，確保測試檔語法錯誤或匯入失敗 100% 暴露。

### 4.4 `D-04` & `D-05` `Checker` 檢核器修復與 `Scaffolder` / Mock 產生器 `CmdBags` 現代化 (`dev/checker.py`, `dev/scaffold.py`, `dev/testing/sandbox.py`, `dev/testing/case.py`)
1. **修復 `Checker._check_custom_rules`、`_check_core_injection` 與 `_check_cli_compliance`（`dev/checker.py`）**：
   - **`_check_custom_rules`（L979–1001，嚴守 `.modules/` 剛性邊界）**：支援解析 `code.func://<mod>/<path>:<func>`、`mod.path:func` 與 `mod.path.func`；載入前自動將對應 Donor 的已安裝運行空間 **`uri.resolve(f"module://{donor}")`** 臨時加入 `sys.path`（**嚴禁將 `module.source://` 注入 `sys.path`**，100% 遵守 `.modules/` 運行時剛性隔離約束）；若載入或執行拋出例外，向 `report.issues` 附加一筆 `CheckSeverity.WARN`（`category="CONTRIBUTES"`）診斷訊息，不再靜默吞沒。
   - **`_check_core_injection`（L399）**：檢驗 `contributes/<target>.json` 時，優先檢查 `module.source://<target>/contributes/_format.json` 是否存在，存在則直接讀取最新源碼 Schema，否則才回退呼叫 `core_contrib.get_format(target)`。
   - **`_check_cli_compliance`（L600–648，精確對齊 ` {full_fn, primary_fn}` 派發契約）**：對齊 `core/commands/dispatcher.py:dispatch_local`（L383 & L386）真實派發邏輯——檢查每個葉節點命令時，合法入口函式候選集合精確定義為 **`candidates = {full_fn, primary_fn}`**（即平鋪底線全名函式如 `config_list`，或頂層第一段群組路由函式如 `config` / `contributes` / `plan`，移除無效的單獨 `leaf_fn` 與 `cmd_*`），既攔截錯誤命名又不誤殺採用頂層群組路由之模組；同時移除過時的 `def process(args)` 錯誤提示文字。
2. **全面汰除 `Scaffolder` 與沙盒 Mock 中的 `process(args)` 及 `main(argv)`（`D-05`）**：
   - **`dev/scaffold.py`**：
     - 生成的 `scripts/cli.py` 改為純淨的 `def hello(cmd_bags: CmdBags) -> int:`（移除已日落的 `def process(args)` 與手動 `sys.path.insert`）。
     - 修正 L86 `tests/__init__.py` 的換行字元為 `'"""\nTest package.\n"""\n'`。
     - 生成的 `tests/test_basic.py` 改為實際匯入並呼叫 `hello(CmdBags(command="hello"))`，斷言回傳值為 `0`。
   - **`dev/testing/sandbox.py:create_mock_package`（L55）**：將生成的 `scripts/cli.py` 由非法 `def main(argv):` 改為合規的 `def hello(cmd_bags): return 0` 並附上最小 `contributes/core.json` 與 `contributes/_manifest.md`。
   - **`dev/testing/case.py:create_mock_source_module`（L210）**：預設生成合規的 `def hello(cmd_bags): return 0`、`contributes/core.json` 與 `contributes/_manifest.md`（若呼叫端未於 `files` 覆寫），使新建立的 Mock 源碼模組預設即可 0 Error、0 Warning 通過 `Checker.check_module()`，並同步更新 `dev/tests/` 中使用舊版 `def process(args)` 測試 `Checker` 的既有測試案例。

### 4.5 `D-06` & `D-07` 沙盒 SemVer 排序、CWD 狀態還原與 `yscb-module-dev` 技能手冊校正 (`sandbox.py`, `case.py`, `builder.py`, `assets/skills/yscb-module-dev/`)
1. **沙盒版本排序、CWD 備份還原與 `Builder` `clean` 參數修復（`D-06`）**：
   - 於 `dev/testing/sandbox.py`（L78, L243, L429）建立輔助函式 `_sort_zip_filenames_by_semver(zips)` 與使用 `functools.cmp_to_key(semver.compare_semver)` 排序版本，徹底取代字典序 `sorted()`；並在解壓 `.build` zip 時加上 `try...except zipfile.BadZipFile` 保護。
   - 於 `dev/testing/case.py:YSCBTestCase` 的 `setUp()` 記錄 `self._orig_cwd = os.getcwd()`，並於 `tearDown()` 開頭執行 `if os.path.isdir(self._orig_cwd): os.chdir(self._orig_cwd)`。
   - 於 `dev/builder.py:build_module(name, clean=True)`（L202）將清空舊產物目錄之迴圈包入 `if clean and os.path.isdir(real_build_dir):`。
2. **校正 `yscb-module-dev` 技能手冊、`README.md` 與 `contributes/_manifest.md`（`D-07`）**：
   - 於 `assets/skills/yscb-module-dev/references/cli_and_commands.md`（§1.2 & §2）：
     - 修正位置參數存取範例為：`target = cmd_bags.args[0] if cmd_bags.args else None`。
     - 修正具值選項存取範例為：`tier = cmd_bags.get_option_value("tier", default="minor")`（並說明 `get_option()` 回傳 `Optional[CmdOption]`）。
     - 修正原始命令存取範例為：`raw_cmd = cmd_bags.raw_cmd`。
     - 同步更新 §5.1 腳手架結構說明（預設版號 `0.1.0.0`、移除 `process(args)` 描述）、§5.3 `.build` 產物路徑與 §5.5 `release-check` 3-Gate 定義。
   - 同步校正 `README.md`（L139）的 `.build` 產物路徑與 `contributes/_manifest.md`（L19–20）的 `agents-workflow.json` 匯出說明。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術路線圖，以單次版本迭代（如 `v1.1.1.0`）完成 CLI 選項契約對齊、發布預檢與 Git 流水線加固、測試引擎三態守門與 `CmdBags` 全面現代化。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：CLI 選項契約對齊與測試引擎三態／過濾加固（`D-01`、`D-03`、`D-08`）**
   - 更新 `contributes/core.json`（補齊 `test`、`op-test`、`op-mksb` 選項與 `events` 宣告，修正 `--sync` 描述）。
   - 更新 `scripts/cli.py`、`dev/__init__.py`、`dev/tester.py` 與 `dev/testing/runner.py`，修復 `-k`/`-v`/`-q` 子進程傳遞、落實 `UNKNOWN` 剛性阻斷、保留 `_FailedTest` 並將 `NETWORK` 納入預設發現。
2. **Stage 2：`Releaser` 3-Gate 防回退與 `Checker` 檢核器盲區修復（`D-02`、`D-04`）**
   - 升級 `Releaser.release_check` Gate 3 全庫最高版本單調性校驗、修復 `release_git` 對 `git commit` 錯誤之攔截與重複預檢、加固 `release_all` 確定性拓撲排序與上游失敗阻斷。
   - 修復 `Checker._check_custom_rules` 跨模組載入、`_check_core_injection` 源碼 Schema 優先讀取與 `_check_cli_compliance` 函式名檢核。
3. **Stage 3：腳手架／沙盒現代化與 `yscb-module-dev` 技能手冊同步（`D-05`、`D-06`、`D-07`）**
   - 移除 `scaffold.py`、`sandbox.py`、`case.py` 中的 `process(args)` 與 `main(argv)` 範本，修復 `sandbox.py` SemVer 排序、`YSCBTestCase` CWD 還原與 `Builder.build_module(clean)`。
   - 更新 `assets/skills/yscb-module-dev/references/cli_and_commands.md`、`acceptance_checklist.md`、`README.md` 與 `contributes/_manifest.md`。

---

# Part 合流路線圖：技術路線圖：Dev 測試集純化、碎片檔收斂與沙盒／發布管線路徑補盲 (`dev_test_suite_purification_roadmap`) (Roadmap)

> 來源路線圖：dev_test_suite_purification_roadmap.md

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
