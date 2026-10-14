# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_10_14_1650_agents_workflow_audit_and_consolidation  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全模板標頭模型屬性擴充 | 於共用標頭 `assets/templates/header.md` 與 4 個獨立標頭模板（`umbrella_overview.md`、`RXX_research_report.md`、`roadmap.md`、`handoff.md`）統一新增 `> 模型：[模型名稱]`，支援各階段 Agent 標註其背後所屬模型 | P0 | [P00:DR-01] |
| **FR-02** | 活躍計畫模型屬性剛性檢核與封存計畫檢查移除 | `PlanVerifier` 新增 `has_model` 必填校驗，並於 `PLACEHOLDER_PATTERNS` 攔截未填寫之 `[模型名稱]`；同時徹底移除 `verify_all_plans()` 對 `workflow.archived://` 封存歷史的掃描與檢查，僅嚴格檢驗進行中之活躍計畫 (`workflow.plans://`) | P0 | [P00:DR-01] |
| **FR-03** | Review Gate 內化至 P07 / FT-3 並移除獨立斷點 | 廢除獨立檔案 `review_gate.md` 與 `Review Verdict Card` 對話停頓點；將三層文檔審查（宏觀 `CHANGELOG.md`、中觀 `docs/` 與 DN 防膨脹、微觀 Docstring）內化為 `phase_07_walkthrough.md` 強制前置之「Step 1：結案前置品質審查與即時修復閉環」，使 P06 / FT-2 通過後直接進入 P07 / FT-3 結案流轉 | P0 | [P00:DR-02] |
| **FR-04** | P07 模板審查欄位結構化與 `PlanVerifier` 剛性阻斷 | 於 `P07_walkthrough.md` 與 `fast_track_plan.md` 設置結構化必填審查表與合規 Checkbox；當計畫狀態為 `Completed` 時，若存在未勾選之 `- [ ]` 審查檢核項，`PlanVerifier` 強制判定 `FAIL`，防禦敷衍跳過 | P0 | [P00:DR-02] |
| **FR-05** | `new-plan` 輕量化與雙重注入斷鏈徹底修復 | 廢除 `DEVELOPMENT_STANDARDS` Token 注入，消除 8.5KB 內容重複、雙重 YAML Frontmatter 與 15 處相對路徑斷鏈；將 `new-plan/SKILL.md` 精簡為 ~25 行專注於 P00 延遲建檔守門與 6 大分流啟動之輕量入口，並語意連結至 `development-sop` | P0 | [P00:DR-03] |
| **FR-06** | 6 大非 Phase 模板 HTML 隱藏註解純淨化 | 徹底移除 `fast_track_plan.md`、`umbrella_overview.md`、`RXX_research_report.md`、`roadmap.md`、`changelog.md`、`handoff.md` 頂部的 HTML 註解，統一指引至 `plan_modes.md` 與專屬 Skill，糾正 Fast Track「檔案數 <= 2」與偏差等級等矛盾定義 | P1 | [P00:DR-03] |
| **FR-07** | 碎片化 Token 大幅收斂、死代碼清理與共用邏輯提取 | 於 `contributes/agents-workflow.json` 清理從未使用的 41 個單階段碎片 Token、7 個 HTML 註解專用 Token 與死錨點 `DYNAMIC_CONTEXT_MAP`，刪除 76 行死代碼 `providers.py`；於 `plans/__init__.py` 抽取共用 `_resolve_uri_path()`，統一 `plans/archived` fallback 路徑，修正 `scripts/cli.py` 之 `plan_search` 選項提取並更新 `_manifest.md` | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 計畫文件 Header 中包含未替換之 `[模型名稱]` 佔位符 | `PlanVerifier` 透過 `PLACEHOLDER_PATTERNS` 識別並拋出 `PlanSeverity.FAIL`，提示必須填入真實模型名稱 |
| **EC-02** | 計畫文件 Header 缺少 `model` / `模型` 欄位 | 對活躍計畫 (`workflow.plans://`) 拋出 `PlanSeverity.FAIL` 阻斷；同時不掃描 `workflow.archived://` 確保歷史封存計畫不受影響 |
| **EC-03** | `P07_walkthrough.md` 狀態標記為 `Completed`，但三層文檔或合規 Checkbox 仍包含未勾選之 `- [ ]` | `PlanVerifier` 檢核判定 `PlanSeverity.FAIL`，強制阻斷未完成審查即宣告結案之行為 |
| **EC-04** | 外部模組或舊版組態引用已收斂廢除之 Token（如 `DEVELOPMENT_STANDARDS`） | `ArtifactCompiler.resolve_stage1_token()` 採安全防禦，未註冊 Token 替換為空字串或優雅忽略，不拋出未捕捉例外 |
| **EC-05** | `plan verify` 執行時專案未建立 `plans/` 或 `plans/archived/` 目錄 | `verify_all_plans()` 針對目錄不存在情境安全返回空結果字典，不崩潰 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 程式碼品質與單元測試覆蓋 | `agents-workflow` 所有單元測試 100% 通過（`Pass: 80+ / 80+`），全生態系 555 項測試 100% 通過 |
| **NFR-02** | 靜態合規與產物物化 | `python yscb.py dev check --all` 0 Warnings, 0 Failed；發布後投影之 `.agents/skills/` 與 `AGENTS.md` 0 斷鏈 |
| **NFR-03** | 效能與資產瘦身 | 移除 `new-plan/SKILL.md` 8.5KB 重複內容，移除 76 行 Python 死代碼，Token 錨點清單自 59 個收斂至約 15 個核心 Token |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`**：`PlanVerifier` 原本會針對 Markdown 文件動態檢查與模板標題的 1:1 鏡像對齊。當 `P07_walkthrough.md` 與 `fast_track_plan.md` 標題微調時，需確保 `verifier.py` 動態提取模板標題邏輯能與新模板完美相容，或於模板本體使用穩定章節標題。
- **`[!NOTE]`**：`compiler.py` 的 Stage 2 URI 解析在路徑尾斜線補齊時，需注意避免與外部手動斜線疊加成雙斜線 `//`。

