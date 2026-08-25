# 語意需求與概念共識 (Phase 0: Semantic Requirements)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據調研報告：[R01](../R01_module_architecture_survey.md), [R02](../R02_yscb_responsibilities.md), [R03](../R03_manifest_and_lifecycle_flow.md), [R04](../R04_lifecycle_invocation_flow.md), [R05](../R05_developer_ecosystem_and_migration.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 核心願景與業務語意 (What & Why)

本子計畫（`sub_07`）的願景是**「正本清源，嚴格對齊主計畫 R01 ~ R05 規範白皮書，全面打磨 Core 模組的核心機制、組態邊界與路徑確定性」**：

1. **`project://` 顯式組態綁定（禁止 Fallback，預設 !undefined）**：
   - `project://` 不在自舉（Bootstrap）最小需求中，是專門提供給上層業務模組調用的專案空間語意 URI；
   - `project://` **100% 依賴 `config/core/config.project.json` 顯式配置之 `project_root`**（例：`"project_root": "./"` 或 `"project_root": "../"`）；
   - **完全禁止猜測或隱式 Fallback**：若該組態未定義（undefined）或設定檔缺失，解析 `project://` 時**立即拋出顯式例外**，阻斷任何不確定性路徑漂移。
2. **`config://` 顯式專案目錄協議**：
   - 將 `.config/` 隱藏目錄導正為顯式之 `config/` 專案目錄（作為受 Git 追蹤之資產）：
     - **`config.root://`** ➔ `yscb://config/`
     - **`config://`** ➔ `yscb://config/{module}/`
3. **模組預設組態分發與安裝機制 (Default Config Seeding)**：
   - 模組在 `source/{module}/` 得提供預設之 `config.project.json` 與 `config.local.json`；
   - `core.installer`（或 `act_reload`）於安裝或重構模組時，若目標專案的 `config://` 尚未建立該設定檔，自動複製安裝至 `config://`；
   - 若專案層級已存在組態，剛性保留現有內容，絕不覆蓋。
4. **精準命名空間生命週期鉤子機制 (Namespaced Hook & Event Dispatching)**：
   - **Hook 檔案規範**：接收端在自身的 `scripts/` 中建立 **`hook.{emit_module}.py`**（例：對接 `core` 建立 `hook.core.py`；對接 `dev` 建立 `hook.dev.py`）；
   - **函式宣告**：定義與事件同名之函式（例：`def on_installed(context: ExecutionContext): ...` 或 `def on_before_build(context: ExecutionContext): ...`）；
   - **派發與調度**：發起端調用 `act_broadcast_event(emit_module, event_name, context)`，Core 動態掃描各模組之 `hook.{emit_module}.py` 並進行 try-except 例外隔離安全執行。
5. **語意 URI 動態擴充與佔位符解算鏈路 (Dynamic URI & Placeholders)**：
   - 實作 `ExecutionContext` 介面；
   - `core.uri.resolve()` 接入動態協議註冊表，支援 `type: "const"`（常數模板）與 `type: "config"`（**僅讀取 `config://config.project.json`**）；
   - 支援 `path_placeholders` 之動態 handler 解算（傳入 `ExecutionContext` 計算）。
6. **模組空間純淨化**：
   - 徹底清除 `modules/core/` 與 `source/core/` 根目錄殘留的非標準 `config.project.json`，確立 `module://`（純淨發布包）與 `config://`（專案/本地組態）的物理隔離。

---

## 2. 核心使用情境與端到端旅程 (User Scenarios & Journeys)

### 情境 A：`project://` 顯式解析與未配置阻斷 (Explicit project:// Resolution)
- **旅程 1（正常解析）**：
  1. `config/core/config.project.json` 定義 `"project_root": "./"`；
  2. 模組呼叫 `uri.resolve("project://AGENTS.md")`；
  3. `core.uri` 讀取 Core 專案設定，成功解析為 `H:\...\AGENTS.md`。
- **旅程 2（未配置阻斷）**：
  1. 若 `config/core/config.project.json` 缺失或未宣告 `project_root`；
  2. 模組呼叫 `uri.resolve("project://AGENTS.md")`；
  3. `core.uri` **拒絕猜測工作目錄，直接拋出 `ValueError: 'project://' is undefined. Please configure 'project_root' in config://config.project.json (core)`**。

### 情境 B：模組預設組態自動初始化至 `config://` (Default Config Seeding)
- **旅程**：
  1. 開發者在 `source/core/` 建立預設 `config.project.json`（內含 `"project_root": "./"`）；
  2. 用戶初次安裝或初始化時，安裝器自動部署至 `config/core/config.project.json`；
  3. 開發者可隨意將 `project_root` 修改為 `"../"` 等自訂位置，系統更新時絕不覆蓋用戶修改。

### 情境 C：命名空間 Hook 對接與事件廣播 (`hook.{emit_module}.py`)
- **旅程**：
  1. `dev` 套件宣告並派發 `on_before_build` 事件；
  2. `agents-workflow` 模組於自身建立 `module.root://agents-workflow/scripts/hook.dev.py`，內含 `def on_before_build(context: ExecutionContext): ...`；
  3. 當 `dev` 執行 `build` 觸發 `act_broadcast_event("dev", "on_before_build", context)` 時；
  4. Core 遍歷所有模組，定位到 `agents-workflow/scripts/hook.dev.py` 中的 `on_before_build` 函式並安全執行；
  5. 若該函式拋出異常，Core 記錄 Warning 日誌，不阻斷 `dev` 的建置流程。

---

## 3. 核心限制與非目標 (Constraints & Non-Goals)

### 核心限制
- **零隱式猜測 (No Fallback)**：`project://` 必須顯式配置，嚴禁任何 cwd 或默認路徑猜測。
- **零外部相依**：100% 依賴 Python 3.8+ 標準庫（`importlib.util` 動態載入 hook）。
- **路徑版控確定性**：`type: "config"` 協議**絕對僅讀取 `config://config.project.json`**，嚴禁讀取 `config.local.json`。
- **用戶自訂組態保護**：組態安裝時**絕對禁止覆蓋既有已存在之專案或本地組態**。

---

## 4. 關鍵設計決策紀錄 (Decision Records)

- **[sub_07:DR-01] project:// 顯式配置與零 Fallback 鐵律**：`project://` 嚴格由 `config/core/config.project.json` 之 `project_root` 解算；若未定義則拋出顯式例外，絕對禁止 Fallback。
- **[sub_07:DR-02] 顯式 config 目錄協議**：`config.root://` 解算為 `yscb://config/`，`config://` 解算為 `yscb://config/{module}/`。
- **[sub_07:DR-03] 模組預設組態安裝策略**：模組在 `source/` 提供的 `config.project.json` / `config.local.json` 於安裝時由 installer 部署至 `config.root://{module}/`（僅在不存在時新建）。
- **[sub_07:DR-04] 命名空間 Hook 對接規範**：對接檔案命名剛性約束為 `module://scripts/hook.{emit_module}.py`，函式名對齊 `{event_name}`。
- **[sub_07:DR-05] 動態 URI 協議與佔位符解算**：`core.uri.resolve()` 讀取 `contributes.merged.json` 聚合表，支援 `const`、`config` 及 handler 動態呼叫。
- **[sub_07:DR-06] 模組空間純淨化**：`module://` 根目錄僅保留代碼與發布檔案，嚴禁殘留 `config.project.json`。

---

## 5. 待釐清問題與討論區 (Open Questions)

- [x] **全數核心架構已釐清定稿**：`project://` 顯式配置、`hook.{emit_module}.py`、`config/` 顯式目錄與預設組態自動分發全數確認。
