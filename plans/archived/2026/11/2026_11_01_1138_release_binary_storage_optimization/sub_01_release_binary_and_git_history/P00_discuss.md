# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：發布產物二進位解耦、本地同版本自給自足與 Git 歷史瘦身 (sub_01)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「先明確一點，這應該是本專案特化，要重新考慮一下 dev release 的指令設計了，因為我們並不能保證其他有開發模組的使用者怎麼維護儲存庫，要考慮通用性 (當然足夠通用後，母庫依然對接成方案 B 形式)」
  - 「1. 可能可以考慮 hook callback? 可由組態定義，預設就是空 2. (1) 本地自給自足，但必須版本號相同」
  - 「1. 可以，但這樣應該不會殘留無引用快取物件吧? 2. 是 3. 要，誤追蹤的項目也一並清除；補充 透過 `core.events.broadcast("on_module_released", ...)` 發出標準事件，不做特化 hook」
  - 「這部分定案，先更新 R01，並先針對整替設計與討論儲存成 主計畫中的 sub01，趁此次機會我想一併處理其他問題」
- **核心目標**：
  - 落實 [`R01_release_binary_and_git_history_analysis.md`](../R01_release_binary_and_git_history_analysis.md) 定案之四大支柱架構，將 `ys_codebase/release/**/*.zip` 從母倉 `main` 分支徹底解耦並清洗歷史冗餘，同時保持 `core` 與 `dev` 對第三方模組儲存庫維護策略的 100% 通用性。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `core.events.broadcast`（`ys_codebase/source/core/core/events.py` 標準全域事件總線）与 `ys_codebase/source/dev/contributes/core.json` 事件宣告
  - `Builder._update_release_index` / `Builder.package_release`（`ys_codebase/source/dev/dev/builder.py`）
  - `Releaser.release_check` / `Releaser.release_git`（`ys_codebase/source/dev/dev/releaser.py`）
  - `AtomicEngine.act_fetch` / `_download_from_release_tier` / `_find_manifest_in_local_provider`（`ys_codebase/source/core/core/engine.py`）
  - `Installer.cmd_restore` / `Installer._restore_module_package`（`ys_codebase/source/core/core/installer.py`）
  - `yscb.py`（`DEFAULT_PROVIDER_URL`、`_discover_latest_core`、`_bootstrap_package_from_provider`）
- **邊界排除 (Explicitly Excluded)**：
  - **嚴禁在 `core/installer.py:INTERNAL_IGNORE_PATTERNS` 寫死忽略 `/release/**/*.zip`**：不強制干預外部模組開發者如何版控其 `release/` 目錄。
  - **嚴禁設計專用 Hook 組態欄位**：統一使用 `core.events.broadcast("on_module_released", ...)` 標準事件機制，不增加額外 `yscb.config.json` 特化 hook 語法。
  - **嚴禁在版本不匹配時從 `source/` 盲目打包**：本地 `source/<mod>` 自給自足動態打包僅限於 `source/<mod>/manifest.json` 之 `"version"` 與請求安裝版本**嚴格相等 (`==`)** 時觸發。
- **架構影響範圍**：
  - `ys_codebase/source/dev/dev/{builder.py,releaser.py}`、`ys_codebase/source/dev/scripts/cli.py`、`ys_codebase/source/dev/contributes/core.json`
  - `ys_codebase/source/core/core/{engine.py,installer.py,update_checker.py}`、`ys_codebase/source/core/tests/test_distribution_lifecycle.py`
  - `yscb.py`、`.github/workflows/release-publish.yml`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 支柱一：通用發布事件廣播 (`on_module_released`) 與 `index.json` 版本帳本 SSOT（`dev` & `core`）**：
  - **標準事件廣播與宣告（遵循 `ExecutionContext` 契約）**：`dev` 模組執行打包/發布完成時，嚴格遵循 `core.events.broadcast(event_name, context, emit_module)` 簽名（不傳入未定義之 `**kwargs`），將模組與產物資訊封裝為 `ExecutionContext("dev", "on_module_released", [module_name, target_version], metadata={"module": module_name, "version": target_version, "zip_path": ...})` 進行廣播；同步於 `ys_codebase/source/dev/contributes/core.json`、`ys_codebase/source/dev/contributes/_manifest.md` 及 `ys_codebase/source/dev/dev/checker.py:992` (`_check_sandbox_hooks`) 宣告註冊 `on_module_released` 事件。
  - **不鎖死 `INTERNAL_IGNORE_PATTERNS`**：`core/installer.py` 不將 `release/**/*.zip` 列入強制內部忽略清單，保留外部使用者自由選擇其儲存庫維護策略的彈性；母倉僅在自身根目錄 `.gitignore`（非託管區）忽略 `ys_codebase/release/**/*.zip`。
  - **`index.json` 升格為版本與依賴元數據 SSOT（區分活躍可下載 `versions` 與永久歷史帳本 `releases`）**：
    - `Builder._update_release_index`（`builder.py:167-192`）對「既有 `index.json["versions"]` $\cup$ 本地現存 `.zip` $\cup$ `{new_version}`」執行 3-Revision 滑動視窗演算法：保留在視窗內的可下載版本寫入頂層 `index.json["versions"]`（完全相容 `test_builder.py:101` 並供 CI 清理過期 `.zip`），而在 `index.json["releases"][<ver>]` 永久保留所有歷史版本元數據，並將滑動視窗保留版本標註為 `"status": "active"`、被淘汰版本標註為 `"status": "pruned"`。
    - `Releaser.release_check`（Gate 2 版本不可變性 & Gate 3 單調遞增守門）與 `Releaser.release_git`（`releaser.py:241-242` 之 `is_already_released` 判定）改以「`index.json["versions"]` $\cup$ `index.json["releases"].keys()` $\cup$ 本地現存 `.zip`」為全歷史版本權威基準，確保新 Clone 環境在無歷史 `.zip` 實體檔時依然 100% 嚴格守門。
