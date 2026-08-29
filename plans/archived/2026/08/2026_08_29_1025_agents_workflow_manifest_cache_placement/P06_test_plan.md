# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 Project Targets 發布時 Manifest 寫入 `storage://`，且檔案清單 100% 為 `project://` 格式 | FR-01 | `python yscb.py dev test agents-workflow` |
| **FT-02** | 單元測試 | 驗證 Local Targets 發布時 Manifest 寫入 `cache://`，且檔案清單 100% 為實體絕對路徑 | FR-01 | `python yscb.py dev test agents-workflow` |
| **FT-03** | 單元測試 | 驗證混合 Targets (Local + Project) 發布時兩份 Manifest 同步獨立寫入且內容各自分流 | FR-02 | `python yscb.py dev test agents-workflow` |
| **FT-04** | 邊界測試 | 驗證移除特定 Target 時，對應軌道舊孤立檔案精確被 prune 清除，另一軌不受影響 | FR-02, EC-02 | `python yscb.py dev test agents-workflow` |
| **FT-05** | 邊界測試 | 驗證讀取含有異機絕對路徑（如 `H:\...`）之歷史 Manifest 時不崩潰且安全遷移 | FR-03, EC-01 | `python yscb.py dev test agents-workflow` |
| **FT-06** | 驗證測試 | 驗證生成檔案之換行符號 100% 為純 LF (`\n`)，無任何 `\r\n` (CRLF) 殘留 | FR-04 | `python yscb.py dev test agents-workflow` |
| **RT-01** | 全生態回歸 | 全生態系 4 大模組與端到端回歸測試 100% Passed | NFR-01 | `python test/run_regression.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_project_target_saves_project_uris_in_storage` 驗證 `storage://` 中 26 筆路徑 100% 為 `project://` 格式 | 2026-08-29 10:33 |
| **FT-02** | `Passed` | `test_ft_02_local_target_saves_absolute_paths_in_cache` 驗證 `cache://` 中路徑 100% 為本地實體絕對路徑 | 2026-08-29 10:33 |
| **FT-03** | `Passed` | `test_ft_03_mixed_targets_dual_channel_manifests` 驗證混合 Targets 時雙軌獨立同步寫入各自 Manifest | 2026-08-29 10:33 |
| **FT-04** | `Passed` | `test_ft_04_legacy_absolute_path_manifest_tolerance` 驗證含異機絕對路徑（如 `H:\...`）之舊 Manifest 安全自癒標準化 | 2026-08-29 10:33 |
| **FT-05** | `Passed` | `test_ft_05_line_endings_are_pure_lf` 二進位讀取驗證所有物化檔案 100% 純 LF (`\n`)，無 `\r\n` | 2026-08-29 10:33 |
| **FT-06** | `Passed` | `test_ft_06_cli_release_with_force_flag` 驗證 CLI release 流程與 `--force` 全覆寫 | 2026-08-29 10:33 |
| **RT-01** | `Passed` | `dev test --all` 全生態系 4 大模組 191/191 測試全數 Passed (9.152s) | 2026-08-29 10:33 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：檢查 `git status` 與 `git diff`，確認執行 `python yscb.py reload` 後 `ys_codebase/storage/` 保持純淨（或僅有標準 `project://` 格式，不再隨本機路徑改變產生 diff），且無 CRLF 警告。


