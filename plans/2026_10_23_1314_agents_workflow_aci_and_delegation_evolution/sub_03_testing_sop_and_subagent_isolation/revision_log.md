# 修訂紀錄書 (Revision Log)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (High)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 對齊原始訴求：移除靜態預建之 `testing_guide.md`，統一交由 `/how-to-config-yscb` 探勘代寫
- **修訂類別**：Docs / Parameter
- **涉及檔案**：
  - `ys_codebase/config/agents-workflow/snippets/testing_guide.md` (Removed pre-baked static file)
  - `ys_codebase/config/agents-workflow/contribute.json`
  - `plans/2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_03_testing_sop_and_subagent_isolation/{P00_discuss.md,P01_requirements_spec.md,P07_walkthrough.md}`
- **修訂摘要**：對照 `sub_03/roadmap.md` §1.2 第 3 點原始訴求，`agents-workflow` 僅負責預留 `TESTING_SOP_STANDARDS` 錨點，而專案專屬之 `config://agents-workflow/snippets/testing_guide.md` 應由 `/how-to-config-yscb` 於實機探勘專案測試框架後草擬、經開發者確認後代寫，不應於開發階段靜態預建導致 `/how-to-config-yscb` 誤觸全綠短路。已移除預建之靜態檔案與掛載項，並同步修正 `P00`、`P01`、`P07` 規格表述。
- **驗證結果**：`python yscb.py contributes check` 與 `python yscb.py agents-workflow plan verify sub_03_testing_sop_and_subagent_isolation` 100% Passed。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

