# 需求語意澄清與架構範疇討論書 (Phase 0: Semantic Requirements)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 原始需求摘要 (Raw User Request)

> *「1. 是（建立統一 core.config SDK）  
> 2. 任何需要 config 的模組，需於 source 定義預設模板:  
>    - configurable/config.project.json  
>    - configurable/config.local.json  
> 3. 需要（提供 config CLI 工具鏈）  
> 4. 添加新的 config 類: contribute。當使用者在專案特化層級想對 `<mod>` 進行注入時 (例如特化 workflow)，需於該 mod config 資料夾提供 contribute.json (禁止 local 級，皆必須受 git 追蹤，不同於 config，注入可能產生不同原碼結果)」*

---

## 2. 核心決策記錄 (Decision Records)

- **[sub_02:P00:DR-01] 確立 `core.config` 統一 SDK**：在 `core` 模組建立 `core.config` 模組/門面，提供 `get(module, key, default=None)`、`get_all(module)`、`set(module, key, value, local=False)` 等標準 API，底層自動完成 `config.local.json` (Tier 1) > `config.project.json` (Tier 2) 的雙層深層合併與快取自愈。
- **[sub_02:P00:DR-02] 確立 `configurable/` 標準模板目錄**：模組若具備預設配置模板，一律存放於標準目錄：
  - `source/<module>/configurable/config.project.json` (預設專案組態)
  - `source/<module>/configurable/config.local.json` (預設本機覆蓋模板)
  - `source/<module>/configurable/contribute.json` (選填，若模組提供預設專案特化注入模板)
  徹底廢除散落於源碼根目錄的 `config.*.json`。
- **[sub_02:P00:DR-03] 部署引擎適配 `configurable/` 結構**：`core.engine.PackageManager.act_deploy_configs_from_modules()` 升級為掃描 `module://<mod>/configurable/` 目錄，執行 `_deep_infill_dict` 注入至 `config://<mod>/`，並物理刪除 runtime 空間之 `configurable/` 檔案以維護純淨性。
- **[sub_02:P00:DR-04] 消費端 100% 收斂至 Config SDK**：全生態系模組（`core.uri`、`knowledge-db`、`agents-workflow` 等）徹底移除手寫開啟檔案、JSON load 與路徑 fallback，100% 透過 `core.config` SDK 存取。
- **[sub_02:P00:DR-05] 實作 `config` CLI 專屬工具鏈**：在 `core` 模組提供標準 CLI 指令體系：
  - `python yscb.py config list [--mod=<module>]`：列出全系統或指定模組的配置狀態（含 Local 覆蓋標記）。
  - `python yscb.py config get <module> [key]`：讀取指定模組/鍵值之有效設定。
  - `python yscb.py config set <module> <key> <value> [--local]`：寫入或更新專案或本機設定檔。
- **[sub_02:P00:DR-06] 專案特化 Contributes 注入專用類別 (`config://<mod>/contribute.json`)**：
  - **職責分離**：將「模組運行組態 (`config.*.json`)」與「專案特化擴充注入 (`contribute.json`)」嚴格分離。
  - **Git 剛性追蹤與禁止 Local 級**：當下游專案欲對目標模組 `<mod>` 進行特化擴充注入時，必須建立於 `config://<mod>/contribute.json`（對應 `config/<mod>/contribute.json`）。**🚨 剛性禁止 `contribute.local.json`，所有注入檔案 100% 必須受 Git 版本控制追蹤**，因為注入會影響工作流編譯與程式碼產物。
  - **聚合引擎適配**：`core.contributes.ContributesAggregator` 階層 ② (專案特化覆蓋) 升級為專門讀取 `config://<target>/contribute.json`，不再自 `config.project.json`/`config.local.json` 讀取。

---

## 3. 功能範疇與非功能性要求 (Scope & NFR)

### 3.1 包含範疇 (In-Scope)
1. **資產目錄結構遷移**：遷移現有 `core`、`knowledge-db`、`agents-workflow` 的 `config.project.json` 至各自的 `configurable/config.project.json`。
2. **核心 SDK 實作**：`source/core/core/config.py`，提供型別標註、Local>Project 雙層深層合併、Auto-Healing 與點分隔（Dot-notated）巢狀鍵值存取。
3. **專案特化 `contribute.json` 規範與聚合引擎升級**：更新 `core/contributes.py` 階層 ② 讀取 `config://<target>/contribute.json`（強制 Git 追蹤、無 Local 級）。
4. **部署引擎與種子注入重構**：升級 `core.engine.PackageManager` 適配 `configurable/` 目錄。
5. **消費端重構**：重構 `source/core/core/uri.py`、`source/knowledge-db/knowledge_db/space.py`、`source/agents-workflow/agents_workflow/targets.py`、`publisher.py`、`initializer.py`。
6. **CLI 工具鏈與 Contributes 註冊**：實作 `source/core/scripts/cli.py` 的 `config` 子指令，並於 `source/core/contributes/core.json` 註冊 CLI Commands 與防呆手冊。
7. **測試套件更新與全模組回歸**：新增 `test_config.py`，更新 `test_contributes.py` 驗證 `contribute.json`，全模組沙盒回歸 100% Passed。

### 3.2 不包含範疇 (Out-of-Scope)
- 外部遠端組態中心同步（如 Consul / ZooKeeper 等），本階段維持純檔案與語意空間 `config://`。

---

## 4. 分流層級建議 (Track Recommendation)

- **推薦模式**：**(Recommended) Level 1 (Full Track)**
- **評估理由**：涉及微內核 SDK (`core.config`)、專案特化 `contribute.json` 體系建立、全模組 `configurable/` 結構遷移、全模組消費端收斂與 CLI 工具鏈擴充，影響層面橫跨全模組，以 Full Track 嚴謹推進。
