# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:gdrive-support` `repo_sync` 組態與子目錄隔離、雙層 `README.md` 本地狀態快取軟合併及本地/外部雙軌分離 Skills (`sub_04_repo_sync_isolation_and_skills`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「我目前其雲端真實路徑 (root) 為 `ys-codebase/repo_sync`，主要是會有不想同步到 git repo 但又要存雲端的資料，我預想就是存 `ys-codebase/**/*` 這樣好嗎？還是我們可以設技能支援這種情況？」
  2. 「主軸不是不進 git repo，而是不拉到本地同步」
  3. 「我覺得可以設計成方案 A 但更完整一點，我們把 branch、後台自動同步的版控 (非原子 API 操作) 定義為 `"repo_sync"`，並改變 config 結構為：基本設定，如憑證維持原樣，`"repo_sync"`: `{ enable: 總開關，預設為 false，以下所有設定皆無效, 原本的各種設定、例如當前 branch、後台輪巡(如果有 server)間隔... 等等 }`。cmd 只要 `repo_sync` `enable: false` 時，都會拒絕直接同步、branch 的操作指令，僅接受原子操作。repo 系列操作的資料夾會在 `root/repo_sync`，`README.md` `root` 和 `root/repo_sync` 可能要都放一份（對於 `root` 的那份，隨 `enable` 開關進行建立、移除或軟合併/軟移除（當 README 已存在或是存在非託管情況時 fallback））？」
  4. 「1. 觸發頂層 `root/README.md` 軟合併 / 軟移除的時機，於本地快取最後啟用狀態，有變動就檢查（就算在 3 個不同主機，這個機制也最多觸發 4 次（1 初始化 + 3 次變動））
     2. `module:gdrive-support` 內建一個"給外部要操作雲端"隨包 Skill，和"給本地要操作 `module:gdrive`"，給本地的可以直接貢獻於 `agents-workflow`，這點要明確分開」
  5. 「可以，先僅修改業務邏輯，先不要進行雲端實機驗證」
