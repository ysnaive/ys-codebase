# 技術調研報告：module:dev 業務代碼五維度靜態診斷與無損重構處方箋 (R02_code_optimization_audit.md)

> 調研主題：module:dev 業務代碼五維度靜態診斷與外科手術無損重構藍圖  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **定錨基準與範圍摘要**：
  - **檢視範圍**：`Module Scope`（`ys_codebase/source/dev/` 全模組生產源碼，排除 `tests/`）。
  - **生命週期模式**：`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`——強制收斂為單一正統入口（Single Canonical Entry），物理刪除無意義轉發包裝、冗餘雙軌 CLI 參數手工解析與重複演算法實作，並同步更新模組內外與測試調用點。
  - **現行模組檔案規模盤點**（共 12 個生產 `.py` 檔，合計 `4,223` LOC）：
    - `dev/checker.py` (`1,111` LOC) — 8 步合規檢查管線、AST 靜態安全掃描與 `custom_checks` 動態擴充執行器
    - `dev/tester.py` (`880` LOC) — `dev test` / `op-mksb` / `op-test` 調度器、平行沙盒執行緒池與報告聚合
    - `dev/testing/sandbox.py` (`592` LOC) — 虛擬沙盒配置器 (`SandboxProvisioner`) 與上下文 (`SandboxContext`)
    - `dev/testing/runner.py` (`409` LOC) — 測試探索 (`TestDiscovery`)、套件過濾 (`filter_suite`)、執行器 (`TestRunner`) 與報表格式化 (`ASCIIReportFormatter`)
    - `scripts/cli.py` (`397` LOC) — 模組 CLI 路由入口與 `CmdBags` 正規化
    - `dev/testing/case.py` (`318` LOC) — `YSCBTestCase` 測試基類與環境狀態還原
    - `dev/builder.py` (`295` LOC) — `.build.zip` 與 `.zip` 原子打包器及滑動視窗索引維護
    - `dev/releaser.py` (`295` LOC) — 3-Gate 發布預檢、Kahn 拓撲批次發布與 `release-git` 本地流水線
    - `dev/scaffold.py` (`135` LOC) — `dev create` 模組骨架生成器
    - `dev/testing/requirement.py` (`62` LOC)、`dev/testing/contract.py` (`58` LOC)、`dev/__init__.py` (`41` LOC)、`dev/testing/__init__.py` (`22` LOC)
- **核心問題與痛點**：
  1. **巨型破窗檔案與職責過度集中（`D1` / `P0`）**：`dev/checker.py` 高達 `1,111` 行，單一 `Checker` 類別囊括資料結構、Manifest/Contributes Schema 校驗、Python AST 安全與反模式掃描、測試類別 AST 查驗、Hook 腳本審計與動態 `custom_checks` 載入，且 `Checker` 內部 **100% 無實例狀態**（所有 `_check_*` 方法均僅操作傳入參數與 `report`）；`dev/tester.py` 達 `880` 行，混雜兩套獨立的手工 `argv` 旗標解析迴圈、in-place 測試統計迴圈、單模組/多模組平行沙盒調度與 `--sync` 子進程安裝。
  2. **CLI 參數「正規化 $\to$ 反序列化為 `argv` 字串陣列 $\to$ 二次手工迴圈解析」雙重往返腐化（`D1` / `D2` / `D3`）**：`scripts/cli.py` 先透過 `_normalize_bags` 將輸入轉為結構化 `CmdBags`，卻又透過 `_build_tester_argv` 將 `CmdBags` 重新拼接回 `List[str]` 傳給 `Tester.run(argv)`；隨後 `Tester` 在 `_parse_test_run_config` (`tester.py:60-148`) 與 `_run_op_test` (`tester.py:277-316`) 各自維護一套近百行的 `while idx < len(argv)` 手工字串解析迴圈。
  3. **多處同構樣板與模組探索邏輯散落重複（`D3` / `D5`）**：「掃描 `module.source://` 下所有含 `manifest.json` 之有效模組目錄」在 `scripts/cli.py:295-301`、`dev/builder.py:288-294`、`dev/checker.py:1102-1109`、`dev/releaser.py:200-203`、`dev/testing/runner.py:85-101` 與 `dev/testing/sandbox.py:263-268` 重複實作了 **6 次**（且部分使用 `vfs.listdir`，部分直接 `os.listdir(uri.resolve(...))`）；模組鷹架生成樣板在 `Scaffolder.create_module`、`YSCBTestCase.create_mock_source_module` 與 `SandboxContext.create_mock_package` 重複出現 **3 次**。
  4. **死代碼轉發方法與假性實例狀態耦合（`D1` / `D2`）**：`Builder._should_ignore` (`builder.py:123-124`) 為 0 外部調用之純轉發死代碼；`Checker`、`Builder`、`Scaffolder` 中大量輔助方法未讀寫 `self` 卻綁定於實例。
