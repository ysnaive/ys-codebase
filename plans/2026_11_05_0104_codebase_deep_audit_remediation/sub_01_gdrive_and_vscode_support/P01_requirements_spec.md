# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_gdrive_and_vscode_support  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `gdrive-support` 單向同步 (`pull`/`push`) 基準線防覆寫保護 (`U1-P0-01`) | 於 `SyncCoordinator.run_sync()` 處理 `SyncActionType.IN_SYNC` 時，嚴格限定僅在 `act.local_entry`、`act.remote_entry` 皆存在且 `act.reason == "identical_digest"` 時才允許更新 `branch_state_dict[rel_p]`；當單向 `pull` 略過本地修改（`pull_skip_local_change`）或單向 `push` 略過遠端修改（`push_skip_remote_change`）時，保留原 `sync_state.json` 基準線不變，確保後續 `run_sync(mode="sync")` 不會將對向修改誤判並靜默回滾（`[P01:DR-01]`）。 | P0 | [P00:DR-01] |
| **FR-02** | `gdrive-support` 空 `sync_spaces` 阻斷守衛與專案組態對齊 (`U1-P0-02`) | 於 `SyncCoordinator.run_sync()` 入口檢核 `self.config.sync_spaces`，若為空則立即拋出 `GDriveConfigError` 拒絕執行同步，防止因未載入空間映射搭配 `push_delete_default=True` 引發全倉誤刪；並補齊確認 `ys_codebase/config/gdrive-support/contribute.json` 宣告 `"sync_spaces": [{"space": "cloud"}]`。 | P0 | [P00:DR-01] |
| **FR-03** | 分支內部系統名稱解耦與 `.`/`_` 子目錄 Level 1 增量放行 (`U1-P0-03`, `U1-P1-06` / `D-01`) | 1. 將分支內部排除集合獨立為 `BRANCH_INTERNAL_SYSTEM_NAMES = {REPO_META_FILENAME, HISTORY_DIRNAME, TRASH_DIRNAME}`（不含 `REPO_README_FILENAME = "README.md"`），修正 `_scan_remote_branch_with_dirs` 與 `_try_incremental_remote_cache` 避免誤濾分支根目錄 `<repo>/<branch>/README.md`。<br/>2. 於 `_try_incremental_remote_cache` 的 `pending_new_folders` 拓撲解析迴圈中，移除對分支內部子目錄的 `dir_name.startswith(".") or dir_name.startswith("_")` 攔截（僅 `ch.parent_id == repo_folder_id` 之頂層目錄保留該限制），使 `.github/workflows/`、`docs/_project/` 等合法子目錄可在 Level 1 完成 0 次 `list_files` 增量掛載（`[P01:DR-01]`）。 | P0 | [P00:DR-01] |
| **FR-04** | CLI `--sandbox-dir` 全鏈路狀態與組態隔離 (`U1-P1-04`) | 於 `gdrive-support/scripts/cli.py` 提取 `_build_coordinator(sandbox_dir)` 統一供 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 調用，當傳入 `--sandbox-dir` 時將 `state_path`、`lock_path`、`log_path`、`readme_state_path` 隔離錨定於沙盒目錄下；於 `SyncCoordinator._persist_active_branch_to_config()` 檢測到 `bool(self.config.sandbox_dir)` 時跳過改寫全域 `config.project.json`；並於 `ys_codebase/source/gdrive-support/contributes/core.json` 將 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 標記為 `"server_compatible": false`，防止透過 `WarmWorker` 同進程執行時與背景 `GDriveSyncServiceWorker` 爭用 `sync.lock` 發生死鎖。 | P1 | [P00:DR-01] |
| **FR-05** | 遠端空父目錄與已歸檔孤兒空殼自動清理 (`U1-P2-04` / `D-03`) | 於 `SyncCoordinator.run_sync()` 執行 `DELETE_REMOTE` 後（以及掃描比對 `dir_ids` 與 `curr_branch_files` 時），由深至淺（依路徑深度降序）識別並透過 `transport.trash_file` 清理已無任何檔案或子目錄殘留之遠端空父目錄與既有已歸檔空資料夾空殼，並同步從 `remote_repo_cache`（`dir_ids`、`known_folder_ids`、`folder_meta`）移除對應條目。 | P1 | [P00:DR-01] |
| **FR-06** | `_folder_cache` 執行緒安全鎖、Level 0/1 預熱與按深度分層 BFS 平行建目錄 (`U1-P1-01` `[TODO-23]`, `U1-P1-07` / `D-02`) | 1. 於 `GoogleDriveApiTransport` 新增 `self._cache_lock = threading.RLock()` 保護 `_folder_cache` 與 `_scanned_prefixes` 的多執行緒讀寫與失效。<br/>2. 當 `_try_incremental_remote_cache` 命中 Level 0 或 Level 1 時，將 `remote_repo_cache` 內已知之 `repo_folder_id` 與當前分支 `dir_ids` / `folder_meta` 預熱注入 `transport._folder_cache`，並為 `trash_file` / `move_file` 支援選填已知 `file_id` / `entry_hint` 直通操作。<br/>3. 將 `SyncCoordinator._precreate_remote_dirs` 改為依路徑深度（`parent_rel.count("/")`）分層 BFS，同層目錄以 `ThreadPoolExecutor(max_workers=8)` 平行呼叫 `transport.mkdir`（`[P01:DR-02]`）。 | P1 | [P00:DR-02] |
| **FR-07** | 同名資料夾非破壞性去重、傳輸重試、401 刷新與 Shortcut 平行解析 (`U1-P1-02`, `U1-P1-05`, `U1-P2-02`, `U1-P2-05` / `D-04`, `U1-P3-01`~`02`) | 1. `GoogleDriveApiTransport.mkdir` 對同名資料夾候選按 `modifiedTime` 降序排序（對齊 `_resolve_folder_id_by_path`），且 `list_files` 同名去重僅對非資料夾項目（檔案／Shortcut）執行 `trash_file`，避免誤刪未合併子項之同名舊資料夾。<br/>2. `LocalSandboxTransport.upload_file` 將 `shutil.copy2` 納入 `with self._lock:`；`GoogleDriveApiTransport.download_file` 補齊退避重試與 `entry_hint` 免重查，`_request_json` 遇 HTTP `401` 自動重置 `_access_token` 重試一次；`run_sync` 入口重置 `_scanned_prefixes`。<br/>3. `_resolve_shortcut_targets` 改用 `ThreadPoolExecutor(max_workers=8)` 平行解析；非活躍分支引用計數遵守紅線 1，僅對 `not auto_discovered` 且 `branch_files_map.get(other_b)` 非空之已註冊分支快取（`[P01:DR-02]`）。 | P2 | [P00:DR-02] |
| **FR-08** | `vscode-support` 卸載守衛 Fail-Closed、Schema 自然版號排序與狀態/還原加固 (`U2-P1-01`, `U2-P2-01`~`02`, `U2-P3-01`) | 1. 將 `vscode-support/scripts/hook.core.py:on_remove` 收緊為 Fail-Closed：僅當 `ctx.args` 為 `list`/`tuple` 且包含 `"vscode-support"` 或 `"vsc"` 時才執行設定清理。<br/>2. 於 `schema_compiler.py` 採用 `core.semver.parse_semver`（或自然數版本元組）選取 `.mirror` 最新模組包，並在單次 `sync_all_schemas` 期間快取 `_collect_uri_scheme_snippets` 結果。<br/>3. 於 `projector.py` 的 `get_status` 補齊 `os.path.isdir(link_path)` 檢查懸空連結與 `strip_jsonc` 容錯解析；於 `revert_vscode_settings` 僅移除 YSCB 託管之排除規則並清理空排除字典（`[P01:DR-03]`）。 | P2 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單向 `pull` 期間本地檔案已修改但遠端未變（`pull_skip_local_change`），或單向 `push` 期間遠端檔案已修改但本地未變（`push_skip_remote_change`） | 對帳器回傳 `SyncActionType.IN_SYNC` 但 `reason != "identical_digest"`；`run_sync` 絕不覆寫 `branch_state_dict[rel_p]`，保留既有基準線，使下次雙向 `sync` 正確推送本地變更或拉取遠端變更。 |
| **EC-02** | 雙端皆已刪除某受管檔案，但本地 `sync_state.json` 或遠端 `curr_branch_files` 仍殘留舊基準紀錄（`act.local_entry is None and act.remote_entry is None and act.baseline_entry is not None`） | 於 `IN_SYNC` 分支精確識別雙端皆刪情境，安全清除 `branch_state_dict[rel_p]` 與 `curr_branch_files[rel_p]` 並標記 `meta_dirty = True` 落盤。 |
| **EC-03** | 外部網頁版 AI 於雲端新建未註冊分支資料夾（`auto_discovered=True` 且初始 `branch_files` 為 `{}`），隨後本地執行 `run_sync` 觸發 `.history/` 垃圾回收 | 嚴格遵守紅線 1：當 `branches[other_b].get("auto_discovered")` 為真或 `branch_files_map.get(other_b)` 為空時，禁止跳過遠端分支掃描，強制實地掃描該分支 Shortcut 目標，防止 `.history/` 被引用之歷史實體檔遭誤刪。 |
| **EC-04** | 雲端同一父目錄下因歷史競態存在兩個同名子資料夾（`mimeType == FOLDER_MIME_TYPE`） | `list_files` 去重邏輯僅選取 `modifiedTime` 最新之資料夾作為有效項目，**嚴禁**將較舊之同名資料夾直接移入垃圾桶（防止其內部尚未合併之子檔案連帶遺失）。 |
| **EC-05** | 遠端目錄下所有檔案均因計畫歸檔或刪除而執行 `DELETE_REMOTE`，或其父目錄為過往殘留之無檔案空資料夾空殼 | 由最深子目錄向上逐層檢查，僅當該遠端目錄下已無任何受管檔案與存活子目錄、且非分支根目錄或系統保留目錄時，將該空資料夾移入垃圾桶並同步更新 `remote_repo_cache`。 |
| **EC-06** | `.vscode/settings.json` 含單行/多行註解與尾隨逗號（JSONC），或 `.venv_link` 指向已刪除之失效目標（Broken Symlink） | `projector.get_status()` 先以 `strip_jsonc` 剝離註解再解析 JSON，並以 `os.path.isdir(link_path)` 驗證連結目標實際存在且為有效目錄；`hook.core.py:on_remove` 在 `ctx` 缺失或移除其他模組時回傳 `False` 不誤拆 VSCode 投影。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與網路 I/O | Level 0/1 快取命中並預熱 `_folder_cache` 後，既有目錄下檔案上傳之父目錄重查 HTTP GET 降為 `0` 次；多層新建目錄透過分層 BFS `ThreadPoolExecutor(max_workers=8)` 平行建立；`sync_all_schemas` 單次執行僅收集 1 次 URI Scheme Snippets。 |
| **NFR-02** | 執行緒安全與沙盒隔離 | `GoogleDriveApiTransport._folder_cache` 與 `_scanned_prefixes` 100% 受 `_cache_lock` (`RLock`) 保護；CLI `--sandbox-dir` 操作對生產環境 `storage.local://` 與 `config://` 達成 100% 零寫入污染。 |
| **NFR-03** | 架構合規與回歸零副作用 | 嚴格限定修改於 `ys_codebase/source/gdrive-support/`、`ys_codebase/source/vscode-support/` 與 `ys_codebase/config/gdrive-support/contribute.json`，100% 通過兩模組 `dev check` 與全量單元測試，且不違反 `R01_codebase_deep_audit.md` 8 大防回歸紅線。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 紅線 1（非活躍分支引用快取防誤刪 `.history/`）**：切勿無條件相信 `meta["branch_files"][other_b]` 而略過遠端掃描；唯有在 `not branches[other_b].get("auto_discovered") and bool(branch_files_map.get(other_b))` 時方可复用帳本紀錄（`[P01:DR-02]`）。
- **`[!CAUTION]` 同名資料夾不可直接 `trash_file`**：Google Drive 允許同名 Folder 並存，若在 `list_files` 將同名舊 Folder 直接移入垃圾桶，會連帶將其底下所有子檔案一併刪除；同名去重自動垃圾桶清理必須嚴格限定於非資料夾（`not entry.is_dir`）（`[P01:DR-02]`）。
- **`[!NOTE]` 前置計畫已修畢項扣除確認**：`U1-P1-03`（單檔 CoW `_meta_lock` + `finally` 寫回 `meta_dirty`）、`U1-P2-03`（`changes` API 三級 `remote_repo_cache`）與 `U2-P1-02`（`[TODO-22]` `extraPaths` 投影）已於前置計畫落地驗證，本計畫不重複拆改，專注於對接與擴充（`[P01:DR-01]`, `[P01:DR-03]`）。

