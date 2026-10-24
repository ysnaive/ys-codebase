# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (High)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-07` 在 API 規格書中有對應介面與文件章節
- [x] **邊界防護**：`EC-01` ~ `EC-05` 具備具體防禦降級與防吹毛求疵策略
- [x] **依賴純淨**：符合 `NFR-01` (Token 經濟性) 與 `NFR-02` (雙層編譯與相容性) 約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 增補 `testing-sop` 技能與 `TESTING_SOP_STANDARDS` 錨點說明 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 增補三支柱 Subagent 任務級上下文隔離協定與測試回歸守門指南 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `DN-15`：三支柱 Subagent 隔離協定與 Single-Writer 計畫檔保護契約 |
| **微觀註解** | `agents_workflow/roadmap.py` Docstring | Modify | 同步更新 `promote_roadmap` 函式註解與多路線圖追加合併規格 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄環境型測試技能 `testing-sop` 與 Subagent 三支柱隔離協定成果 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 Subagent 在執行編碼任務時修改了 `plans/` 下的 `P05_task.md` 或 `changelog.md`，該如何防範狀態機與模型紀錄損毀？  
> [*] **防護解法**：嚴格落實 Single-Writer 鐵律——主視窗在派發 Prompt 中明確標註「嚴禁建立或修改 `plans/` 下的任何檔案」；Subagent 僅回傳 5 行結構化狀態代碼，主視窗收到後原地統一寫入 `P05_task.md` 與伴隨 `changelog.md`。

> [?] **尖銳問題 2**：若 Phase 07 Step 1 派發之 Reviewer Subagent 開始回報主觀排版、型別命名偏好等瑣碎微調，是否會引發無限返工迴圈？  
> [*] **防護解法**：實施「防吹毛求疵（Anti-Nitpicking）」硬性邊界——限制 Reviewer Subagent 僅允許回報違反三類硬性契約（① 敷衍修補/測試反模式、② 需求/介面遺漏、③ 三層文檔未同步）；若無上述三類缺失，強制直接回傳 `REVIEW_STATUS: PASSED`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 [ACI-Roadmap]**：修改 `agents_workflow/roadmap.py` 補強 `RoadmapManager.promote_roadmap()`，支援目標目錄已存在 `roadmap.md` 時無損追加合併與移除原來源檔，並於 `tests/test_roadmap.py` 擴充單元測試 (`FR-07`, `ET-05`)。
2. **TASK-02 [Skill-Core]**：建立 `assets/skills/testing-sop/SKILL.md`（六大測試鐵律 + 自檢清單 + 錨點）與 `references/test_suite_audit_and_purification.md`（`T-01`~`T-06` 體檢模型與純化工作流）(`FR-01`, `FR-02`)。
3. **TASK-03 [Contributes-Export]**：於 `contributes/agents-workflow.json` 註冊 `testing-sop` 技能匯出與 `TESTING_SOP_STANDARDS` Token (`FR-01`)。
4. **TASK-04 [SOP-Standards-Hardening]**：更新 `assets/standards/AgentsStandards.md` 條件式技能路由表，並於 `phase_04_plan.md`、`phase_05_task.md`、`phase_06_test.md`（雙重守門）及 `plan_modes.md` 植入 `testing-sop` 強制連鎖引用 (`FR-03`)。
5. **TASK-05 [Delegation-Pillar1-Pillar2]**：於 `research/SKILL.md`、`discuss/SKILL.md`（支柱一：唯讀廣域探索）及 `auto/SKILL.md`、`phase_05_task.md`、`phase_06_test.md`（支柱二：序列實作、二振熔斷與 Single-Writer）內化委派協定 (`FR-04`, `FR-05`)。
6. **TASK-06 [Delegation-Pillar3-FreshEyes]**：於 `phase_07_walkthrough.md` Step 1 內化支柱三 Fresh-Eyes Review、Untracked 新檔防護與三類硬性審查契約 (`FR-06`)。
7. **TASK-DOC [Documentation-Sync]**：同步更新 `docs/agents-workflow/` 模組手冊、用戶指南與 `DESIGN_NOTES.md`，並更新 `test_plans_model_record.py` 技能預期清冊 (`FR-01`, `NFR-02`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全鏈路測試守門與 Subagent 內化成熟度**：
  不額外增加獨立 Subagent Skill 或外部依賴，透過現有 5 份技能與階段手冊內化三支柱委派，並與 `testing-sop` 形成雙層品質防護網。

