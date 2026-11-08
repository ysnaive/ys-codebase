# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_dev_closed_loop_ast_static_guardrails  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Checker` 7 步純靜態管線已移除 `_check_custom_rules` 與 `dev/contributes/_format.json`，且對 `core`、`dev` 與全倉 9 大模組檢查皆 `passed == True`（零動態 `importlib` 載入外部模組） | FR-01, NFR-01, NFR-02 | `python yscb.py dev test --target=dev:TestDevChecker.test_check_all_passes` |
| **FT-02** | 單元測試 | 驗證 `_SourceGuardrailVisitor` 單次遍歷正確攔截 `A1`~`F13` 13 項運行期隔離紅線、`from ... import ... as ...` 符號別名呼叫，以及 `getattr(os/sys, ...)` 與 `globals()[...]` 反射規避，且合法不可變常數/`@dataclass(frozen=True)`/含 `timeout=` 之 `subprocess.run` 零誤報通過 | FR-02, FR-03, FR-04, EC-01, EC-02, EC-03 | `python yscb.py dev test --target=dev:TestDevChecker.test_checker_runtime_isolation_guardrails_a_to_f` |
| **FT-03** | 單元測試 | 驗證 `_check_sandbox_hooks` 擴展掃描所有 `scripts/hook.*.py`（如 `hook.core.py`、`hook.dev.py`），強制生命週期事件函式（`on_*`、`pre_cli_dispatch`、`post_cli_dispatch`）至少接受 1 個參數並阻斷頂層裸執行語句 | FR-05 | `python yscb.py dev test --target=dev:TestDevChecker.test_sandbox_hook_compliance` |
| **FT-04** | 整合與回歸測試 | 驗證 `tests/` 目錄豁免生產隔離守門但強制 `YSCBTestCase` 繼承，且 `dev` 全量測試套件（109/109）、`core` 全量測試套件（281 Pass）、`knowledge-db` 測試套件（112/112），以及全倉 9 大模組 `python yscb.py dev check --all` 100% 通過 | FR-01, FR-02, FR-03, FR-04, FR-05, EC-04, NFR-01, NFR-02 | `python yscb.py dev test dev -q --sync` / `python yscb.py dev check --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestDevChecker` 31/31 全數通過（`Summary : 31 Total, 31 Passed, 0 Failed`） | 2026-11-08 |
| **FT-02** | `Passed` | `test_checker_runtime_isolation_guardrails_a_to_f` 驗證 `[A1]`~`[F13]` 負向攔截與正向合規模組全綠通過 | 2026-11-08 |
| **FT-03** | `Passed` | `test_sandbox_hook_compliance` 驗證 `scripts/hook.dev.py` 與 `scripts/hook.core.py` 參數契約與頂層語句攔截通過 | 2026-11-08 |
| **FT-04** | `Passed` | `dev` 全量測試 `109/109 (100.0%)` 通過、`core` 全量測試 `281 Pass / 0 Fail`、`knowledge-db` 測試 `112/112 (100.0%)` 通過，且全倉 `python yscb.py dev check --all` 9 Total, 9 Passed, 0 Warnings, 0 Failed | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev check --all`，確認全倉 9 大模組在全新 13 項 AST 靜態守門下 0 Failed、0 Warnings 全數 `[PASS]` | `[測試通過]` | 開發者驗收確認通過（2026-11-08） |
