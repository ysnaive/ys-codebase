# 實作任務清單 (Task Breakdown)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (資產分拆)**：為 4 大核心模組建立 `contributes/<target>.json` 檔案
  - [x] `source/core/contributes/core.json`
  - [x] `source/core/contributes/agents-workflow.json`
  - [x] `source/dev/contributes/core.json`
  - [x] `source/dev/contributes/agents-workflow.json`
  - [x] `source/knowledge-db/contributes/core.json`
  - [x] `source/agents-workflow/contributes/core.json`
  - [x] `source/agents-workflow/contributes/agents-workflow.json`
- [x] **TASK-02 (Manifest 瘦身)**：自 4 大核心模組之 `manifest.json` 徹底移除 `"contributes"` 區塊
  - [x] `source/core/manifest.json`
  - [x] `source/dev/manifest.json`
  - [x] `source/knowledge-db/manifest.json`
  - [x] `source/agents-workflow/manifest.json`
- [x] **TASK-03 (Core 聚合引擎重構)**：重構 `source/core/core/contributes.py`，僅掃描 `contributes/<target>.json` 與 `config://`
- [x] **TASK-04 (Core 消費端收斂)**：
  - [x] `source/core/core/providers.py` (移除 `module.source://`，改調用 SDK)
  - [x] `source/core/core/engine.py` (改調用 SDK)
- [x] **TASK-05 (Knowledge-DB 消費端收斂)**：重構 `source/knowledge-db/knowledge_db/space.py` (改調用 SDK，廢除手寫掃描與 `origin`)
- [x] **TASK-06 (Agents-Workflow 消費端收斂)**：重構 `source/agents-workflow/agents_workflow/compiler.py` (改調用 SDK，廢除手寫掃描與 `module.source://`)
- [x] **TASK-07 (單元測試與全系統驗證)**：更新 `source/core/tests/test_contributes.py` 並更新各模組關聯測試

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
