# API 與介面規格書 (API & Interface Specification)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-18  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `AgentsStandards.md` | `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md` | Public (Asset) | 全域核心行為公理、模型紀錄規則與條件式技能攔截表 (`FR-08`) |
| `context-init`, `yscb-cli-guild`, `new-plan`, `research`, `roadmap` | `ys_codebase/source/agents-workflow/assets/skills/*/SKILL.md` | Public (Asset) | L0 熱啟動與權限契約、L1 立項與調研/路線圖狀態流轉契約 (`FR-01`, `FR-04`, `FR-08`) |
| `development-sop` & `references/*` | `ys_codebase/source/agents-workflow/assets/skills/development-sop/**` | Public (Asset) | L2 核心 SOP 樞紐、6 大模式轉型/主從同步契約與 P07 結案守門管線 (`FR-03`, `FR-04`, `FR-05`, `FR-08`) |
| `auto`, `pause`, `continue`, `discuss`, `session-analysis` | `ys_codebase/source/agents-workflow/assets/skills/*/SKILL.md` | Public (Asset) | L3 連續推進、`handoff.md` 消費即銷毀、次要問題三出口與回填鏈 (`FR-02`, `FR-06`, `FR-08`) |
| `P00`, `P01`, `P03`, `P04`, `P07`, `fast_track_plan`, `revision_log`, `roadmap`, `changelog` | `ys_codebase/source/agents-workflow/assets/templates/*.md` | Public (Asset) | 標準計畫產物模板結構、三層 5 列文檔表與結案檢核清單契約 (`FR-04`, `FR-05`, `FR-07`, `FR-08`) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

本子計畫聚焦於 `assets/` 內之宣告式提示詞、流程規範與標準模板契約（Python 工具鏈公開 API 簽名維持 100% 不變）。以下定義各核心資產之結構與狀態契約：

```python
# 1. 各產物落檔預設標頭狀態契約 (FR-08 / GAP-05, 相容於 PlanStatusResolver.VALID_STATUSES)
DEFAULT_HEADER_STATE_CONTRACT = {
    "P00_discuss.md": "Discussing (尚有待確認議題) | Confirmed (需求已收斂確認)",
    "P01_requirements_spec.md": "Confirmed (落檔即定稿，免 Draft 中繼寫入)",
    "P02_architecture_plan.md": "Confirmed (落檔即定稿，免 Draft 中繼寫入)",
    "P03_api_spec.md": "Confirmed (落檔即定稿，免 Draft 中繼寫入)",
    "P04_implementation_plan.md": "Confirmed (落檔即定稿，§1 交叉驗證勾選 [x]，§4 為無 Checkbox 有序清單)",
    "P05_task.md": "In Progress (分步實作中) -> Completed (全數 TASK 勾選 [x])",
    "P06_test_plan.md": "Draft (P02 初始化，/auto 豁免) -> Confirmed (P04 定稿) -> Passed (P06 自動測試通過) -> Completed (UX 驗收完成)",
    "P07_walkthrough.md": "Completed (落檔即結案，全數檢核 Checkbox 勾選 [x])",
    "fast_track_plan.md": "Confirmed / In Progress (FP-01/02) -> Completed (FP-03 結案，全數 [x])",
    "revision_log.md": "In Progress (修訂中) -> Completed (修訂結案，全數 [x])",
    "RXX_research_report.md": "Draft / In Progress (調研中) -> Concluded (三大出口拍板收斂)",
    "umbrella_overview.md": "Planning (藍圖建立) -> In Progress (首個 sub_XX 啟動) -> Completed (全數 sub_XX 完成且里程碑 [x])",
    "roadmap.md": "Backlog | Proposed | Ready | Deferred -> In Progress (流轉立項) -> Completed (實作結案)",
    "changelog.md": "In Progress | Active (建檔初始化設定，全週期免回寫標頭狀態)",
}

# 2. P04 §2 與 P07 §4.1 三層 5 列文檔表格對稱契約 (FR-07 / GAP-10)
THREE_TIER_DOC_TABLE_ROWS = [
    ("宏觀 (Macro)", "__${project://CHANGELOG.md}__"),
    ("中觀 (Meso) - 模組手冊", "__${workflow.docs://}__/<Category>/README.md"),
    ("中觀 (Meso) - 專題手冊", "__${workflow.docs://}__/<Category>/[topic].md"),
    ("中觀 (Meso) - 設計決策", "__${workflow.docs://}__/<Category>/DESIGN_NOTES.md"),
    ("微觀 (Micro) - 代碼註解", "源碼 Public API Docstring 與 Why-Driven 註解"),
]

# 3. 錯誤與例外防護契約 (Error & Validation Contracts)
# - PlanVerifier 動態標題契約 (EC-01): P00/P01/P03/P04/P07/fast_track_plan/revision_log 之 ## 與 ### 標題保持與既有活躍計畫 (sub_01) 100% 相容。
# - PlanVerifier 完成態 Checkbox 契約 (FR-05, EC-04): P00 §3 預設不使用 `- [ ]`；P04 §4 不使用 `- [ ]`；P07 / fast_track_plan / revision_log 先勾選 `[x]` 並設 `Completed` 後再執行 `plan verify`。
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Stage 1: 標準模板層更新 (ys_codebase/source/agents-workflow/assets/templates/)
  ├── P00_discuss.md, P01_requirements_spec.md, P03_api_spec.md, changelog.md (FR-08, EC-04)
  ├── P04_implementation_plan.md, P07_walkthrough.md (FR-05, FR-07, EC-01)
  └── fast_track_plan.md, revision_log.md, roadmap.md (FR-04, FR-05, FR-08, EC-02)
         ⬇
Stage 2: L0/L1 全域治理與入口技能層更新 (assets/standards/ & assets/skills/)
  ├── standards/AgentsStandards.md, skills/context-init/SKILL.md, skills/yscb-cli-guild/SKILL.md (FR-01, FR-08)
  └── skills/new-plan/SKILL.md, skills/research/SKILL.md, skills/roadmap/SKILL.md (FR-04, FR-08)
         ⬇
Stage 3: L2/L3 核心 SOP 與流程控制技能層更新 (assets/skills/development-sop/ & 控制技能)
  ├── development-sop/SKILL.md & references/{plan_modes,phase_00,phase_01,phase_03,phase_07}.md (FR-03, FR-04, FR-05, FR-08)
  └── skills/{pause,continue,discuss,auto,session-analysis}/SKILL.md (FR-02, FR-03, FR-06, FR-08)
         ⬇
Stage 4: 單元測試擴充與靜態/合規驗證 (tests/ & CLI Verification)
  └── tests/test_plans_model_record.py -> dev check -> dev test -> plan verify
```

