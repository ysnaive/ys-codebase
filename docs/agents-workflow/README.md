# Agents Workflow 模組 (General Agents Workflow Framework)

`agents-workflow` 為 YS-Codebase 體系的一等公民核心模組，提供通用、純淨且工廠化的 Agent 工作流程與規範治理體系。

---

## 1. 核心定位與三位一體資產

模組徹底剝離特定專案特化規則，提供 100% 通用抽象資產：
- **規範 (`assets/standards/`)**：
  - `DocumentationStandards.md`：知識庫 7 大抽象維度、Topic 專題文檔與 1:1 交付原則。
  - `DevelopmentStandards.md`：SOP 0~7 標準生命週期、三大分流 (Fast/Full/Umbrella) 與防呆紀律。
- **流程 (`assets/workflows/`)**：
  - `ContextInit.md`：上下文熱啟動流程。
- **模板 (`assets/templates/`)**：
  - 13 大標準模板庫（`P00`~`P07`, `FT_plan`, `umbrella_overview`, `changelog`, `R_research_report`, `handoff`）與共用標頭 `header.md`。

---

## 2. CLI 快速使用指南

```bash
# 列出全系統已註冊之 Token 錨點清單與說明
python yscb.py agents-workflow tokens

# 列出當前所有模組導出之 Standards, Workflows, Templates 清冊
python yscb.py agents-workflow list

# 觸發工廠物化流水線，執行多輪遞迴狀態機解算並寫入 exports/
python yscb.py agents-workflow compile
```

---

## 3. 架構與專題手冊導引

- **協議產物工廠化與多輪狀態機**：詳見 [FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md)。
- **設計決策與工程妥協**：詳見 [DESIGN_NOTES.md](./DESIGN_NOTES.md)。
