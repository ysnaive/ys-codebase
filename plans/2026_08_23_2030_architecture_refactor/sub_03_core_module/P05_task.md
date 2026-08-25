# 任務清單 (Task Breakdown)

> 功能名稱：核心微內核基礎設施模組 (Core Infrastructure Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 狀態：Completed
> 擴充項目：none
> 模板版本：v1.3

---

## 實作任務進度

- [x] **Task 1: 建立模組元數據與能力宣告**
  - 產出檔案：[`source/core/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/manifest.json)
  - 內容：宣告 `core@1.0.0`、進入點 `scripts/cli.py` 與基礎描述

- [x] **Task 2: 建立極簡語意上下文介面**
  - 產出檔案：[`source/core/core/context.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/context.py)
  - 內容：實作 `ExecutionContext(module_name, command, args)` 極簡資料模型

- [x] **Task 3: 建立語意 URI 系統與一級 VFS 檔案系統**
  - 產出檔案：[`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/uri.py)
  - 內容：實作 9 大通用協議解析、佔位符代換，以及一級 VFS 操作（`read/write_text`, `read/write_json`, `read/write_bytes`, `exists`, `is_file`, `is_dir`, `makedirs`, `remove`, `rmtree`, `listdir`, `copy`, `move` 等）

- [x] **Task 4: 建立 Contributes 聚合與依賴注入引擎**
  - 產出檔案：[`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/contributes.py)
  - 內容：實作 `ContributesAggregator` 5 大來源掃描與靜態注入

- [x] **Task 5: 建立 12 大原子操作引擎**
  - 產出檔案：[`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/engine.py)
  - 內容：實作 `AtomicEngine` 12 大原子行為（`act_download`, `act_delete`, `act_register`, `act_unregister`, `act_solve_deps`, `act_prepare`, `act_reload` 兩階段純淨物化, `act_fetch`, `act_snapshot`, `act_restore_snapshot`, `act_broadcast_event`）

- [x] **Task 6: 建立 7 大套件管理子指令**
  - 產出檔案：[`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/installer.py)
  - 內容：實作 `Installer` 高階管線（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`）

- [x] **Task 7: 建立模組對外 CLI 進入點**
  - 產出檔案：[`source/core/scripts/cli.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/scripts/cli.py)
  - 內容：實作 `main(argv)` 參數解析與派發

- [x] **Task 8: 建立套件頂層匯出**
  - 產出檔案：[`source/core/core/__init__.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/source/core/core/__init__.py)
  - 內容：匯出 `uri`, `ExecutionContext`, `AtomicEngine`, `ContributesAggregator`, `Installer`

---

## 品質與編譯驗證結果

- **語法編譯**：實機執行 `python -m py_compile` 驗證 `source/core/` 全部 7 個 Python 檔案，**100% 通過（0 Error / 0 Warning）**。
