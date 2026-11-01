# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：版本相容性事後修正機制、釋出元數據與更新嚴重度治理 (sub_02)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「sub 02 要討論的則是現有功能性的不足，我發現現在的組態有個盲點，我知道我現在需要相依的模組到哪個版本，但是我不知道我在未來哪個版本會無法支援，這怎麼半?」
  - 「我覺得應該在事後可修正，你覺得要改為可以拆包改組態，還是我們應該把組態和 .zip 分開? 形成 index -> 組態 -> .zip ?」
  - 「方案 II，但是組態 SSOT 在 .zip 包中」
  - 「和我想得差不多，另外我想加的是本次版本的釋出信息和嚴重性，例如只是單純修 bug、有新功能、惡性問題修補。還有是否有必要對此次上游更新進行本地更新的建議」
  - 「1. 可以，但寫解析實要預留非既定項目的輸出方式，有可能未來加其他類型，要保證舊版解析安全 2. 兩者皆支援，可以自己直接寫在 manifest.json 裡後調用 release，也可以一鍵指令執行 3. 印出醒目的 [CRITICAL UPDATE] 告警；可以提供輕量級指令」
- **核心目標**：
  1. **解決未來版本不相容之盲點（事後可修正機制）**：保持 `.zip` 包內 `manifest.json` 作為模組出廠本體組態 SSOT，同時採用方案 II（兩層聚合結構）將各版本的 `dependencies` 與釋出元數據匯總於 `release/<mod>/index.json` 的 `releases[<ver>]` 中；當未來某上游模組發布破壞性變更時，無須拆改舊版 `.zip`，即可透過輕量 CLI 指令或直接編輯 `index.json` 事後為舊版本補上相容上界（如 `<1.4.0`），並由 `core` 在安裝與更新時執行雙向相容校驗（含 `core` 本身版本校驗）。
  2. **引入版本釋出元數據與更新建議分級（向前相容解析）**：支援記錄各版本之變更類型（`type`）、本地更新建議等級（`urgency`）與釋出摘要（`summary`），具備對未知新類型之向前相容安全解析兜底，支援 `manifest.json` 直寫與 `dev release` CLI 參數雙軌注入，並於 `UpdateChecker` 實現跨版本累積嚴重度探測與 `[CRITICAL UPDATE]` 醒目告警。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `ys_codebase/source/core/core/semver.py`（`match_constraint`、`find_best_version`）
  - `ys_codebase/source/core/core/engine.py`（`AtomicEngine.act_solve_deps`、`_get_module_manifest_from_provider_or_local`）
  - `ys_codebase/source/core/core/installer.py`（`Installer.cmd_install`、`cmd_update`、`cmd_list`）
  - `ys_codebase/source/core/core/update_checker.py`（`UpdateChecker.check_updates`、`get_tips`）
  - `ys_codebase/source/dev/dev/{builder.py,releaser.py,checker.py}` 及 `ys_codebase/source/dev/scripts/cli.py`
