# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：合併落實 `dev_toolchain_and_sandbox_hardening_roadmap.md`（`D-01` ～ `D-08`）與 `dev_test_suite_purification_roadmap.md`（`DT-01` ～ `DT-05`），加固開發、檢核、打包與沙盒測試引擎。
- **核心目標**：
  1. 補齊 `contributes/core.json` 中 `test`、`op-test`、`op-mksb` 之選項契約與 `events` 宣告，修復 `-k <pattern>`、`-v`、`-q`、`--sequential` 跨沙盒子進程傳遞失真與 `--sync` 描述不一致（`D-01`, `D-08`）。
  2. 升級 `Releaser.release_check` Gate 3 為全庫最高版本防回退、加固 `release_all` 確定性拓撲排序與上游失敗阻斷、修復 `release_git` 無條件吞沒 `git commit` 失敗及重複預檢（`D-02`）。
  3. 落實測試引擎 `UNKNOWN > 0` 剛性阻斷與 `custom_passed` 扣減、將 `Requirement.NETWORK` 納入預設發現並強制保留 `_FailedTest`（`D-03`）。
  4. 修復 `Checker._check_custom_rules`（僅注入 `module://<donor>`）、`_check_core_injection`（優先讀 `module.source://` Schema）與 `_check_cli_compliance`（對齊 `{full_fn, primary_fn}`），全面汰除 `process(args)` 與 `main(argv)` 遺留範本，修復 SemVer 排序與 CWD 還原，並校正 `yscb-module-dev` 手冊（`D-04` ～ `D-07`）。
  5. 將 `dev/tests/` 由 10 檔收斂為 7 個子系統測試檔，消除 `DummySharedTestCase` 雙重發現、修復 5 處虛假／自我 Mock 測試與 4 處暫存目錄洩漏，並補齊 5 大高風險回歸測試（`DT-01` ～ `DT-05`）。
- **邊界排除 (Explicitly Excluded)**：不破壞既有合規模組之 `dev check` 兼容性，嚴禁向運行時 `sys.path` 注入 `module.source://`。
- **架構影響範圍**：`ys_codebase/source/dev/dev/{__init__.py,checker.py,builder.py,tester.py,releaser.py,scaffold.py}`、`dev/testing/{runner.py,sandbox.py,case.py}`、`contributes/`、`scripts/cli.py`、`assets/skills/yscb-module-dev/` 與 `tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **`_check_cli_compliance` 精確對齊 `{full_fn, primary_fn}` (`D-04`)**：合法候選集合保留平鋪底線全名 `full_fn` 與頂層第一段群組路由函式 `primary_fn`，移除無效之 `leaf_fn` 與 `cmd_*`。
- **[P00:DR-02]** **`_check_custom_rules` 嚴守 `.modules/` 剛性隔離 (`D-04`)**：載入跨模組檢查函式時僅將 `uri.resolve(f"module://{donor}")` 臨時加入 `sys.path`，絕不注入 `module.source://`。
- **[P00:DR-03]** **測試 `UNKNOWN` 與 `SyntaxError` 之 AST 靜態掃描防呆 (`DT-05`)**：一律透過 `create_mock_source_module(..., files={"tests/test_bad.py": "..."})` 寫入沙盒暫存檔受測，嚴禁直接於 `dev/tests/test_tester.py` AST 中定義未呼叫 `self.mark_passed()` 之類別。

---

## 3. 開放議題與確認紀錄

- 規格與防呆邊界已於前置路線圖審查中 100% 確認收斂，狀態標記為 `Confirmed`。

