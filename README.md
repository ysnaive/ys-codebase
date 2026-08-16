# Agent Workflow Core (`agent.workflow`)

一套嚴謹、可追溯、防臆測的 AI Agent 標準開發作業流程 (SOP) 與工程規範標準庫。

---

## 🌟 核心哲學與架構

1. **三大原則 (Core Principles)**：
   - **零臆測 (Zero Speculation)**：嚴禁自行假設需求或 API 行為。
   - **可追溯 (Traceability)**：全生命週期文件留痕（FR/EC $ightarrow$ 架構 $ightarrow$ API $ightarrow$ Task $ightarrow$ Test $ightarrow$ Walkthrough）。
   - **分級管控 (Graduated Control)**：Full Track (Phase 0~7) 與 Fast Track (FT-1~3) 分流。
2. **防呆鐵律 (Guardrails)**：
   - **嚴禁連發**：單次 Turn 最多執行一個 Phase，產出後強制 End Turn 等待確認。
   - **嚴禁空降實作**：未經規劃與 Checkpoint 核准前，絕對禁止修改原始碼。
   - **Test-First 前置定稿**：P06 測試計畫於 Phase 4 與實作計畫同步定稿。
   - **人工/UX/實機驗證 Checkpoint**：嚴禁 Agent 代勾測試 Passed，無 Log 視同未驗證。

---

## 📁 儲存庫結構

```text
agent.workflow/
├── workflows/
│   ├── DevelopmentSOP.md          # 核心標準作業流程 (Phase 0~7 / FT)
│   ├── DevelopmentSOP_Continue.md # 任務接續工作流
│   ├── DevelopmentSOP_Review.md   # 結案審查工作流
│   ├── DocumentationStandards.md  # 知識庫四分法與 docs/ 規範
│   │
│   ├── templates/                 # 通用規格書與計畫模板 (P01~P07 / FT / docs)
│   │   ├── P01_requirements_spec.md
│   │   ├── P02_architecture_plan.md
│   │   ├── P03_api_spec.md
│   │   ├── P04_implementation_plan.md
│   │   ├── P06_test_plan.md
│   │   ├── P07_walkthrough.md
│   │   ├── FT_plan.md
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
│   └── README.md                  # 腳本使用指南
│
├── .workflow_config.template.json # 專案同步設定檔範本
├── .gitignore
└── README.md
```

---

## 🚀 快速開始：在專案中引入

### 方法 1：使用同步腳本 (`sync_workflow.py`)
1. 將本倉庫的 `scripts/sync_workflow.py` 複製至專案的 `.agents/scripts/`。
2. 於專案 `.agents/` 建立 `.workflow_config.json`：
   ```json
   {
     "core_repo": "https://github.com/YsNaive/agent.workflow.git",
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
