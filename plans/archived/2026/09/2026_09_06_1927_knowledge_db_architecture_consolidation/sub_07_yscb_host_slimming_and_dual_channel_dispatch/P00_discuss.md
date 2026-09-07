# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「先清空本地所有快取環境(不受 git 追蹤部分)，並進行 @build 版本自部屬 + yscb入口檔案功能聚合。啟動完整 Roadmap 瘦身重構 (將套件還原等邏輯全面下沉至 core，yscb.py 轉為極簡雙管道路由)。」
- **核心目標**：
  1. **業務邏輯全面下沉至 `core`**：
     - 套件批量還原邏輯 (`cmd_restore` / `_restore_module_package`) 下沉至 `core.installer`。
     - Git 內部忽略規則維護 (`_generate_internal_gitignore`) 下沉至 `core.vfs`。
     - 全域 Help 格式化與指令聚合 (`_get_installed_module_commands` / `_print_global_help`) 下沉至 `core.contributes`，完整支援讀取 `contributes/core.json` 動態聚合各模組之真實子命令（包括 `server`、`dev`、`knowledge-db`、`agents-workflow`）。
     - 事件清冊查詢 (`cmd_event`) 統一由 `core event` 處理。
  2. **`yscb.py` 宿主入口極簡瘦身至 ~200-250 行**：
     - 保留私有 `.venv` 注入、環境變數與安全防偽 Token (`YSCB_HOST_DISPATCH_TOKEN`) 注入。
     - 僅保留最小自舉 `cmd_init`（在環境無任何模組時下載解壓 `core`）。
     - 實作純淨之雙管道派發路由（管道 A：進程內冷啟動派發；管道 B：熱派發轉發至 `server` 模組）。
     - 退出碼剛性透傳 (Exit Code Passthrough) 與模糊拼寫建議 (`difflib`)。
  3. **生態系相容性與回歸驗證**：確保所有既有 CLI 指令（含 `core`, `dev`, `server`, `knowledge-db`, `agents-workflow`）在瘦身後的 `yscb.py` 雙管道路由下 100% 正常運作。
- **邊界排除 (Explicitly Excluded)**：
  - 本次重構不破壞 CLI 對外參數契約與語意。
  - 保留 `*.local.json` 與 `.venv/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 業務下沉對齊微內核職責**：
  - 嚴格遵守微內核架構分層，宿主腳本 `yscb.py` 不應夾帶任何具體模組業務（套件下載解壓、Git 規則維護、全域 Help 手動迭代遍歷）。
  - 將還原與套件管理歸入 `core.installer`，全域 Help 與指令動態聚合歸入 `core.contributes`。
- **[P00:DR-02] 雙管道派發與極速路由**：
  - 管道 A (冷啟動)：若無在線 `server`，安全插入 `sys.path` 並以 `importlib` 呼叫模組之 `process(args)` 入口。
  - 管道 B (熱派發)：若 `server` 在線且非管理自循環指令，以極簡 HTTP POST `/api/dispatch` 串流接收 stdout/stderr 並即時印出，延遲達到 sub-50ms。
  - 雙管道均剛性保障退出碼 (Exit Code) 1:1 透傳給 Shell。
- **[P00:DR-03] 全域 Help 動態聚合引擎**：
  - `python yscb.py --help` 直接委託給 `core help` 派發。
  - 掃描各已安裝模組之 `contributes/core.json`（及 `manifest.json`），動態列出所有一級指令與二級子指令說明，形成生態系統一功能展示。

---

## 3. 開放議題與確認紀錄

- [x] **開放議題 1**：快取環境清空範疇？（已確認：清空 `.cache/`、`.mirror/`、`.snapshots/`、`__pycache__` 與所有 `*.local.json`，僅保留 `.venv/`）
- [x] **開放議題 2**：`@build` 自部署目標？（已確認：已全數完成 `core`, `server`, `dev`, `agents-workflow`, `knowledge-db` 的 `@build` 物化安裝）
- [x] **開放議題 3**：`yscb.py` 瘦身目標行數？（已確認：自 1100 行收斂至 200~250 行）
