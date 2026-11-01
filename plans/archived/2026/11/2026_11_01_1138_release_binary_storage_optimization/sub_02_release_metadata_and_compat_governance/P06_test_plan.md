# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：版本相容性事後修正機制、釋出元數據與更新嚴重度治理 (sub_02)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **ET-01** | 邊界測試 | 當遠端最新版本於 `index.json["releases"]` 被事後修補為要求更高 `core` 版本（如 `core:>=9.0.0`）時，`UpdateChecker` 與 `Installer.cmd_update` 均過濾該不相容版本，僅推薦與升級至最高相容版本並清除舊快取 | EC-01 | `python yscb.py dev test core -q` |
| **ET-02** | 邊界測試 | 跨版本升級區間 `(cur_ver, latest_ver]` 中，中間版本已標記為 `status: "pruned"` 但帶 `urgency: "critical"`，最新活躍版本為 `optional` 時，`UpdateChecker` 仍正確捕捉並觸發 `[CRITICAL UPDATE]` 告警 | EC-02 | `python yscb.py dev test core -q` |
| **ET-03** | 邊界測試 | `index.json["releases"]` 含未知 `type`（如 `"security"`）與未知 `urgency`（如 `"urgent"`）時，`UpdateChecker` 不拋出例外並轉為 `[SECURITY]` 一般更新提示 | EC-03 | `python yscb.py dev test core -q` |
| **ET-04** | 邊界測試 | 離線 `reload` 時，`_reload_materialize_single_module` 透過 `module.mirror://<mod>/index.json` 覆寫 `.mirror/<mod>/<ver>.zip` 解壓後之 `manifest.json["dependencies"]` | EC-04 | `python yscb.py dev test core -q` |
| **ET-05** | 邊界測試 | `Releaser.patch_release_index` 與 `Checker._check_manifest` 對無效 `status` 或格式錯誤之 `"release"` 元數據正確攔截報錯 | EC-05 | `python yscb.py dev test dev -q` |
| **FT-06** | 單元測試 | `AtomicEngine` 優先採用 `index.json["releases"][<ver>]["dependencies"]` 並於 `act_solve_deps` 檢核 `dep_name == "core"` 與已安裝 `core` 版本相容性 | FR-01 | `python yscb.py dev test core -q` |
| **FT-07** | 單元測試 | `dev index-patch` 更新 `index.json["releases"][<ver>]` 之 `dependencies`、`status`、`type`、`urgency`、`summary` 並同步維護頂層 `versions` 清單 | FR-02 | `python yscb.py dev test dev -q` |
| **FT-08** | 單元測試 | `Releaser.release_module` 帶入 `release_meta` 時雙軌寫入 `source/<mod>/manifest.json["release"]` 與 `release/<mod>/index.json["releases"][<ver>]`，且 `Builder._update_release_index` 保留歷史版本已修補之元數據 | FR-03 | `python yscb.py dev test dev -q` |
| **FT-09** | 單元測試 | `UpdateChecker` 對 `urgency: "critical"`（或 `type: "hotfix"`）渲染雙線 `[!] [CRITICAL UPDATE]` 警告橫幅，對一般更新附帶 `[<TYPE>]` 與 `summary` | FR-04 | `python yscb.py dev test core -q` |
| **RT-10** | 回歸測試 | `dev index-patch` 僅修改 `index.json` 且不重壓 `.zip`；`dev` 全量單元測試 100% 通過 | NFR-01 | `python yscb.py dev test dev -q` |
| **RT-11** | 回歸測試 | 舊格式 `manifest.json` 與 `index.json` 無 `"release"` 欄位時向後相容；`core` 全量單元測試 100% 通過 | NFR-02 | `python yscb.py dev test core -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **ET-01** | `Passed` | `TestUpdateChecker.test_forward_safe_unknown_metadata_and_incompatible_core_filtering` 驗證不相容 `core` 版本過濾 | 2026-11-01 |
| **ET-02** | `Passed` | `TestUpdateChecker.test_cross_version_pruned_critical_aggregation_and_banner` 驗證跨版本 `pruned` 之 `critical` 告警聚合 | 2026-11-01 |
| **ET-03** | `Passed` | `TestUpdateChecker.test_forward_safe_unknown_metadata_and_incompatible_core_filtering` 驗證未知 `type`/`urgency` 向前相容 | 2026-11-01 |
| **ET-04** | `Passed` | `TestDistributionLifecycle.test_release_index_dependency_override_core_compat_and_offline_mirror_reload` 驗證 `mirror://` 離線 `reload` 覆寫 | 2026-11-01 |
| **ET-05** | `Passed` | `TestReleasePipeline.test_dual_track_release_meta_index_patch_and_manifest_validation` 驗證無效 `--dep` 與 `release` 欄位攔截 | 2026-11-01 |
| **FT-06** | `Passed` | `TestDistributionLifecycle.test_release_index_dependency_override_core_compat_and_offline_mirror_reload` 驗證 `index.json` 依賴覆寫與 `core` 依賴檢核 | 2026-11-01 |
| **FT-07** | `Passed` | `TestReleasePipeline.test_dual_track_release_meta_index_patch_and_manifest_validation` 驗證 `dev index-patch` 更新與排序 | 2026-11-01 |
| **FT-08** | `Passed` | `TestReleasePipeline.test_dual_track_release_meta_index_patch_and_manifest_validation` 驗證雙軌寫入與歷史修補保留 | 2026-11-01 |
| **FT-09** | `Passed` | `TestUpdateChecker.test_cross_version_pruned_critical_aggregation_and_banner` 驗證 `[CRITICAL UPDATE]` 雙線橫幅與 `[<TYPE>]` 標籤 | 2026-11-01 |
| **RT-10** | `Passed` | `python yscb.py dev test dev -q` 全量 82/82 (100.0%) 通過 | 2026-11-01 |
| **RT-11** | `Passed` | `python yscb.py dev test core -q` 全量 213/213 (100.0%) 通過 | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev index-patch -h` 與 `python yscb.py dev release -h`，確認 CLI 參數說明與更新告警格式符合預期 | `[跳過/免測]` | 開發者指示免測 |
