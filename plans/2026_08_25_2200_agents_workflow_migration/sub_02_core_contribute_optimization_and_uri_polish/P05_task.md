# 任務清單與進度追蹤 (Task Tracking)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據計畫：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：`Completed` (Phase 5 實作完畢)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Contributes `__provider__` 自動注入與拓撲排序)**：修改 `source/core/core/contributes.py` 之 `scan_and_inject()`，注入來源標記並按 Topological Order 排序合併。
- [x] **TASK-02 (微內核標準 Contribute 查詢 SDK)**：在 `source/core/core/contributes.py` 實作 `get()` 與 `get_for_current_module()`。
- [x] **TASK-03 (URI 系統 JIT 攔截、選單與 `--help` 清冊展開)**：修改 `source/core/core/uri.py`，定義 `UndefinedURIError` 並在 `uri.resolve()` 攔截提示。
- [x] **TASK-04 (自動持久化寫回、連鎖遞迴與熱刷新)**：實作 `reconcile_undefined_uri()`、設定檔寫回、連鎖遞迴解算與快取刷新。
- [x] **TASK-05 (單元測試套件與全系統回歸驗證)**：建立單元測試覆蓋 FT-01~08、ET-01~04，並實機執行 `dev test --all` (97/97 測試 100% Passed)。

---

## 2. 變更紀錄與進度追蹤 (Progress Notes)

- **2026-08-26**：初始化 Phase 5 任務清單，開始執行 TASK-01~TASK-05。
