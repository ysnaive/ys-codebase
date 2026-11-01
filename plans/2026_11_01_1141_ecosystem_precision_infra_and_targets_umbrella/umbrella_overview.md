# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：生態系檢索精準度、基礎設施韌性與多平台發布目標擴充統籌計畫 (ecosystem_precision_infra_and_targets_umbrella)  
> 建立日期：2026-11-01  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  1. **`sub_01` (`knowledge-db` 檢索精準度、拓撲消歧與多語言解析專項)**：收斂 `TODO-04`, `TODO-08`, `TODO-09`, `TODO-14`, `TODO-15`，根治 `TopologyLinker` 三處靜態消歧漏洞、對齊 `.watcher_active` / `.watcher_dirty` 狀態時序、支援 `SpaceDef` 宣告式檢索權重 (`weight`)、修復 C#/C++ AST `visibility` 修飾詞解析與 C# 跨檔 `partial class` 成員聚合，並於未安裝 `agents-workflow` 時隱藏 Agent 專屬提示。
  2. **`sub_02` (`core / dev / server` 基礎設施韌性與跨分支自癒專項)**：收斂 `TODO-03`, `TODO-07`, `TODO-11`, `TODO-12`，修復 `yscb.py` / `installer.py` `cmd_restore` 版號比對死迴圈、將 `ensure_venv` / `_bootstrap_pip` 改拋 `PipInstallError`、於報錯尾端注入 `[Agent Directive]` 技能路由、支援 Windows 安裝前主動通知 Server 釋放句柄與 `.old_*` 延遲清理，並完善 `core.vfs` 實體代理邊界文檔。
  3. **`sub_03` (主流 AI 開發平台 `release_target` 矩陣擴充與並聯渲染專項)**：落地 `multi_platform_release_targets_expansion_roadmap.md` 與 `TODO-05`, `TODO-06`，解決多 `release_target` 共用實體路徑之專有名詞與路由連結並聯渲染、將環境變數嗅探正規化為宣告式規則，並一步到位擴充 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 發布目標。
- **架構邊界**：
  - 涵蓋 `ys_codebase/source/{knowledge-db,core,dev,server,agents-workflow}/`、`yscb.py` 與 `docs/`。各子計畫獨立完成實作、單元測試、`@build` 熱部署與文檔同步。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_knowledge_db_precision_and_weights` | Full Track | `Completed` | `TODO-04`, `TODO-08`, `TODO-09`, `TODO-14`, `TODO-15`：`knowledge-db` 拓撲消歧、Watcher 時序、宣告式空間權重 (`weight`)、C#/C++ `visibility` 與 C# `partial class` 跨檔聚合 |
| **sub_02** | `sub_02_core_infra_resilience` | Full Track | `Completed` | `TODO-03`, `TODO-07`, `TODO-11`, `TODO-12`：`cmd_restore` 版號比對、`PipInstallError` 降級、報錯 `[Agent Directive]`、Windows 安裝前 Server 句柄釋放與 `.old_*` 延遲清理 |
| **sub_03** | `sub_03_multi_platform_release_targets` | Full Track | `Completed` | `multi_platform_release_targets_expansion_roadmap` + `TODO-05` + `TODO-06`：同路徑多 Target 並聯渲染與 Warning、宣告式宿主環境嗅探、8 大預設 `release_target` 擴充 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `knowledge-db` 拓撲消歧、Watcher 時序、空間權重 `weight` 與 C#/C++ AST 解析強化，全量測試通過並熱部署 `@build`。
- [x] **里程碑 2 (`sub_02`)**：完成 `core / dev / server / yscb.py` 跨分支 `cmd_restore`、Windows 句柄釋放、報錯 `[Agent Directive]` 與 `PipInstallError` 加固，全量測試通過並熱部署 `@build`。
- [x] **里程碑 3 (`sub_03`)**：完成 `agents-workflow` 同路徑多 Target 並聯渲染、宣告式環境嗅探與 8 大預設 `release_target` 矩陣擴充，全量測試通過並完成 Umbrella 總結案。

