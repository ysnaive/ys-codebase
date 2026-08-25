# Phase 0: 語意需求與討論模式 (Semantic Requirements) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 當前狀態：`Confirmed` (Phase 0 討論確認完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 原始需求摘要 (Raw Requirements Summary)

- **核心目標**：將 `agents-workflow` 原有的 HTML 註解格式佔位符全面遷移為視覺友善、易於閱讀且 Markdown 原生可視之強定義語法。
- **背景痛點**：原 HTML 註解格式（`<!-- __TOKEN__ -->`、`<!-- __URI(...)__ -->`）在 Markdown 渲染模式（Preview Mode / IDE 檢視器）中會被完全隱藏，導致開發者與維護者無法直觀肉眼察覺模板中是否存在未展開錨點或注入點。
- **全新佔位符語法**：
  1. **插入佔位符 (Token Anchor)**：`__@{token}__`（例：`__@{PHASEXX_STANDARD_HEADER}__`、`__@{DYNAMIC_CONTEXT_MAP}__`）
  2. **路徑佔位符 (URI Reference)**：`__#{uri}__`（例：`__#{standards/DocumentationStandards.md}__`）

---

## 2. 釐清與架構決策紀錄 (Clarification & Decision Records)

### [P00:DR-01] 佔位符正則匹配精準邊界與空白容錯
- **語意**：
  - 插入佔位符 (Token Anchor)：`r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"`
  - 路徑佔位符 (URI Reference)：`r"__#\{\s*([^}]+)\s*\}__"`
- **容錯性**：支援大括號內部微量空格（例如 `__@{ PHASEXX_STANDARD_HEADER }__` 與 `__@{PHASEXX_STANDARD_HEADER}__` 均可精準匹配並提取 token 名稱）。

### [P00:DR-02] 路徑佔位符語意保留行為
- **語意**：
  - `__#{uri}__` 專用於 Markdown 文檔中的語意參照與路徑錨點定位，編譯期保持原樣保留，供下游工具、人眼或跨檔案解析器讀取。
  - 完全淘汰並取代舊格式 `<!-- __URI(...)__ -->`。

### [P00:DR-03] 5-Step 工廠編譯流水線狀態機升級
- **語意**：
  - `ArtifactCompiler.resolve_single_artifact()` 狀態機全面升級為匹配 `__@{token}__` 錨點。
  - 支援 `replace`、`below`、`above` 注入模式並維持自指死鎖防護。
  - 解算完成後自動徹底清除殘留的 `__@{token}__` 標籤行。

### [P00:DR-04] 純淨升級與舊格式全面清除
- **語意**：
  - 徹底移除舊的 `<!-- __TOKEN__ -->` 匹配邏輯（純淨單一語法，不進行雙重語法維護）。
  - 全面更新 `source/agents-workflow/assets/` 下所有 13 大標準模板、規範手冊與工作流文檔中的標籤。

---

## 3. 開發者釐清確認結果 (Clarification Outcomes)

| 釐清項目 | 開發者確認結果 | 對應決策 |
| :--- | :--- | :---: |
| **1. 路徑佔位符行為** | 保留在 Markdown 文檔中供下游工具或人眼閱讀之語意參照，僅取代原 URI 格式 | `[P00:DR-02]` |
| **2. 空白容錯支援** | 允許大括號內部微量空格相容 | `[P00:DR-01]` |
| **3. 舊語法相容性** | 完全升級清除，全面轉為新語法 | `[P00:DR-04]` |

---

## 4. 當前階段確認狀態

- **討論狀態**：`Draft` (已整合開發者所有釐清結論)  
- **推進關卡**：請開發者確認本階段內容是否無誤，可否定稿 `P00` 並進入三大分流層級評估？
