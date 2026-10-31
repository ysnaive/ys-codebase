# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_04_knowledge_db_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `io_utils.py` 並重構 `config.py`、`schema.py`、`tokenizer.py`、`space.py` (`M-01, M-03, M-05, M-07, F-07, F-08`)
- [x] **TASK-02**：重構 `scanner.py` 與 `parsers/` (`registry.py`, `treesitter.py`, `spice_parser.py`) (`M-02, M-04, F-05, F-09`)
- [x] **TASK-03**：重構 `retrieval.py`、`graph.py`、`linker.py`、`embedding.py`、`bundler.py` (`M-06, M-10, F-02, F-04, F-06, F-09`)
- [x] **TASK-04**：建立 `topology_query.py` 並重構 `pipeline.py`、`engine.py`、`service.py` (`M-08, M-09, F-01`)
- [x] **TASK-05**：重構 `formatter.py`、`scripts/cli.py` 與 `scripts/hook.server.py` (`M-10, F-03`)
- [x] **TASK-06**：同步更新 `tests/` 測試案例並通過 `python -m py_compile` 靜態語法檢查 (`[P01:DR-01]`, `[P04:DR-02]`)
- [x] **TASK-07**：完成 `R02` 審查收斂（修復 `resolve_threads` SSOT、`_resolve_config_uri`、`context_lines` 透傳與 `Mode A` 殘留清除）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
