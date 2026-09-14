# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`knowledge_db/embedding.py` 實作本地探針 `is_model_downloaded`、`_init_model` 平滑靜默降級與 `[GUARD]` 引導輸出、`download_model` 顯式預載。
- [x] **TASK-02**：`knowledge_db/engine.py` 擴充 `status(scan=True)` 與 `model_*` 介面。
- [x] **TASK-03**：`contributes/core.json` 徹底移除 `scan`/`bundle`，新增 `model` 指令群組，擴充 `status` 與 `index` 選項。
- [x] **TASK-04**：`scripts/cli.py` 移除 `scan`/`bundle` 進入點，實作 `model` 路由與處理函式，擴充 `status` 差異比對與 `index` 導出。
- [x] **TASK-05**：`tests/test_cli.py` 升級測試套件覆蓋 FT-01 ~ FT-06、ET-01 與 RT-01。
- [x] **TASK-DOC**：同步更新 `docs/knowledge-db/README.md`、`retrieval.md` 與 `DESIGN_NOTES.md` (`[DN-25]`)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
