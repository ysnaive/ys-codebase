# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`sub_05_project_readme_and_quickstart`  
> 建立日期：2026-08-29  
> 所屬主計畫：`user_guidance_and_module_readme_enhancement`  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  站在**專案使用者與 AI Agent 接入視角**，重構專案根目錄 [`README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/README.md)。
  核心結構與規範：
  1. **專案概覽與 Agent 醒目提示 (Overview & Agent Guidance)**：
     - 專案核心價值與微核心定位。
     - **🤖 給 AI Agent 的安裝引導提醒**：頂部明確告知 Agent「*若您為 AI Agent 且被要求將本專案/功能安裝至目標環境，請直接跳轉參閱後續 `# 🛠️ 安裝與快速上手指南 (Installation Guide)` 章節*」。
  2. **全景架構與生態系概覽 (Architecture & Ecosystem)**：
     - 展示微核心、擴充模組與工作流生態系全景架構圖（不附模組內部手冊導航，維持專案宏觀定位）。
  3. **標準基礎安裝流程 (Standard Installation Guide)**：
     - 下游專案引入 YSCB 與 Python 3.9+ 環境要求。
     - 專案根目錄綁定：`python yscb.py config set core project_root ./`（提示路徑以 `yscb.host` 為基準）。
  4. **`agents-workflow` 安裝與設定流程 (Agents-Workflow Setup)**：
     - **模組功能概述**：AI Agent 標準化協同工作流引擎、SOP 0~7 與 6 大計畫分支拓撲、Agent 行為公理與防呆紀律、Slash Commands 體系。
     - **一鍵初始化預設填充內容 (`--init-default`)**：
       - 計畫目錄：`paths.plans` ➔ `project://plans`
       - 知識庫目錄：`paths.docs` ➔ `project://docs`
       - 封存目錄：`paths.archived` ➔ `workflow.plans://archived`
       - 路線圖目錄：`paths.roadmap` ➔ `workflow.plans://roadmap`
     - **手動修改路徑方案**：`python yscb.py config set agents-workflow paths.plans <custom_path>` 等。
     - **🚨 給 Agent 的剛性提示**：**在執行一鍵初始化前，必須先和開發者確認一鍵初始化的預設填充內容（`paths.plans: project://plans`, `paths.docs: project://docs` 等），詢問是否需要修改！**
     - **初始化與發布**：`python yscb.py agents-workflow plan --init-default` 與 `python yscb.py agents-workflow release`。
  5. **`knowledge-db` 安裝與設定流程 (Knowledge-DB Setup)**：
     - **模組功能概述**：多語言 AST 符號解析器、雙階增量指紋引擎、多欄位加權 BM25 語意檢索與代碼切片預覽。
     - **專案源碼空間 (Source Code Space) 設定說明**：如何在專案設定中為目標源碼目錄設定 `source` space（指定 includes 包含目錄與 file_patterns 副檔名過濾）。
     - **🚨 給 Agent 的剛性提示**：**在完成安裝與初次構建索引前，Agent 必須主動詢問開發者：「請問專案中是否有需要納入檢索的特定原始碼目錄或空間（例如 `src/`, `lib/` 等）需要先完成設定？」**
     - **掃描、構建索引與驗證**：`python yscb.py knowledge-db scan && python yscb.py knowledge-db index` 與 `status`/`search` 驗證。
- **影響範圍**：
  - 修改：[`README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/README.md)（專案根目錄）
- **Fast Track 4 維度確認**：
  - [x] 修改行數預估 $\le 100$ 行 (文檔型任務)
  - [x] Public API 契約 0 變更
  - [x] 架構自包含、零外部 `docs/` 斷鏈
  - [x] 既有測試/CLI 可 100% 驗證指令正確性

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：依據上述精確結構重構專案根目錄 [`README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/README.md)。
- **測試案例**：
  - `FT-01`：驗證文檔內所有示範之 CLI 安裝、路徑設定與知識庫空間指令均可在真實環境中正常解析與運作。
  - `FT-02`：以 `python yscb.py agents-workflow plan verify` 檢核計畫完整性與合規狀態。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於專案根目錄 `README.md` 產出高品質全景導引文檔，包含頂部 Agent 醒目提示、全景 Mermaid 架構圖、4 大生態系模組職責表、標準基礎安裝流程、`agents-workflow` 安裝/設定與 Pre-flight 確認提示、`knowledge-db` 安裝/源碼空間設定與 Pre-flight 詢問提示、及全域 CLI Cheat Sheet。
- **實機測試日誌**：
  - `dev test --all`：全生態系 4 大模組 **211/211 測試 100% Passed**（耗時 11.25s）。
  - `uri check`：全系統 URI 協定狀態 HEALTHY。
  - `python yscb.py list` & `status`：所有模組解析運行正常。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_2035_user_guidance_and_module_readme_enhancement/sub_05_project_readme_and_quickstart` 驗證 100% Passed。
- **結案狀態**：`Completed`