- **核心目標**：
  1. **重構 `config://gdrive-support/` 結構**：頂層保留連線與憑證設定（`root_folder_id`, `auth_mode`, `credentials_uri`, `token_uri`, `sandbox_dir`），將所有分支與同步相關設定移入 `"repo_sync"` 物件（`enable: false` 預設關閉、`repo_sync_root: "repo"` 預設同步倉子目錄、`active_branch: "main"`、`auto_sync: false`、`poll_interval_sec: 30.0`、`pull_delete_default: false`、`push_delete_default: false`）。
  2. **`repo_sync.enable: false` 剛性攔截與 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）物理隔離**：
     - 當 `repo_sync.enable == false` 時，`init`、`branch`、`checkout`、`pull`、`push`、`sync` 指令一律拒絕執行並拋出 `GDriveRepoSyncDisabledError`；`GDriveSyncServiceWorker` 直接處於 `standby`。
     - 原子指令（`status`, `auth`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）隨時可用，且根目錄為 `<root_folder_id>/`（可供單點存取不拉到本地同步之純雲端檔案）。
     - 當 `repo_sync.enable == true` 時，同步倉所有目錄與元數據一律收納於 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/.yscb_gdrive.json`、`repo/README.md`、`repo/.history/`、`repo/.trash/`、`repo/main/`、`repo/<branch>/`）。
     - 雲端刪除與回收直接移入 Google Drive 原生 30 天垃圾桶 (`trashed=true`)，頂層不建立 `.trash/`；`<repo_sync_root>/.trash/` 僅供外部 AI 暫存刪除檔，並於下次本地同步/分支操作時自動清空至原生 30 天垃圾桶。
  3. **雙層 `README.md` 與頂層 `root/README.md` 本地狀態快取軟合併/軟移除**：
     - 本地快取 `cache://gdrive-support/readme_sync_state.json` 記錄最後檢查之 `(repo_sync.enable, repo_sync.repo_sync_root)` 狀態。
     - 當狀態變動（或首次初始化）時，檢查雲端頂層 `root/README.md`：
       - `enable == true`：若不存在則建立含 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === --> ... <!-- === YSCB GDRIVE REPO_SYNC END === -->` 託管區塊之 `root/README.md`；若已存在則保留非託管內容並軟合併更新託管區塊。
       - `enable == false`：若 `root/README.md` 存在，剝除託管區塊；若剝除後剩餘非空白內容為空則移入原生垃圾桶（沙盒為 `.trash/`）移除，若有使用者非託管內容則原地寫回保留（軟移除）。
  4. **雙軌明確分離之 Agent Skills**：
     - **給本地操作 `module:gdrive-support` 的 Skill**：透過 `contributes/agents-workflow.json` `export` 技能 `gdrive-local-ops`（`assets/skills/gdrive-local-ops/SKILL.md`）並注入 `AGENTS_SKILL_ROUTING`、`HOW_TO_YSCB_MODULES`、`HOW_TO_CONFIG_MODULES`。
     - **給外部（雲端 Web Gemini / 外部 Agent）操作雲端的隨包 Skill**：獨立存放於 `assets/external_cloud_skill/SKILL.md`（不注入本地 `agents-workflow`），並在頂層 `root/README.md` 託管區塊與 `<repo_sync_root>/README.md` 中指引外部雲端 Agent 遵循（含 `<repo_sync_root>/.trash/` 自動清空警示）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `gdrive_support/{config,reconciler,transport,coordinator,service}.py` 與 `core.gitignore` 風格之區塊標記軟合併演算法。
- **邊界排除 (Explicitly Excluded)**：
  - 自動化 `tests/` 100% 鎖定 `LocalSandboxTransport`，嚴禁將對外 Google Drive API 寫入自動化測試。
- **架構影響範圍**：
  - `ys_codebase/source/gdrive-support/`、`ys_codebase/config/gdrive-support/config.project.json`、`docs/gdrive-support/README.md`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `repo_sync` 組態結構與 `enable: false` 剛性守門**：
  - `GDriveConfig` 新增 `repo_sync_enabled: bool = False` 與 `repo_sync_root: str = "repo"`（映射自 `config["repo_sync"]`），當 `repo_sync.enable == false` 時，`auto_sync` 強制視為 `False`，且 `SyncCoordinator` 所有倉庫與分支同步方法（`init_repo`, `list_branches`, `create_branch`, `delete_branch`, `checkout_branch`, `run_sync`）在入口處執行 `ensure_repo_sync_enabled()` 守門，未啟用時立即拋出 `GDriveRepoSyncDisabledError`。
- **[P00:DR-02] `<root>/<repo_sync_root>/`（預設 `repo/`）物理隔離、原生 30 天垃圾桶與頂層 `root/README.md` 軟合併/軟移除**：
  - `SyncCoordinator` 以 `config.repo_sync_root`（預設 `DEFAULT_REPO_SYNC_ROOT = "repo"`）為同步倉根前綴（即 `repo/.yscb_gdrive.json`、`repo/README.md`、`repo/.history`、`repo/.trash`、`repo/<branch>`）。
  - `GoogleDriveApiTransport.trash_file()` 直接呼叫 `PATCH /files/{id}` (`{"trashed": true}`) 移入 Google Drive 原生 30 天垃圾桶，並由 `SyncCoordinator._flush_external_repo_trash()` 自動將外部 AI 放入 `repo/.trash/` 之項目移入原生垃圾桶清空。
  - 頂層 `root/README.md` 軟合併/軟移除由 `reconcile_root_readme_state()` 執行，透過比對 `cache://gdrive-support/readme_sync_state.json` 中記錄之狀態與當前 `(config.repo_sync_enabled, config.repo_sync_root)`，僅在狀態變動（或尚未記錄且 `enable == true`）時觸發雲端讀寫。
- **[P00:DR-03] 本地 `agents-workflow` Skill 與外部雲端隨包 Skill 嚴格分離**：
  - 本地技能：`ys_codebase/source/gdrive-support/assets/skills/gdrive-local-ops/SKILL.md`（由 `contributes/agents-workflow.json` 注入本地工作流）。
  - 外部雲端技能：`ys_codebase/source/gdrive-support/assets/external_cloud_skill/SKILL.md`（純隨包資產，供外部雲端 AI / Web Gemini 操作雲端目錄時使用，不註冊進本地 `agents-workflow`）。

---

## 3. 開放議題與確認紀錄

- 均已與開發者確認完畢（含 `repo_sync_root: "repo"` 預設值、Google Drive 原生 30 天垃圾桶與自動清空 `repo/.trash/`、新雲端根目錄 `1MeDEInAzn11JobNbfA_6uQ2OPpRTGAhF` 實機驗證及 `/blind-subagent` 審查補強）。

