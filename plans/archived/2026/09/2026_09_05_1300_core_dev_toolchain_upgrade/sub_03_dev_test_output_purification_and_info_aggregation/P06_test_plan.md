# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_run_test` 在 `--quiet` 且全通時徹底屏蔽子進程 stderr，輸出嚴格維持單行統計 | FR-01, FR-03 | `test_quiet_mode_zero_stderr_leak` |
| **FT-02** | 整合測試 | 驗證單模組測試統一改採 `--report-json` 導出並於宿主端格式化渲染 | FR-02 | `test_single_module_json_ipc_pipeline` |
| **FT-03** | 單元測試 | 驗證一般模式下前置生命週期日誌結構化，且子進程警告完成計數折疊收斂 | FR-04 | `test_normal_mode_warning_collation` |
| **FT-04** | 單元測試 | 驗證 `dev op-test` 在宿主環境直接調用時被剛性阻斷並提示改用 `dev test` | FR-05 | `test_op_test_host_guard` |
| **ET-01** | 邊界測試 | 驗證 `YSCBTestCase.setUp` 在無法向上解析合法沙盒時拋出 `SecurityError`，絕不回退至當前工作目錄 | FR-05 | `test_sandbox_path_validation_blocks_leak` |
| **ET-02** | 邊界測試 | 驗證沙盒進程非預期崩潰（無 report JSON 且非 0 返回碼）時精準提取 stderr 尾部切片診斷 | EC-01 | `test_sandbox_crash_stderr_tail_fallback` |
| **RT-01** | 回歸測試 | 驗證 dev 模組自動化測試全套 100% 通過 | NFR-02 | `python yscb.py dev test dev --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_quiet_mode_zero_stderr_leak`: 驗證 quiet 模式完全屏蔽 stderr 且單行 Pass: 10(100.0%), Fail: 0, Skip: 0 | 2026-09-05 13:53 |
| **FT-02** | `Passed` | `test_single_module_json_ipc_pipeline`: 驗證調度器注入 --report-json 與 --quiet-report 跨進程交換 | 2026-09-05 13:53 |
| **FT-03** | `Passed` | `test_normal_mode_warning_collation`: 驗證一般模式折疊警告為 Notices: 3 sandbox warning(s) captured | 2026-09-05 13:53 |
| **FT-04** | `Passed` | `test_op_test_host_guard`: 驗證宿主直接調用 op-test 觸發 Security Guard Blocked (code 1) | 2026-09-05 13:53 |
| **ET-01** | `Passed` | `test_sandbox_path_validation_blocks_leak`: 驗證非沙盒與無 host_env 時強制拋出 SecurityError 阻斷 | 2026-09-05 13:53 |
| **ET-02** | `Passed` | `test_sandbox_crash_stderr_tail_fallback`: 驗證沙盒崩潰時截取 stderr tail 20 行切片診斷輸出 | 2026-09-05 13:53 |
| **RT-01** | `Passed` | `python yscb.py dev test dev --quiet`: dev 模組 78/78 (100.0%) 全量通過，0 警告外洩 | 2026-09-05 13:54 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py dev test dev --quiet`，確認終端無任何編譯器警告且僅輸出單行 `Pass: X(100.0%), Fail: 0, Skip: 0` | `[測試通過]` | 開發者實機驗收通過 (Pass: 78(100.0%), Fail: 0, Skip: 0, 0 警告) |
| **UX-02** | 實機執行 `python yscb.py dev op-test dev`，確認系統安全阻斷並提示無法在宿主執行 | `[測試通過]` | 開發者實機驗收通過 (Security Guard Blocked, code 1) |
