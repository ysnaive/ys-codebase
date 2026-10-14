# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_10_14_1650_agents_workflow_audit_and_consolidation  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  


> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 對當前 `agents-workflow` 模組進行內容全量審計，針對「語意聚合、語意優化、功能整併」進行全面重構。
  2. 對標準模板 Header 添加 property `model`（`> 模型：[模型名稱]`），要求 Agents 紀錄撰寫該紀錄檔案的後台模型（如 P00/P01 規劃者與後續執行者模型）。
  3. 原將 Review 拉出作為單獨一個階段是因為併入 P07 容易讓 Agents 忽略詳細步驟，但現在 `Review -> P07` 加斷點太拖沓，本質上 Review 屬於 P07 的工作，需將 Review 併回 P07 / FT-3 並確保不忽略詳細步驟。
- **核心目標**：
  1. **模板標頭模型溯源 (`model` Property) 與驗證器封存邊界純化**：於全數 15 個模板（`header.md` 共用之 10 個模板 + `umbrella_overview.md`、`RXX_research_report.md`、`roadmap.md`、`handoff.md`）統一新增 `> 模型：[模型名稱]`；同步**移除 `PlanVerifier.verify_all_plans()` 對封存計畫 (`workflow.archived://`) 的檢查邏輯**（封存即代表已完成或棄置之凍結歷史，僅檢核活躍計畫 `workflow.plans://`），使活躍計畫無條件強制檢核 `model` 欄位與未替換佔位符攔截。
  2. **Review Gate 內化併回 P07 / FT-3（零額外斷點 + 三重防忽略防線）**：移除獨立 `review_gate.md` 與 `Review Verdict Card` 對話停頓點，使 `P06`（或 `FT-2`）通過後直接進入 `P07`（或 `FT-3`），並以「指引 3-Step 強制管線 + 模板剛性審查表 + `PlanVerifier` 未勾選 `- [ ]` 強制阻斷」三道防線確保三層文檔對齊與測試合規 100% 落實。
  3. **語意聚合、語意優化與功能整併（審計項目 A~E 全量落地）**：
     - **項目 A**：解除 `new-plan/SKILL.md` 對 `development-sop/SKILL.md` 的雙重注入，消除 8.5KB 重複、雙重 YAML Frontmatter 與 15 處斷鏈，將 `new-plan` 精簡為 ~25 行輕量啟動與分流引導並指向 `development-sop`。
     - **項目 B**：清除 `fast_track_plan.md`、`umbrella_overview.md`、`RXX_research_report.md`、`roadmap.md`、`changelog.md`、`handoff.md` 頂部重複且規則矛盾的 HTML 隱藏註解，使 15 個模板 100% 純淨。
     - **項目 C**：大幅收斂 `contributes/agents-workflow.json` 中 59 個碎片化/死 Token（移除從未使用的 41 個單階段碎片 Token、7 個 HTML 註解專用 Token、以及孤兒錨點 `DYNAMIC_CONTEXT_MAP` 與死代碼 `agents_workflow/providers.py`），保留核心擴充 Token 並同步更新描述。
     - **項目 D**：修正各 Skills 指向 `development-sop`，收斂單一 `R01` / `Roadmap` 回覆卡片格式，精簡 `continue/SKILL.md` 狀態判定通則，更新 `context-init` 與 `README.md` 規範描述，並修復展開後 `plans//` 與 `docs//` 雙斜線問題。
     - **項目 E**：抽取 `verifier.py`、`scanner.py`、`archiver.py`、`searcher.py` 共用的 `_resolve_uri_path()` 至 `plans/__init__.py`，統一 `plans/archived` fallback 路徑，修復 `scripts/cli.py` 之 `plan_search` 誤用 `get_option()` 為 `get_option_value()`，清理 `compiler.py` / `verifier.py` 死代碼，並同步更新 `contributes/_manifest.md`。
- **邊界排除 (Explicitly Excluded)**：
  - 僅包含 `agents-workflow` 模組本體（`ys_codebase/source/agents-workflow/`、`docs/agents-workflow/` 及發布投影產物），不修改其他模組之 `contributes`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模板標頭 `model` 屬性格式與移除封存計畫檢核**：
  - 統一採用中文標籤 `> 模型：[模型名稱]`（`PlanVerifier` 同時識別 `["模型", "model", "使用模型", "執行模型", "ai_model"]`）；並徹底移除 `PlanVerifier` 對 `workflow.archived://` 封存計畫的掃描與檢查（封存即代表完成或棄置之歷史紀錄，無須亦不應再受新版驗證規則回溯檢查），對所有進行中活躍計畫 (`workflow.plans://`) 剛性要求 `model` 欄位 (`FAIL`)。
- **[P00:DR-02] Review 併回 P07 / FT-3 之三道剛性防忽略防線**：
  - 廢除獨立 `review_gate.md` 與 `Review Verdict Card` 對話斷點；將三層文檔審查內化為 `phase_07_walkthrough.md` 的「Step 1：結案前置品質審查與即時修復閉環」，並在 `P07_walkthrough.md` 與 `fast_track_plan.md` 設置必填審查表與 `- [x]` 合規 Checkbox，由 `PlanVerifier` 對 `Completed` 狀態下未勾選之 `- [ ]` 強制判定 `FAIL`。
- **[P00:DR-03] `new-plan` 輕量入口定位與 Token 收斂原則**：
  - 廢除 `DEVELOPMENT_STANDARDS` 全量注入，保留 `new-plan/SKILL.md` 作為 ~25 行輕量啟動入口（負責 P00 延遲建檔守門與 6 大模式分流導引，並連結至 `development-sop`）；同步清理 `agents_workflow/providers.py` 死代碼與 40+ 個未使用的碎片化 Token。

---

## 3. 開放議題與確認紀錄

- [x] **範疇確認**：開發者確認全部納入（優化 1 + 優化 2 + 審計項目 A~E 全量收斂整併）。
- [x] **`new-plan` 定位確認**：開發者確認保留 `new-plan` 作為輕量入口 Skill 並連結至 `development-sop`。
- [x] **模板 `model` 標籤與驗證器邊界確認**：開發者確認使用 `> 模型：[模型名稱]`，並移除 `verify_all_plans` 對封存計畫之檢查（僅檢核活躍計畫）。
