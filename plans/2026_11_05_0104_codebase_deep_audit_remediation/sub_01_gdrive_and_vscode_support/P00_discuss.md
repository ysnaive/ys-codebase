# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_gdrive_and_vscode_support  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：執行全倉深度審計分類型主計畫（`2026_11_05_0104_codebase_deep_audit_remediation`）之子計畫 `sub_01_gdrive_and_vscode_support`（重點新模組 gdrive-support 與 vscode-support 審計問題修復與優化）。
- **核心目標**：依據主計畫 `R01_codebase_deep_audit.md` 經盲眼反向查驗確認之問題清單與防回歸紅線，完成 `ys_codebase/source/gdrive-support/ 與 ys_codebase/source/vscode-support/` 範圍內所有確認缺陷之無損修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：復用目標模組既有鎖機制、快取結構與 `YSCBTestCase` 隔離沙盒測試框架。
- **邊界排除 (Explicitly Excluded)**：嚴格限制寫入範圍於 `ys_codebase/source/gdrive-support/ 與 ys_codebase/source/vscode-support/`，不觸碰其他子計畫負責之模組目錄，且不修改 `R01_codebase_deep_audit.md` 已駁回之偽陽性項目。
- **架構影響範圍**：`ys_codebase/source/gdrive-support/ 與 ys_codebase/source/vscode-support/` 及對應 `tests/` 測試案例。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `gdrive-support` 三方對帳基準線保護、空 `sync_spaces` 防誤刪守衛、`README.md` 漏同步修復與沙盒狀態隔離（`U1-P0-01`, `U1-P0-02`, `U1-P0-03`, `U1-P1-04`, `U1-P1-03`, `U1-P2-04`）**：**（已對齊 `2026_11_05_0528` 扣除已修畢之 `U1-P1-03` 與 `U1-P2-03`）** 於 `coordinator.py` 入口阻斷空 `sync_spaces` 同步並補齊 `ys_codebase/config/gdrive-support/contribute.json`（`U1-P0-02`）；修正 `_scan_remote_branch_with_dirs` (`L1700`) 與 `_try_incremental_remote_cache` (`L2058, L2136`) 避免 `SYSTEM_NAMES` 誤濾分支根目錄 `README.md`（`U1-P0-03`）；於 `DELETE_REMOTE` 後清理已騰空之遠端父目錄並同步更新 `remote_repo_cache`（`U1-P2-04`）；於 `coordinator.py` 處理 `SyncActionType.IN_SYNC` 時嚴格限定 `act.reason == 'identical_digest'` 方得更新 `branch_state_dict[rel_p]`（`U1-P0-01`）；於 `scripts/cli.py` 新增 `_build_coordinator(sandbox_dir)` 將 `--sandbox-dir` 狀態檔與組態寫入完全隔離於沙盒目錄（`U1-P1-04`）。
- **[P00:DR-02] `gdrive-support` 執行緒安全快取、分層平行建目錄與傳輸加固（`U1-P1-01` `[TODO-23]`, `U1-P1-02`, `U1-P2-02`, `U1-P1-05`, `U1-P2-03`, `U1-P3-01`~`02`）**：為 `GoogleDriveApiTransport` 新增 `_cache_lock` 保護 `_folder_cache` 與 `_scanned_prefixes`，將 `_precreate_remote_dirs` 升級為依深度分層 BFS + `ThreadPoolExecutor(max_workers=8)` 平行 `mkdir`；將 `LocalSandboxTransport.upload_file` 檔案複製納入 `self._lock`；為 `download_file` 補齊退避重試与 `entry_hint` 免重查、`_request_json` 補齊 HTTP 401 Token 重置刷新；遵守紅線 1 僅對非 `auto_discovered` 且非空之已註冊分支快取引用表，並平行化 `_resolve_shortcut_targets`。
- **[P00:DR-03] `vscode-support` 生命週期守衛與 Schema 編譯加固（`U2-P1-02` `[TODO-22]` 已於 `2026_11_04_1739/sub_01` 修畢；聚焦剩餘 `U2-P1-01`, `U2-P2-01`~`02`, `U2-P3-01`）**：將 `scripts/hook.core.py:on_remove` 收緊為 Fail-Closed；於 `schema_compiler.py` 採用自然數版號排序選取最新 `.mirror` 壓縮包並快取 URI Snippets；於 `projector.py` 補齊 `get_status` 懸空連結 `os.path.isdir` 檢查、`strip_jsonc` 回退與 `revert` 空字典清理。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：子計畫範疇、防回歸紅線與修復方案已由主計畫 `R01_codebase_deep_audit.md` 定錨確認，可隨時啟動 Phase 01～07（或 `/auto`）推進實作。
