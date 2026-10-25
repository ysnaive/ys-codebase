# 功能需求規格書 (Requirements Specification)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求 ID | 來源追溯 | 需求名稱 | 核心行為與交付目標 |
| :--- | :--- | :--- | :--- |
| **FR-01** | `P00 §1` | **`auto/SKILL.md` 兩階段 JIT 讀模板瘦身** | 拔除 `auto/SKILL.md` §3 內聯骨架速查表（使技能本體瘦身 ~45% 並回歸模板 SSOT），改為 Batch A（動筆寫 `P01~P04` 前平行讀取 `.agents/.yscb/templates/P01~P04.md`）與 Batch B（Phase 5 測試通過後、動筆寫 `P05~P06` 前平行讀取 `P05_task.md` 與 `P06_test_plan.md`），全程維持免讀 `phase_01~05.md`。 |
| **FR-02** | `P00 §1` | **`auto/SKILL.md` 量化支柱二實作子代理門檻** | 於 `auto/SKILL.md` 明確規範當 `P04` 涉及 **跨 $\ge 5$ 個檔案修改/整併、或預估需讀改 $> 1,500$ 行代碼** 時，推薦委派 `self` 實作子代理隔離執行 `TASK-XX` 並跑測，保護主對話 Context 免於壓縮。 |
| **FR-03** | `P00 §1` | **`PlanVerifier` 確定性環境標頭無損自癒** | 於 `PlanVerifier` 檢核管線中，針對缺少 **100% 確定性環境標頭欄位**（`> 建立日期：` 預設當日、`> 所屬主計畫：` 二級子計畫自動取父目錄名、`> 功能名稱：` 繼承同目錄 `P00/P01` 或取目錄名）之受檢 Markdown 檔案，自動無損補入頂部 Blockquote 並記錄於 `PlanReport.header_healed` 清單。 |
| **FR-04** | `P00 §1` | **`PlanVerifier` 章節缺失率速評分流與原始標題處方** | 廢除於 `TEMPLATE` 報錯中僅輸出正規化小寫字串（如 `'人工/ux驗證checkpoint'`），改為保留模板原始 Markdown 標題與首行表頭，並依章節缺失率 $R_{\text{section}}$ 分流輸出 `[TRIAGE: QUICK_PATCH]`（$0 < R_{\text{section}} < 50\%$，內聯缺失之原始標題骨架供 `edit_file` 修補）與 `[TRIAGE: FULL_REWRITE]`（$R_{\text{section}} \ge 50\%$，警告盲寫偏離並內聯完整原始標題骨架及 `.agents/.yscb/templates/<tmpl>.md` 路徑供 `write_file` 重寫）。 |
| **FR-05** | `P00 §1` | **`plan verify` 下一階段前瞻領航提示 (`NEXT PHASE GATE`)** | 當單一計畫執行 `plan verify` 結果為 `PASSED` 且尚未結案（如處於 `P00`~`P06`）時，結合 `PlanStatusResolver.resolve_next_action` 與對應模板原始標題，於 `PlanReport.next_phase_hint` 及 CLI 報告底部輸出下一階段目標檔名、模板路徑與必備章節預告。 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界 ID | 關聯需求 | 情境描述 | 預期防護與攔截行為 |
| :--- | :--- | :--- | :--- |
| **EC-01** | `FR-03` | 檔案已具備標頭欄位（或含未替換 `[...]` 佔位符） | 確定性標頭自癒僅針對「完全缺失該欄位鍵名」之情況補入；若欄位已存在但值為 `[功能名稱]` 等未替換佔位符，維持報出 `PLACEHOLDER` `FAIL` 而不靜默掩蓋。 |
| **EC-02** | `FR-03` | 檔案頂部無任何 `>` Blockquote 區塊 | 若前 35 行完全無 `>` 標頭行，於第一個 `# ` 一級標題下方自動插入確定性標頭區塊並重新解析 `headers`。 |
| **EC-03** | `FR-04` | 多章節同時缺失時避免 N 條重複碎片化報錯洗版 | 當同一檔案缺失多個模板章節時，彙整為單一結構化 `TEMPLATE` `PlanIssue`（內含缺失率 `M/N`、`QUICK_PATCH` 或 `FULL_REWRITE` 處方等級與全部缺失/完整原始 Markdown 標題清單），杜絕碎片洗版。 |
| **EC-04** | `FR-05` | 計畫已處於 `Completed`（如 `P07` 已完成或 `verify_all_plans` 批次模式） | 當計畫狀態已為 `Completed` 或處於無目標參數之全量批次掃描時，`next_phase_hint` 為 `None`，不輸出冗餘前瞻提示。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求 ID | 類別 | 具體指標與驗證方式 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部依賴與向下相容** | 100% 使用 Python 標準庫；`PlanReport` 新增 `header_healed` 與 `next_phase_hint` 屬性維持預設值與既有 Tuple 解構向下相容。 |
| **NFR-02** | **Skill 規模精簡度** | `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md` 移除內聯骨架表後，總行數控制在 $\le 75$ 行（較原 97 行減少 $> 20\%$）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- 查閱 `docs/agents-workflow/DESIGN_NOTES.md` (`[DN-AW-10]`、`[DN-AW-15]`)：伴隨檔與標頭自癒嚴禁修改 `> 模型：` 欄位（`> 模型：` 仍須由 Agent 顯式填寫以符合 `AGENTS.md §1.2` 零臆測原則，故 `> 模型：` 缺失時維持報錯而不自動偽造）。

