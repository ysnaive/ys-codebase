# 實作計畫與交叉驗證書 (Implementation Plan)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求覆蓋度**：`P01` 之 `FR-01` ~ `FR-05`、`EC-01` ~ `EC-04`、`NFR-01` ~ `NFR-02` 已 100% 映射至 `P02` 架構與 `P03` 介面契約。
- [x] **向下相容性**：`get_resolved_template_headers()` 保持原回傳型別 `List[str]`，新增 `get_resolved_template_header_specs()` 回傳 `List[Tuple[str, str]]`，確保既有調用端無損相容。
- [x] **零臆測與模型紀律保護**：確定性標頭自癒僅修補 `功能名稱`、`建立日期`、`所屬主計畫`，絕不偽造 `模型` 或 `狀態`。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 目標文檔路徑 | 預計更新內容 |
| :--- | :--- | :--- |
| **模組導覽 (`<Category>/README.md`)** | `docs/agents-workflow/README.md` | 檢視確認架構圖與 CLI 概覽與現行一致（免改動或微調）。 |
| **專題手冊 (`[topic].md`)** | `docs/agents-workflow/user_guide.md` | 更新 `plan verify` 診斷報告說明（新增確定性標頭自癒、`QUICK_PATCH`/`FULL_REWRITE` 缺失率分流與 `NEXT PHASE GATE` 前瞻提示）。 |
| **防坑指南 (`DESIGN_NOTES.md`)** | `docs/agents-workflow/DESIGN_NOTES.md` | 新增 `[DN-AW-16]` 記錄 `/auto` 兩階段 JIT 讀模板防壓縮失憶機制與 `PlanVerifier` 缺失率分流處方設計。 |
| **微觀程式碼註解 (Docstrings)** | `verifier.py`, `cli.py` | 為新增之公開與內部方法補齊 Google-style Docstrings 與型別標註。 |
| **根目錄變更日誌 (`CHANGELOG.md`)** | `CHANGELOG.md` | 主計畫收官時統一記錄，本子計畫維護 `sub_09/changelog.md` 與主計畫 `changelog.md`。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

1. **問：若 Agent 在寫 `P05_task_auto.md` 時，頂部寫了 `> 計畫：sub_09`（而非 `> 功能名稱：`），確定性標頭自癒會如何處理？**  
   **答**：`parse_plan_header` 發現缺少 `功能名稱`、`建立日期`、`所屬主計畫` 時，`_auto_heal_deterministic_headers` 會自動從同目錄 `P00/P01` 讀取真實 `功能名稱`（若無則取 `target_dir.name`）、補上當日 `建立日期` 與父目錄 `所屬主計畫`，直接插回檔案頂部 Blockquote 並回傳更新後的 `headers`，使該檔在單次 `plan verify` 中直接無損通過標頭檢核。
2. **問：拔除 `auto/SKILL.md` 內聯骨架表後，會不會讓 `/auto` 的工具調用次數反彈回 `sub_07` 優化前的水準？**  
   **答**：不會。優化前慢是因為讀了 6 份 `phase_01~06.md`、分階段寫了 `P06 Draft/Confirmed` 與 `P05 In Progress`、又跑了 5 次 `plan verify`。改為 Batch A（平行讀 `P01~P04` 模板）與 Batch B（平行讀 `P05~P06` 模板）僅需 2 個平行讀取批次（共 4.2K chars），卻能讓 `auto/SKILL.md` 永久瘦身 45% 並 100% 根除壓縮後盲寫失憶。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：升級 `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`：擴充 `PlanReport`（`header_healed`, `next_phase_hint`），實作 `_auto_heal_deterministic_headers`（自動無損補齊缺失之功能名稱、建立日期、所屬主計畫）、`get_resolved_template_header_specs`（保留原始 Markdown 標題）、章節缺失率分流處方（`QUICK_PATCH` $< 50\%$ vs `FULL_REWRITE` $\ge 50\%$）與 `_build_next_phase_hint`（`PASSED` 時預告下一階段模板與必備章節）。
2. **TASK-02**：更新 `ys_codebase/source/agents-workflow/scripts/cli.py`：於 `plan_check` 報告輸出 `[SELF-HEAL] 已自動補齊確定性標頭` 與 `[NEXT PHASE GATE]` 前瞻領航提示。
3. **TASK-03**：精實化重構 `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md` 與 `development-sop/SKILL.md`：拔除 `auto/SKILL.md` §3 內聯骨架速查表（壓降至 $\le 75$ 行），改為 Batch A（寫 `P01~P04` 前平行直讀 `P01~P04` 模板）與 Batch B（Phase 5 測試通過後平行直讀 `P05_task.md` 與 `P06_test_plan.md`）兩階段 JIT 讀模板，並量化支柱二 Phase 5 實作子代理觸發門檻（跨 $\ge 5$ 檔或預計讀改 $> 1,500$ 行）。
4. **TASK-04**：更新 `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`：更新 `test_ft_13` 並新增 `test_ft_14` 驗證確定性標頭自癒、`QUICK_PATCH` / `FULL_REWRITE` 分流處方、`next_phase_hint` 前瞻提示與 `auto/SKILL.md` 合規斷言測試，執行 `dev check`、`dev test`、編譯與 `@build` 發布驗證。
5. **TASK-DOC**：同步更新 `docs/agents-workflow/{user_guide.md,DESIGN_NOTES.md}`（新增 `[DN-AW-16]`）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 確立兩階段 JIT 讀模板 + `PlanVerifier` 三合一智慧診斷（標頭自癒 + 缺失率分流 + 前瞻提示）為 `/auto` 與 `plans` 工具鏈最終標準架構**。
