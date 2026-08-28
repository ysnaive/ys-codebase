# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Draft  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | CLI `--snippet` / `-s` 旗標支援 | 於 `python yscb.py knowledge-db search` 新增 `--snippet`（短旗標 `-s`，別名 `--preview`），預設為 `False`，維持極簡單行模式向前相容。 | P0 | [P00:DR-02] |
| **FR-02** | 符號代碼片段 (Code Snippet) 提取 | 啟用 `--snippet` 時，根據命中符號之 `file_path` 與 `line_number`，延遲讀取原始碼並提取定義所在區塊（包含定義行與前後 3~5 行上下文），附帶行號標註排版。 | P0 | [P00:DR-02] |
| **FR-03** | 符號 Docstring / 摘要段落高亮呈現 | 在 Snippet 排版中，若符號具有 `docstring`，於代碼片段上方高亮顯示 Docstring 第一行或簡短摘要，使 Agent 無需開啟檔案即可掌握函式功能與參數約定。 | P0 | [P00:DR-02] |
| **FR-04** | Workspace 相對路徑正規化 | 搜尋結果輸出之檔案路徑自動正規化為以工作區根目錄為錨點之標準相對路徑（杜絕 `ys_codebase/source/` 與 `source/` 混淆），且格式對齊 IDE 點擊跳轉標準 `#<rank:02d> <rel_path>:<line_number>`。 | P0 | [P00:DR-03] |
| **FR-05** | JSON 結構化輸出擴充 Snippet 欄位 | 當指定 `--json` 且啟用 `--snippet` 時，在各搜尋結果物件中新增 `"snippet"`（含 `code`, `start_line`, `end_line`）與 `"docstring"` 欄位，供自動化工具鏈解析。 | P1 | [P00:DR-02] |
| **FR-06** | Agents-Workflow 注入資產與 CLI 指引同步更新 | 同步更新 `knowledge-db` 注入至 `agents-workflow` 的規範與資產（`KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 以及 `contributes/core.json`），使 Agent 能直接習得 `--snippet` 語法並在工作流引導下主動調用代碼預覽。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 原始檔案缺失或無讀取權限 | 倒排索引中存在該符號但磁碟原始檔案已遺失或權限不足時，Snippet 提取優雅降級為 `[Snippet Unavailable: File not found]`，嚴禁拋出未捕捉例外或中斷檢索結果輸出。 |
| **EC-02** | 行號缺失或超出檔案總行數 | 符號之 `line_number <= 0` 或大於實體檔案總行數時，自動截斷保護在有效邊界 `[1, total_lines]`；若無有效行號則僅顯示 Docstring 或略過代碼片段。 |
| **EC-03** | 超長函式或大檔案 Snippet 膨脹保護 | 單一函式或類別代碼極長時，限制 Snippet 最多輸出 10~12 行，超出部分標記 `... (X lines omitted)`，避免衝爆終端排版或 LLM 上下文。 |
| **EC-04** | Non-TTY 與無色彩終端環境 | 在 CI 或輸出重定向環境下，自動偵測 TTY，輸出純文字無 ANSI escape code 之 Snippet，保障輸出純淨度。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴約束 | 100% 基於 Python 3.9+ 原生標準庫（`os`, `sys`, `pathlib`, `linecache`），嚴禁引入任何第三方相依。 |
| **NFR-02** | 延遲 I/O 效能 | 未指定 `--snippet` 時保持 0 額外磁碟 I/O；指定 `--snippet` 時僅對最終 Top-K 命中結果進行延遲行讀取，搜尋延遲增加 $< 5 \text{ ms}$。 |
| **NFR-03** | 測試覆蓋率 | 新增完整單元與邊界測試（FT-01~05, ET-01~04），模組測試與全系統沙盒回歸 100% Passed。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 專案呈現 Dogfooding 自引用架構，源碼空間 `ys_codebase/source/knowledge-db/` 才是唯一修改 SSOT，運行端 `modules/` 為產物，修改必須在 `source/` 進行。
- **`[!CAUTION]`** 提取 Snippet 時，應使用 `linecache` 或以 `utf-8` / `errors="replace"` 安全開啟檔案，防範非 UTF-8 編碼檔案引發解碼崩潰。
