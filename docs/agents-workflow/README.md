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

## 2. 佔位符語法與渲染機制 (Placeholder Architecture)

系統採用 Markdown 原生可視的強定義佔位符語法，淘汰被 HTML 隱藏的舊註解格式：

| 佔位符類型 | 語法結構 | 正則表達式 | 核心職責與編譯行為 |
| :--- | :--- | :--- | :--- |
| **插入佔位符 (Token Anchor)** | `__@{TOKEN_NAME}__` | `r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"` | 主動注入點。由編譯器 5-Step 狀態機進行 `replace` / `below` / `above` 多輪遞迴展開，解算完成後自動乾淨抹除殘留標籤行。 |
| **路徑佔位符 (URI Reference)** | `__#{URI_OR_PATH}__` | `r"__#\{\s*([^}]+)\s*\}__"` | 被動語意參照。於物化編譯時 100% 原樣保留，作為文檔中的語意協議錨點供下游工具與人眼閱讀。 |

> [!TIP]
> 插入佔位符支援大括號內部微量空格容錯（例 `__@{ PHASEXX_STANDARD_HEADER }__` 與 `__@{PHASEXX_STANDARD_HEADER}__` 等價）。

---

## 3. CLI 快速使用指南

```bash
# 列出全系統已註冊之 Token 錨點清單與說明
python yscb.py agents-workflow tokens

# 列出當前所有模組導出之 Standards, Workflows, Templates 清冊
python yscb.py agents-workflow list

# 觸發工廠物化流水線，執行多輪遞迴狀態機解算並寫入 exports/
python yscb.py agents-workflow compile
```

---

## 4. 架構與專題手冊導引

- **協議產物工廠化與多輪狀態機**：詳見 [FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md)。
- **設計決策與工程妥協**：詳見 [DESIGN_NOTES.md](./DESIGN_NOTES.md)。
