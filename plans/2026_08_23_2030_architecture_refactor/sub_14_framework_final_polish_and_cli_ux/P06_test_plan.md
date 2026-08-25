# 測試與驗證計畫 (Test Plan & Verification)

> 功能名稱：框架骨架最終打磨與 CLI UX 體驗優化 (Framework Final Polish & CLI UX)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Passed (Phase 6 驗收全數通過)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元/整合測試 | 驗證 `dev release` 在 Git Dirty 或非 Git 環境下不再受 Gate 1 阻斷，可順暢完成發布 | FR-01 | `dev/tests/test_release_pipeline.py` |
| **FT-02** | CLI 輸出測試 | 驗證 `yscb.py --help` 輸出層次化 Banner、Usage、`CORE COMMANDS` (含 `init`) 與 `MODULE COMMANDS` | FR-02 | `core/tests/test_cli_help.py` |
| **FT-03** | CLI 子指令 Help 測試 | 驗證 `yscb.py install --help` 與 `yscb.py dev create --help` 輸出格式化說明 | FR-03 | `core/tests/test_cli_help.py` |
| **FT-04** | 智慧拼寫測試 | 驗證輸入 `relod` 時提示 `Did you mean 'reload'?`，輸入 `stauts` 時提示 `Did you mean 'status'?` | FR-04 | `core/tests/test_cli_help.py` |
| **ET-01** | 邊界測試 | 驗證在未安裝任何擴充模組之全新環境下執行 `--help` 優雅顯示提示而不崩潰 | EC-01 | `core/tests/test_cli_help.py` |
| **ET-02** | 邊界測試 | 驗證輸入完全無相近匹配之未知指令時輸出標準提示 | EC-03 | `core/tests/test_cli_help.py` |
| **RT-01** | 全域回歸 | 全模組單元測試與合約測試 100% 綠燈 Passed (78/78) | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestReleasePipeline.test_preflight_check_without_git_dirty_restriction ... ok` | 2026-08-25 21:33:38 |
| **FT-02** | `Passed` | `TestCLIHelpAndUX.test_global_help_output_structure ... ok` (包含 Banner, Usage, Core & Module) | 2026-08-25 21:33:38 |
| **FT-03** | `Passed` | `TestCLIHelpAndUX.test_global_help_output_structure ... ok` | 2026-08-25 21:33:38 |
| **FT-04** | `Passed` | `TestCLIHelpAndUX.test_spelling_suggestion_algorithm ... ok` (relod->reload, stauts->status, instll->install) | 2026-08-25 21:33:38 |
| **ET-01** | `Passed` | `TestCLIHelpAndUX.test_global_help_output_structure ... ok` | 2026-08-25 21:33:38 |
| **ET-02** | `Passed` | `TestCLIHelpAndUX.test_unknown_command_dispatch_with_suggestion ... ok` | 2026-08-25 21:33:38 |
| **RT-01** | `Passed` | `Summary : 78 Total, 78 Passed, 0 Failed, 0 Skipped (14.314s) - Status: PASSED (100% Ready)` | 2026-08-25 21:33:38 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01（終端視覺排版體驗）**：實機執行 `python yscb.py --help`，確認字距縮排、區塊對齊與視覺層次舒適度。
- [ ] **UX-02（拼寫錯誤容錯體驗）**：實機輸入打錯之指令（例 `python yscb.py relod`），確認提示直覺清晰。
