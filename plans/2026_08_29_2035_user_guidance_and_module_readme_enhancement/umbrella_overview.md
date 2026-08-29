# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：`user_guidance_and_module_readme_enhancement`  
> 建立日期：2026-08-29  
> 狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  在 YS-Codebase 核心功能與生態系擴充完備後，全面補齊面向使用者與開發者的「人因操作引導 (Ergonomics)」與領域概念模型。建立專案級與各子模組級 (`core`, `dev`, `agents-workflow`, `knowledge-db`) 的高階概覽 README、快速上手 (Quickstart) 與 CLI 操作導引手冊。
- **架構邊界與受眾定位**：
  - **純用戶與 Release 消費者視角**：下游專案透過 `python yscb.py install` 安裝模組後僅包含各模組之 Release 發布內容。因此各模組 `README.md` 置於 `source/<module>/README.md`，內容必須 **100% 自包含 (Self-Contained)**，絕不外鏈或依賴專案內部的 `docs/` 知識庫。
  - 本主計畫為 Level 2 Umbrella 總綱（模式 B-1 預先規劃型），負責統籌 5 個子計畫之推進順序與里程碑驗收。
  - 各子計畫遵循最多兩層目錄約束（`主計畫/sub_XX/`），各自獨立依循 SOP 完成規劃、文檔撰寫、測試檢核與交付。
  - 文檔結構嚴格遵循 [`DocumentationStandards.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/modules/agents-workflow/assets/standards/DocumentationStandards.md) 之 7 大知識維度，維持 README 的高階概覽與輕量聚焦。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_module_readme` | Fast Track | `Completed` | **`core` 模組導引手冊**：微核心架構定位、語意空間協議 (`project://`, `yscb://` 等) 使用範例、2x2 組態矩陣配置說明與 Core CLI 指令速查 |
| **sub_02** | `sub_02_dev_module_readme` | Fast Track | `Completed` | **`dev` 模組導引手冊**：Dogfooding 雙軌閉環流水線、模組打包構建、沙盒測試守門 (`dev test`) 與版本發布指令全景指南 |
| **sub_03** | `sub_03_agents_workflow_readme` | Fast Track | `Completed` | **`agents-workflow` 模組導引手冊**：SOP 0~7 開發全生命週期與 6 大計畫分支拓撲、Agent 核心紀律規範、動態 Token 注入體系與 Slash Commands 導覽 |
| **sub_04** | `sub_04_knowledge_db_readme` | Fast Track | `Completed` | **`knowledge-db` 模組導引手冊**：AST 多語言符號解析、向量/語意/符號混合搜尋引擎說明與日常檢索 CLI (`search --ftype`, `scan`, `index`) 實用導引 |
| **sub_05** | `sub_05_project_readme_and_quickstart` | Fast Track | `Completed` | **專案根目錄高階導航與全景快速上手**：全專案根目錄 [`README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/README.md) 重構、整合全景架構圖 (Mermaid)、一鍵安裝/初始化 Quickstart 與全域 CLI 速查表 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`core` 模組 README 建立)**：完成 `sub_01`，產出 `core` 模組架構概覽、空間協議與指令導覽。
- [x] **里程碑 2 (`dev` 模組 README 建立)**：完成 `sub_02`，產出 `dev` 模組雙軌流水線、打包測試與發布指南。
- [x] **里程碑 3 (`agents-workflow` 模組 README 建立)**：完成 `sub_03`，產出 `agents-workflow` 模組 SOP 拓撲、Token 體系與 Agent 紀律手冊。
- [x] **里程碑 4 (`knowledge-db` 模組 README 建立)**：完成 `sub_04`，產出 `knowledge-db` 模組檢索引擎、AST 解析與 CLI 檢索手冊。
- [x] **里程碑 5 (專案根目錄 README 重構與全景快速上手)**：完成 `sub_05`，匯聚 4 大模組成果，重構專案根目錄 `README.md`，建立清晰之全景導覽與 Quickstart。
