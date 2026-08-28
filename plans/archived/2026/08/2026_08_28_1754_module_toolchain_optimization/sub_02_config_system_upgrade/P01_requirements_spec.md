# 需求規格說明書 (Requirements Specification)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 需求詳細說明 | 優先級 | 對應決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **`core.config` 統一 SDK** | 在 `core` 模組建立 `core.config` 門面與管理器，提供 `get(module, key, default=None)`、`get_all(module)`、`set(module, key, value, local=False)`、`reload(module=None)` 等公開 API，支援點分隔（Dot-notated）巢狀鍵值存取。 | **P0** | `[sub_02:P00:DR-01]` |
| **FR-02** | **雙層深層合併與快取自愈** | `core.config` 讀取時自動執行 `Tier 1 (config.local.json)` > `Tier 2 (config.project.json)` 深度遞迴合併，並物化快取至記憶體；當設定檔於磁碟被修改時支援自動/手動自愈刷新。 | **P0** | `[sub_02:P00:DR-01]` |
| **FR-03** | **`configurable/` 模板標準目錄** | 模組若提供預設配置模板，一律存放於 `source/<mod>/configurable/`（`config.project.json`、`config.local.json`、`contribute.json`），遷移全生態系現有散落檔案。 | **P0** | `[sub_02:P00:DR-02]` |
| **FR-04** | **部署引擎自動注入與淨化** | `core.engine.PackageManager.act_deploy_configs_from_modules()` 升級為掃描 `module://<mod>/configurable/`，對 `config://<mod>/` 執行 `_deep_infill_dict` 增量補齊，並物理刪除 runtime 空間之 `configurable/` 檔案維護代碼純淨。 | **P0** | `[sub_02:P00:DR-03]` |
| **FR-05** | **專案特化 `contribute.json` 體系** | `core.contributes.ContributesAggregator` 階層 ② (專案特化覆蓋) 升級為專門讀取 `config://<target>/contribute.json`，**強制受 Git 版本控制追蹤，嚴禁 `contribute.local.json`**。 | **P0** | `[sub_02:P00:DR-06]` |
| **FR-06** | **全生態系消費端 SDK 收斂** | `core.uri`、`knowledge-db/space.py`、`agents-workflow/targets.py`、`publisher.py`、`initializer.py` 徹底移除手寫讀寫代碼，100% 收斂至 `core.config` SDK。 | **P0** | `[sub_02:P00:DR-04]` |
| **FR-07** | **`config` CLI 工具鏈實作** | 於 `core` 模組實作 `config` CLI 子指令體系（`config list`、`config get`、`config set`），並於 `contributes/core.json` 登載防呆手冊。 | **P1** | `[sub_02:P00:DR-05]` |

---

## 2. 非功能性需求 (Non-Functional Requirements)

- **NFR-01 (零第三方依賴)**：`core.config` 100% 基於 Python 原生標準庫（`json`, `os`, `copy`, `typing`）實作。
- **NFR-02 (效能與 I/O 降噪)**：查詢時預設命中記憶體快取（<0.1ms），避免重複從磁碟重複開啟與解析 JSON 檔案。
- **NFR-03 (Dogfooding 空間隔離)**：所有代碼修改嚴格在 `source/` 進行，並透過標準閉環建置、測試與安裝同步。
- **NFR-04 (全系統回歸保證)**：升級後全系統 4 大模組自動化測試 100% Passed。

---

## 3. 邊界條件與異常防護 (Edge Cases & Exception Handling)

- **EC-01 (無 Config 目錄與檔案安全回退)**：若模組從未建立任何 config 檔案，`core.config.get()` 安全返回 `default` 值，不拋出未捕獲例外。
- **EC-02 (損毀 JSON 容錯隔離)**：當 `config.project.json` 或 `config.local.json` 語法損毀時，輸出警告日誌並安全降級，不導致微內核崩潰。
- **EC-03 (型別防禦與單一字串轉型)**：`set()` 寫入時支援型別自動轉型（如字串 `"true"` / `"false"` / 數字 / JSON 物件），並進行安全原子寫入。
- **EC-04 (專案特化 `contribute.local.json` 阻斷防呆)**：聚合引擎若檢測到 `config://<mod>/contribute.local.json` 存在，主動輸出安全警示阻斷或忽略，嚴格貫徹「注入必受 Git 追蹤」鐵律。

---

## 4. 追溯矩陣 (Traceability Matrix)

| 需求編號 | 決策依據 | 實作檔案預排 | 測試案例預排 |
| :--- | :--- | :--- | :--- |
| **FR-01** | `[sub_02:P00:DR-01]` | `source/core/core/config.py` | `test_config.py::test_config_get_and_set` |
| **FR-02** | `[sub_02:P00:DR-01]` | `source/core/core/config.py` | `test_config.py::test_local_overrides_project` |
| **FR-03** | `[sub_02:P00:DR-02]` | `source/<mod>/configurable/` | `test_checker.py::test_configurable_directory` |
| **FR-04** | `[sub_02:P00:DR-03]` | `source/core/core/engine.py` | `test_engine.py::test_deploy_configurable_templates` |
| **FR-05** | `[sub_02:P00:DR-06]` | `source/core/core/contributes.py` | `test_contributes.py::test_project_contribute_json_override` |
| **FR-06** | `[sub_02:P00:DR-04]` | `knowledge-db/space.py`, `agents-workflow/*` | `test_space.py`, `test_targets.py` |
| **FR-07** | `[sub_02:P00:DR-05]` | `source/core/scripts/cli.py`, `contributes/core.json` | `test_cli.py::test_config_cli_commands` |
