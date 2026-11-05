# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_gdrive_and_vscode_support  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Gemini  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：執行全倉深度審計分類型主計畫（`2026_11_05_0104_codebase_deep_audit_remediation`）之子計畫 `sub_01_gdrive_and_vscode_support`（重點新模組 gdrive-support 與 vscode-support 審計問題修復與優化）。
- **核心目標**：依據主計畫 `R01_codebase_deep_audit.md` 經盲眼反向查驗確認之問題清單與防回歸紅線，並結合 `2026_11_05_0826_file_space_foundation_research` 落地後之資料夾增量同步深度排查結論（`D-01` ~ `D-04`），完成 `ys_codebase/source/gdrive-support/` 與 `ys_codebase/source/vscode-support/` 範圍內所有確認缺陷之無損修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：復用目標模組既有鎖機制、快取結構與 `YSCBTestCase` 隔離沙盒測試框架。
- **邊界排除 (Explicitly Excluded)**：嚴格限制寫入範圍於 `ys_codebase/source/gdrive-support/` 與 `ys_codebase/source/vscode-support/`，不觸碰其他子計畫負責之模組目錄，且不修改 `R01_codebase_deep_audit.md` 已駁回之偽陽性項目。
- **架構影響範圍**：`ys_codebase/source/gdrive-support/` 與 `ys_codebase/source/vscode-support/` 及對應 `tests/` 測試案例。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `gdrive-support` 三方對帳基準線保護、空 `sync_spaces` 防誤刪守衛、`README.md` 與 `.`/`_` 子目錄誤濾修復、遠端空目錄清理及沙盒狀態隔離（`U1-P0-01`, `U1-P0-02`, `U1-P0-03`, `U1-P1-04`, `U1-P1-06` `[D-01]`, `U1-P2-04` `[D-03]`）**：**（已對齊 `2026_11_05_0528` 與 `2026_11_05_0826` 扣除已修畢之 `U1-P1-03` 與 `U1-P2-03`）**
  1. 於 `coordinator.py` 入口阻斷空 `sync_spaces` 同步並補齊 `ys_codebase/config/gdrive-support/contribute.json`（`U1-P0-02`）。
  2. 修正 `_scan_remote_branch_with_dirs` (`L1712`) 與 `_try_incremental_remote_cache` (`L2066, L2082, L2190, L2268`) 避免 `SYSTEM_NAMES` 誤濾分支根目錄 `README.md`（`U1-P0-03`）。
  3. **修正 Level 1 拓撲建目錄誤殺 `_` 與 `.` 開頭之分支內子目錄（`U1-P1-06` / `D-01`, `coordinator.py:L2064-2070`）**：於 `pending_new_folders` 拓撲解析迴圈中，移除對分支內部子目錄的 `dir_name.startswith(".") or dir_name.startswith("_")` 攔截（該限制僅適用於 `ch.parent_id == repo_folder_id` 之頂層分支名稱），放行 `docs/_project/`、`.github/workflows/` 等合法業務子目錄於 Level 1 完成 0 次 `list_files` 增量掛載，避免無故退回 138s Level 2 全掃。
  4. **遠端空父目錄與孤兒空殼清理（`U1-P2-04` / `D-03`, `coordinator.py:L1269-1298`）**：於 `DELETE_REMOTE` 執行後由深至淺清理已無任何檔案或子目錄之遠端空父目錄（含清理 `dir_ids` 中無任何 `curr_branch_files` 前綴對應之既有已歸檔空資料夾空殼），並同步更新 `remote_repo_cache`（`dir_ids`、`known_folder_ids`、`folder_meta`）；雲端 `repo/main/plans/` 現存之 5 個已歸檔空資料夾空殼（`2026_11_04_1517`、`2026_11_05_0321`、`2026_11_05_0528`、`2026_11_05_0708`、`2026_11_05_0826`）刻意保留於原處作為本項實機清理驗收標的。
  5. 於 `coordinator.py` 處理 `SyncActionType.IN_SYNC` 時嚴格限定 `act.reason == "identical_digest"` 方得更新 `branch_state_dict[rel_p]`（`U1-P0-01`）；於 `scripts/cli.py` 新增 `_build_coordinator(sandbox_dir)` 將 `--sandbox-dir` 狀態檔與組態寫入完全隔離於沙盒目錄（`U1-P1-04`）。
