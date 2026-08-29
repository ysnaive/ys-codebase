# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：`workflow_and_agents_guidance_optimization`  
> 建立日期：2026-08-29  
> 狀態：In Progress  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  全面檢視並增量優化專案的工作流體系 (`agents-workflow`)、SOP 指南規範、JIT 引導資產與 Agent 行為指引，提升 Agent 在各階段的專案默契、防呆執行力與協同開發效率。
- **架構邊界**：
  - 本主計畫為 Level 2 Umbrella 總綱，負責子計畫拆分規劃、里程碑排期與跨子計畫進度追蹤。
  - 後續將跟隨開發進度增量開立與更新所屬之 `sub_XX` 子計畫。
  - 所有具體修改均在各自所屬子計畫中依照 SOP 閉環執行，嚴格遵守最多兩層目錄約束（`主計畫/sub_XX/`）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_cli_guidance_and_privilege_optimization` | Full Track | `Completed` | **CLI 指令引導與三級權限防呆優化**：擴充 `contributes.core.commands` 資料結構（`tier`, `phases`），動態生成帶權限標籤手冊與各 Phase JIT 模板註解引導 |
| **sub_02** | `sub_02_uri_placeholders_and_workflow_path_healing` | Full Track | `Completed` | **佔位符解析完全替代與工作流路徑治癒**：修復 `compiler.py` Stage 2 佔位符反引號剝除邏輯、工作流讀檔動線全面改用 `__${...}__`、修復非標準協議前綴與 Dogfooding 同步 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (CLI 指令引導與三級權限防呆優化)**：完成 `sub_01` 實作，建立 commands SSOT 結構擴充、動態 JIT 指令注入與全生態系 commands 標註。
- [x] **里程碑 2 (佔位符解析完全替代與工作流路徑治癒)**：推進 `sub_02`，修復 Stage 2 佔位符解析邏輯、全生態系工作流路徑治癒、協議前綴修正與自引用物化驗證。


