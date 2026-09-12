# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「我希望改在 config，預設 false， --console 作為強制開啟的可選附加 (通常 debug 用)」
- **核心目標**：
  1. 在 `server` 模組整合微內核組態管理機制 (`core.config`)，提供 `enable_console` 組態項，預設值為 `false`。
  2. 重構 `server start` 命令列參數解析與啟動分流決策：CLI 顯式旗標具備最高優先權（`--console` 強制開啟前台除錯，`--daemon` 強制背景脫鉤）；未指定時回退讀取 `core.config` 之 `enable_console` 設定。
  3. 保障單元測試覆蓋：針對 config 預設值、project/local 設定覆蓋、CLI 顯式參數覆蓋等所有組合撰寫嚴謹的自動化測試。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `server` 現有的 HTTP Master-Worker 架構與 IPC 派發協議。
  - 不引入第三方視窗管理器，維持純 Python 標準跨平台前台/背景進程原語。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 組態讀取選型與鍵名規範**：
  - 直接調用微內核 `core.config.get("server", "enable_console", False)`，支援 Local > Project 雙層合併與 `mtime` 快取自癒。
  - 鍵名統一宣告為 `enable_console: bool`，預設常數 `DEFAULT_ENABLE_CONSOLE: bool = False`。
- **[P00:DR-02] 啟動模式優先級決策矩陣 (Precedence Matrix)**：
  - 優先級 1 (最高)：CLI `--console` 顯式提供 $\rightarrow$ 強制前台 Console 模式 (`console = True`)。
  - 優先級 2：CLI `--daemon` 顯式提供 $\rightarrow$ 強制背景脫鉤模式 (`console = False`)。
  - 優先級 3：未提供 CLI 模式參數 $\rightarrow$ 依據 `core.config.get("server", "enable_console", False)` 之布林值決定。
- **[P00:DR-03] CLI 參數解析器重構防呆**：
  - 原先 `parser.add_argument("--daemon", action="store_true", default=True)` 導致預設值恆為 `True` 遮蔽 config。
  - 重構為 `default=None`（三態：`None` / `True`），使 CLI 能精確識別使用者是否顯式指定 `--daemon` 或 `--console`。

---

## 3. 開放議題與確認紀錄

- [x] **開放議題 1**：組態鍵名是否統一定義為 `enable_console`？（已確認：統一採用 `enable_console`）
- [x] **開放議題 2**：預設值是否為 `False`？（已確認：預設 `False` 走背景靜默脫鉤常駐）
- [x] **開放議題 3**：`--console` 行為是否為當前終端前台阻塞運行（除錯用）？（已確認：方便即時觀察 Log 與 Ctrl+C 結束）
