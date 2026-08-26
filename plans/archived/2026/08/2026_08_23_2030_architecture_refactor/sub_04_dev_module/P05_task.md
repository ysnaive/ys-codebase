# 任務清單 (Task Breakdown)

> 功能名稱：開發者工具模組 (Dev Developer Tools Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 狀態：Completed
> 擴充項目：none
> 模板版本：v1.3

---

## 實作任務進度

- [x] **Task 1: 建立模組元數據與依賴宣告**
  - 產出檔案：[`source/dev/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/manifest.json)
  - 內容：宣告 `dev@1.0.0`、依賴 `core@>=1.0.0` 與進入點 `scripts/cli.py`

- [x] **Task 2: 建立模組腳手架產生器**
  - 產出檔案：[`source/dev/dev/scaffold.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/dev/scaffold.py)
  - 內容：實作 `Scaffolder`（模組名稱合法識別碼校驗、一鍵生成 `manifest.json`, `scripts/cli.py`, `<mod>/__init__.py`, `tests/test_basic.py`, `.yscbignore`）

- [x] **Task 3: 建立規範合規檢查器**
  - 產出檔案：[`source/dev/dev/checker.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/dev/checker.py)
  - 內容：實作 `Checker`（`manifest` 格式檢查、進入點檢查、全量 Python AST 語法靜態解析與路徑封裝檢查）

- [x] **Task 4: 建立純淨建置發布工具**
  - 產出檔案：[`source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/dev/builder.py)
  - 內容：實作 `Builder`（前置 `check` 守門、讀取 `.yscbignore` 與全域黑名單雙層過濾、純淨輸出 `build/<mod>/`）

- [x] **Task 5: 建立套件頂層匯出**
  - 產出檔案：[`source/dev/dev/__init__.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/dev/__init__.py)
  - 內容：匯出 `Scaffolder`, `Checker`, `Builder`

- [x] **Task 6: 建立模組對外 CLI 進入點**
  - 產出檔案：[`source/dev/scripts/cli.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/dev/scripts/cli.py)
  - 內容：實作 `main(argv)` 分發 `create`, `check`, `build` 及 `--all`, `--clean`, `--desc` 參數

---

## 品質與編譯驗證結果

- **語法編譯**：實機執行 `python -m py_compile` 驗證 `source/dev/` 全部 Python 檔案，**100% 通過（0 Error / 0 Warning）**。
