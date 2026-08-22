# YS-Codebase (`ys-codebase`)

一套專為個人獨立開發者、中小型團隊與 Case-by-Case / 接案專案打造的嚴謹、可追溯、防臆測 AI Agent 代碼庫工程工具與標準規範庫。

---

## 🌟 核心哲學與架構

1. **三大原則 (Core Principles)**：
   - **零臆測 (Zero Speculation)**：嚴禁自行假設需求或 API 行為。
   - **可追溯 (Traceability)**：全生命週期文件留痕（P00 語意 $\rightarrow$ P01 FR/EC $\rightarrow$ 架構 $\rightarrow$ API $\rightarrow$ Task $\rightarrow$ Test $\rightarrow$ Walkthrough）。
   - **分級管控 (Graduated Control)**：Level 0 (Fast Track)、Level 1 (Full Track) 與 Level 2 (Umbrella 主計畫) 三大分流體系。
2. **防呆鐵律 (Guardrails)**：
   - **嚴禁連發**：單次 Turn 最多執行一個 Phase，產出後強制 End Turn 等待確認。
   - **嚴禁空降實作**：未經規劃與 Checkpoint 核准前，絕對禁止修改或編寫原始碼。
   - **Test-First 前置定稿**：P06 測試計畫於 Phase 4 與實作計畫同步定稿。
   - **人工/UX/實機驗證 Checkpoint**：嚴禁 Agent 代勾測試 Passed，無 Log 視同未驗證。

---

## 📁 儲存庫結構

```text
ys-codebase/
├── workflows/
│   ├── sop_NewPlan.md             # 核心標準作業流程 (Phase 0~7 / 三大分流體系)
│   ├── sop_Continue.md            # 任務接續工作流
│   ├── sop_Review.md              # 結案審查與合規驗證工作流
│   ├── sop_Discuss.md             # 根因排查與深度討論工作流
│   ├── sop_Idea.md                # 構想與靈感孵化池
│   ├── sop_Pause.md               # 任務暫停與現場凍結
│   ├── sop_Research.md            # 深度技術調研工作流
│   ├── sop_ContextInit.md         # 專案上下文熱啟動工作流
│   ├── DocumentationStandards.md  # 知識庫四分法與 docs/ 規範
│   │
│   ├── templates/                 # 通用規格書與計畫模板 (P00~P07 / FT / docs)
│   │   ├── AGENTS.template.md
│   │   ├── P00_semantic_requirements.md
│   │   ├── P01_requirements_spec.md
│   │   ├── P02_architecture_plan.md
│   │   ├── P03_api_spec.md
│   │   ├── P04_implementation_plan.md
│   │   ├── P06_test_plan.md
│   │   ├── P07_walkthrough.md
│   │   ├── R_research_report.md
│   │   ├── FT_plan.md
│   │   ├── handoff.md
│   │   ├── idea.md
│   │   ├── changelog.md
│   │   ├── global_changelog.md
│   │   ├── umbrella_overview.md
│   │   └── docs/ (readme, topic, design_notes, changelog, global_index)
│   │
│   └── extensions/
│       └── ext_template.md        # 專案特化擴充模板
│
├── scripts/                       # 定式作業 Python 工具庫
│   ├── archive_plan.py            # 計畫安全歸檔
│   ├── scan_plan_status.py        # 計畫進度與狀態矩陣掃描
│   ├── search_dev_plans.py        # 歷史計畫與 DR 決策全文檢索
│   ├── sync_workflow.py           # 中央庫雙向同步工具
│   ├── verify_plan.py             # 計畫合規性與 Extension 深度稽核
│   └── README.md                  # 腳本使用指南
│
├── .workflow_config.template.json # 專案同步設定檔範本
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🚀 快速開始：在專案中引入

### 方法 1：使用同步腳本 (`sync_workflow.py`)
1. 將本倉庫的 `scripts/sync_workflow.py` 複製至專案的 `.agents/scripts/`。
2. 於專案 `.agents/` 建立 `.workflow_config.json`：
   ```json
   {
     "core_repo": "https://github.com/YsNaive/ys-codebase.git",
     "branch": "main"
   }
   ```
3. 執行同步：
   ```bash
   python .agents/scripts/sync_workflow.py pull
   ```

---

## 📄 License
MIT License
