# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：`module:gdrive-support` 原子雲端操作、Shortcut 差量分支與雙向同步模組 (`gdrive_bidirectional_sync_module`)  
> 建立日期：2026-11-04  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 建立官方選配模組 `module:gdrive-support`（Python package `gdrive_support`，短別名 `gdrive`），依據 [P00_discuss.md](./P00_discuss.md) 與 [R01_gdrive_architecture_and_design.md](./R01_gdrive_architecture_and_design.md) 定案之五大正交核心部件（`config.py`、`reconciler.py`、`transport.py`、`coordinator.py`、`service.py`），提供：
    1. 不依賴背景常駐服務、100% 保持原檔案類型之原子 Google Drive API / SDK 與 CLI 操作（`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）。
    2. 整合 `module:file-space` 空間幾何與選填 `mapping`、雲端 `<root_folder_id>` 標準頂層結構（`.yscb_gdrive.json`、`README.md`、`.history/` Copy-on-Write 與無引用自動回收至 `.trash/`、`main/` 主幹與 Shortcut 差量分支）及三方狀態機雙向同步（預設 `auto_sync: false`）。
    3. 針對無法在無金鑰 CI/沙盒環境執行自動化單元測試之真實對外 Google Drive REST API v3 / OAuth2 連線與實機行為，以獨立子計畫收斂驗證與打磨（自動化 `tests/` 100% 僅針對 `LocalSandboxTransport` 與無狀態核心邏輯撰寫，嚴禁將需外部使用者金鑰之對外 Google Drive API 寫入自動化 test cases）。
- **架構邊界**：
  - 本體開發空間：`ys_codebase/source/gdrive-support/`（含 `gdrive_support/`、`scripts/cli.py`、`contributes/`、`configurable/`、`tests/`）與 `docs/gdrive-support/`。
  - 零 `.gitignore` 耦合；不做 Google Workspace (`application/vnd.google-apps.*`) 原生線上文件特化匯出轉檔，100% 保持原檔案類型同步。
  - **測試鐵律**：`ys_codebase/source/gdrive-support/tests/` 下所有自動化測試案例必須 100% 基於 `LocalSandboxTransport` 與純記憶體/本地沙盒執行，**嚴禁針對對外真實 Google Drive HTTP/OAuth API 編寫自動化 test cases**（因無法保證任何開發或測試環境皆具備使用者金鑰與雲端憑證）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_atomic_api_and_sdk` | Full Track | `Completed` | 建立 `module:gdrive-support` 模組骨架、組態與 `file-space`/`mapping` 映射 (`config.py`)、雙模傳輸基座 (`AbstractSyncTransport` / `LocalSandboxTransport` / `GoogleDriveApiTransport` 原子操作 `ls`/`get`/`put`/`rm`/`mkdir`/`shortcut`) 與 CLI/SDK 入口（自動化測試 100% 僅測本地沙盒與組態邏輯） |
| **sub_02** | `sub_02_branch_and_sync_engine` | Full Track | `Completed` | 實作雲端 `<root_folder_id>` 分支管理機制（`.yscb_gdrive.json`、`README.md`、`init`、`branch list/create/delete`、`checkout` 原子工作樹切換、Shortcut 差量分支、`.history/` Copy-on-Write 與無引用自動移入 `.trash/` GC）、100% 純函式三方對帳 (`reconciler.py`)、增量帳本落盤 (`coordinator.py` 之 `pull`/`push`/`sync`) 與 `auto_sync: false` 預設待機之 `service.py`（自動化測試 100% 基於 `LocalSandboxTransport` 驗證） |
| **sub_03** | `sub_03_live_gdrive_verification` | Revision | `Completed` | 修訂與非沙盒可測試內容功能驗證：針對對外真實 Google Drive REST API v3（OAuth2 Desktop Loopback / Service Account 憑證流、`files.*` / `changes.list` 真實雲端端點相容性、錯誤訊息與 CLI DX 細節）進行實機手動驗證與微調修訂（不將需使用者金鑰之對外 API 納入自動化 `tests/`） |
| **sub_04** | `sub_04_repo_sync_isolation_and_skills` | Full Track | `Completed` | 將雲端區分為「頂層純雲端原子儲存區 (`<root_folder_id>/`)」與「子目錄受管同步倉 (`<root_folder_id>/<repo_sync_root>/`，預設 `repo/`)」；重構組態為 `"repo_sync": {"enable": false, "repo_sync_root": "repo", ...}`（`enable: false` 時拒絕 `init/branch/checkout/pull/push/sync` 僅開放原子操作）；雲端刪除改用 Google Drive 原生 30 天垃圾桶 (`trashed=true`) 並自動清空外部 AI 暫存之 `<repo_sync_root>/.trash/`；依本地快取最後啟用狀態變動觸發頂層 `root/README.md` 軟合併/軟移除與 `<repo_sync_root>/README.md` 維護；並新增雙軌分離之「本地 `agents-workflow` Skill」與「給外部/雲端操作之隨包 Skill」 |
| **sub_05** | `sub_05_ecosystem_refinements_and_release` | Revision | `Completed` | 生態系關聯模組微調更新（`[REV-01]` `server` 預設 30 分鐘 Timeout 與 `touch_activity` 保活探針 SDK 整合、`[REV-02]` 外部隨包技能與網頁版 Gemini 引導手冊、`[REV-03]` 實機背景自動同步驗證、`[REV-04]` 三維度正交邊界收斂、`[REV-05]` CI 與 `yscb.py` 宿主 `releases` 分支發布管線升級、`[REV-06]` 全模組相依/組態對齊與正式版打包發布） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0**：完成 `P00_discuss.md` 與 `R01_gdrive_architecture_and_design.md` 專題調研及兩批 `/blind-subagent` 深度驗證定案 (`Concluded`)。
- [x] **里程碑 1 (`sub_01_atomic_api_and_sdk`)**：完成 `module:gdrive-support` 模組骨架、組態映射與原子雲端操作 API/SDK/CLI（`ls`/`get`/`put`/`rm`/`mkdir`/`shortcut`）及沙盒單元測試。
- [x] **里程碑 2 (`sub_02_branch_and_sync_engine`)**：完成 `<root_folder_id>` Shortcut 差量分支系統、`.history/` 引用計數回收至 `.trash/`、三方同步狀態機與選配背景服務（`auto_sync: false`）及沙盒整合測試。
- [x] **里程碑 3 (`sub_03_live_gdrive_verification`)**：完成非沙盒可測試之對外 Google Drive API 實機功能驗證與 OAuth2 Loopback 實證。
- [x] **里程碑 4 (`sub_04_repo_sync_isolation_and_skills`)**：完成 `repo_sync` 組態與子目錄隔離、雙層 `README.md` 本地快取軟合併/軟移除，以及本地/外部雙軌分離之 Agent Skills。
- [x] **里程碑 5 (`sub_05_ecosystem_refinements_and_release`)**：完成關聯模組微調更新與最終釋出作業。

