# 測試計畫書 (Test Plan)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：Passed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 測試策略與驗證架構

本測試計畫採 Test-First 前置設計，全面覆蓋 P01 定義之所有功能需求 (FR-01~06) 與邊界條件 (EC-01~06)：
- **單元/整合測試環境**：繼承 `dev.testing.YSCBTestCase`，在 `temp://sandbox_<uuid>` 隔離沙盒執行。
- **下游獨立專案隔離驗證**：專門模擬「外部下游專案與工具庫目錄實體分離、`project_root` 為 `!undefined`」的極限情境，確保 `yscb.config.json` 讀寫 100% 穩定。

---

## 2. 測試案例清冊 (Test Cases Matrix)

| 測試編號 | 測試名稱 | 驗證目標 | 執行方式 / 斷言 | 對應 FR / EC | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `test_host_config_isolation_from_project_uri` | 驗證 `_get_config`、`_save_config` 與快照讀寫直接使用 `host_dir`，當 `project_root` 為 `!undefined` 時套件管理零阻斷 | 呼叫 `engine.act_register`, `act_snapshot`, `act_restore_snapshot`，斷言在 `project_root` 未定義時 100% 成功 | FR-01<br/>EC-01 | ✅ Passed |
| **FT-02** | `test_yscb_uri_constant_self_locating` | 驗證 `yscb://` 採 `__file__` 常數確定性自定位，且支援 `YSCB_HOST_DIR` 與 `set_host_dir` 注入 | 驗證在不同工作目錄下 `uri.resolve("yscb://modules")` 解析精確無誤 | FR-02 | ✅ Passed |
| **FT-03** | `test_uninitialized_host_raises_file_not_found` | 驗證在完全未初始化的目錄中調用 `_find_host_config` 拋出顯式 `FileNotFoundError`，絕不隱式猜測 | 在無 `yscb.config.json` 環境下執行，斷言拋出 `FileNotFoundError` | FR-02<br/>EC-02 | ✅ Passed |
| **FT-04** | `test_builder_generates_and_updates_index_json` | 驗證 `dev build` 打包模組後自動在 `build/{module}/index.json` 生成/更新版本清冊且排序去重 | 執行 `Builder.build_module` 兩次不同版本，驗證 `index.json` 包含有序 `versions: ["1.0.0", "1.1.0"]` | FR-03<br/>EC-05 | ✅ Passed |
| **FT-05** | `test_remove_reverse_dependency_guard` | 驗證 `cmd_remove` 阻斷被其他模組依賴的模組移除，且 `--force` 允許強制移除 | 安裝依賴 `dev` 的模組 `mock_app`，執行 `remove dev` 斷言回傳 1；帶 `force=True` 斷言成功 | FR-04<br/>EC-03<br/>EC-04 | ✅ Passed |
| **FT-06** | `test_manifest_dependencies_schema_compatibility` | 驗證 `dependencies` 同時支援 Dict 與 List 格式宣告 | 測試解析 `{"core": ">=1.0.0"}` 與 `["core >=1.0.0"]` 均能正確提取相依資訊 | FR-05 | ✅ Passed |
| **FT-07** | `test_cmd_init_seeds_default_provider` | 驗證 `yscb.py` `cmd_init` 寫入的 `yscb.config.json` 包含 `default_provider` 欄位 | 執行 `cmd_init`，斷言產出之組態包含 `"default_provider"` | FR-05 | ✅ Passed |
| **FT-08** | `test_act_solve_deps_recursive_and_cycle_guard` | 驗證 `act_solve_deps` 遞迴拓撲解析與循環相依檢測 | 模擬相依鏈 `A -> B -> C` 斷言返回順序 `[C, B, A]`；模擬循環依賴 `A -> B -> A` 斷言拋出 `ValueError` | FR-06<br/>EC-06 | ✅ Passed |
| **RT-01** | `test_full_regression_suite` | 驗證全系統既有功能與 Auto-Contract 契約測試不受影響 | 實機執行 `python yscb.py dev test --all --verbose` | NFR-03 | ✅ Passed |

---

## 3. 測試執行結果 (Test Execution Log)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (21/21)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (11/11)
----------------------------------------------------------------------
Summary : 38 Total, 38 Passed, 0 Failed, 0 Skipped (0.555s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. UX / 人工驗證 Checkpoint

- [x] 開發者指示免測：CLI 自動化測試 38/38 (100%) 通過，免測通過進入 Phase 7。
