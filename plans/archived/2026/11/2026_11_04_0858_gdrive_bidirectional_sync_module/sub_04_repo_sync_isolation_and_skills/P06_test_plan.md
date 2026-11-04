# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`module:gdrive-support` `repo_sync` 組態與子目錄隔離、雙層 `README.md` 本地狀態快取軟合併及本地/外部雙軌分離 Skills (`sub_04_repo_sync_isolation_and_skills`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `repo_sync` 巢狀組態結構解析，當 `repo_sync.enable: false` 時 `auto_sync` 與 `sync_spaces` 強制不生效 | FR-01 | `TestGDriveAtomicApiAndConfig.test_ft_01_default_config_and_lazy_sdk_exports` |
| **FT-02** | 整合測試 | 驗證 `init_repo()` 於 `<root>/<repo_sync_root>/`（預設 `repo/`）子目錄內建立 `.yscb_gdrive.json`、`README.md`、`.history/`、`.trash/` 與 `main/`，並同步建立頂層 `README.md` | FR-02, FR-03 | `TestGDriveBranchAndSyncEngine.test_ft_02_init_repo_and_readme_generation` |
| **FT-03** | 整合測試 | 驗證 `repo/` 下之分支 Shortcut 建立、Copy-on-Write 退避至 `repo/.history/`、無引用自動回收以及外部 AI 放入 `repo/.trash/` 之暫存檔自動清空 | FR-02 | `TestGDriveBranchAndSyncEngine.test_ft_03_branch_shortcut_cow_history_and_unreferenced_gc_to_trash` |
| **FT-06** | 整合測試 | 驗證 `repo_sync_enabled=False` 攔截 `init` / `branch` / `checkout` / `sync` 並拋出 `GDriveRepoSyncDisabledError`，以及 `repo_sync_enabled=True` 時頂層純雲端檔案（如 `cloud_only_notes.txt`）100% 不受 `repo_sync` 影響 | FR-01, FR-02, EC-01, EC-04, NFR-02 | `TestGDriveBranchAndSyncEngine.test_ft_06_repo_sync_disabled_gate_and_cloud_only_root_isolation` |
| **FT-07** | 整合測試 | 驗證本地快取 `readme_sync_state.json` 驅動之頂層 `root/README.md` 軟合併（100% 保留手寫內容）、快取命中零請求 (`noop_cached`)、軟移除（保留手寫內容）與純託管檔自動移入 `.trash/`，以及雙軌 Skills (`gdrive-local-ops` vs `external_cloud_skill`) 契約驗證 | FR-03, FR-04, EC-02, EC-03, NFR-01, NFR-02 | `TestGDriveBranchAndSyncEngine.test_ft_07_local_cache_driven_root_readme_soft_merge_and_soft_remove` & `python yscb.py contributes check` |
| **ET-05** | 邊界與安全測試 | 驗證 `/blind-subagent` 審查補強：未映射 1:1 空間越界路徑（如 `secrets/leak.txt`）於 `pull`/`sync` 時遭 `SyncSpaceSpec.is_local_abs_allowed()` 剛性攔截不落盤；跨分支外部新增 Shortcut 於 `run_sync` 動態重新整理 `branch_files_map` 並觸發 Copy-on-Write；以及 `push --force --backup` 建立雲端 `.conflict.<ts>.bak` 備份 | FR-02, EC-04 | `TestGDriveBranchAndSyncEngine.test_et_05_path_escape_guard_and_external_branch_shortcut_cow_and_push_backup` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-07, ET-05** | `Passed` | `python yscb.py dev check gdrive-support` (PASSED) & `python yscb.py dev test gdrive-support -q` (`Pass: 23(100.0%), Fail: 0, Skip: 0`) & `python yscb.py contributes check` (`Checked 28 file(s) [PASS]`) | 2026-11-04 12:09 |
| **LIVE-01** | `Passed` | 對 Google Drive 新根目錄 (`1MeDEInAzn11JobNbfA_6uQ2OPpRTGAhF`) 執行實機端到端驗證：<br/>1. `repo_sync.enable: false` 時拒絕 `init`，允許原子 `put` 純雲端檔案 (`cloud_vault/pure_cloud_asset.txt`) 與手寫頂層 `README.md`。<br/>2. `repo_sync.enable: true` 且 `repo_sync_root: "repo"`（預設）時，`init` 建立 `<root>/repo/` (`1gneGCsRj8Gq0iajWsoWaaliY3_HGsP4M`) 結構（含 `repo/.yscb_gdrive.json`, `repo/README.md`, `repo/.history/`, `repo/.trash/`, `repo/main/`）並將受控區塊軟合併至頂層 `README.md`（100% 保留手寫內容）。<br/>3. 實機驗證 `push` v1 $\to$ `branch create v1.0` Shortcut $\to$ `push` v2 觸發 `.history/` Copy-on-Write $\to$ `checkout v1.0`/`main` $\to$ `branch delete v1.0` 自動回收至 Google Drive 原生 30 天垃圾桶 (`trashed=true`)，且自動清空外部 AI 放入 `repo/.trash/` 之暫存檔 (`1Yu2wQeti6WqLCDhIPD6U4s7mQZipE5G4` $\to$ `count: 0`)。<br/>4. 切回 `repo_sync.enable: false` 時自動觸發頂層 `README.md` 軟移除，精準還原原始手寫內容（`63 bytes`, MD5 `628102e089f7bc40294f8ece58ccdd18`），頂層不再殘留 `.trash` 資料夾。 | 2026-11-04 11:53 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `sub_04_repo_sync_isolation_and_skills` 之業務邏輯修改、新雲端根目錄 (`1MeDEInAzn11JobNbfA_6uQ2OPpRTGAhF`) 實機驗證、Google Drive 原生 30 天垃圾桶 (`trashed=true`) 與 `repo/.trash/` 自動清空、`/blind-subagent` 安全與雙向追溯審查補強，以及本地沙盒測試 (`23/23 PASS`) 與本地/外部雲端雙軌 Skills 產物 | `[測試通過]` | 開發者與 2 名盲眼子代理均已完成複查驗收確認通過 |