- **[P00:DR-02] 支柱二：本地自給自足之同版本 (`source_version == target_version`) 動態打包與 `pruned` 版本同三元組 (`X.Y.Z.*`) 平滑遞補（涵蓋 `yscb.py`、`core/engine.py` 與 `core/installer.py`）**：
  - **零 `dev` 依賴之標準庫打包過濾器**：鑑於 `yscb.py` 自舉與 `core` 早期載入時 `dev` 模組尚未安裝，`yscb.py` 與 `core` 內部必須內建純 Python 標準庫實作之忽略過濾邏輯（對齊 `RELEASE_IGNORES` 與 `.yscbignore` 規則，排除 `tests/`、`__pycache__`、`*.pyc`、`.DS_Store` 等非運行資產），嚴禁 `import dev.builder`。
  - **打通三條本地探測與還原路徑（確保 `cmd_init` 先打包為 `.zip` 再解壓）**：
    1. `yscb.py:_discover_latest_core`（`yscb.py:347-352`）與 `cmd_init`（`yscb.py:466-472`）：讀取本地 `index.json` 的 `versions` 時，若 `c_dir/<ver>.zip` 不存在但同倉庫 `source/core/manifest.json` 版本嚴格等於 `v`，當場呼叫內建標準庫打包函式將 `source/core` 打包為 `.mirror/core/<ver>.zip`（並回填 `release/core/<ver>.zip`）後回傳該 `.zip` 檔案路徑，杜絕 `_fetch_and_extract_zip` 直接 `copytree` 未過濾之原始碼目錄。
    2. `yscb.py:_bootstrap_package_from_provider`（`yscb.py:538-583`）與 `core/engine.py:AtomicEngine._download_from_release_tier`：當本地 Provider 缺失 `<mod>/<ver>.zip` 時，若 `ys_codebase/source/<mod>/manifest.json` 存在且 `"version" == ver`，當場動態打包至 `.mirror/<mod>/<ver>.zip`（並回填 `release/<mod>/<ver>.zip` 本地快取）。
    3. `core/installer.py:Installer._restore_module_package`（`installer.py:748-839`）：`yscb.py restore` 的獨立還原路徑同步支援此「同版本 `source/<mod>` 動態打包至 `.mirror/` 與 `release/`」機制。
  - **老舊版本新環境 Clone 之同三元組 (`X.Y.Z.*`) 自動平滑遞補**：當外部老專案於新環境 Clone（無本地 `.mirror/` 亦無 `source/`），且 `yscb.config.json` 鎖定之舊 revision `X.Y.Z.W` 已被上游滑動視窗標記為 `pruned`（無遠端 `.zip`）時，`yscb.py` 自舉與 `core`（`cmd_restore` / `act_reload`）自動於 `index.json` 的 `active` 版本中尋找**同三元組 (`X.Y.Z.*`) 且滿足環境依賴約束之最高可用 revision**（如 `1.1.2.0` $\to$ `1.1.2.3`）進行下載還原，印出明確遞補提示並同步更新 `yscb.config.json`。
- **[P00:DR-03] 支柱三：母倉遠端分發管線對接（全處 `DEFAULT_PROVIDER_URL` 更新 + 頂層與模組級 URL 無感遷移 + GitHub Actions 工作流）**：
  - **全倉預設 URL 統一更新**：同步將 `yscb.py:20` 之 `DEFAULT_PROVIDER_URL`、`core/installer.py:690` 之 `cmd_restore` 預設 `default_provider` 以及對應測試斷言（如 `test_distribution_lifecycle.py:37`）更新為 `https://raw.githubusercontent.com/ysnaive/ys-codebase/releases`。
  - **頂層與模組級 Provider URL 雙層無感遷移**：在讀取或更新 `yscb.config.json` 時，若偵測到頂層 `"default_provider"` **或任何 `installed_modules[<mod>]["provider"]`**（涵蓋 `yscb.py:475`、`engine.py:472`、`update_checker.py:118`）指向舊官方 URL `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release`，自動無感遷移改寫為 `.../releases/ys_codebase/release`。
  - **建立 `.github/workflows/release-publish.yml`**：當推送至 `main` 時，於雲端 Runner 自動拉取遠端 `releases` 分支既有 `.zip`、打包當前更新模組、依 `index.json` 滑動窗口剔除過期 `.zip`，並透過無父節點之**單一孤兒 Commit (Orphan Commit)** 強制推送至 `origin/releases`。
  - *(註：實際存量 37 個 `.zip` 遷移、母倉 `.gitignore` 切換與 `git filter-repo` 全歷史淨化工程獨立拆分至 [`sub_03_legacy_release_migration_and_history_purge`](../sub_03_legacy_release_migration_and_history_purge/P00_discuss.md) 執行)*。

---

## 3. 開放議題與確認紀錄

- [x] `sub_01` 發布解耦架構與本地同版本自給自足引擎設計已確認（`Confirmed`），存量遷移與歷史淨化已拆分至 `sub_03`。

