# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：`module:space` 通用檔案空間底座模組研發與生態系收斂遷移  
> 建立日期：2026-11-02  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  1. 依據 [`R01_module_space_evaluation.md`](R01_module_space_evaluation.md)、[`R02_space_api_and_architecture_design.md`](R02_space_api_and_architecture_design.md) 與 [`R03_ecosystem_contracts_and_cli_design.md`](R03_ecosystem_contracts_and_cli_design.md) 三階段調研定案契約，正式建立 `ys-codebase` 第 6 枚核心基座模組 `module:space@1.0.0.0`（`ys_codebase/source/space/`），收斂「命名空間配置解算（Contributes + URI）」、「雙階段指紋與四模雜湊策略 (`hash_policy`)」、「多消費者獨立水位線二進位快照 (`YFP2` + `cursors/<consumer_id>.json`)」與「原生 `watchdog` 背景增量監聽 (`space-watcher`)」。
  2. 針對 `knowledge-db` 啟動 `/code-optimizer` **`Mode A（收斂期 / 允許破壞性清理）`** 與 **`[軌道 3B / 2B：主代理 + 盲眼子代理協同]`**，將空間掃描與背景監聽職責 100% 移交 `module:space` 單一正統入口，物理刪除重複基建並消除跨模組耦合。
- **架構邊界**：
  - **納入本階段實作 (`sub_01` ~ `sub_03`)**：`ys_codebase/source/space/` 全新模組建置、`ys_codebase/source/knowledge-db/` 遷移重構、`ys_codebase/config/space/contribute.json` 宿主空間遷移，以及 `sub_03` `knowledge-db` 功能細節優化。
  - **暫緩納入 (`sub_04` 後續討論)**：`agents-workflow` 之 `workflows_space` 指紋整合延後列為 `sub_04`（`Deferred`），待 `sub_03` 完成後再行討論啟動。
  - **明確排除**：跨模組通用 `.gitignore` 受管區塊服務與無關外部工具假設。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | [`sub_01_space_module_core`](sub_01_space_module_core/P07_walkthrough.md) | Full Track | `Completed` | 建置 `ys_codebase/source/space/` (`v1.0.0.0`)：實作 `SpaceManager`、`FingerprintScanner`（含 `adaptive/full_hash/stat_only/lazy_stabilized` 四模雜湊與 Racy-Clean 防護）、`BinarySnapshotManager (YFP2)`、多消費者獨立水位線 (`cursors/<consumer_id>.json`)、`merkle_root()`、`SpaceWatcherServiceWorker` (`watchdog>=4.0.0`) 及 5 個 CLI 指令 (`status/scan/files/diff/clean`) |
| **sub_02** | [`sub_02_knowledge_db_space_migration`](sub_02_knowledge_db_space_migration/P07_walkthrough.md) | Full Track | `Completed` | 採 `/code-optimizer` (`Module Scope: knowledge-db` × `Mode A` × `軌道 2B/3B`) 執行 `R01_code_optimization_audit.md` 五維度診斷與無損重構：改由 `from space import ...` 單一正統入口驅動增量同步，物理移除 `knowledge_db/{space,scanner,service}.py` 與 `contributes/server.json`，新增 `scripts/hook.space.py` 並遷移 `config/space/contribute.json`（淨削減 `-973` LOC） |
| **sub_03** | [`sub_03_knowledge_db_feature_refinement`](sub_03_knowledge_db_feature_refinement/P07_walkthrough.md) | Full Track | `Completed` | `knowledge-db` 功能細節優化：恢復專屬常駐 `KnowledgeDBServiceWorker` 兩階段微批次向量自癒、背景自動下載向量模型、`is_worker_busy() -> int`（已運行 ms）探針與預設 `jit_vector_timeout_ms=3000` 動態剩餘等待降級、以及 `knowledge-db status` 直白詳盡化升級 |
| **sub_04** | [`sub_04_rename_to_file_space`](sub_04_rename_to_file_space/P07_walkthrough.md) | Full Track | `Completed` | 全面將 `space` 更名為 `file-space`（`file_space` / `FileSpace`）：基於 `git diff` 腳本掃描、過濾非本次 diff 內容、批量替換與反查驗收 |
| **sub_05** | [`sub_05_contributes_format_merge_strategy`](sub_05_contributes_format_merge_strategy/P07_walkthrough.md) | Full Track | `Completed` | `core.contributes` 格式驅動合併策略（`_format.json` Inline DSL `\| merge/extend/replace/unique` 與 `__providers__` 完整來源追蹤）及 `FileSpaceManager` 空間來源 (`origin(A)` / `merged(A, B, ...)`) 精確判定修正 |
| **sub_06** | [`sub_06_fingerprint_and_self_healing_audit`](sub_06_fingerprint_and_self_healing_audit/P07_walkthrough.md) | Full Track | `Completed` | 全生態系（`core`、`file-space`、`knowledge-db`、`agents-workflow`）指紋快取與熱自癒機制完善度審視 (`R01`)、Devil's Advocate 反向查驗與自癒死角修復 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0（前置調研定案）**：完成 `R01` 效益與可行性評估、`R02` 盲眼 API 架構設計與 `R03` 生態系前置契約設計。
- [x] **里程碑 1（`sub_01` 核心底座落成）**：完成 `module:space@1.0.0.0` 研發、合規檢查、單元測試與 `@build` 熱部署驗證。
- [x] **里程碑 2（`sub_02` 知識庫 `Mode A` 收斂遷移）**：完成 `knowledge-db` `/code-optimizer` `R01` 診斷與 `Mode A` 破壞性清理重構，通過雙模組聯合回歸測試與常駐熱自癒驗證。
- [x] **里程碑 3（`sub_03` 知識庫功能細節優化）**：完成 `knowledge-db` 功能細節優化需求釐清與落地驗收。
- [x] **里程碑 4（`sub_04` 全面更名為 `file-space` 重構與驗收）**：透過 `git diff` 範圍腳本化替換與反查，將 `space` 全面更名為 `file-space` 並通過全套測試。
- [x] **里程碑 5（`sub_05` `contributes` 格式驅動合併與來源修正）**：完成 `_format.json` 合併策略 DSL、`__providers__` 來源追蹤與 `FileSpaceManager` 來源判定修復。
- [x] **里程碑 6（`sub_06` 全系統指紋與自癒機制調研審視与修復）**：全面盤點與審計當前全生態系指紋快取與自癒機制是否完善，產出 `R01` 調研報告並透過 Devil's Advocate 反向查驗與 `/auto` 完成四大模組自癒死角修復。

