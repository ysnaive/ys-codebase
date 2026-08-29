# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`sub_04_knowledge_db_readme`  
> 建立日期：2026-08-29  
> 所屬主計畫：`user_guidance_and_module_readme_enhancement`  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  站在**純用戶與模組 Release 消費者視角**（在專案環境中執行 `python yscb.py install knowledge-db` 獲得多語言符號解析與 BM25 語意檢索引擎的開發者與 Agent），於模組源碼目錄撰寫 100% 自包含 (Self-Contained) 的 `knowledge-db` 模組導引手冊 [`source/knowledge-db/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/knowledge-db/README.md)。
  涵蓋：
  1. **模組角色與核心引擎架構**：多語言 AST 符號解析器、雙階增量指紋比對引擎、多欄位 BM25 語意檢索引擎、軟工中英雙向同義詞庫 (`ThesaurusEngine`) 與 CamelCase/snake_case 分詞器 (`CodeTokenizer`)。
  2. **日常檢索決策樹與 `--ftype` 路由規範**：
     - 代碼精確檢索：`--ftype=c,cpp,py`
     - 規範與文檔檢索：`--ftype=md`
     - 廣義探索/概念檢索：不帶 `--ftype`
     - 即時代碼切片預覽：強制附加 `-s` / `--snippet` 獲取行號與上下文
  3. **強制工具替代原則 (Search Tool Substitution)**：
     - 以 `knowledge-db search` 作為 Agent 與開發者第一反射工具，替代盲目 `grep_search` 或整檔 `view_file`。
  4. **純用戶全量 CLI 指令集速查**：
     - 語意檢索：`knowledge-db search <query> [-s|--snippet] [--ftype=<types>] [-n <top_k>] [--json]`
     - 狀態查詢：`knowledge-db status`
     - 指紋掃描：`knowledge-db scan [--force]`
     - 倒排索引：`knowledge-db index [--rebuild]`
     - 符號打包：`knowledge-db bundle`
     - 快取清理：`knowledge-db clean`
  5. **Python SDK 快速上手 (Public API Quickstart)**：
     - `from knowledge_db.engine import KnowledgeEngine`
     - `engine.search()`, `engine.status()`, `engine.scan()` 範例代碼。
  6. **實用 Cookbook**：初次構建索引、日常快速定位符號與切片即時確認、跨語言專案檢索。
- **影響範圍**：
  - 新增：[`source/knowledge-db/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/knowledge-db/README.md)（隨模組發布打包分發給所有下游用戶）
- **Fast Track 4 維度確認**：
  - [x] 修改行數預估 $\le 100$ 行 (文檔型任務)
  - [x] Public API 契約 0 變更
  - [x] 架構自包含、零外部 `docs/` 依賴
  - [x] 既有測試/CLI 可 100% 驗證指令正確性

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：撰寫並交付 100% 自包含的 [`source/knowledge-db/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/knowledge-db/README.md)。
- **測試案例**：
  - `FT-01`：驗證文檔內所有示範之 `python yscb.py knowledge-db` CLI 指令均能在真實環境中無誤解析與執行。
  - `FT-02`：以 `dev test knowledge-db` 驗證模組測試 100% 通過且無回歸。
  - `FT-03`：以 `python yscb.py agents-workflow plan verify` 檢核計畫完整性與合規狀態。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於 `source/knowledge-db/README.md` 產出完整自包含說明文檔，包含四層架構全景圖、日常檢索決策樹 Mermaid 圖與強制替代原則、全量 CLI 指令速查矩陣、Python SDK `KnowledgeEngine` 調用範例及 3 大典型情境 Cookbook。
- **實機測試日誌**：
  - `dev test knowledge-db`：59/59 測試全數通過（3 契約測試 + 56 自訂單元測試，耗時 2.28s）。
  - `dev check knowledge-db`：合規靜態檢查 100% Passed。
  - CLI 指令驗證（`status`, `search -s`, `index` 等）：解析執行 100% 正常。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_2035_user_guidance_and_module_readme_enhancement/sub_04_knowledge_db_readme` 驗證 100% Passed。
- **結案狀態**：`Completed`
