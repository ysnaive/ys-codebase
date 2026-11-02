# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:space` 通用檔案空間與指紋快取底座模組可行性、效益與架構合理性調研  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Umbrella  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對外部提交之「`module:space` 通用檔案空間與指紋快取底座模組概念設計報告」，開啟專項技術調研，客觀評估方案之效益、可行性與合理性；定案後原地升級為分類型主計畫（`Umbrella`）推進實作與遷移。
- **核心目標**：
  1. 對照 `ys-codebase` v1.2.1 真實原始碼（`knowledge-db`、`core`、`server`、`agents-workflow`），完成 `R01` 效益評估、`R02` 盲眼 API 設計與 `R03` 生態系前置契約定案。
  2. 於 `sub_01_space_module_core` 建置 `module:space@1.0.0.0`（含分級雜湊 `hash_policy`、`YFP2` 快照、多消費者獨立水位線、`watchdog` 背景監聽與 5 個 CLI 指令）。
  3. 於 `sub_02_knowledge_db_space_migration` 採用 `/code-optimizer` **`Mode A（收斂期 / 允許破壞性清理）`** 與 **`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`**，將 `knowledge-db` 空間與掃描層 100% 遷移至 `module:space` 單一正統入口。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `ys_codebase/source/knowledge-db/knowledge_db/space.py`（208 行）：雙軌空間聚合與 URI 解算（將於 `sub_01` 泛化上提、`sub_02` 物理移除）。
  - `ys_codebase/source/knowledge-db/knowledge_db/scanner.py`（430 行）：`BinarySnapshotManager (YFP1)` 與 `FingerprintScanner`（將於 `sub_01` 升級為 `YFP2` + 多消費者游標、`sub_02` 物理移除）。
  - `ys_codebase/source/knowledge-db/knowledge_db/service.py`（336 行）：`KnowledgeDBServiceWorker` 背景監聽（將於 `sub_01` 升級為 `SpaceWatcherServiceWorker`、`sub_02` 改為 `hook.space.py` 事件訂閱並物理移除舊 Worker）。
- **邊界排除 (Explicitly Excluded)**：
  - 跨模組 `.gitignore` 受管區塊服務不納入 `module:space`。
  - `agents-workflow` 空間整合列為 `sub_03_agents_workflow_space_integration`（`Deferred`），暫不納入本輪實作，留待後續討論。
- **架構影響範圍**：新增 `ys_codebase/source/space/`、重構 `ys_codebase/source/knowledge-db/`、更新 `ys_codebase/config/` 空間宣告。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 調研評估四維度框架與三階段報告 (`R01` ~ `R03`)**：完成 `R01_module_space_evaluation.md`（保留分級雜湊 `hash_policy` 與直接依賴 `watchdog>=4.0.0`）、`R02_space_api_and_architecture_design.md`（盲眼子代理第一性原理 API 與 `merkle_root` 設計）及 `R03_ecosystem_contracts_and_cli_design.md`（`contributes/_format.json`、5 個 CLI 指令、`YFP2` 快照與 `Mode A` 遷移契約）。
- **[P00:DR-02] 原地升級為 Umbrella 主計畫與 `/code-optimizer` `Mode A` + `軌道 3B/2B` 裁決**：
  - 開發者拍板採納 `R01~R03` 契約，將本計畫原地升級為 `Umbrella` 主計畫（`umbrella_overview.md`）。
  - 契約三（`knowledge-db` 遷移）採 `/code-optimizer` **`Mode A（收斂期 / 允許破壞性清理）`** 進行重構審視（因引入全新模組依賴屬 minor 以上版本迭代，不保留薄轉發殼層或相容別名）。
  - 執行軌道採用 **`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`**，且依開發者指示將 `agents-workflow` 排除於首波之外，額外列為 `sub_03` 後續再討論。

---

## 3. 開放議題與確認紀錄

- 已完成 `R01` ~ `R03` 定案並建立 `umbrella_overview.md`、`sub_01_space_module_core` 與 `sub_02_knowledge_db_space_migration`（含盲眼子代理 `R01_code_optimization_audit.md` 診斷）。

