# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：推進全局落地順序 Global Step 2 (`sub_03_testing_sop_and_subagent_isolation`)，將合流遷入之兩份技術路線圖 [roadmap.md](./roadmap.md)（Part I：`testing_sop_and_phase06_hardening_roadmap` 與 Part II：`subagent_task_isolation_evaluation`）一次性完整落地至 `agents-workflow` 模組，建立與 `documentation` 對偶之環境型測試規範技能 `testing-sop`，並於核心 SOP 技能與階段手冊內化「三支柱門檻觸發式 Subagent 任務級上下文隔離協定」。
- **核心目標**：
  1. **環境型技能 `testing-sop` 與漸進式揭露雙層結構 (`assets/skills/testing-sop/`)**：
     - 建立主技能檔 `assets/skills/testing-sop/SKILL.md`：採三段式環境型 Frontmatter Description（功能宣告 + `觸發情境：` + `排除情境：`），內建「六大自動化測試建置與回歸鐵律（Six Core Test Hygiene Invariants）」（① 子系統 1:1 歸戶禁建計畫名碎片檔、② 實質副作用與正負雙向斷言禁空殼/寬容放行、③ 管線實機產出驗證取代靜態文檔搜尋、④ 零歷史墓碑與舊測同步清理、⑤ 100% 狀態隔離與 `tearDown`/`try...finally` 零殘留、⑥ 本體獨立性與零跨層反向耦合）、`Phase 06` 測試品質與回歸自檢清單（Test Hygiene Gate）、預留 Stage 1 專案專屬測試流程錨點 `__@{TESTING_SOP_STANDARDS}__`，並配置情境 A（日常增量測試）與情境 B（存量測試集大掃除）按需載入分流。
     - 建立按需載入參考指南 `assets/skills/testing-sop/references/test_suite_audit_and_purification.md`：定義存量測試集六大病灶體檢模型（`T-01` 虛假放行、`T-02` 跨檔重複、`T-03` 過時墓碑、`T-04` 跨模組耦合、`T-05` 狀態污染、`T-06` 高風險漏測）、子系統 1:1 歸戶收斂映射表（Gate）與無損整併驗收工作流。
     - 於 `contributes/agents-workflow.json` 註冊 `testing-sop` 技能匯出與 `TESTING_SOP_STANDARDS` 擴充 Token（專案層級之 `config://agents-workflow/snippets/testing_guide.md` 留待 `sub_04` 執行 `/how-to-config-yscb` 時自動探勘草擬與確認後代寫）。
  2. **`AgentsStandards.md` 與 `development-sop` 引用連鎖觸發及 `Phase 06` 雙重守門**：
     - 於 `assets/standards/AgentsStandards.md` §2 條件式技能路由表新增 `testing-sop` 強制觸發路由列。
     - 於 `phase_04_plan.md`（§3 定稿 `P06_test_plan.md` 前）、`phase_05_task.md`（§2 編寫測試代碼前）、`phase_06_test.md`（頂部檢核表與 §2 測試品質與回歸雙重守門：守門 ① 子系統回歸全綠 + 守門 ② 新增測試反模式自檢）及 `plan_modes.md`（`Fast Track` `FP-02` 實作與驗證）植入 `` [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) `` 強制引用連鎖觸發。
  3. **內化「三支柱門檻觸發式 Subagent 任務級上下文隔離協定」**：
     - **支柱一（`/research` 與 `/discuss` 唯讀廣域探索隔離）**：於 `assets/skills/research/SKILL.md` 與 `assets/skills/discuss/SKILL.md` 增補唯讀 Subagent 廣域探索委派指引（支援單一或平行派發），規定子代理僅回傳濃縮證據、檔案行號與方案優劣摘要（150~300 Tokens），主視窗保留乾淨 Context 撰寫 `R{NN}_{topic}.md` 或歸因討論卡。
     - **支柱二（`/auto` 與大型 `Phase 05/06` 受限讀寫實作隔離）**：於 `assets/skills/auto/SKILL.md`、`phase_05_task.md` 與 `phase_06_test.md` 增補門檻判定表（處於 `/auto` 進入 Phase 05/06，或 `P05_task.md` 含 $\ge 3$ 個跨模組任務組時啟用；`Fast Track`、`Revision` 或 $\le 2$ 個任務維持主視窗直行）、高內聚任務組**強制序列派發**、檔案路徑傳址（傳遞 `P03/P04/P05` 與 `testing-sop` 路徑指針）、內部「二振失敗熔斷（2-Strike Limit）」（單元測試連續 2 次修復失敗立即停手回傳 `STATUS: MAJOR_BLOCKER` 交主視窗轉 `/discuss`）、四級狀態回傳碼（`COMPLETED | MINOR_DEVIATION | MAJOR_BLOCKER | CRITICAL_BLOCKER`）與 `plans/` Single-Writer 鐵律（Subagent 嚴禁修改 `plans/` 任何檔案）。
     - **支柱三（`Phase 07` Step 1 唯讀 Fresh-Eyes 冷眼審查）**：於 `phase_07_walkthrough.md` Step 1 植入獨立無偏誤 Reviewer Subagent 審計協定，結合 `P04_implementation_plan.md` 變更清單、`git status --short`、`git diff HEAD` 與直讀 `Untracked (??)` 新建檔案（防呆 2），強制僅查核三類硬性契約（① 違反 `AGENTS.md` 核心原則 3 敷衍修補或 `testing-sop` 六大測試鐵律反模式、② `P01/P03` 需求與介面遺漏、③ `P04` 應同步之三層文檔或公開 API Docstring 遺漏；防呆 3 禁報主觀風格微調，無缺失直接回傳 `REVIEW_STATUS: PASSED`），並嚴格對齊 `Phase 07` 三步結案時序（Step 1 冷眼審查與修正 $\to$ Step 2 產出 `P07` `Completed` 與更新 `CHANGELOG.md` / `umbrella_overview.md` $\to$ Step 3 執行 `plan verify --log`）。
