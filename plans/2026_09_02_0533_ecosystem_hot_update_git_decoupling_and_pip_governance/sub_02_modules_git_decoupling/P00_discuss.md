# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 接續子計畫 sub 02：`modules/` 運行端冷啟動再生管線與 Git 追蹤解耦（含 bootstrap/restore 命令、.gitignore 配置、空間協議更新）。
  - 使用者補充指示 1：「git ignore 應修改於 yscb:// 自動生成、控管的 git ignore」。
  - 使用者補充指示 2：「module:// 協議路徑應同時將 modules 更名為 .modules」。
  - 使用者補充指示 3：「不需要加入平滑遷移過渡，不考慮過往 modules 目錄，直接以最新設計為主，該功能不會影響既有內容，就不要額外加，下游端可自行考慮移除 modules」。
  - 使用者補充指示 4：「有延伸問題，modules 不再 git 追蹤後，我們應紀錄當前專案安裝的模組和版本，以利在不同開發端JIT自動同步」。
  - 使用者補充指示 5：「yscb://.gitignore 需考慮 "yscb://" == "project://" 的狀況，須採用軟合併方式修改 git ignore (可參考 agents workflow 中用到的方案)」。
- **核心目標**：
  1. 將 `module://` 與 `module.root://` 語意 URI 協議映射之實體底層目錄自 `yscb://modules/` 正式更名為 `yscb://.modules/`，與系統既有之 `.mirror/`、`.cache/`、`.snapshots/` 等內部運行目錄對齊隱藏規範。
  2. 將 `yscb://.modules/` 運行端產物從 Git 追蹤中徹底解耦，消除頻繁編譯、安裝與升級對 Git 歷史產生的冗餘變更污染。
  3. 修改 `yscb.py` 內建自主控管之 `_generate_internal_gitignore`，將 `/.modules/` 納入 `yscb://.gitignore`，並支援軟合併 (Soft Merge) 機制，在 `"yscb://" == "project://"` 拓撲下完整保留宿主專案自訂規則及其他模組管理區塊，杜絕粗暴覆蓋。
  4. 升級宿主引導腳本 `yscb.py` 與 `core` 模組，全面將執行分發、鏡像解壓與動態調度對齊至 `.modules/` 目錄。
  5. 以 Git 追蹤之 `yscb.config.json` 的 `installed_modules` 清冊作為唯一契約，於 `yscb.py` 分發層建立 JIT 模組同步守門（JIT Auto-Sync Gate），在跨端拉取更新或全新克隆時自動偵測並原地還原同步對應版本之模組。
  6. 提供健壯的冷啟動模組再生機制（`python yscb.py restore` 或在缺少模組時自動/引導提示修復），依據 `yscb.config.json` 的 `installed_modules` 自本地 `release/`、`build/` 或 `.mirror/` 快速原地還原運行端代碼至 `.modules/`。
  7. 同步更新全專案最高工程規範 [docs/_project/STANDARDS.md](file:///workspace/ys-codebase/docs/_project/STANDARDS.md)，將 `module.root://` 與 `module://` 之路徑映射改為 `yscb://.modules/`，且 Git 追蹤政策修訂為 `🚫 忽略`。
- **邊界排除 (Explicitly Excluded)**：
  - **零平滑過渡**：絕對不加入任何針對舊 `modules/` 目錄的探測、搬移、更名或平滑遷移相容邏輯，代碼庫保持純淨，由下游端自行處置舊 `modules`。
  - 不更動 `source/` 源碼目錄的 Git 追蹤政策（`source/` 始終為唯一 SSOT 與 Git 核心追蹤資產）。
  - 不破壞既有 `init`、`install`、`update` 與 Dogfooding 閉環流程。
  - 本子計畫不包含私有 Pip 微環境治理（留待 `sub_03` 處理）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Git 忽略規則自動化控管源頭**：
  - 嚴格落實使用者補充指示：不手動修改靜態檔案，而是在宿主引導腳本 `yscb.py` 的 `_generate_internal_gitignore(yscb_dir)` 中，將 `/.modules/` 加入 `yscb://.gitignore` 宣告清單。
  - 每次 `yscb.py` 執行 `init`、`restore` 或自檢時，自動確保 `yscb://.gitignore` 具備 `/.modules/` 忽略條目，維持零逃逸與自動控管。

- **[P00:DR-02] 冷啟動再生 (Restore) 管線設計與執行層次**：
  - 當使用者或 CI 全新 Clone 倉庫時，`.modules/` 目錄將為空，此時 `.modules/core` 尚未物化，因此冷啟動再生命令必須直接實作於 `yscb.py` 宿主層。
  - 新增 `python yscb.py restore` 指令：讀取 `yscb.config.json` 中的 `installed_modules` 清單，遍歷所有已登記模組與版本，依序自 `default_provider`、本地 release 或 mirror 鏡像還原解壓縮至 `.modules/<name>`，並觸發 `reload`。
  - 當執行任何模組命令且偵測到 `.modules/` 缺失相應模組時，輸出友善的引導診斷提示（例如：「模組未物化，請執行 python yscb.py restore」）。

- **[P00:DR-03] Git 歷史追蹤解耦方針**：
  - 核心關注點在於新系統的 `.modules/` 必須被 Git 忽略；若倉庫既有之舊 `modules/` 需自 Git 移除，由專案或下游端自主執行清理，YSCB 核心腳本不注入專案清理命令。

- **[P00:DR-04] 空間協議與工程規範對齊**：
  - 於 `docs/_project/STANDARDS.md` 第 1 節「語意空間協議清單」中，將 `module.root://` 實體解析路徑更新為 `yscb://.modules/`，`module://` 更新為 `yscb://.modules/{module}/`，且 Git 追蹤政策由「✅ 受追蹤」正式變更為「🚫 忽略」。

- **[P00:DR-05] module:// 協議路徑與實體目錄全面對齊 .modules (無遷移包袱)**：
  - 嚴格落實使用者補充指示：運行端目錄名稱從 `modules` 全面更名為 `.modules`，直接以最新設計為主。
  - **堅決排除過渡代碼**：工具鏈完全不探測、不搬移、不相容舊 `modules/`，杜絕過渡期技術債。
  - 影響層面：
    1. `core.uri`：更新 `_BOOTSTRAP_FALLBACK_SCHEMES` 中 `module` 的預設值為 `yscb://.modules/`；
    2. `core.contributes`：更新 `source/core/contributes/core.json` 之 `module` 協議預設為 `yscb://.modules/`；
    3. `yscb.py`：所有路徑組裝直接使用 `.modules`（包含 `cmd_init`、`dispatch_module`、`_get_installed_module_commands`、`restore` 等）。

- **[P00:DR-06] yscb.config.json 模組清冊鎖定與 yscb.py JIT 自動同步自愈**：
  - **依賴鎖定契約**：受 Git 追蹤之 `yscb.config.json` 的 `installed_modules` 欄位即為專案模組清冊與版本鎖定檔 (Manifest & Lockfile)。
  - **JIT 模組同步守門 (JIT Auto-Sync Gate)**：在 `yscb.py` 的命令分發入口前置加入 $< 2\text{ms}$ 極速嗅探。比對 `installed_modules` 宣告之模組與版本 vs 本機 `.modules/` 現況。
  - **跨端無感自愈**：當偵測到缺失或版本落後/不符時，自動從 provider 或本地鏡像執行原地 JIT Restore 並完成 reload，達成零手動介入的跨開發端自動同步體驗。

- **[P00:DR-07] yscb://.gitignore 軟合併支援 ("yscb://" == "project://")**：
  - **情境適配**：針對 `yscb://` 與 `project://` 位於同一目錄（即 `yscb_root` 為 `./`）時，嚴禁全量覆寫 `.gitignore`，避免清空宿主專案原有規則。
  - **軟合併演算法**：採用標記區塊（`# === YSCB INTERNAL IGNORE BEGIN ===` 至 `# === YSCB INTERNAL IGNORE END ===`）與歷史舊規則相容正則，精確替換或追加內部管理忽略區塊，完整保留宿主專案自訂規則及其他模組（如 `agents-workflow`）之管理區塊。

---

## 3. 開放議題與確認紀錄

- [x] 是否已明確 Git Ignore 的修改來源？（已確認：由 `yscb.py` 自主生成與控管 `yscb://.gitignore`）
- [x] 是否已明確運行端實體目錄更名？（已確認：`module://` 底層全面更名為 `.modules`）
- [x] 是否需要舊 modules 平滑遷移相容？（已確認：堅決不加，直接以最新設計為主，下游端自行處置舊目錄）
- [x] 是否已確立跨開發端模組相依性記錄與 JIT 自動同步機制？（已確認：以 `yscb.config.json` 為鎖定檔，`yscb.py` 前置 JIT Auto-Sync 守門自愈）
- [x] 是否已確立 yscb://.gitignore 軟合併機制以因應 "yscb://" == "project://" 拓撲？（已確認：參考 agents-workflow 標記區塊軟合併方案）