- **調研目標**：
  - 依 `code-optimizer` 之 `D1~D5` 靜態診斷矩陣與 `Mode A` 規範，完整盤點 `ys_codebase/source/dev/` 的契約邊界、病灶座標（`P0 / P1 / P2`）與 `S1~S6` 無損重構處方箋。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 契約邊界與內部工具函式查驗表 (`Mode A` 收斂基準)

| 類別 | 符號 / 入口座標 | 跨模組 / 外部調用現況 | `Mode A` 處置策略 |
| :--- | :--- | :--- | :--- |
| **CLI 註冊公開契約** | `scripts/cli.py`: `create`, `check`, `build`, `test`, `release`, `release_check`, `release_git`, `bump_major`, `bump_minor`, `bump_patch`, `bump_revision`, `op_mksb`, `op_test` | 由 `contributes/core.json` 註冊供 `core` 路由器分派 | **維持公開函數名稱與 `CmdBags -> int` 契約**；收斂內部重複報表渲染與 `Tester` 參數傳遞鏈 |
| **模組頂層導出 (`dev/__init__.py`)** | `Scaffolder`, `Checker`, `Builder`, `Tester`, `Releaser`, `testing` | 外部模組生產代碼 **0 調用**；`dev/tests/` 單元測試直接引用 | **維持 PEP 562 懶載入導出契約**；內部支援 `S6` 物理拆分子模組並由原類別/模組匯總編排 |
| **測試框架 SDK (`dev/testing/__init__.py`)** | `YSCBTestCase`, `Requirement`, `require`, `is_network_available`, `SandboxContext`, `SandboxProvisioner`, `make_contract_suite`, `TestRunner`, `TestDiscovery`, `ASCIIReportFormatter`, `filter_suite` | 全專案 5 大模組 `tests/test_*.py` 廣泛引用 `YSCBTestCase` 與 `Requirement` / `require` | **維持 `dev.testing` 公開匯出簽名 100% 穩定** |
| **死代碼 / 冗餘薄轉發層 (`Mode A` 直接拔除)** | `Builder._should_ignore` ([builder.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/builder.py#L123-L124)) | 全專案（含 `tests/`）**0 調用**，僅單行轉發至模組級 `_should_ignore` | **物理刪除** `Builder._should_ignore` 方法 |
| **內部私有輔助函式（0 外部跨模組調用）** | • `scripts/cli.py`: `_normalize_bags`, `_get_short_to_canonical_pairs`, `_should_skip_alias`, `_build_tester_argv`, `_handle_bump`<br>• `dev/builder.py`: `_should_ignore`, `_create_module_archive_atomic`, `_load_module_ignores`, `_update_build_index`, `_update_release_index`<br>• `dev/checker.py`: `_extract_ast_tokens`, `_collect_declared_cli_commands`, `_audit_cli_script_ast`, `_check_require_decorator_node`, `_method_has_none_requirement`, `_method_calls_mark_passed`, `_verify_test_class_isolation_and_marks`, 以及 `Checker._check_*` 8 個私有方法<br>• `dev/releaser.py`: `resolve_module_dependency_order`, `_extract_manifest_dependencies`, `Releaser._run_git_cmd`<br>• `dev/tester.py`: `safe_print` (僅 `test_tester.py` 測試引用), `_TestRunConfig`, `_parse_test_run_config`, `_extract_test_cases_from_suite`, `_record_test_failure_entry`, `Tester._run_*` | 全專案跨模組生產代碼 **0 調用** | **直接執行 `Mode A` 破壞性收斂**（提取共用發現函式、合併重複參數解析、剝離無狀態方法、拆分子模組） |

### 2.2 重構策略候選方案對比

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：僅做檔案內局部函數微調 (`S1`~`S4`)，不進行物理模組拆分 (`S6`)** | 保持現有 12 個檔案結構不變，僅在 `checker.py` (`1,111` 行) 與 `tester.py` (`880` 行) 內部提取小函式並簡化分支 | 改動檔案少，無匯入路徑調整成本 | `checker.py` 與 `tester.py` 仍維持近千行規模，違反 `P0` God File 治理標準；AST 規則與基礎設施檢查依然強耦合於同一檔案 | ⭐⭐ |
| **方案 B：外科手術式五維度重構 + 正交職責物理拆檔 (`S1`~`S6` 完整組合，推薦)** | 1. 將 `checker.py` (`1,111` 行) 拆解為核心資料模型/編排器與無狀態 AST/Schema 規則子模組（或提取獨立規則函式群）<br>2. 收斂 `tester.py` 雙軌參數解析與報表聚合，消除重複結果計算<br>3. 統一全模組共用之 `discover_source_modules` 與 `safe_print` / 流寫入工具 | 徹底消除 `> 800` 行之 P0 破窗檔，消除 6 處重複模組掃描與 2 套重複 CLI 解析迴圈，且 100% 保持外部與跨模組測試契約無損 | 涉及跨檔案移動與內部匯入更新，需透過 **Full Track** 計畫嚴密控管 | ⭐⭐⭐⭐⭐ |
| **方案 C：全面引入物件導向 Rule Engine / Abstract Visitor 設計模式階層** | 為 `Checker` 的 8 個步驟建立 `BaseCheckRule` 抽象基類與 8 個衍生 Rule 子類別及工廠註冊表 | 形式上符合 GoF 設計模式 | **嚴重違反防過度設計紅線 ②（No Pattern Mania）**，將原本清晰的 8 步線性驗證膨脹為十幾個碎片化類別 | ⭐ |

### 3.1 `D1 ~ D5` 五維度分級診斷矩陣

| 座標 (`檔案路徑:行號區間`) | 維度 | 嚴重度 | 具體結構病徵 (Structural Symptoms) | 建議重構策略 |
| :--- | :---: | :---: | :--- | :---: |
| [checker.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/checker.py#L1-L1111) | **`D1`** | **`P0`** | **巨型破窗檔案 (God File, `1,111` LOC) 與無狀態假性方法綁定**：單一檔案塞入資料模型 (`CheckSeverity`/`CheckIssue`/`CheckReport`)、CLI AST 審計、測試類別 AST 審計、Manifest/Pip/Contributes/Locale 校驗、Python 源碼 Zero-Probing 掃描、Hook 審計與 `custom_checks` 動態模組載入。且 `Checker` 類別無任何 `__init__` 實例狀態，8 個 `_check_*` 方法 100% 為未讀寫 `self` 的無狀態程序。 | `S1`, `S2`, `S6` |
| [tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L1-L880) | **`D1`** | **`P0`** | **巨型複合調度檔 (`880` LOC) 與多重正交職責混雜**：同時承載終端安全編碼輸出 (`safe_print`)、兩套 CLI 旗標解析器 (`_parse_test_run_config` 與 `_run_op_test` 內嵌迴圈)、單進程測試結果分類統計 (`_run_op_test:366-477`)、沙盒子進程調度 (`_execute_single_module_in_sandbox`)、多執行緒平行池 (`_run_parallel_test`) 與宿主 `--sync` 安裝 (`_handle_post_test_sync`)。 | `S1`, `S2`, `S5`, `S6` |
| [checker.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/checker.py#L470-L619)<br>[checker.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/checker.py#L801-L886)<br>[checker.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/checker.py#L1008-L1098) | **`D3`** | **`P1`** | **深層巢狀 (Arrow Anti-pattern, 達 6~8 層縮排) 與超長方法**：<br>1. `_check_core_injection` (`150` 行，縮排達 7 層)：混雜 `core.json` 存在性检查、`_format.json` 元校驗、`<target>.json` 迴圈解析、`locales` 對 `manifest.json` 依賴版本反查 (`L561-585`) 與 `validate_module_locales`。<br>2. `_check_source_files` (`86` 行，縮排達 8 層)：`os.walk` $\to$ `for f` $\to$ `ast.walk` $\to$ 字串常數零探測檢查。<br>3. `_check_custom_rules` (`91` 行，縮排達 6 層)：混雜 4 種 URI/字串格式拆解、臨時篡改 `sys.path`、3 種 `importlib`/`resolve_callable` 載入分支與例外包裝。 | `S1`, `S4` |
| [cli.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/scripts/cli.py#L14-L108)<br>[tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L60-L148)<br>[tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L265-L327) | **`D3`** | **`P1`** | **CLI 參數雙重反序列化與兩套手工 `while` 解析迴圈重複**：`scripts/cli.py` 將 `CmdBags` 透過 `_build_tester_argv` 轉回 `List[str]`，到了 `tester.py` 又在 `_parse_test_run_config` (`89` 行) 與 `_run_op_test` (`63` 行) 各自用 `while idx < len(argv)` 重新解析 `--logical`/`--env`/`--workflow`/`--perf`/`-k`/`--target`/`-q`/`-v`。 | `S3`, `S4`, `S5` |
| [tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L250-L493)<br>[tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L660-L795) | **`D1`**<br>**`D3`** | **`P1`** | **超長程序 (`_run_op_test` 達 `244` 行、`_run_parallel_test` 達 `136` 行)**：`_run_op_test` 內部直接內嵌單一模組測試執行、失敗回溯解析、Contract vs Custom 計數、4 大分類 (`logic`/`env`/`workflow`/`perf`) 統計與 `UNKNOWN` 狀態掃描（`L366-477` 達 110 行），且與 `_run_parallel_test` (`L720-776`) 重複建構相同結構之 `report_data` 字典（`D4` 鬆散裸字典跨階段傳遞）。 | `S1`, `S5` |
| [cli.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/scripts/cli.py#L156-L223) | **`D3`** | **`P1`** | **`check` 命令單模組與全模組報表渲染邏輯重複**：`check()` 函式中 `if check_all:` (`L165-202`) 與 `else:` (`L203-223`) 重複實作相同的 Banner 列印、Issue 格式化 (`|-- [{tag}] [{issue.category}]{loc} {issue.message}`) 與 `status_text` 判定。 | `S3` |
| [cli.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/scripts/cli.py#L295-L301)<br>[builder.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/builder.py#L288-L294)<br>[checker.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/checker.py#L1102-L1109)<br>[releaser.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/releaser.py#L200-L203)<br>[runner.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py#L85-L101)<br>[sandbox.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py#L263-L268) | **`D3`**<br>**`D5`** | **`P1`** | **跨 6 檔重複實作「源碼模組探索」且 VFS 抽象遵從不一致**：6 處各自掃描 `module.source://` 下具備 `manifest.json` 的子目錄；其中 `cli.py:295`、`runner.py:89`、`sandbox.py:264` 繞過 `vfs.listdir` 直接使用 `os.listdir(uri.resolve("module.source://"))`，而 `builder.py`、`checker.py`、`releaser.py` 使用 `vfs.listdir("module.source://")`。 | `S3`, `S5` |
| [builder.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/builder.py#L109-L202) | **`D1`**<br>**`D2`** | **`P1`** | **無狀態方法綁定與孤兒轉發死代碼**：`Builder._should_ignore` (`L123-124`) 為 0 調用之純轉發死代碼；`_load_module_ignores`、`_update_build_index`、`_update_release_index` 完全未讀寫 `self`（僅操作 VFS 與檔案系統），且 `_update_release_index` (`L147-201`) 與 `_update_build_index` (`L126-145`) 共享相同的 `*.zip` 掃描、SemVer 排序與 `index.json` 寫入骨架。 | `S2`, `S3` |
| [scaffold.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/scaffold.py#L10-L135)<br>[case.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/case.py#L178-L255)<br>[sandbox.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py#L37-L120) | **`D3`** | **`P1`** | **三處模組骨架生成樣板高度同構重複**：`Scaffolder.create_module`、`YSCBTestCase.create_mock_source_module` 與 `SandboxContext.create_mock_package` 各自硬編碼生成 `manifest.json`、`scripts/cli.py` (`def hello(cmd_bags)`)、`contributes/_manifest.md` 與 `contributes/core.json`。 | `S3` |
| [sandbox.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py#L153-L243)<br>[sandbox.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py#L245-L320)<br>[sandbox.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py#L419-L500) | **`D3`** | **`P1`** | **`SandboxProvisioner` 內部結構性重複**：<br>1. `prune_sandboxes` (`L153-201`) 與 `cleanup_all_sandboxes` (`L204-243`) 在鎖獲取、`sandbox_parent` 解析、`_ACTIVE_SANDBOXES` 排除集合建構、`sandbox_*` 目錄列舉與迴圈調用 `cleanup_sandbox` 上 **90% 邏輯完全重複**（僅差在 `max_keep` 切片）。<br>2. 「掃描 `module.build://<mod>` 下 `*.zip` 並以 `_sort_zip_filenames_by_semver` 取最新 zip 包」在 `adapt_build_pip_dependencies` (`L274-288`) 與 `_deploy_target_and_dependency_modules` (`L454-467`) 重複實作。 | `S1`, `S3` |
| [tester.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/tester.py#L17-L42)<br>[runner.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/runner.py#L364-L385) | **`D3`** | **`P2`** | **Windows 主控台 Unicode 容錯寫入邏輯重複**：`tester.py` 的 `safe_print` 與 `runner.py` 的 `SafeStreamWriter.write` 各自實作 `UnicodeEncodeError` 捕捉與 `encode(enc, errors="replace").decode(...)` 降級邏輯。 | `S3` |
| [case.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/testing/case.py#L68-L162) | **`D1`**<br>**`D3`** | **`P2`** | **`YSCBTestCase.setUp` (`59` 行) 與 `tearDown` (`34` 行) 混雜環境快照與沙盒探索細節**：`setUp` 內嵌向上走訪父目錄尋找 `sandbox_*` / `host_env` 的迴圈 (`L104-112`)，可提取為具名輔助函式 `_resolve_existing_sandbox_dir()` 以提升主幹可讀性。 | `S1`, `S2` |
| [releaser.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/releaser.py#L97-L168) | **`D1`**<br>**`D3`** | **`P2`** | **`Releaser.release_check` (`72` 行，縮排 6 層)**：Gate 1、Gate 2、Gate 3 邏輯全數平鋪於單一方法內，其中 Gate 3 掃描 `module.release://<mod>` 下所有 `.zip` 並解析最高版本 (`L137-167`) 縮排達 6 層，且與 `Builder._update_release_index` 重複解析目錄版本。 | `S1`, `S2` |

*(註：`D4` 資源生命週期方面，`builder.py` 之 `_create_module_archive_atomic`、`sandbox.py` 之 `create_sandbox` 回滾保護與 `runner.py` 之 `OutputCapturer`/`TestRunner.run_suite` 皆已具備完善的 `try...finally` / `with` 確定性釋放保護，無 `P0` 資源洩漏風險。)*

---

### 3.2 `S1 ~ S6` 外科手術重構處方箋 (Refactoring Blueprint)

#### 處方 1：`dev/checker.py` 業務階段拆解、無狀態剝離與模組瘦身 (`S1` + `S2` + `S4` + `S6`)
1. **階段拆解與扁平化 (`S1` + `S4`)**：
   - **拆解 `_check_manifest` (`L293-433`)**：將 `_check_optional_dependencies(opt, report)` 與 `_check_core_dependency(name, deps, report)` 拆出，消除 `L370-410` 的 6 層 `if-else` 縮排。
   - **拆解 `_check_core_injection` (`L470-619`)**：提取 `_validate_contributes_format_file(contrib_dir, report)`、`_resolve_target_format_schema(target)` 與 `_validate_core_locales_contribution(name, real_dir, fname, c_data, val_res, report)`，將原本 150 行、7 層縮排的巨型方法化為清晰的 3 步管線。
   - **拆解 `_check_source_files` (`L801-886`)**：提取單檔 AST 審計純函式 `_audit_python_source_file(name, full_p, rel_p, is_test_file, report)`，搭配衛語句提早返回，將縮排由 8 層降至 $\le 3$ 層。
   - **拆解 `_check_custom_rules` (`L1008-1098`)**：提取 `_parse_custom_rule_spec(c_func) -> Tuple[str, str]` 與 `_load_and_invoke_custom_checker(c_func, donor, func_name, donor_real, name, real_dir, report)`，消除複雜字串切割與動態匯入交織。
2. **無狀態邏輯剝離與物理拆分 (`S2` + `S6`)**：
   - 若採完整物理拆檔（`S6`），可將 `dev/checker.py` (`1,111` 行) 的 AST 與檔案規則下沉至內部私有輔助模組 `dev/_checker_rules.py`（或保留 `CheckSeverity`, `CheckIssue`, `CheckReport`, `Checker` 於 `dev/checker.py` 作為高階編排門面），使 `dev/checker.py` 行數由 `1,111` 行降至 `< 400` 行，同時 `from dev.checker import Checker, CheckSeverity, CheckIssue, CheckReport` 100% 零破壞。

#### 處方 2：`dev/tester.py` 與 `scripts/cli.py` 參數解析收斂與執行管線化 (`S1` + `S3` + `S5`)
1. **收斂重複的測試選項解析 (`S3` + `S5`)**：
   - 在 `dev/tester.py` 提取統一的測試旗標解析輔助邏輯（或擴充 `_TestRunConfig` 同時支援 `op-test` 所需之 `report_json_path`, `quiet_report`, `test_type`, `pattern`, `contract_only`），彻底消除 `_parse_test_run_config` (`L60-148`) 與 `_run_op_test` (`L265-327`) 兩處高度重複的 `while idx < len(argv)` 解析迴圈。
2. **拆解 `_run_op_test` (`244` 行) 與 `_run_parallel_test` (`136` 行) (`S1` + `S5`)**：
   - 提取 `_execute_and_classify_module_suite(runner, mod_name, test_type, pattern, target, contract_only, sandbox_id, verbose, quiet_report, quiet_mode) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]`，封裝單一模組的測試執行、失敗擷取与 4 維度 (`logic`/`env`/`workflow`/`perf`/`unknown`) 統計，讓 `_run_op_test` 主幹濃縮至 60 行內。
   - 提取 `_build_empty_report_data(filter_mode, target_scope, no_build) -> Dict[str, Any]` 與 `_aggregate_parallel_worker_reports(...)`，消除 `_run_op_test` 與 `_run_parallel_test` 之間重複的報告字典組裝樣板。
3. **收斂 `safe_print` 與 `SafeStreamWriter` (`S3`)**：
   - 將 Windows 安全字元編碼輸出收斂為單一共用底層輔助函式，供 `safe_print` 與 `SafeStreamWriter` 共用（保留 `dev.tester.safe_print` 符號以維持 `test_tester.py` 測試引用）。

#### 處方 3：`dev/testing/sandbox.py` 沙盒清理與建置包檢索聚合 (`S1` + `S3`)
1. **合併 `prune_sandboxes` 與 `cleanup_all_sandboxes` 同構骨架 (`S3`)**：
   - `prune_sandboxes` (`L153-201`) 與 `cleanup_all_sandboxes` (`L204-243`) 可合併核心掃描邏輯：実は `cleanup_all_sandboxes` 即為 `max_keep=0` 時的特例（僅需保留 `is_harness_cleanup` 參數傳遞），或提取共用私有方法 `_collect_removable_sandboxes(sandbox_parent_dir, exclude) -> List[str]`，直接消除 40 行重複的目錄鎖定與過濾代碼。
2. **提取 `_find_latest_build_zip(mod_name: str) -> Optional[str]` (`S3`)**：
   - 收斂 `adapt_build_pip_dependencies` (`L274-281`) 與 `_deploy_target_and_dependency_modules` (`L454-460`) 兩處重複的「定位 `module.build://<mod>` 最新 `.zip` 檔」邏輯。

#### 處方 4：`dev/builder.py`、`dev/releaser.py` 與 `scripts/cli.py` 死代碼清除與樣板統一 (`S2` + `S3`)
1. **物理刪除死代碼 (`Mode A` / `D2`)**：
   - 刪除 `Builder._should_ignore` ([builder.py](file:///d:/repos/ys_codebase/ys_codebase/source/dev/dev/builder.py#L123-L124))。
2. **統一源碼模組探索入口 (`S3` / `D5`)**：
   - 以 `TestDiscovery.discover_modules()`（或於 `dev` 內部提供共用 `list_source_modules()`）統一取代散落於 `scripts/cli.py:295`、`builder.py:288`、`checker.py:1102`、`releaser.py:200` 的重複目錄掃描迴圈。
3. **收斂 `scripts/cli.py` 中 `check()` 報表輸出 (`S3`)**：
   - 提取 `_print_module_check_report(mod: str, rep: CheckReport, show_Only_warn_on_warn_status: bool)`，消除 `check()` 中單模組與全模組分支的重複格式化程式碼。
4. **拆解 `Releaser.release_check` 與共用版本掃描 (`S1` + `S3`)**：
   - 提取 `_list_existing_release_versions(mod_rel_root: str) -> List[semver.VersionTuple]`，供 `Releaser.release_check` (Gate 3) 與 `Builder._update_release_index` 共用，將 `release_check` 縮排由 6 層降為 3 層。

---

## 3. 結論 (Conclusion)

- **診斷總結**：
  - **`P0`（高危破窗 / 巨型檔案）**：**2 項**（`dev/checker.py` 1,111 行、`dev/tester.py` 880 行）。
  - **`P1`（結構耦合 / 重複樣板 / 深層巢狀 / 死代碼）**：**8 項**（`checker.py` 6~8 層深層巢狀、CLI 雙軌重複參數解析、`_run_op_test` 244 行超長程序、`cli.py` 報表重複、跨 6 檔源碼模組探索重複、`Builder._should_ignore` 死代碼与無狀態綁定、3 處模組鷹架樣板重複、`SandboxProvisioner` 沙盒清理與最新 build zip 檢索重複）。
  - **`P2`（局部異味 / 可讀性打磨）**：**3 項**（`safe_print` 與 `SafeStreamWriter` 重複、`YSCBTestCase.setUp` 沙盒路徑向上探索內嵌、`Releaser.release_check` Gate 3 版本掃描深層巢狀）。
- **推薦落地策略與流轉出口**：
  - 建議選擇 **「出口 ① 立即原地升級實作」**：由於涉及單一模組內多檔案深度重構、物理拆檔（`S6`）且預估重構變更行數 `> 100` 行，依 `code-optimizer` 步驟 4 軌道規則，應於子計畫 `sub_02_dev_code_optimization` 內走 **Full Track（`P01`~`P07`）** 分階段執行外科手術無損重構，並以既有 7 個測試檔（`test_builder.py`, `test_case.py`, `test_checker.py`, `test_release_pipeline.py`, `test_sandbox.py`, `test_scaffold.py`, `test_tester.py`）執行 100% 行為等價回歸驗證。
- **預估重構前後結構量化改善目標 (Projected Before / After Metrics)**：

| 量化指標 (Metric) | 重構前 (Before) | 預計重構後 (After Target) | 預期變化幅度 | 結構改善說明 |
| :--- | :---: | :---: | :---: | :--- |
| **最大單一檔案行數 (`checker.py` / `tester.py`)** | `1,111 行` / `880 行` | `< 450 行` / `< 500 行` | `-50% ~ -60%` | 透過 `S1/S2/S6` 剝離無狀態 AST/Schema 規則與測試結果聚合器，徹底消滅千行 God File |
| **最大單一函式行數 (`_run_op_test` / `_check_core_injection`)** | `244 行` / `150 行` | `< 65 行` / `< 50 行` | `-70%+` | 透過 `S1` 業務階段拆解，使公開與核心方法退化為清晰的高階編排器 |
| **最大控制流縮排深度 (`_check_source_files`)** | `8 層` | `≤ 3 層` | `-5 層` | 透過 `S4` 衛語句提早返回與單檔審計純函式提取拉平控制流 |
| **重複模組探索 / 參數解析 / 清理樣板收斂** | `6 處 / 2 套 / 2 處` | `各收斂為 1 處正統入口` | `100% DRY 收斂` | 消除跨檔重複實作，移除 `Builder._should_ignore` 死代碼 |