- **邊界排除 (Explicitly Excluded)**：
  - 不開發任何獨立 Subagent 技能或 `plan task-brief` 切片 CLI（全面採用檔案路徑傳址）。
  - `/how-to-config-yscb` 探勘並代寫 `config://agents-workflow/snippets/testing_guide.md` 之自動化精靈流程，留待 Global Step 8 (`sub_04_onboarding_and_config_coaching`) 建立 `/how-to-config-yscb` 技能時一併實作；本子計畫先行完成 `testing-sop` 技能、`TESTING_SOP_STANDARDS` 錨點註冊與本倉組態掛載驗證。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/skills/testing-sop/SKILL.md` 及 `references/test_suite_audit_and_purification.md`（新建）
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`（註冊 `testing-sop` 技能與 `TESTING_SOP_STANDARDS` Token）
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md`（擴充 §2 條件式技能路由表）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/{phase_04_plan.md,phase_05_task.md,phase_06_test.md,phase_07_walkthrough.md,plan_modes.md}`（植入 `testing-sop` 連鎖引用守門與支柱二/支柱三 Subagent 協定）
  - `ys_codebase/source/agents-workflow/assets/skills/{research,discuss,auto,development-sop}/SKILL.md`（植入支柱一/支柱二 Subagent 委派與路由索引）
  - `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py`（補強當同一個子計畫合併遷入第 2 份 Roadmap 時，`roadmap promote --plan` 支援無損追加合併至 `roadmap.md` 而非直接覆寫）
  - `ys_codebase/source/agents-workflow/tests/` 與 `docs/agents-workflow/`（同步更新技能清冊測試與三層文檔）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 建立與 `documentation` 對偶之環境型技能 `testing-sop` 及漸進式雙層結構**：
  `testing-sop/SKILL.md` 控制在精簡篇幅內，聚焦日常必遵之「六大自動化測試建置與回歸鐵律」、「Phase 06 測試品質自檢清單」與 `__@{TESTING_SOP_STANDARDS}__` 專案專屬測試流程錨點；將高篇幅的「存量測試集六大病灶體檢模型（`T-01`~`T-06`）與子系統 1:1 歸戶收斂工作流」拆分至 `references/test_suite_audit_and_purification.md` 按需載入，確保日常開發零冗餘 Token 負擔，同時為後續 Stage 2~4 各模組測試純化提供標準作業依據。
- **[P00:DR-02] 全鏈路引用連鎖觸發 (`P04 -> P05 -> P06 / FP-02`) 與 Phase 06 雙重守門**：
  除了於 `AgentsStandards.md` 路由表掛載 `testing-sop` 外，於 `phase_04_plan.md`（規劃測試案例時即強制子系統 1:1 歸戶與正負雙向斷言）、`phase_05_task.md`（編寫測試時強制實質副作用與沙盒零殘留）、`phase_06_test.md`（雙重守門：① 子系統回歸全綠 + ② 新增測試反模式自檢）與 `plan_modes.md` (`FP-02`) 以 Stage 2 語意連結 `__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__` 強制連鎖觸發，事前阻斷碎片測試檔與虛假斷言。
- **[P00:DR-03] 內化三支柱門檻觸發式 Subagent 委派協定（檔案路徑傳址 + Single-Writer + 八大護欄）**：
  不新增獨立 Subagent Skill，直接將三支柱協定內化至 `research` / `discuss`（支柱一：唯讀廣域探索）、`auto` / `phase_05` / `phase_06`（支柱二：門檻觸發之高內聚任務組強制序列編碼委派、綁定 `testing-sop` 必讀上下文、內部二振失敗熔斷 `2-Strike Limit`）與 `phase_07` Step 1（支柱三：唯讀 Fresh-Eyes Review，結合 `P04` 清單、`git status --short`、`git diff HEAD` 與直讀 `Untracked` 新檔，僅查核三類硬性契約並嚴格對齊三步結案時序）；所有 `plans/` 檔案 100% 由主視窗 Single-Writer 寫入。
- **[P00:DR-04] 多路線圖合流子計畫之 `roadmap promote --plan` 無損追加防呆**：
  鑑於實務上單一子計畫常合流消費 2 份高度關聯之 Roadmap（如本子計畫 `sub_03` 及 `2026_10_23_1122` 之 `sub_01`~`sub_04`），同步於 `RoadmapManager.promote_roadmap()` 補強：當目標目錄已存在 `roadmap.md` 時，自動以分隔線無損追加合併第二份路線圖內容並移除原檔，避免 `shutil.move` 覆寫既有 `roadmap.md`。

---

## 3. 開放議題與確認紀錄

- 兩份來源路線圖之所有機制設計、六大測試鐵律與八大 Subagent 護欄均已完整對齊，無未決開放議題。

