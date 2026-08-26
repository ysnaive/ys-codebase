# 任務清單與實作追蹤 (Phase 5: Task Tracking)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 任務執行進度清單 (Task Checklist)

- [x] **TASK-01**：升級 `source/agents-workflow/config/config.project.json` 模板（`release_targets: ["antigravity"]`，保留 `enable_agents_md` 與 `enable_project_changelog`）。
- [x] **TASK-02**：在 `source/agents-workflow/manifest.json` 宣告 `release_target` (`antigravity`，包含 `projections` 與 Header 模板）。
- [x] **TASK-03**：重構 `source/agents-workflow/agents_workflow/compiler.py`，廢棄 `exports/`，實作 Stage 1 `cache.root://.../resolved_contents/` 中繼物化與 Stage 2 `resolve_stage2_uri` 三層重映射。
- [x] **TASK-04**：實作 `source/agents-workflow/agents_workflow/publisher.py`，包含發布拓撲映射、純文字/陣列 Header 巨集插值、4 步原子發布交易與 `AGENTS.md` 軟合併。
- [x] **TASK-05**：實作 `source/agents-workflow/agents_workflow/targets.py` 與更新 `source/agents-workflow/scripts/cli.py`，實裝 `release` 與 `release-target --list|--add|--remove`。
- [x] **TASK-06**：全面更新 `source/agents-workflow/assets/` 中所有 standards、workflows、templates 之路徑引用為 `__#{uri}__` 語意標籤。
- [x] **TASK-07**：更新 `source/agents-workflow/tests/test_compiler.py`，覆蓋 ST-01 ~ ST-08 測試案例並實機回歸驗證。

---

## 2. 實作偏差紀錄 (Deviation Logs)

| 任務編號 | 偏差等級 (Minor/Moderate/Major) | 偏差原因與具體內容 | 處置方式與對齊決策 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