- **邊界排除 (Explicitly Excluded)**：
  - **嚴禁事後拆改已發布之舊版 `.zip` 二進位壓縮包**：舊版 `.zip` 保持二進位不可變性（Immutability），事後相容性收緊或元數據微調統一作用於 `release/<mod>/index.json`（並在安裝解壓至 `.modules/<mod>/` 時同步覆寫生效）。
  - **嚴禁在解析 `type` / `urgency` 時使用封閉式 Enum 拋出例外**：舊版 `core` 讀取未來新增之未知 `type` 或 `urgency` 字串時，必須 100% 安全降級並原樣格式化顯示。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/{engine.py,installer.py,update_checker.py,semver.py}`
  - `ys_codebase/source/dev/dev/{builder.py,releaser.py,checker.py}`、`ys_codebase/source/dev/scripts/cli.py`
  - `ys_codebase/release/*/index.json` 與各模組 `manifest.json`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 方案 II 兩層聚合結構：出廠本體 SSOT 在 `.zip/manifest.json`，事後相容與釋出帳本在 `index.json`（含 `"status": "active" | "pruned"` 標註與 `act_reload` 離線快取冪等注入）**：
  - **出廠單向自動提取與滑動視窗 `"status": "active" | "pruned"` 數據標註**：模組本體組態（`name`, `version`, `entry`, `contributes`, `onboarding`, `optional`, `pip_dependencies`, 初始 `dependencies`, `release`）之 SSOT 位於 `source/<mod>/manifest.json` 並封裝於 `.zip` 中。當 `dev`（`Builder._update_release_index`）打包新版本時，自動提取該版本的 `dependencies` 與 `release` 元數據寫入 `release/<mod>/index.json` 的 `releases[<ver>]` 字典，並標註 `"status": "active"`；**當 3-Revision 滑動視窗淘汰舊版實體 `.zip` 時，將該版本自頂層可下載清單 `versions` 移除，並在 `releases[<ver>]` 中將其狀態標註為 `"status": "pruned"`（永久保留其歷史相容與釋出元數據，絕不刪除或覆蓋已被事後修正過的紀錄）**。
  - **事後相容性修正、候選版本相容過濾與 `core` 雙向解算（涵蓋 `install` 與 `update`）**：
    - 當未來發現某歷史版本 `<ver>` 無法支援新版相依模組時，直接於 `index.json` 的 `releases[<ver>]["dependencies"]` 修正約束區間（如補上 `<1.4.0`）。
    - 修正 `AtomicEngine._find_manifest_in_local_provider`（`engine.py:531-543`）與 `_get_module_manifest_from_provider_or_local`（`engine.py:590-595`）：先根據 `index.json` 中 `status == "active"`（或本地已存在快取）之 `releases[<ver>]["dependencies"]` 過濾出**與當前環境（含當前已安裝之 `core` 版本與其他模組）相容**的候選版本後，再選出最高相容版本；若使用者顯式指定已 `pruned` 之版本且無本地快取，則於 `restore` 自動平滑遞補至同三元組 (`X.Y.Z.*`) 最高可用 revision（或於 `install` 給出明確提示）。
    - 修正 `AtomicEngine.act_solve_deps`（`engine.py:634`）：補齊對 `dep_name == "core"` 的版本約束校驗（若目標模組要求之 `core` 版本與當前已安裝之 `core` 不相容，明確阻斷或納入升級解算，不再靜默跳過）。
    - 修正 `Installer.cmd_update`（`installer.py:475-484`）：更新模組時必須先通過 `act_solve_deps` 執行 `index.json` 之 `dependencies` 傳遞相依解算與環境雙向相容校驗，僅升級至相容於當前環境之最高版本（且即使 `updated_any == False` 亦刷新 `UpdateChecker` 快取）。
  - **`module.mirror://<mod>/index.json` 同步快取與 `act_reload` 物化階段冪等覆寫注入**：
    - 為支援從遠端 HTTP Provider 安裝模組後在離線環境執行 `yscb.py reload` 或 `rollback`（`act_restore_snapshot` 結尾呼叫 `act_reload`），`act_download` / `act_solve_deps` 讀取 `index.json` 時同步將其快取至 `module.mirror://<mod>/index.json`。
    - 於 `AtomicEngine._reload_materialize_single_module`（`engine.py:805-823`）從 `.mirror/<mod>/<ver>.zip` 解壓後，讀取 `module.release://<mod>/index.json` 或 `module.mirror://<mod>/index.json` 中該版本的外部覆寫約束並合併回 `.modules/<mod>/manifest.json`，確保離線 `reload` 與 `rollback` 後事後修正之 `dependencies` 100% 持久生效。
- **[P00:DR-02] 提供 `dev` 輕量級索引維護指令、補齊 `Checker` 校驗並擴充 CLI 選項正規化**：
  - 於 `dev` CLI 提供輕量維護子命令（如 `dev index-patch`），支援免手改 JSON 直接對 `release/<mod>/index.json` 中指定版本 `<ver>` 事後更新相依約束（`--dep`）、狀態（`--status`）或調整釋出嚴重度與說明（`--type`、`--urgency`、`--summary`），並同步更新 `ys_codebase/source/dev/contributes/core.json` 與 `_manifest.md`。
  - 同步於 `ys_codebase/source/dev/scripts/cli.py`（第 19-22 行 `_normalize_bags` 之 `value_options` 集合）註冊新增之帶值選項（如 `"urgency"`, `"summary"`, `"dep"`, `"ver"`, `"version"`, `"status"`），並於 `Checker._check_manifest`（`checker.py:350-464`）補齊對 `manifest.json` 選填 `"release"` 欄位之字典結構與非空字串校驗。
- **[P00:DR-03] 版本釋出元數據 (`type` / `urgency` / `summary`) 與向前相容（Forward-Safe）解析契約**：
  - **標準欄位結構**：
    - `type`（變更性質）：預設建議值含 `bugfix`（一般修補）、`feature`（新功能）、`hotfix`（惡性問題/緊急修補）、`breaking`（不相容變更）、`refactor`（重構優化）。
    - `urgency`（本地更新建議等級）：預設建議值含 `optional`（可選更新）、`recommended`（建議更新）、`critical`（強烈建議立即更新 / 惡性問題修補）。
    - `summary`（簡短釋出說明字串）。
  - **向前相容安全解析**：解析器對任何非既定之未來擴充字串（例如未來新增 `type: "security"` 或未知 `urgency`），一律不報錯、不拋例外；未知 `type` 直接轉大寫標籤 `[<TYPE>]` 原樣輸出，未知 `urgency` 安全回退至一般建議提示格式并附帶原始標籤。
- **[P00:DR-04] 雙軌發布注入（含 `/bump-revision` 技能同步）與 `UpdateChecker` 同 Major 相容過濾暨跨版本 `[CRITICAL UPDATE]` 醒目告警**：
  - **雙軌注入與 `/bump-revision` 同步**：開發者既可先在 `source/<mod>/manifest.json` 填妥 `"release": {"type": "...", "urgency": "...", "summary": "..."}` 再執行 `dev release`，也可直接在 `python yscb.py dev release <mod> [--type ...] [--urgency ...] [--summary ...]` 命令列傳入參數一鍵寫入 `manifest.json` 並打包發布；同步更新 `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md` 引導填寫或傳遞釋出元數據。
  - **同 Major 相容過濾、跨版本累積嚴重度探測與 12h 快取結構擴充**：
    - `UpdateChecker.check_updates`（`update_checker.py:126-149`）探測遠端 `index.json` 時，必須對齊 `cmd_update` 的同 Major 鎖定約束（`^major.minor.patch`）與當前環境依賴相容性過濾（避免對無法透過 `update` 安裝的不相容跨 Major 版本發出假陽性告警死循環）。
    - 掃描 `index.json["releases"]`（包含 `active` 與中間已被 `pruned` 的過渡版本）介於 `(current_version, latest_compatible_version]` 之間的所有版本元數據，將計算出之最高嚴重度（`is_critical`、`urgency`、`type`、`summary`）**完整寫入 `cache://core/update_check.json` 的 `updates[<mod>]` 快取結構中**，確保 12h 快取命中期間呼叫 `get_tips()` 皆能穩定印出醒目的 `[!] [CRITICAL UPDATE]` 框線告警與釋出摘要。

---

## 3. 開放議題與確認紀錄

- [x] `sub_02` 事後相容修正、輕量維護指令、釋出元數據向前相容解析與 `[CRITICAL UPDATE]` 告警設計已全數確認（`Confirmed`）。

