# 任務執行與進度追蹤 (Task Progress & Tracking)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據計畫：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：Implementing  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 實作任務進度清單 (Task Checklist)

- [x] **TASK-01**：重構 [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py)
  - [x] 實作 `ExecutionContext` 凍結資料類別
  - [x] 實作 `project://` 顯式配置解算（讀取 `config/core/config.project.json` 之 `project_root`，未定義拋出 `ValueError`，無 fallback）
  - [x] 更新 `config.root://` ➔ `yscb://config/`，`config://` ➔ `yscb://config/{module}/`
  - [x] 打通 `contributes.merged.json` 之動態 URI 協議 (`type: "config"` / `"const"`) 與自訂佔位符 handler 解析
- [x] **TASK-02**：更新 [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py)
  - [x] 實作 `_seed_or_update_config`（全新複製、已存在時遞迴原地補齊缺失鍵）
  - [x] 實作 `act_broadcast_event`（動態掃描 `hook.{emit_module}.py`，傳入 Context，try-except 例外隔離）
- [x] **TASK-03**：更新 [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py)
  - [x] 於 `cmd_install`, `cmd_update`, `cmd_reload` 流程串接組態自動分發與事件廣播
  - [x] 移除 `source/core/config.project.json` 與 `modules/core/config.project.json`，維護模組空間純淨度
- [x] **TASK-04**：更新 [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests) 標準測試套件
  - [x] 更新 `test_uri.py`（驗證 `project://` 顯式解析與未定義拋錯阻斷、`config/` 新協議）
  - [x] 更新 `test_engine.py`（驗證 `hook.{emit_module}.py` 命名空間廣播、例外隔離、組態增量補齊）
  - [x] 更新 `test_installer.py`（驗證安裝時組態自動種入與補齊）
- [x] **TASK-05**：同步更新主計畫白皮書調研報告（`R01`~`R04`）
  - [x] 回填 `hook.{emit_module}.py` 命名空間規範
  - [x] 回填顯式 `config/` 目錄協議規範
  - [x] 回填 `project://` 顯式無 Fallback 約束與增量組態補齊規範

---

## 2. 實作過程偏差紀錄 (Deviation Log)

| 時間戳記 | 偏差等級 | 涉及檔案 | 偏差內容與原因說明 | 處置方式 |
| :--- | :---: | :--- | :--- | :--- |
| *(暫無偏差)* | - | - | - | - |
