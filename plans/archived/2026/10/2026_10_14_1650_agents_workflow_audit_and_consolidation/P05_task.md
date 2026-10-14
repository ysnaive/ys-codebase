# 實作任務清單 (Task Breakdown)

> 功能名稱：2026_10_14_1650_agents_workflow_audit_and_consolidation  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：基礎建設與 Token 清理（刪除 `providers.py`，更新 `contributes/agents-workflow.json` 收斂至 ~15 個 Token，同步 `contributes/_manifest.md`）
- [x] **TASK-02**：共用模組提取與 CLI 修正（於 `plans/__init__.py` 抽取 `_resolve_uri_path`，統一 fallback 為 `plans/archived`，修正 `cli.py` 之 `plan_search` 選項提取）
- [x] **TASK-03**：模板標頭新增 `> 模型：[模型名稱]` 與 6 大非 Phase 模板 HTML 註解清除純淨化
- [x] **TASK-04**：`new-plan/SKILL.md` 輕量化重構，廢除 `DEVELOPMENT_STANDARDS` 雙重注入並修復 15 處超連結斷鏈，修復各 Skills 指向與雙斜線
- [x] **TASK-05**：Review 內化併回 P07（刪除 `review_gate.md`，重構 `phase_07_walkthrough.md`、`P07_walkthrough.md`、`phase_06_test.md`、`auto/SKILL.md`、`plan_modes.md` 等）
- [x] **TASK-06**：`PlanVerifier` 與核心工具鏈代碼升級（`has_model` 檢查、佔位符攔截、移除歸檔計畫掃描、未勾選 Checkbox 阻斷）
- [x] **TASK-07**：單元測試更新與驗證（更新 `test_plans_toolchain.py`、`test_compiler.py`，跑通全生態系測試）
- [x] **TASK-DOC**：文檔對齊（`docs/agents-workflow/README.md`、`docs/agents-workflow/DESIGN_NOTES.md` 登記 `[DN-AW-15]`）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
