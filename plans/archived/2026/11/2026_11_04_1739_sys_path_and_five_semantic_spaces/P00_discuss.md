# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 排查為何 `gdrive` 未自動同步遠端新計畫文件（發現容器重啟清空 `tmpfs` 掛載之 `.cache`，導致 `token.json` 與 `sync_state.json` 蒸發，且 `knowledge-db` 每次重啟皆重新下載 91MB 模型與重算索引；同時 `gdrive auth` 冷派發因 `.modules/file-space` 未加入 `sys.path` 而報錯）。
  2. 針對冷/熱派發跨模組尋址：由 `core` 於派發前統一將所有已安裝 `module` 寫入 `sys.path`（包含熱派發）。
  3. 針對儲存空間語意架構：進階設計為 `storage.local` + `storage` + `config.local` + `config` + `cache` 五大語意（物理目錄採用 `.config.local` 與 `.storage.local`，並將 `config.local.json` 同步遷移至 `config.local://`），拆分為三個子計畫依序推進。
- **核心目標**：
  1. **統一跨模組執行期 `sys.path` (`sub_01`)**：確保無論冷派發、Server WarmWorker 熱派發、Hook 事件廣播或 `code.func://` 動態載入，所有已安裝於 `yscb://.modules/<mod>` 之模組皆自動在 `sys.path` 中立即可見。
  2. **建立五大語意資料空間 (`sub_02`)**：
     - `config://` $\to$ `yscb://config/<mod>/`（團隊共享設定，Git Tracked，納入 Snapshot）
     - `config.local://` $\to$ `yscb://.config.local/<mod>/`（本機個人設定 `config.local.json` 與機密憑證，Git Ignored，磁碟持久，納入 Snapshot）
     - `storage://` $\to$ `yscb://storage/<mod>/`（團隊共享持久化資料，Git Tracked，納入 Snapshot）
     - `storage.local://` $\to$ `yscb://.storage.local/<mod>/`（本機持久化狀態帳本、AI 模型權重與索引快照，Git Ignored，磁碟持久不掛 `tmpfs`，**不納入** `act_snapshot` 每次安裝備份）
     - `cache://` $\to$ `yscb://.cache/<mod>/`（純揮發性快取、IPC 鎖、日誌與測試沙盒，Git Ignored，可掛載 `tmpfs` RAM Disk，重啟或卸載清空零副作用）
  3. **全生態系模組空間映射對齊 (`sub_03`)**：將 `gdrive-support`、`knowledge-db`、`ast`、`file-space`、`agents-workflow`、`core` 現有混放於 `cache://` 或 `config://` 的本機憑證、模型、索引與狀態帳本全面對齊至 `config.local://` 與 `storage.local://`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core/uri.py` 之 Scheme B 解析器、`core/config.py` 之雙層設定合併器、`core/gitignore.py` 之統一根目錄 `.gitignore` 收斂引擎，以及 `core/engine.py` 之組態模板物化與快照治理管線。
- **邊界排除 (Explicitly Excluded)**：
  - 本主計畫不變更 `server` 與 `vscode-support` 綁定 IDE 進程生命週期之新功能（該議題待本基礎設施重構完成並同步遠端計畫後再行立項）。
- **架構影響範圍**：
  - 涵蓋 `core`、`server`、`dev`、`vscode-support`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`gdrive-support` 共 9 個模組及 `docs/` 系統知識庫。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `core` 統一注入全已安裝模組至 `sys.path`（涵蓋冷派發與熱派發）**：
  - 於 `core` 提供統一的運行時模組路徑準備函式，掃描 `yscb://.modules/` 下所有已安裝模組目錄並注入 `sys.path`（優先序：`[.modules/<target_module>, .modules/core, ...其餘已安裝 .modules/<mod> 依字典序]`），嚴格過濾禁止任何 `/source/` 路徑混入。統一掛載於 `dispatcher.dispatch_local`、`events.broadcast`、`symbols.resolve_callable` 與 `WarmWorker.pre_warm`。
- **[P00:DR-02] 五大語意空間之物理目錄映射與 Git / Snapshot 邊界**：
  - 新增 `config.local://` 映射至 `yscb://.config.local/`、新增 `storage.local://` 映射至 `yscb://.storage.local/`，兩者皆寫入 `core/contributes/core.json` 之預設 `gitignore`。
  - `AtomicEngine.act_snapshot` 備份 `config://`、`config.local://` 與 `storage://`，顯式排除 `storage.local://` 與 `cache://` 以防止複製百 MB 模型與索引；`act_delete(purge=True)` 則完整清理 `config`、`config.local`、`storage`、`storage.local` 與 `cache`。
- **[P00:DR-03] `config.local.json` 遷移至 `config.local://` 與平滑向下相容**：
  - 各模組之本機覆蓋設定檔統一改存於 `config.local://<mod>/config.local.json`（使 `yscb://config/` 成為 100% 純淨之 Git Tracked 目錄）；`core.config` 與 `AtomicEngine` 讀取/部署時若偵測到舊路徑 `config://<mod>/config.local.json` 存在且新路徑尚無檔案，自動執行平滑遷移。
- **[P00:DR-04] 現有模組本機憑證、模型、索引與同步帳本之語意歸位**：
  - `gdrive-support` 之 `credentials.json` 與 `token.json` 歸入 `config.local://gdrive-support/`；`sync_state.json` 與 `readme_sync_state.json` 歸入 `storage.local://gdrive-support/`；`sync.lock` 與 `sync.log` 留存於 `cache://gdrive-support/`。
  - `knowledge-db`（含 `models/` 與 `indices/`）、`ast`（符號與呼叫圖譜快照）、`file-space`（YFP2 指紋與游標）、`agents-workflow`（`project_release_manifest.json`, `release_manifest.json`, `source_sha1_cache.json`）與 `core`（`gitignore_dynamic.json`）全面歸入 `storage.local://<mod>/`，而跨進程 `.lock` 鎖檔則留存於 `cache://<mod>/`。

---

## 3. 開放議題與確認紀錄

- 物理目錄命名：已由開發者確認採用 `.config.local` 與 `.storage.local`。
- `config.local.json` 定位：已由開發者確認一併遷移至 `config.local://<mod>/config.local.json`。
- 子計畫拆分結構：已由開發者確認拆分為 `sub_01`（`core` 全模組 `sys.path`）、`sub_02`（五大語意空間重構）、`sub_03`（現有全模組語意空間映射對齊）。

