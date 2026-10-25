# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **CLI 選項契約、單一 Token 子進程傳遞與 PEP 562 延遲載入 (`D-01`, `D-08`, `FR-01`, `FR-07`, `EC-01`)**：補齊 `contributes/core.json` 中 `test`、`op-test`、`op-mksb` 全選項宣告與 `events` 生命週期導覽；於 `scripts/cli.py` 正規化帶值選項與 `alias_map_skip` 防重複展開，於 `tester.py` 將 `-k <pat>` 正規化為單一 Token `--pattern=<pat>`；於 `dev/__init__.py` 實作 PEP 562 `__getattr__` 按需延遲載入並匯出 `Releaser`。
  2. **發布流水線 3-Gate 跨三元組防回退、字母序穩定 Kahn DAG 與 `git commit` 錯誤攔截 (`D-02`, `FR-02`, `EC-02` ~ `EC-04`)**：升級 `Releaser.release_check()` Gate 3 以全庫最高版本 `global_highest` 嚴格攔截跨三元組版本回退（即使 `--force` 亦剛性阻斷）；重構 `release_all()` 採初始字母序穩定 Kahn 演算法拓撲排序，並在偵測循環依賴時拋出 `CyclicDependencyError`、上游模組失敗時自動跳過下游模組；修復 `release_git()` 嚴格攔截非 `nothing to commit` 之致命 `git commit` 失敗；`scripts/cli.py:release_check` 支援無參數預設檢核全模組。
  3. **測試引擎 `UNKNOWN > 0` 剛性阻斷、`_FailedTest` 保留與檢核器/沙盒現代化 (`D-03` ~ `D-07`, `FR-03` ~ `FR-06`, `EC-05` ~ `EC-07`)**：於 `tester.py` 與 `runner.py` 實作 `unknown > 0` 時 `all_passed = False`、扣除 `custom_passed`、報表顯示 `FAILED` 且行程回傳非零退出碼 `1`；`filter_suite()` 強制跨 `--type` 保留 `_FailedTest` 並將 `Requirement.NETWORK` 納入預設發現；`Checker._check_custom_rules()` 支援 `code.func://` 並以 `module://<donor>` 臨時注入與 `try...finally` 還原 `sys.path`、異常轉 `WARN`；`_check_core_injection()` 優先讀取 `module.source://<target>/contributes/_format.json`；`_check_cli_compliance()` 精確對齊 `candidates = {full_fn, primary_fn}`；全面汰除 `Scaffolder` 與 Mock 產生器之 `process(args)` 遺留模板；`SandboxProvisioner` 改用 `semver.parse()` 數值排序並防護損毀 Zip，`YSCBTestCase.tearDown()` 自動還原 CWD，`Builder.build_module()` 尊重 `clean` 旗標。
  4. **測試套件 10 檔 $\to$ 7 檔純化收斂與高風險路徑補盲 (`DT-01` ~ `DT-05`, `FR-08`, `FR-09`, `NFR-01`, `NFR-02`)**：刪除 `test_cli_compliance.py`、`test_output_purification.py`、`test_pip_adaptation.py` 3 個碎片檔並無損整併至 7 個子系統測試檔；消除頂層 `DummySharedTestCase` 重複發現與共享沙盒 `mock_*` 模組／暫存檔殘留；重寫 5 處虛假／自寫自驗測試並補齊 `D-01`~`D-08` 完整回歸覆蓋。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/dev/contributes/core.json` | Modify | 補齊 `test`、`op-test`、`op-mksb` 選項契約（含 `quiet_report` 獨立群組）與 `events` 宣告 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 同步更新貢獻導覽清冊、`events` 與 `yscb-module-dev` 技能路由說明 |
| `ys_codebase/source/dev/dev/__init__.py` | Modify | 實作 PEP 562 `__getattr__` 按需延遲載入並匯出 `Releaser` |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | 強化 `_normalize_bags` 帶值選項與 `alias_map_skip` 防重複展開；`release_check` 支援無參數檢核全模組 |
| `ys_codebase/source/dev/dev/tester.py` | Modify | 子進程 `--pattern=<pat>` 單一 Token 正規化、`UNKNOWN > 0` 剛性阻斷與 `custom_passed` 扣除 |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | `filter_suite` 跨 `--type` 保留 `_FailedTest`、納入 `NETWORK` 預設發現；`format_summary` 校驗 `unknown == 0` |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | `tearDown()` 自動還原 `self._orig_cwd`；`create_mock_source_module` 改生成 `CmdBags` 合規模板 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `semver.parse()` 數值排序選包、`zipfile.BadZipFile` 防護；`create_mock_package` 改生成 `CmdBags` 模板 |
| `ys_codebase/source/dev/dev/testing/contract.py` | Modify | 更新 `test_contract_entrypoint_valid` 介面註解對齊 `CmdBags` 合約 |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | Gate 3 `global_highest` 跨三元組防回退、`release_all` 字母序穩定 Kahn DAG 與 `CyclicDependencyError`、`release_git` commit 失敗攔截 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_custom_rules` 支援 `code.func://` 與 `module://` 隔離、`WARN` 降級；`_check_core_injection` 源碼優先；`_check_cli_compliance` 對齊 `{full_fn, primary_fn}` |
| `ys_codebase/source/dev/dev/scaffold.py` | Modify | 新模組骨架生成 `def hello(cmd_bags)`、`guard_dispatch`、真實換行 `tests/__init__.py` 與 `mark_passed()` 測試 |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `build_module()` 尊重 `clean: bool` 參數控制是否預清 `.build/<name>` |
| `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/cli_and_commands.md` | Modify | 校正 `CmdBags` 取值語法、預設版號 `0.1.0.0`、`.build.zip` 路徑與 3-Gate 定義 |
| `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/acceptance_checklist.md` | Modify | 更新 CLI 入口檢核紅線說明為具名 `CmdBags` 命令函式 |
| `ys_codebase/source/dev/README.md` | Modify | 同步更新模組手冊 CLI 選項、3-Gate 與 `.build.zip` 路徑 |
| `docs/dev/README.md` | Modify | 同步更新系統知識庫 `dev` 模組手冊 |
| `docs/dev/DESIGN_NOTES.md` | Modify | 新增 `[DN-DEV-04]` 記錄 CLI 具名函式對稱契約、3-Gate 全庫最高版本防回退與 `UNKNOWN` 剛性阻斷 |
| `ys_codebase/source/dev/tests/test_*.py` | Modify / Delete | 刪除 3 個歷史碎片測試檔，收斂為 7 個子系統測試檔（79 項測試 100% 通過且沙盒零殘留） |
| `CHANGELOG.md` | Modify | 增補 `sub_02_dev_toolchain_and_tests` 結案發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev check dev` 100% PASSED（0 Fail, 0 Warn）；`python yscb.py dev test dev --sync` **79/79 Passed (100% Ready, 6.19s)**（Contract: 3/3, Custom: 76/76 [Logic: 64, Env: 12], 0 Failed, 0 Unknown, 0 Skipped），並自動完成 `dev@1.1.0.build` 本地熱部署。
- **實機 UX / 人工驗證**：
  - `UX-01`：執行 `python yscb.py dev test core -k manifest -q`，輸出 `Pass: 2(100.0%), Fail: 0, Skip: 0`（Exit 0），子進程參數無損傳遞。
  - `UX-02`：執行 `python yscb.py dev release-check --force`，預設掃描全數 5 模組並逐一通過 3-Gate 檢核。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [CHANGELOG.md](../../../CHANGELOG.md) | 已完成 | 同步記錄 `sub_02_dev_toolchain_and_tests` 架構強化與測試純化亮點 |
| **中觀 (Meso)** | [docs/dev/README.md](../../../docs/dev/README.md)、[ys_codebase/source/dev/README.md](../../../ys_codebase/source/dev/README.md) | 已完成 | 同步更新 `dev` CLI 選項、3-Gate 全庫防回退與 `.build.zip` 路徑說明 |
| **中觀 (Meso)** | [cli_and_commands.md](../../../ys_codebase/source/dev/assets/skills/yscb-module-dev/references/cli_and_commands.md) | 已完成 | 校正 `CmdBags` 取值語法、預設版號 `0.1.0.0`、產物路徑與 3-Gate 定義 |
| **中觀 (Meso)** | [docs/dev/DESIGN_NOTES.md](../../../docs/dev/DESIGN_NOTES.md) | 已完成 | 增補 `[DN-DEV-04]` CLI 具名函式契約、全庫單調防回退與 `UNKNOWN` 阻斷註記 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 完整維護 `tester.py`、`releaser.py`、`checker.py`、`runner.py`、`contract.py` Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（通過 Pillar 3 Fresh-Eyes Review `REVIEW_STATUS: PASSED`）。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(dev): harden dev toolchain contracts, 3-gate release pipeline, and purify test suite (sub_02)

- Normalize CLI options and single-token --pattern=<pat> forwarding in scripts/cli.py and tester.py (D-01)
- Enforce Gate 3 global_highest cross-triplet rollback protection, alphabetical Kahn DAG release_all, and git commit failure interception in Releaser (D-02)
- Enforce rigid failure when UNKNOWN > 0, retain _FailedTest across --type filters, and include NETWORK in default discovery (D-03)
- Support code.func:// and module:// runtime isolation in Checker._check_custom_rules, prioritize source _format.json, and align CLI handler check to {full_fn, primary_fn} (D-04)
- Modernize Scaffolder and mock module templates to CmdBags, fix SemVer zip sorting, restore CWD in tearDown, and respect Builder clean flag (D-05, D-06)
- Implement PEP 562 lazy loading in dev/__init__.py and align yscb-module-dev skill references and docs/dev (D-07, D-08)
- Consolidate dev/tests/ from 10 files into 7 subsystem suites with 79/79 passing tests and zero sandbox leakage (DT-01~DT-05)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify sub_02_dev_toolchain_and_tests` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

