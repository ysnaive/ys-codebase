# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：`knowledge_db_algorithm_optimization`  
> 建立日期：2026-08-29  
> 狀態：In Progress  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  全面審查與增量優化 `knowledge-db` 知識庫模組的演算法深度、檢索召回精準度、分詞切片強韌性、AST 符號邊界截取能力與儲存快取效率，建立強健、高效、零破壞性回歸的代碼知識檢索體系。
- **架構邊界**：
  - 本主計畫為 Level 2 Umbrella 總綱，負責子計畫拆分規劃、里程碑排期與跨子計畫品質驗收。
  - 所有具體代碼修改、測試案例與文件變更均在各自所屬的 `sub_XX` 子計畫中閉環執行。
  - 專案嚴格遵守最多兩層目錄約束（`主計畫/sub_XX/`）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_jit_invalidation_and_hot_healing` | Full Track | `Completed` | **JIT 查詢智能變更感知與索引熱自愈**：在檢索入口實作輕量 mtime 變更嗅探，支援檔案異動時無感增量熱自愈並回傳最新搜尋結果，索引維持 `cache://` 儲存 |
| **sub_02** | `sub_02_agents_workflow_injection_optimization` | Full Track | `Completed` | **Agents-Workflow 注入內容與引導優化**：建立剛性檢索決策樹（簽章/複合詞/語意分流）、確立定位至定向閱讀非暴力廣蒐哲學，並更新 Phase 0 / Research / Phase 7 JIT 引導資產 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (JIT 變更感知與索引熱自愈)**：完成 `sub_01` 實作與驗證，徹底根絕跨開發者異地同步過期問題與 Git 二進位衝突。
- [x] **里程碑 2 (Agents-Workflow 注入內容優化)**：完成 `sub_02` 注入資產修訂與 `agents-workflow` 渲染同步。


