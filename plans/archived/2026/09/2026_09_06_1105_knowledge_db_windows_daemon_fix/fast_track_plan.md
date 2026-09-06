# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge-db Windows 守護進程啟動失敗、進程誤殺與降級架構清理  
> 建立日期：2026-09-06  
> 所屬主計畫：無  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界

#### 4 大剛性守門檢驗
1. **代碼修改行數**：預估修改約 50 行，實際修改 79 行（$\le 100$ 行，合規）。
2. **Public API 簽名契約**：`is_pid_alive`、`stop`、`get_cache_dir` 等所有介面簽名 0 變更（合規）。
3. **零跨模組新依賴**：使用 Python 內建標準庫 `ctypes`，無引入任何第三方新依賴（合規）。
4. **既有單元測試套件守門**：涵蓋 `test_hot_reload_server.py`、`test_hot_reload.py` 等 15 個測試套件（合規）。

#### 架構決策與需求描述 (Architecture Decisions)
遵循開發者最高架構準則「**yscb.py 為唯一入口，完全刪除降級回補**」：
1. **Windows `os.kill(pid, 0)` 語意陷阱修復**：在 Windows 平台改用原生 Win32 API (`kernel32.OpenProcess` + `kernel32.GetExitCodeProcess`) 探測進程存活，改用 `kernel32.TerminateProcess` 終止進程，徹底杜絕跨控制台發送 Ctrl+C 導致的 Detached Process 崩潰 (WinError 87) 與控制台廣播誤殺 (`KeyboardInterrupt`)。
2. **貫徹 yscb.py 唯一入口原則，禁止 _modules_root 注入**：不於各模組內部自行手寫 `_modules_root` 尋找邏輯；背景進程啟動時剛性限定透過 `yscb.py` 入口分發，確保環境標準一致。
3. **完全刪除 get_cache_dir 降級回補**：徹底移除 `get_cache_dir` 內部的降級備用候選搜尋與 `root / ".cache"` 兜底；由 `core.uri.resolve("cache://knowledge-db")` 作為唯一真理來源，解析失敗直接報錯，杜絕在根目錄盲目自建 `.cache` 污染版控。
4. **背景進程日誌即時 Flush**：引入 `FlushingFileHandler`，於每筆日誌 `emit` 後即時 `flush()`，防止背景進程異常退出時日誌緩衝遺失。

#### 影響範圍
- `ys_codebase/source/knowledge-db/knowledge_db/daemon.py`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 `daemon.py` 中，針對 Windows 平台改以 `ctypes` 調用 `kernel32.OpenProcess` + `GetExitCodeProcess` 實作 `is_pid_alive`；在 `stop()` 中使用 `TerminateProcess`。
- [x] **TASK-02**：在 `daemon.py` 的 `get_cache_dir` 中，完全刪除降級候選搜尋與 root 兜底，剛性收斂為 `core.uri.resolve("cache://knowledge-db")`。
- [x] **TASK-03**：在 `daemon.py` 的背景進程啟動中，強制要求以 `yscb.py` 為唯一入口，刪除退回調用 `cli.py` 之非標準路徑。
- [x] **TASK-04**：在 `daemon.py` 的 `_setup_logger` 引入 `FlushingFileHandler`。
- **測試案例**：
  - `FT-01`：`test_hot_reload_server.py` 單元測試全數通過，不再因 `os.kill` 觸發 `KeyboardInterrupt`。
  - `FT-02`：Windows 守護進程啟動、狀態查詢與停止驗證。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - **TASK-01 完成**：在 `daemon.py` 中針對 Windows 平台全面切換為 Win32 原生 API (`kernel32.OpenProcess` 搭配 `GetExitCodeProcess` 判斷 `STILL_ACTIVE = 259`；`kernel32.TerminateProcess` 停止進程)，徹底根絕控制台 Ctrl+C 廣播與 Detached 進程崩潰。
  - **TASK-02 完成**：在 `get_cache_dir` 中刪除所有降級候選搜尋清單與 `root / ".cache"` 兜底，剛性收斂為 `core.uri.resolve("cache://knowledge-db")`。
  - **TASK-03 完成**：背景守護進程啟動強制以 `yscb.py` 為唯一入口分發，移除調用 `cli.py` 的旁路分支。
  - **TASK-04 完成**：引入 `FlushingFileHandler`，在每次 `emit` 後即時 `self.flush()`。
  - **模板同步**：補齊 `configurable/config.local.json` 模板檔案。
- **實機測試日誌**：
  - `python yscb.py dev check knowledge-db`：100% Passed。
  - `python yscb.py dev test knowledge-db --quiet`：`Pass: 148(100.0%), Fail: 0, Skip: 0`，全生態系單元與邊界測試 100% 通過，0 錯誤 0 中斷。
  - 變更統計：`source/knowledge-db/knowledge_db/daemon.py` 修改 79 行（$\le 100$ 行守門合規）。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md` `[DN-17]`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_06_1105_knowledge_db_windows_daemon_fix` 驗證 100% Passed。
- **結案狀態**：`Completed`
