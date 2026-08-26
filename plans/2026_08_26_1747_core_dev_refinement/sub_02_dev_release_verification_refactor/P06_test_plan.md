# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Passed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `Builder.build_module` 自動清空 `build/<mod>/` 並產出完整包（保留 `tests/`） | `FR-01` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_build_auto_clean` |
| **FT-02** | 單元測試 | 驗證 `Releaser.release_module` 通過 3-Gate 校驗並產出純淨發布包（排除 `tests/` 與 `.yscbignore`） | `FR-02` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_pure_package` |
| **FT-03** | 整合測試 | 驗證 3-Revision 滑動窗口（同三元組至多 3 份 Revision）與跨三元組升級舊版收斂至 1 份 Revision 之淘汰演算法，以及 `index.json` 實體 SSOT 同步 | `FR-03` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_version_retention_policy` |
| **FT-04** | 整合測試 | 驗證 `Releaser.release_all` 依 `dependencies` DAG 進行 Kahn 拓撲排序批次發布 | `FR-04` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_all_toposort` |
| **FT-05** | 整合測試 | 驗證 `dev test` 預設自動前置執行 `Builder.build`，且傳入 `--no-build` 時跳過 build 直接跑測 | `FR-05` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_tester_pipeline_with_prebuild` |
| **FT-06** | 單元測試 | 驗證 `dev bump-[major\|minor\|patch\|revision]` 對 `manifest.json` 版本號進行單向遞增並寫回 | `FR-06` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_bump_version_commands` |
| **FT-07** | 單元測試 | 驗證 `dev release-check <mod>` 獨立執行 3-Gate 校驗（合規性、未重複、未倒退） | `FR-07` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_check_command` |
| **FT-08** | 整合測試 | 驗證 `dev release-git <mod> <msg>` 依序執行 test ➔ release-check ➔ release ➔ 本地 git commit & tag（確認無 push） | `FR-08` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_git_pipeline` |
| **ET-01** | 邊界測試 | 驗證 Gate 2：嘗試發布發布庫中已存在的四元版本號時拋出 `ReleaseVersionExistsError` 阻斷發布 | `EC-01` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_gate2_version_exists_error` |
| **ET-02** | 邊界測試 | 驗證 Gate 3：嘗試發布小於或等於同三元組在庫最高 revision 版本時拋出 `VersionRollbackError` 阻斷發布 | `EC-02` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_gate3_version_rollback_error` |
| **ET-03** | 邊界測試 | 驗證 `release-git` 任一步驟（test/check/release）失敗時立即終止，絕對禁止執行 Git Commit 與 Tag | `EC-03` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_git_atomic_abort` |
| **ET-04** | 邊界測試 | 驗證 `release-check` 傳入 `--all` 時回報錯誤並拒絕執行 | `EC-04` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_check_reject_all` |
| **ET-05** | 邊界測試 | 驗證 `dev test` 前置 build 失敗時立即阻斷，禁止進入沙盒執行測試 | `EC-05` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_tester_prebuild_fail_abort` |
| **ET-06** | 邊界測試 | 驗證 `release --all` 偵測到循環依賴時拋出異常並輸出依賴環鏈路 | `EC-06` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_toposort_cyclic_dependency_error` |
| **ET-07** | 邊界測試 | 驗證模組首次發布時自動初始化 `release/<mod>/` 目錄與初始 `index.json` | `EC-07` | `python -m unittest test.test_dev_toolchain_refactor.TestDevToolchainRefactor.test_release_first_time_init` |
| **RT-01** | 回歸測試 | 驗證全系統沙盒端到端與契約測試 100% 通過（109/109 Passed） | 全模組 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 斷言結果 | 驗證時間 |
| :--- | :---: | :--- | :--- |
| **FT-01** | `Passed` | `test_build_auto_clean`: 自動清空目標舊檔案，成功產出 `1.0.0.build.zip` (含 `tests/` 與 `manifest.json`) | 2026-08-26 21:11 |
| **FT-02** | `Passed` | `test_release_pure_package`: 通過 3-Gate 校驗，產出純淨 `1.2.3.0.zip` (排除 `tests/` 與 `.yscbignore`) | 2026-08-26 21:11 |
| **FT-03** | `Passed` | `test_version_retention_policy`: 4 份同三元組 zip 成功淘汰第 1 份；跨三元組升級舊三元組收斂至 1 份，`index.json` 實體 SSOT 同步 | 2026-08-26 21:11 |
| **FT-04** | `Passed` | `test_release_all_toposort`: 依據 core ➔ dev ➔ app 拓撲順序安全批次發布 | 2026-08-26 21:11 |
| **FT-05** | `Passed` | `test_tester_pipeline_with_prebuild`: 自動前置執行 build_module 產出 build zip | 2026-08-26 21:11 |
| **FT-06** | `Passed` | `test_bump_version_commands`: `bump-revision` 1.0.0.0➔1.0.0.1，`bump-patch`➔1.0.1.0，`bump-minor`➔1.1.0.0，`bump-major`➔2.0.0.0 | 2026-08-26 21:11 |
| **FT-07** | `Passed` | `test_release_check_command`: 獨立執行 3-Gate 預檢回傳 READY (All 3 Gates Passed) | 2026-08-26 21:11 |
| **FT-08** | `Passed` | `test_release_git_pipeline`: 依序執行 test➔check➔release➔本地 commit & tag，100% 無 remote push | 2026-08-26 21:11 |
| **ET-01** | `Passed` | `test_gate2_version_exists_error`: 重複版本發布時 Gate 2 攔截報錯 | 2026-08-26 21:11 |
| **ET-02** | `Passed` | `test_gate3_version_rollback_error`: 版本倒退時 Gate 3 攔截報錯 | 2026-08-26 21:11 |
| **ET-03** | `Passed` | `test_release_git_atomic_abort`: Step 1 測試失敗立即中斷，禁止 Git Commit & Tag | 2026-08-26 21:11 |
| **ET-04** | `Passed` | `test_release_check_reject_all`: 傳入 `--all` 立即報錯拒絕執行 | 2026-08-26 21:11 |
| **ET-05** | `Passed` | `test_tester_prebuild_fail_abort`: 缺 entry 模組 pre-build 失敗阻斷 | 2026-08-26 21:11 |
| **ET-06** | `Passed` | `test_toposort_cyclic_dependency_error`: 偵測循環依賴拋出 `CyclicDependencyError` | 2026-08-26 21:11 |
| **ET-07** | `Passed` | `test_release_first_time_init`: 首次發布自動建立目錄與 index.json | 2026-08-26 21:11 |
| **RT-01** | `Passed` | `dev test --all`: 109/109 全模組沙盒端到端測試 100% 全部通過 (25.651s) | 2026-08-26 21:12 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者於終端機實際執行 `python yscb.py dev bump-revision <mod>`、`python yscb.py dev release-check <mod>`、`python yscb.py dev release-git <mod> "test commit"`，確認操作體驗流暢、日誌輸出清晰且本地 Git Commit/Tag 正確生成（且未發生 remote push）。
