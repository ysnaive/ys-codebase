# 測試計畫書 (Test Plan)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、三層安裝降級鏈、發布流水線與 Migration 機制重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Confirmed (CLI 自動化測試 70/70 100% 通過，等候 UX / 手動驗證 Checkpoint)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試策略與驗證維度

本測試計畫遵循 Test-First 原則，針對四段式 SemVer、雙軌來源庫、三層降級鏈、發布流水線與 Migration 引擎進行全面覆蓋：
- **功能測試 (FT)**：驗證四段式版本解析比大小、同 X.Y.Z Revision 淘汰、三層降級鏈解析、`dev build` 完整打包與 Hermetic 清理、`dev release` 5 步流水線、智慧 Git Tag 與 Migration 階梯調用。
- **邊界測試 (ET)**：驗證三段式自動補齊、發布版本重複衝突阻斷、發布中斷原子回滾、Migration 缺腳本跳過、Migration 拋錯快照回滾、跨 Major 鎖定防護。
- **回歸測試 (RT)**：驗證全模組 (core, dev) 現有 59 項測試與新增測試全數 100% 綠燈通過 (70/70 Passed)。

---

## 2. 測試案例清冊 (Test Cases Matrix)

| 測試編號 | 測試名稱 | 驗證目標 | 執行方式 / 斷言 | 對應 FR / EC | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `test_semver_v4_parsing_and_numerical_ordering` | 驗證四段式 `(major, minor, patch, revision)` 解析，前三段數值比大小，`revision` 不參與大小比較 | 呼叫 `parse_semver` 並比對 `1.10.0.0 > 1.9.0.0` 與 `1.0.0.213 == 1.0.0.100` (前三段相同判定同級) | FR-01 | ✅ Passed |
| **FT-02** | `test_single_active_revision_per_xyz` | 驗證 `release/` 發布同 `X.Y.Z` 之新 Revision 時，自動淘汰清理舊版目錄並更新 `index.json` | 模擬存在 `1.0.0.1`，發布 `1.0.0.2`，斷言 `1.0.0.1` 目錄被刪除，`index.json` 僅記錄 `1.0.0.2` | FR-02<br/>EC-03 | ✅ Passed |
| **FT-03** | `test_three_tier_resolution_chain` | 驗證安裝三層降級鏈：`build://` 存在優先 ➔ `mirror://` 次優 ➔ `provider` 兜底 | 在不同層級模擬套件產物，執行 `act_solve_deps`，斷言解析來源依序符合降級鏈 | FR-04 | ✅ Passed |
| **FT-04** | `test_dev_build_complete_packaging_and_hermetic_clean` | 驗證 `dev build` 完整打包（保留 `tests/`，版本強制為 `X.Y.Z.build`），建置前 Hermetic 清空 | 執行 `dev build core`，斷言產物包含 `tests/`，版本為 `*.build`，且清理舊版 `*.build` | FR-05 | ✅ Passed |
| **FT-05** | `test_dev_test_blackbox_pipeline` | 驗證 `dev test` 測試前自動 build，沙盒內依三層鏈標準 install，原地測試（零 source/ 拷貝） | 執行 `dev test core`，斷言沙盒內無 `source/` 目錄，透過 `modules/core/tests` 完成測試 | FR-06 | ✅ Passed |
| **FT-06** | `test_dev_release_five_step_pipeline` | 驗證 `dev release` 依序執行 Bump、純淨打包、更新 Index、Git Commit 與 Git Tag | 執行 `dev release`，斷言 Manifest 版本遞進，`release/` 產物排除 tests，Git Tag 成功建立 | FR-07, FR-09 | ✅ Passed |
| **FT-07** | `test_smart_git_tag_matrix` | 驗證 `major`/`minor` 預設自動打 Tag，`patch`/`revision` 預設不打 Tag，支援 `--tag`/`--no-tag` 覆蓋 | 分別以各級別執行 release，斷言 Git Tag 建立情況符合智慧矩陣 | FR-09 | ✅ Passed |
| **FT-08** | `test_migration_incremental_ladder` | 驗證 `1.0.0` ➔ `1.3.0` 依序調用 `1.1.x.py`, `1.2.x.py`, `1.3.x.py` 增量遷移 | 建立 mock migration 腳本並執行 update，斷言各階梯 `migrate()` 依序被調用 | FR-10 | ✅ Passed |
| **ET-01** | `test_semver_three_segment_auto_normalization` | 驗證三段式版本字串（如 `"1.0.0"`）輸入解析器自動補齊為 `(1, 0, 0, 0)` | 呼叫 `parse_semver("1.0.0")`，斷言輸出四元組且 `canonical_str` 為 `"1.0.0.0"` | FR-01<br/>EC-01 | ✅ Passed |
| **ET-02** | `test_release_duplicate_version_raises_conflict` | 驗證發布完全相同之版本字串時，Gate 3 阻斷並拋出 `VersionConflictError` | 嘗試重複發布已存在版本，斷言拋出衝突例外且無任何修改 | FR-08<br/>EC-02 | ✅ Passed |
| **ET-03** | `test_release_failure_atomic_rollback` | 驗證發布流水線中途拋錯時，自動還原 Manifest、刪除殘留 release 目錄並還原 index | 注入失敗點至打包或 Git 階段，斷言 Manifest 恢復舊版且 release 目錄被乾淨清理 | FR-08<br/>EC-04 | ✅ Passed |
| **ET-04** | `test_migration_missing_script_silently_skipped` | 驗證跨版本階梯中某個 minor 無腳本時，系統自動靜默跳過不報錯 | 升級 `1.0.0` ➔ `1.3.0` 但缺少 `1.2.x.py`，斷言遷移順利完成 | FR-10<br/>EC-05 | ✅ Passed |
| **ET-05** | `test_migration_failure_triggers_snapshot_rollback` | 驗證 Migration 腳本拋錯時，觸發 Snapshot 原子回滾代碼、組態與 `storage://` | 模擬 migration 拋錯，斷言代碼與 `storage://` 資料庫 100% 恢復為升級前舊版 | FR-10, FR-12<br/>EC-06 | ✅ Passed |
| **ET-06** | `test_update_major_boundary_lock` | 驗證日常 `update` 自動鎖定同 Major，不自動升級至下一 Major 破壞性版本 | 當前為 `1.0.0` 遠端有 `2.0.0`，執行 `update` 斷言不自動升級至 `2.0.0` | FR-10<br/>EC-07 | ✅ Passed |
| **RT-01** | `test_full_regression_all_modules` | 驗證全模組 (core, dev) 既有測試與本計畫新增測試全數 100% 綠燈通過 | 實機執行 `python yscb.py dev test --all`，斷言全部測試 100% Passed (70/70) | 全功能 | ✅ Passed |

---

## 3. 測試執行結果 (Test Execution Log)

實機執行命令：`python yscb.py dev test --all`

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (41/41)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (23/23)
----------------------------------------------------------------------
Summary : 70 Total, 70 Passed, 0 Failed, 0 Skipped (9.703s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. UX / 人工驗證 Checkpoint

- [ ] 開發者實機執行 `python yscb.py dev build <mod>` 驗證 `build/` 產物自帶 `tests/` 且版本為 `X.Y.Z.build`。
- [ ] 開發者實機執行 `python yscb.py dev test <mod>` 與 `dev test --all` 驗證黑盒測試順暢無人工 source 拷貝。
- [ ] 開發者實機執行 `python yscb.py dev release <mod> patch/minor` 驗證 Pre-flight 守門、Bump、純淨打包與 Git Tag 觸發行為。
- [ ] 開發者實機檢視 `release/` 目錄，確認同 `X.Y.Z` 僅存單一最新 Revision 產物。
