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
