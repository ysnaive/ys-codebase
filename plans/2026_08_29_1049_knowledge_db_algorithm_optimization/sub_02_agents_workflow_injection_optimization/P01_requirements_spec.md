# 需求規格說明書 (Requirements Specification)

> 功能名稱：`sub_02_agents_workflow_injection_optimization` (agents workflow 注入內容優化)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 剛性檢索決策樹注入 | 於 `KnowledgeAgentsStandards.md` 注入明確、可執行的代碼探索分流決策樹：<br/>1. 已知明確唯一簽章 (如 `foo.doSomething`) ➔ 調用原生 `grep_search`<br/>2. 具備明確分類/模組概念 ➔ 複合關鍵詞 `knowledge-db search '<詞組>' -s`<br/>3. 廣義需求或探索 ➔ 語意化敘述 `knowledge-db search '<敘述>' -s` | P0 | [P00:DR-02] |
| **FR-02** | 定向閱讀與非暴力廣蒐規範 | 於 `KnowledgeAgentsStandards.md` 明確界定工具定位：使用 `knowledge-db search -s` 快速收斂候選符號與行號切片，僅在需要完整上下文時進行極小範圍定向閱讀 (`view_file`) 或精準 grep，嚴禁盲目發起全域暴力正則/廣蒐 | P0 | [P00:DR-03] |
| **FR-03** | 需求與調研階段 JIT Guild 升級 | 於 `phase00_guild.md` 與 `research_guild.md` 強化 `-s` (`--snippet`) 參數指引與複合關鍵詞檢索建議，提醒 Agent 定向閱讀思維 | P0 | [P00:DR-02]<br/>[P00:DR-05] |
| **FR-04** | 結案 JIT 指引過時敘述移除 | 於 `phase07_guild.md` 移除強制手動執行 `python yscb.py knowledge-db index`，改為說明知識庫已支援 JIT 查詢智能變更感知與背景熱自愈（可選全量校準） | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 檢索未命中候選結果 | 當 `knowledge-db search` 找不到符號時，指引 Agent 放寬關鍵詞組合或更換語意同義詞重新檢索，嚴禁直接退回盲目暴力全專案正則遍歷 |
| **EC-02** | 注入 Token 標籤與 Markdown 結構安全 | 確保所有修改後之資產檔案語法標準，相容 `agents-workflow` 之 `__@{...}__` 模板注入引擎與 `AGENTS.md` 軟合併機制 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | Token 開銷控制 | 新增之決策樹與規範描述精練直觀，注入後 `AGENTS.md` Token 增量控制在 $\le 10\%$ |
| **NFR-02** | 回歸與相容性 | 100% 通過全專案 198+ 單元測試，且 `agents-workflow` 生成流程無損相容 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 遵循專案三層空間邊界：所有修改 100% 必須在空間 ① `ys_codebase/source/knowledge-db/assets/` 進行，嚴禁手動編輯空間 ③ 之產物。
- **`[!IMPORTANT]`** 修改完成後必須依序執行 Dogfooding 四步流水線（Build ➔ Regression ➔ Sync ➔ Agents-Workflow 重新渲染）。
