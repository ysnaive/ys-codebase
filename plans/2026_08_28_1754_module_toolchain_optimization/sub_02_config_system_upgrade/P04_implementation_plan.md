# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 實作任務拓撲與依賴拆解 (Task Breakdown)

| 任務編號 | 任務名稱 | 核心實作內容 | 依賴前置 | 預計產出檔案 |
| :--- | :--- | :--- | :---: | :--- |
| **TASK-01** | **資產目錄結構遷移** | 建立 `source/<mod>/configurable/` 並遷移 `core`, `knowledge-db`, `agents-workflow` 之 `config.project.json` | 無 | `source/<mod>/configurable/config.project.json` |
| **TASK-02** | **`core.config` SDK 實作** | 建立 `source/core/core/config.py`，實作 `get`, `get_all`, `set`, `delete`, `reload`, `list_modules` 與 mtime 快取自愈 | TASK-01 | `source/core/core/config.py` |
| **TASK-03** | **部署引擎適配與淨化** | 升級 `source/core/core/engine.py` 之 `act_deploy_configs_from_modules` 掃描 `configurable/` 並物理刪除 runtime 模板 | TASK-01, TASK-02 | `source/core/core/engine.py` |
| **TASK-04** | **`contribute.json` 專案特化升級** | 升級 `source/core/core/contributes.py` 階層 ② 改讀 `config://<target>/contribute.json`，並阻斷警告 local 級 | TASK-02 | `source/core/core/contributes.py` |
| **TASK-05** | **消費端 SDK 100% 收斂** | 重構 `core.uri`、`knowledge-db/space.py`、`agents-workflow/targets.py`、`publisher.py`、`initializer.py` 全面收斂調用 `core.config` | TASK-02, TASK-04 | `core/uri.py`, `knowledge_db/space.py`, `agents_workflow/*` |
| **TASK-06** | **CLI 工具鏈與 Contributes 註冊** | 實作 `source/core/scripts/cli.py` 之 `config list / get / set`，並於 `source/core/contributes/core.json` 註冊防呆說明 | TASK-02 | `core/scripts/cli.py`, `core/contributes/core.json` |
| **TASK-07** | **測試套件編寫與全系統跑測** | 建立 `source/core/tests/test_config.py`，更新 `test_contributes.py`、`test_engine.py`，全系統回歸驗證 | ALL | `core/tests/test_config.py` |

---

## 2. 交叉驗證檢查表 (Cross Validation)

- [x] **P01 需求覆蓋**：FR-01~07 全數映射至 TASK-01~07 與 P06 測試案例。
- [x] **P02 架構吻合**：嚴格落實 Local > Project 雙層深層合併、mtime 快取自愈與 `contribute.json` Git 追蹤公理。
- [x] **P03 介面吻合**：公開 API 簽名與參數型別 100% 保持一致。
- [x] **P06 測試前置**：FT-01~07、ET-01~02 與 RT-01 案例全數對齊。

---

## 3. 架構靈魂拷問 (Architecture Soul-Searching)

### 拷問 1：如果開發者直接在外部手動修改了 `config.project.json` 或 `config.local.json`，記憶體快取會不會導致髒讀（Stale Data）？
- **防護機制**：
  `core.config` 在快取中記錄了 `(project_mtime, local_mtime)` 雙時間戳。在每次調用 `get()` 或 `get_all()` 時，會執行輕量級的 `os.path.getmtime()` 檢測（耗時 ~0.001ms）。若檢測到任一檔案之 mtime 大於快取時間戳，自動觸發即時自愈重載（Auto-Healing Reload），100% 杜絕髒讀。

### 拷問 2：專案特化 `contribute.json` 為什麼剛性禁止 `contribute.local.json`？會不會限制本地調試彈性？
- **防護機制**：
  `contribute.json` 涉及工作流編譯（`release_targets`、Token 注入、URI 協議注入、同義詞庫等），這類擴充會實質改變發布產物與代碼生成。若允許 local 級且被 Git 忽略，會造成「同一個倉庫在不同機器編譯產出不同代碼/工作流」的災難性非決定論（Non-deterministic Build）。因此剛性禁止 local 級是保障軟體確定性與建置一致性的必要公理。本地個人調試應透過 `config.local.json` 調整運行參數（如開關、目錄、快取大小），而非修改注入結構。

---

## 4. 知識庫與文檔衝擊規劃 (Documentation Delivery Plan)

- [ ] **維度 1**：`source/core/contributes.format.md` 增補 `commands.config` CLI 防呆規格。
- [ ] **維度 2**：`source/agents-workflow/contributes.format.md` 說明專案特化 `config://<mod>/contribute.json` 注入途徑。
- [ ] **維度 3**：`source/knowledge-db/contributes.format.md` 說明 `config://knowledge-db/contribute.json` 空間與同義詞注入。
- [ ] **維度 4**：專案根目錄 `CHANGELOG.md` 追加 sub_02 發布摘要。
