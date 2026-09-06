# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge-db 守護進程 Server Console 開啟選項支援  
> 建立日期：2026-09-06  
> 所屬主計畫：無  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  在 `knowledge-db` 組態與啟動管線中，新增 `enable_server_console` 選項（預設為 `False`，不開啟）。
  - 當為 `False`（預設）：守護進程以隱藏背景模式常駐運行（Windows WMI 託管 / Detached），無控制台彈窗干擾。
  - 當為 `True`（或 CLI 帶有 `--console`）：在 Windows 下拉起獨立可見之 Console 視窗，即時輸出守護進程之啟動與熱修補日誌，方便開發者即時觀測。
- **影響範圍**：
  - `source/knowledge-db/knowledge_db/config.py`
  - `source/knowledge-db/knowledge_db/daemon.py`
  - `source/knowledge-db/scripts/cli.py`
  - `config/knowledge-db/config.local.json`
  - `source/knowledge-db/tests/test_hot_reload_server.py`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 `KnowledgeDBConfig` 中新增 `enable_server_console`（預設值 `DEFAULT_ENABLE_SERVER_CONSOLE = False`），並於 `load()` 實作嚴格型態防禦解析（支援 `enable_server_console` 與 `hot_reload_server_console` 鍵名）。
- [x] **TASK-02**：在 `daemon.py` 的 `ensure_running()` 中新增 `enable_console: Optional[bool] = None` 參數；若為 `True` 則在 Windows 下透過 `Start-Process` 拉起可見 Console 視窗，若為 `False` 則維持隱藏背景模式。
- [x] **TASK-03**：在 `cli.py` 的 `daemon start` 子命令中支援 `--console` 與 `--no-console` 覆寫參數；於 `config.local.json` 顯式配置 `"enable_server_console": false`。
- [x] **TASK-04**：在 `tests/test_hot_reload_server.py` 增設 `FT-23` 測試案例，覆蓋組態解析與 `enable_console` 啟動分流，全量測試 100% 通過。
- **測試案例**：`FT-23` (enable_server_console 組態防禦與啟動分流驗證)

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `KnowledgeDBConfig` 新增 `enable_server_console: bool = False`，支援字串 ("true"/"false"/"1"/"0") 與別名 `hot_reload_server_console` 解析。
  2. `daemon.py` 實作 `resolve_console_enabled` 與 `ensure_running(enable_console=...)`，支援 Windows `Start-Process` 可見視窗與 WMI 隱藏背景雙模式。
  3. `cli.py` 在 `daemon start` 支援 `--console` 與 `--no-console` 覆寫旗標。
  4. `config.local.json` 顯式配置 `"enable_server_console": false`。
  5. `tests/test_hot_reload_server.py` 新增 `FT-23` 測試套件。

- **實機測試日誌**：
  - 執行 `python yscb.py dev test knowledge-db`：
    `Summary : 160 Total, 160 Passed, 0 Failed, 0 Skipped (19.139s)`
    `Status  : PASSED (100% Ready)`
  - 執行 `python yscb.py install knowledge-db@build` 安裝成功。
  - 驗證 `daemon start` (預設不開視窗) 與 `daemon start --console` (可見視窗模式) 分流正常。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：微觀註解、`DESIGN_NOTES.md` 對齊，測試 100% 通過。
- [x] **日誌與發布交付**：追加 `changelog.md`。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證合規。
- **結案狀態**：`Completed`
