# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 建立日期：2026-11-04  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  1. **統一全模組 `sys.path` 運行時尋址**：於 `core` 派發層（含本地冷派發 `dispatch_local`、事件廣播 `events.broadcast`、符號載入 `symbols.resolve_callable`）與 `server` 預熱層（`WarmWorker.pre_warm`）統一將 `yscb://.modules/<mod>` 所有已安裝模組注入 `sys.path`，徹底根除冷/熱派發跨模組匯入（如 `gdrive-support` 匯入 `file-space`）不一致與各模組手工維護 `_ensure_module_path` 的技術債。
  2. **確立五大語意資料空間架構 (`config` / `config.local` / `storage` / `storage.local` / `cache`)**：將模組資料按「職責（組態 vs 資料狀態）」、「Git 追蹤政策（團隊共享 vs 本機私有忽略）」與「硬體持久性（實體磁碟持久 vs `tmpfs` 揮發快取）」正交解耦為五大語意空間，解決容器重啟清空 `tmpfs` (`.cache`) 導致 OAuth `token.json` 憑證遺失、`gdrive` 三方同步基準帳本失憶、以及 `knowledge-db` 每次重啟重複下載 91MB 模型與重算 54MB 索引之痛點。
- **架構邊界**：
  - **第一方影響模組**：`core`、`server`、`dev`、`vscode-support`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`gdrive-support` 及系統知識庫 `docs/`。
  - **剛性約束**：`sys.path` 注入嚴格限定於 `yscb://.modules/<mod>` 已安裝運行時空間，嚴禁混入 `source/` 開發源碼空間；`storage.local://` (`yscb://.storage.local/`) 不納入 `act_snapshot` 每次安裝快照拷貝，避免百 MB 級模型與索引拖慢模組安裝。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_all_modules_sys_path` | Full Track | `Completed` | 於 `core.platform` 統一在派發、預熱、事件廣播與符號解析前注入所有已安裝 `.modules/<mod>` 至 `sys.path`，拔除 13 處散落補丁，並於 `dev/checker.py` 新增禁止非 `core` 生產代碼變動 `sys.path` 之零豁免靜態 AST 守門。 |
| **sub_02** | `sub_02_five_semantic_spaces_architecture` | Full Track | `Completed` | 於 `core` 擴充 `config.local://` (`yscb://.config.local/`) 與 `storage.local://` (`yscb://.storage.local/`) 語意協議、預設 `.gitignore` 保護、`core.config` 雙軌讀寫與舊版 `config.local.json` 自動遷移、`act_snapshot` 排除 `storage.local://` 及 `act_delete --purge` 生命週期治理，並對齊 `dev` 與 `vscode-support` Schema/檢核。 |
| **sub_03** | `sub_03_ecosystem_modules_space_alignment` | Full Track | `Completed` | 將全生態系模組（`gdrive-support`、`knowledge-db`、`ast`、`file-space`、`agents-workflow`、`core`）之本機憑證（`credentials.json`, `token.json`）、模型權重（`models/`）、索引圖譜、同步狀態帳本（`sync_state.json`）與發布清冊全面對齊遷移至 `config.local://` 與 `storage.local://`，保留純揮發性快取與鎖檔於 `cache://`。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `core` 與 `server` 全已安裝模組 `sys.path` 統一注入並通過單元與沙盒回歸測試。
- [x] **里程碑 2 (`sub_02`)**：完成 `config` / `config.local` / `storage` / `storage.local` / `cache` 五大語意空間核心引擎、組態雙軌合成與快照生命週期重構。
- [x] **里程碑 3 (`sub_03`)**：完成全倉 9 模組語意空間映射對齊、本機既有資產無損遷移與 `gdrive` 實機同步驗證。

