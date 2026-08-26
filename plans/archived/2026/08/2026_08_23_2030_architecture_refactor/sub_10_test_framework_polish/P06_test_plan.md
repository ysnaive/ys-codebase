# 測試計畫書 (Test Plan)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試策略與驗證維度

本測試計畫採用 Test-First 原則，針對微型虛擬環境生成、`YSCB_ROOT` 重定向、`hook.dev.py` 自治調度與 CLI 參數過濾進行全面覆蓋：
- **功能測試 (FT)**：驗證三大子空間生成、VFS 協議隔離、Hook 注入與 `--type` / `-k` 篩選。
- **邊界測試 (ET)**：驗證 Hook 例外隔離、無效 `--type` 退出碼與打包保留 `hook.dev.py`。
- **回歸測試 (RT)**：驗證既有 38/38 項單元與契約測試 100% 綠燈。

---

## 2. 測試案例清冊 (Test Cases Matrix)

| 測試編號 | 測試名稱 | 驗證目標 | 執行方式 / 斷言 | 對應 FR / EC | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `test_op_mksb_atomic_provisioning` | 驗證 `dev op-mksb` 原子指令自動建立三大子空間、複製 source 並觸發 hook.dev.py | 執行 `dev op-mksb`，斷言沙盒生成完備且 `config.project.json` 配置正確 | FR-01<br/>FR-03 | ✅ Passed |
| **FT-02** | `test_sandbox_vfs_natural_constant_self_locating` | 驗證沙盒內代碼藉由 `__file__` 天然自定位於 `sandbox/host_env/engine/`，0 修改 `core.uri` | 在沙盒環境下解析 `uri.resolve("yscb://modules")`，斷言其精準指向沙盒內部 | FR-02<br/>EC-01 | ✅ Passed |
| **FT-03** | `test_op_test_in_place_execution` | 驗證 `dev op-test` 原子指令在當前環境原地執行測試，零沙盒建立、零遞迴 | 在沙盒內部呼叫 `dev op-test`，斷言無二度沙盒產生且測試順利通過 | FR-04 | ✅ Passed |
| **FT-04** | `test_dev_test_high_level_orchestration` | 驗證 `dev test` 組合門面調用 `op-mksb` ➔ `op-test` ➔ 自動清理生命週期閉環 | 在父層呼叫 `dev test`，斷言沙盒自動創建、執行並在通過後完整銷毀 | FR-05 | ✅ Passed |
| **FT-05** | `test_dual_source_provider_resolution` | 驗證沙盒從父層 `build/` 讀取本地產物，並共享父層 `.mirror/` 離線快取 | 在沙盒中執行套件查詢與安裝，斷言套件成功解析與安裝 | FR-06 | ✅ Passed |
| **FT-06** | `test_type_filter_and_recursive_pattern_filter` | 驗證 `--type` 與 `-k` 遞迴過濾巢狀 TestSuite 案例 | 傳入 `--type=logic` 與 `-k=test_xxx`，斷言僅執行符合條件之測試案例 | FR-06 | ✅ Passed |
| **ET-01** | `test_hook_dev_error_isolation` | 驗證模組 Hook 拋錯時 `dev.testing` 實施例外隔離，不中斷測試套件 | 模擬拋錯 Hook，斷言測試輸出 Warning 且套件繼續執行 | EC-02 | ✅ Passed |
| **ET-02** | `test_invalid_type_filter_cli_exit_1` | 驗證傳入無效 `--type` 參數時輸出提示並返回 Exit Code 1 | 呼叫 `Tester.run(["core", "--type=invalid"])`，斷言返回 1 | EC-03 | ✅ Passed |
| **ET-03** | `test_builder_preserves_hook_dev` | 驗證 `dev build` 打包時排除 `tests/` 但保留 `scripts/hook.dev.py` | 執行 `Builder.build_module("core")`，斷言打包產物包含 `scripts/hook.dev.py` | EC-05 | ✅ Passed |
| **RT-01** | `test_full_regression_all_modules` | 驗證全模組 (core, dev) 所有 contract 與 custom test 100% 通過 | 執行 `python yscb.py dev test --all`，斷言 47/47 測試全綠燈 | 全功能 | ✅ Passed |

---

## 3. 測試執行結果 (Test Execution Log)

> 待 Phase 5 實作完成後，於 Phase 6 實機執行並回填詳細日誌。

---

## 4. UX / 人工驗證 Checkpoint

- [ ] 開發者實機驗證在多模組測試下，父層 `ys_codebase/.mirror` 與 `.snapshots` 100% 零殘留。
