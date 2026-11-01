# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：發布產物二進位解耦、本地同版本自給自足與孤兒分支分發管線 (sub_01)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Builder._update_release_index` 計算 3-Revision 滑動視窗時，正確將活躍版本寫入 `index.json["versions"]`，並於 `index.json["releases"][<ver>]` 永久保存歷史版本與 `"status": "active" \| "pruned"` 標記 | FR-02 | `python yscb.py dev test dev -k test_revision_purge_deletes_old_zip` |
| **FT-02** | 單元與邊界測試 | 驗證當本機 `release/<mod>/` 無任何 `.zip` 檔案、僅存 `index.json` 雙軌帳本時，`Releaser.release_check` Gate 2 與 Gate 3 依然精準攔截重複版本與版本倒退，且 `release_module` 發出 `on_module_released` 事件廣播 | FR-01, FR-02, EC-03 | `python yscb.py dev test dev -k test_release_check_with_index_json_ssot_without_local_zip` |
| **FT-03** | 單元測試 | 驗證 `DEFAULT_PROVIDER_URL` 指向 `releases` 分支，且 `load_config` / `AtomicEngine._get_config` 自動將舊版官方 `main` 分支 URL 無感遷移至 `releases` 分支 | FR-05 | `python yscb.py dev test core -k test_legacy_provider_url_auto_migration_and_pruned_same_triplet_fallback` |
| **FT-04** | 整合與邊界測試 | 驗證當請求之 `X.Y.Z.W` 版本已被滑動視窗淘汰 (`pruned`) 且本地無 `.mirror/` 時，自動從 `index.json["versions"]` 解析同三元組 (`X.Y.Z.*`) 最高可用 `active` 版本還原並同步更新 `yscb.config.json`；若無同三元組版本則阻斷不盲猜 | FR-04, EC-04 | `python yscb.py dev test core -k test_legacy_provider_url_auto_migration_and_pruned_same_triplet_fallback` |
| **FT-05** | 整合與邊界測試 | 驗證當本地無 `.zip` 但 `source/<mod>/manifest.json` 版本與請求版本嚴格相等時，以純標準庫動態打包（排除 `tests/`）至 `.mirror/` 並解壓；若版本不相等則嚴格拒絕打包混裝 | FR-03, EC-01, EC-02, NFR-01 | `python yscb.py dev test core -k test_exact_version_local_source_dynamic_packaging` |
| **RT-01** | 全量回歸測試 | 驗證 `core` 與 `dev` 模組靜態合規檢查、`contributes check` 及全量沙盒測試 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check core && python yscb.py dev check dev && python yscb.py dev test core -q && python yscb.py dev test dev -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_revision_purge_deletes_old_zip` 通過，`index.json["releases"]` 準確標記 `1.0.0.1`~`1.0.0.3` 為 `pruned`、`1.0.0.4` 與 `1.0.1.0` 為 `active` | 2026-11-01 |
| **FT-02** | `Passed` | `test_release_check_with_index_json_ssot_without_local_zip` 通過，無 `.zip` 下 Gate 2/3 攔截 `1.0.0.1`，升級 `1.0.0.3` 發布通過並廣播 `on_module_released` | 2026-11-01 |
| **FT-03** | `Passed` | 舊版 `main` 分支 `default_provider` 自動遷移為 `releases` 分支 URL，且 `DEFAULT_SELF_UPDATE_URL` 保持獨立 | 2026-11-01 |
| **FT-04** | `Passed` | 鎖定 `pruned` 之 `1.0.0.1` 自動退回同三元組最高可用 `1.0.0.4` 並回寫 `yscb.config.json` | 2026-11-01 |
| **FT-05** | `Passed` | 版本不符 (`1.1.0.0` vs `1.2.0.0`) 拒絕混裝；版本相等 (`1.2.0.0`) 動態打包至 `.mirror/` 並解壓且不含 `tests/` | 2026-11-01 |
| **RT-01** | `Passed` | `dev check core` (PASS)、`dev check dev` (PASS)、`contributes check --all` (15/15 Valid)、`core` 測試 `210/210 (100.0%)` 通過、`dev` 測試 `81/81 (100.0%)` 通過，並完成 `core@build` 與 `dev@build` 熱部署 | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `sub_01` 實作成果（`index.json` 雙軌帳本、本地嚴格同版 `source/` 動態打包、`pruned` 同三元組自動補位、`.github/workflows/release-publish.yml` 與 `core` 210/210、`dev` 81/81 全綠測試報告），確認是否同意驗收通過並繼續推進 `sub_02` | `[跳過/免測]` | 開發者指示免測 |

