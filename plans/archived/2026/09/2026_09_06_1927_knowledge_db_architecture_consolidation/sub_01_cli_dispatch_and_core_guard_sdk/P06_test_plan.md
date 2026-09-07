# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | Core 守門 SDK 授權通過：當存在合法 Token 與 Host Dir 時不中斷 | FR-03 | `python yscb.py dev test core -k test_guard_authorized` |
| **FT-02** | 單元測試 | Core 守門 SDK 繞道阻斷：當缺乏合法 Token 時以 Exit Code 126 退出並印出引導 | FR-03, EC-04 | `python yscb.py dev test core -k test_guard_unauthorized_exit` |
| **FT-03** | 單元測試 | Core 守門 SDK 測試豁免：當 `YSCB_TESTING=1` 時不觸發阻斷 | FR-03, EC-05 | `python yscb.py dev test core -k test_guard_testing_mode` |
| **FT-04** | 單元測試 | `dev.scaffold` 骨架合規：新模組產出之 `scripts/cli.py` 含 `process`、無 `main` | FR-04 | `python yscb.py dev test dev -k test_scaffold_cli_format` |
| **FT-05** | 單元測試 | `dev.checker` 正向檢測：合規 `scripts/cli.py` 驗證判定為 PASS | FR-05, FR-06 | `python yscb.py dev test dev -k test_checker_cli_pass` |
| **FT-06** | 單元測試 | `dev.checker` 負向檢測：缺少 `process` 函式立即判定 FAIL | FR-05, EC-01 | `python yscb.py dev test dev -k test_checker_missing_process` |
| **FT-07** | 單元測試 | `dev.checker` 負向檢測：殘留 `main` 函式或 `__main__` 立即判定 FAIL | FR-02, EC-02 | `python yscb.py dev test dev -k test_checker_forbidden_main` |
| **FT-08** | 單元測試 | `dev.checker` 負向檢測：包含頂層裸執行陳述式立即判定 FAIL | FR-06, EC-03 | `python yscb.py dev test dev -k test_checker_toplevel_statements` |
| **FT-09** | 整合測試 | `yscb.py` 分派協議：調用模組 `process(args)` 並完整透傳 exit code | FR-07 | `python yscb.py dev test core -k test_yscb_dispatch_process` |
| **RT-01** | 全模組回歸 | 全生態系現有模組單元測試全數回歸通過 | FR-08 | `python yscb.py dev test core && python yscb.py dev test dev && python yscb.py dev test agents-workflow && python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | Core 守門 SDK 於合法 Token/HostDir 下順利通過，未觸發中斷 | 2026-09-06 |
| **FT-02** | `Passed` | 繞道調用時輸出安全警告引導訊息，並精確拋出 SystemExit(126) | 2026-09-06 |
| **FT-03** | `Passed` | `YSCB_TESTING=1` 測試模式下成功放行，無阻斷異常 | 2026-09-06 |
| **FT-04** | `Passed` | `dev create` 生成模組骨架之 `scripts/cli.py` 符合 AST 規範 | 2026-09-06 |
| **FT-05** | `Passed` | `dev.checker` AST 正向檢核合規 `scripts/cli.py` 判定 PASS | 2026-09-06 |
| **FT-06** | `Passed` | `dev.checker` 缺少 `process` 函式時精確攔截並回報 FAIL | 2026-09-06 |
| **FT-07** | `Passed` | `dev.checker` 包含 `main` 或 `__main__` 時精確攔截並回報 FAIL | 2026-09-06 |
| **FT-08** | `Passed` | `dev.checker` 包含頂層裸語句時精確攔截並回報 FAIL | 2026-09-06 |
| **FT-09** | `Passed` | 直接繞道調用被 exit 126 阻斷；yscb 派發透傳退出碼正確 | 2026-09-06 |
| **RT-01** | `Passed` | 全生態系 4 模組共 437 個測試案例 100% PASS (0 Failed) | 2026-09-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端直接執行 `python ys_codebase/source/knowledge-db/scripts/cli.py`：確認因已徹底移除 `__main__` 執行區塊，直接執行零輸出、零副作用退出；若以 Python 呼叫其 `process([])` 則精確觸發 Core 守門 SDK 警示並以 126 退出。 | `[跳過/免測]` | 開發者確認免測 (2026-09-06) |
