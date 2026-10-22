# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-18  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在架構與規格書中有 1:1 對應資產檔案與變更規則
- [x] **邊界防護**：EC-01 ~ EC-04 有具體防禦策略（保留 `P04 §4` 標題相容 `sub_01`、移除 `P00 §3` 預設 `- [ ]`）
- [x] **依賴純淨**：符合 NFR-01（零雙重路由膨脹）與 NFR-02（測試與 `plan verify` 100% 守門）指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_02` 流程閉環與提示詞優化摘要 |
| **模組手冊** | `docs/agents-workflow/README.md` | 免更 | 本次為內部模板與 Skill 流程提示詞精進，模組頂層架構與 CLI 用法不變 |
| **專題手冊** | `docs/agents-workflow/author_guide_and_checklist.md` | Modify | 同步對齊三層 5 列文檔表與標頭預設狀態說明 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | 免更 | 遵循 DN 防膨脹守門，本次無反直覺工程妥協，不新增 DN 條目 |
| **微觀註解** | 源碼 Public API Docstring 與測試註解 | Modify | 新增單元測試函式具備清晰驗證目標 Docstring |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：修改 `assets/templates/P04_implementation_plan.md` 與 `P07_walkthrough.md` 時，是否會導致同主計畫下已完成的 `sub_01_workflow_audit_remediation` 在執行 `plan verify` 時失敗？  
> [*] **防護解法**：`PlanVerifier.get_resolved_template_headers()` 僅比對 `##` 與 `###` 標題文字（忽略表格內容與清單格式）。我們嚴格保持 `P00`、`P01`、`P03`、`P04`、`P07`、`fast_track_plan`、`revision_log` 的所有 `##` / `###` 標題文字 100% 不變（見 `[P01:DR-01]` 與 `[P02:DR-01]`），僅調整章節內部的表格列與清單項目，因此 `sub_01` 與 `sub_02` 在執行 `plan verify` 時均能 100% 通過。

> [?] **尖銳問題 2**：在 `templates/P00_discuss.md` 將 §3 預設 `- [ ]` 改為 `- ` 後，若某些計畫在 `P00` 確實有開放議題需要 `- [ ]` 怎麼辦？  
> [*] **防護解法**：`P00` 處於 `Discussing` 時允許使用 `- [ ]` 列出待確認問題，定稿轉為 `Confirmed` 時勾選為 `- [x]`；而對於立項即收斂無開放議題之計畫，模板預設 `- 無待決開放議題` 可避免殘留空 `- [ ]` 在未來歸檔或狀態變更時誤觸未勾選錯誤。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：更新 `ys_codebase/source/agents-workflow/assets/templates/` 下 9 份標準模板（`P00_discuss.md`、`P01_requirements_spec.md`、`P03_api_spec.md`、`P04_implementation_plan.md`、`P07_walkthrough.md`、`fast_track_plan.md`、`revision_log.md`、`roadmap.md`、`changelog.md`），落實 `FR-04`、`FR-05`、`FR-07`、`FR-08` 與 `EC-01` ~ `EC-04`。
2. **TASK-02**：更新 L0/L1 全域治理與入口技能資產（`assets/standards/AgentsStandards.md`、`assets/skills/context-init/SKILL.md`、`assets/skills/yscb-cli-guild/SKILL.md`、`assets/skills/new-plan/SKILL.md`、`assets/skills/research/SKILL.md`、`assets/skills/roadmap/SKILL.md`），落實 `FR-01`、`FR-04`、`FR-08`。
3. **TASK-03**：更新 L2/L3 核心 SOP 與流程控制技能資產（`assets/skills/development-sop/SKILL.md`、`references/plan_modes.md`、`references/phase_00_discuss.md`、`references/phase_01_requirements.md`、`references/phase_03_api_spec.md`、`references/phase_07_walkthrough.md`、`assets/skills/pause/SKILL.md`、`assets/skills/continue/SKILL.md`、`assets/skills/discuss/SKILL.md`、`assets/skills/auto/SKILL.md`、`assets/skills/session-analysis/SKILL.md`），落實 `FR-02`、`FR-03`、`FR-04`、`FR-05`、`FR-06`、`FR-08`。
4. **TASK-04**：於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 擴充單元測試驗證 `FR-01` ~ `FR-08` 並更新 `docs/agents-workflow/author_guide_and_checklist.md`，執行 `dev check`、`dev test` 與 `@build` 部署驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 `P04_implementation_plan.md` 與 `P06_test_plan.md` 同步定稿為 `Confirmed`；所有資產變更嚴格於 `ys_codebase/source/agents-workflow/` 進行，並透過自動化單元測試驗證模板與技能內容合規性。

