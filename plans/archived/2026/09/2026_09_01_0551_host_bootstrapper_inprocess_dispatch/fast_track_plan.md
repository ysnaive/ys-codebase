# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：宿主引導腳本同進程動態調度優化 (Host Bootstrapper In-Process Dispatch Optimization)  
> 建立日期：2026-09-01  
> 所屬主計畫：無 (獨立 Level 0 敏捷計畫)  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  - 目前 [yscb.py](file:///workspace/ys-codebase/yscb.py#L448-L483) 中的 `dispatch_module` 使用 `subprocess.run` 派發子程序，在非交談式/後台 Headless 環境下容易因 `stdin` 管道未關閉及多層進程冷啟動造成 I/O 阻塞或延遲。
  - 改用 Python 內建 `runpy.run_path` 進行同進程動態調度（In-Process Dispatch），在派發模組時動態設定 `sys.argv`、注入 `YSCB_HOST_DIR` 並精確捕獲 `SystemExit` 與異常，實現零子進程開銷與即時響應。
- **影響範圍**：
  - 專案根目錄 [yscb.py](file:///workspace/ys-codebase/yscb.py) 之 `dispatch_module` 函式。
  - 不更動任何 Public API 簽名與模組接口。

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 [yscb.py](file:///workspace/ys-codebase/yscb.py) 引入 `runpy`，重構 `dispatch_module` 實作同進程調度邏輯，包含 `sys.argv` 現場維護、`SystemExit` 狀態碼轉譯與健全例外處理。
- [x] **TASK-02**：實機測試全模組 CLI 指令（`agents-workflow plan status`、`core status`、`knowledge-db status` 等）與未註冊指令拼寫建議，驗證秒級響應與 0 阻塞。
- **測試案例**：
  - `FT-01`：`python3 yscb.py agents-workflow plan status` 驗證即時輸出並返回 0。
  - `FT-02`：`python3 yscb.py core status` / `knowledge-db status` 驗證各模組 CLI 正確解析。
  - `ET-01`：未註冊指令拼寫建議與非 0 狀態碼捕獲（例如 `python3 yscb.py relod` 輸出建議並返回 1）。
  - `RT-01`：既有 `test_cli_help.py` 單元測試全數通過。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於 [yscb.py](file:///workspace/ys-codebase/yscb.py#L470-L495) 將 `dispatch_module` 升級為 `runpy.run_path(target_cli, run_name="__main__")` 同進程分發機制，妥善維護 `sys.argv` 現場並捕捉 `SystemExit` 狀態碼。
- **實機測試日誌**：
  - `FT-01` (Plan Status)：`python yscb.py agents-workflow plan status` 於 0.8s 內同步完成並輸出矩陣，狀態碼 0。
  - `FT-02` (Core / Knowledge-DB Status)：`python yscb.py status` 輸出 HEALTHY (100% Ready)；`python yscb.py knowledge-db status` 輸出摘要，狀態碼皆為 0。
  - `ET-01` (Spelling Suggestion & Exit Code)：`python yscb.py relod` 正確提示 `Did you mean 'reload'?` 並返回 1。
  - `RT-01` (Unit Tests)：`dev test core` 54/54 Passed (0.22s)；`dev test agents-workflow` 47/47 Passed (3.46s)。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **文檔與日誌交付**：同步追加 [CHANGELOG.md](file:///workspace/ys-codebase/CHANGELOG.md) 變更摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_01_0551_host_bootstrapper_inprocess_dispatch` 驗證 100% Passed。
- **結案狀態**：`Completed`
