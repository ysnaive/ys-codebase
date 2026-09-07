# 需求規格說明書 (Requirements Specification)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 套件還原與環境自愈下沉至 core | 將 `cmd_restore` / `_restore_module_package` 下沉至 `core.installer.Installer.cmd_restore`；將 `_generate_internal_gitignore` 下沉至 `core.installer` / `core.vfs`，在 restore / reload / install 時自動維護忽略規則。 | P0 | [P00:DR-01] |
| **FR-02** | 全域 Help 動態聚合引擎 | 在 `core.contributes` 與 `core.scripts.cli` 實作 `cmd_help` / `print_global_help()`，完整讀取已安裝模組之 `contributes/core.json` 與 `manifest.json`，動態聚合並排版展示全模組一二級命令。 | P0 | [P00:DR-01, DR-03] |
| **FR-03** | yscb.py 宿主入口瘦身至 200~250 行 | 徹底精簡 `yscb.py`，僅保留環境變數注入 (`YSCB_HOST_DIR`、`PYTHONUNBUFFERED=1`)、私有 `.venv` 探測注入、安全防偽標記 (`YSCB_HOST_DISPATCH_TOKEN`) 與最小自舉 `init`。 | P0 | [P00:DR-02] |
| **FR-04** | 雙管道派發路由與 Exit Code 透傳 | 實作雙管道路由：<br/>• **管道 B (熱派發)**：若常駐 `server` 在線且非自循環管理指令，透過 HTTP POST `/api/dispatch` 串流接收 stdout/stderr 並即時印出。<br/>• **管道 A (冷啟動)**：若 `server` 離線或熱派發失敗，安全動態載入模組 `scripts/cli.py` 呼叫 `process(args)`。<br/>• 雙管道皆 1:1 透傳 Exit Code 給作業系統 Shell。 | P0 | [P00:DR-02] |
| **FR-05** | 智慧模糊拼寫建議與說明代理 | 未知命令時調用標準庫 `difflib.get_close_matches` 給出最相近命令建議並回傳 exit code 1；`--help` 或無參數時直接委託派發至 `core help`。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Server 常駐進程崩潰、連線超時或回傳非預期格式 | 熱派發通道捕捉所有異常，透明無感降級 (Fallback) 至管道 A (本地冷啟動進程內執行)，絕不中斷用戶操作。 |
| **EC-02** | 未初始化環境執行模組指令或 --help | 提示 `[yscb] Error: Environment not initialized. Please run 'python yscb.py init <yscbRoot>' first.`，並回傳 exit code 1。 |
| **EC-03** | 呼叫尚未安裝之模組指令 | 提示未安裝並給予模糊拼寫建議 (若有相近模組或指令)，引導用戶執行 `python yscb.py install <module>`。 |
| **EC-04** | 目標模組既無 process(args) 亦無 main(args) | 拋出明確 `AttributeError` 提示規格不合規，回傳 exit code 1。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 代碼體積約束 | `yscb.py` 實體代碼行數嚴格控制在 200 ~ 250 行區間（上限不超過 260 行）。 |
| **NFR-02** | 零第三方依賴 | `yscb.py` 100% 使用 Python 標準庫，在尚未安裝任何第三方套件前可單檔自舉運作。 |
| **NFR-03** | 效能指標 | 熱轉發管道下 CLI 響應時間達成 sub-50ms；冷啟動保留既有秒級以內水準。 |
| **NFR-04** | 回歸相容性 | 5 大既有模組（`core`, `dev`, `server`, `knowledge-db`, `agents-workflow`）所有既有 CLI 語意 100% 保持向後相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]` 剛性防偽 Token 注入**：`yscb.py` 在調用管道 A 或管道 B 前，必須確保注入 `os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"`，否則各模組由 `core.guard.guard_dispatch` 守門時會拋出 `PermissionError` 拒絕執行。
- **`[!CAUTION]` Server 自循環死鎖防護**：派發目標若為 `server` 模組本身（如 `server stop`, `server reload`, `server start`），絕對禁止走管道 B 熱派發，必須強制直通管道 A 冷啟動，防範對自身的請求造成死鎖或在關閉過程中掛死。