- **[P00:DR-02] `gdrive-support` 執行緒安全快取、Level 0/1 `_folder_cache` 預熱、分層平行建目錄、同名資料夾安全去重與傳輸加固（`U1-P1-01` `[TODO-23]`, `U1-P1-02`, `U1-P1-05`, `U1-P1-07` `[D-02]`, `U1-P2-02`, `U1-P2-05` `[D-04]`, `U1-P3-01`~`02`）**：
  1. 為 `GoogleDriveApiTransport` 新增 `_cache_lock` 保護 `_folder_cache` 與 `_scanned_prefixes`，將 `_precreate_remote_dirs` 升級為依深度分層 BFS + `ThreadPoolExecutor(max_workers=8)` 平行 `mkdir`（`U1-P1-01` `[TODO-23]`）。
  2. **Level 0/1 命中時預熱 `transport._folder_cache` 與已知 `file_id` 直通刪除/搬移（`U1-P1-07` / `D-02`, `coordinator.py:L1009-1011, L1290, L1301`, `transport.py:L918, L1294-1346, L1460-1514`）**：當 `_try_incremental_remote_cache` 命中 Level 0 或 Level 1 時，將 `state["remote_repo_cache"]` 內已知之 `repo_folder_id` 與當前分支 `dir_ids` + `folder_meta` 注入預熱至 `transport._folder_cache`，消除 Stage 3 `_precreate_remote_dirs` 自 `root_folder_id` 逐層重查既有父目錄之 6~7 次冗餘 HTTP GET；並為 `trash_file` / `move_file` 支援選填已知 `file_id` / `entry_hint` 免除路徑重查。
  3. **同名資料夾時間排序對齊與非破壞性去重（`U1-P2-05` / `D-04`, `transport.py:L1232-1253, L1317-1324`）**：於 `GoogleDriveApiTransport.mkdir` 對 `folder_matches` 按 `modifiedTime` 降序排序（對齊 `_resolve_folder_id_by_path`）；於 `list_files` 同名去重中僅對非資料夾項目（檔案／Shortcut）直接執行 `trashed=True`，避免遇到同名資料夾時未合併子項即誤刪舊資料夾內之子檔案。
  4. 將 `LocalSandboxTransport.upload_file` 檔案複製納入 `self._lock`（`U1-P1-02`）；為 `download_file` 補齊退避重試與 `entry_hint` 免重查、`_request_json` 補齊 HTTP 401 Token 重置刷新（`U1-P2-02`, `U1-P3-01`~`02`）；遵守紅線 1 僅對非 `auto_discovered` 且非空之已註冊分支快取引用表，並平行化 `_resolve_shortcut_targets`（`U1-P1-05`）。
- **[P00:DR-03] `vscode-support` 生命週期守衛與 Schema 編譯加固（`U2-P1-02` `[TODO-22]` 已於 `2026_11_04_1739/sub_01` 修畢；聚焦剩餘 `U2-P1-01`, `U2-P2-01`~`02`, `U2-P3-01`）**：將 `scripts/hook.core.py:on_remove` 收緊為 Fail-Closed；於 `schema_compiler.py` 採用自然數版號排序選取最新 `.mirror` 壓縮包並快取 URI Snippets；於 `projector.py` 補齊 `get_status` 懸空連結 `os.path.isdir` 檢查、`strip_jsonc` 回退與 `revert` 空字典清理。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：子計畫範疇、防回歸紅線、`2026_11_05_0826` 後續資料夾創建/清理排查項目（`D-01` ~ `D-04`）與修復方案均已定錨確認，並保留雲端 `repo/main/plans/` 5 個已歸檔空資料夾空殼供 `U1-P2-04` 實機清理驗收，可隨時啟動 Phase 01～07（或 `/auto`）推進實作。
