# 實作任務清單 (Task Breakdown)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `agents_workflow/plans/status.py` 實作 `PlanStatusResolver`（FR-01、EC-01、EC-02）
- [x] **TASK-02**：重構 `scanner.py` 與 `archiver.py`，改以標頭狀態解析驅動，修正 handoff 刪除時序與 Research Track 判定（FR-02、FR-03、FR-04、FR-08、EC-04、EC-05、EC-07）
- [x] **TASK-03**：重構 `verifier.py`，實作調研檔放寬映射、正則收緊、動態佔位符推導與死代碼清理（FR-05、FR-06、FR-07、FR-09、EC-06、EC-09、EC-10）
- [x] **TASK-04**：編寫單元測試 `tests/test_plans_status.py` 覆蓋 FT-01 ~ FT-09
- [x] **TASK-05**：更新規範資產 `AgentsStandards.md`（指針改向指向 development-sop 佔位符、FP-03 更名）（FR-10、FR-11）
- [x] **TASK-06**：更新 7 大技能手冊 (`development-sop`, `new-plan`, `continue`, `auto`, `pause`, `research`, `context-init`)（FR-11 ~ FR-17、FR-19、FR-21 ~ FR-25）
- [x] **TASK-07**：更新 5 大標準模板 (`fast_track_plan`, `P07_walkthrough`, `revision_log`, `umbrella_overview`, `RXX_research_report`)（FR-18、FR-20、FR-22、FR-26）
- [x] **TASK-08**：更新貢獻宣告與導覽清冊 (`agents-workflow.json`, `_manifest.md`)（FR-27）
- [x] **TASK-09**：全文件原始碼自檢修復（F-01 ~ F-07：`handoff.md`、`phase_00_discuss.md`、`roadmap` 狀態與路徑、`author_guide_and_checklist.md` 去特化、`session-analysis` 廢除 Workflows 維度與 Mermaid 引號修復、模板 `workflow.docs://` 佔位符統一、CLI 權限燈號對齊）
- [x] **TASK-DOC**：更新知識庫文檔 (`docs/agents-workflow/README.md`, `DESIGN_NOTES.md`) 與全域 `CHANGELOG.md`

> Claude Opus 5.5

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-09 | Minor | 依開發者指示於 P06 階段執行 `assets/` 41 檔全文件自檢，發現 F-01~F-07 共 7 項跨檔殘留與佔位符細節並直接納入 `sub_01` 一併修正 | 已全數修正並通過單元測試與編譯核驗 |

> Claude Opus 5.5

