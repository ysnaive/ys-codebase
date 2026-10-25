# 實作任務清單 (Task Breakdown)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：升級 `verifier.py` 實作確定性標頭自癒、章節缺失率分流與下一階段預告（詳見 P04 §4）
- [x] **TASK-02**：更新 `scripts/cli.py` 輸出 `[SELF-HEAL]` 標頭自癒與 `[NEXT PHASE GATE]` 提示（詳見 P04 §4）
- [x] **TASK-03**：重構 `auto/SKILL.md`（$\le 75$ 行）與 `development-sop/SKILL.md` 落實兩階段 JIT 讀模板（詳見 P04 §4）
- [x] **TASK-04**：更新 `test_plans_toolchain.py` 與 `test_initializer.py` 並通過 133/133 沙盒測試與發布（詳見 P04 §4）
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/{user_guide.md,DESIGN_NOTES.md}` 新增 `[DN-AW-16]`（詳見 P04 §4）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

