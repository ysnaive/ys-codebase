# 技術調研報告：`core` 模組五維度靜態診斷與 Mode A 無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：sub_01_core_code_optimization (`core` 模組五維度靜態診斷與 Mode A 無損重構處方)  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Draft  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **跨層次轉發與循環耦合（`D2`）**：`ys_codebase/source/core/core/uri.py`（721 LOC）負責 URI 語法解析與沙盒邊界校驗，卻在檔案尾部（`L650-720`）塞入 15 個檔案系統 I/O 薄轉發函式（`uri.exists`、`uri.read_json` 等）並於函式內延遲 `from . import vfs`，而 `vfs.py` 頂層又依賴 `uri`，形成 `uri <-> vfs` 雙向循環依賴，導致 `core` 內部（約 154~170 處）與跨模組（`dev`、`agents-workflow` 約 85~89 處）混用兩套 I/O 入口。
  2. **歷史過渡別名與死代碼殘留（`D2` / `D5`）**：歷次重構遺留多處相容別名（`Config = ConfigManager`、`emit = broadcast`、`translate = t`、`get_execution_context = get_module_context`、`_find_host_config = _get_host_config`、`isfile`/`isdir`、`scripts/cli.py` 底部 12 個 `cmd_*` 舊測試轉發）與 0 調用死方法（`AtomicEngine._seed_or_update_config`、`AtomicEngine.act_get_installed_commands_summary`、`contributes_cmd.cmd`），其中 `_seed_or_update_config` 更殘留了 `core` 模組初次安裝寫入 `locale` 預設值的孤島邏輯（`engine.py:505-512`）。
  3. **巨型類別與跨層級長函式（`D1` / `D3`）**：`AtomicEngine`（1,066 LOC）、`Installer`（763 LOC）、`dispatcher.py`（696 LOC）、`locale.py:validate_module_locales`（205 LOC）、`validator.py:validate_node`（225 LOC）等核心組件存在大量不依賴實例狀態 `self` 的方法，以及同時混雜「前置參數校驗、I/O 讀取、核心轉換、錯誤渲染」的 100~225 行長程序。
  4. **跨檔案樣板重複與資源鎖對稱性缺口（`D3` / `D4`）**：`_resolve_yscb_root` 在 5 支檔案中各自實作、`.gitignore` 合併邏輯在 `installer.py` 與 `pip_manager.py` 重複且規則不一致、`contributes_cmd.py` 連續 3 次複製貼上相同的 `validate_module_locales` 迴圈，且 `installer.py:cmd_reload/cmd_restore` 的 `act_lock("global")` 缺乏 `try...finally` 確定性釋放保護。
- **調研目標**：
  - 鎖定 **範圍 = 單一模組（`ys_codebase/source/core/`，含 `core/` 20 檔與 `scripts/cli.py` 1 檔，共 21 檔 / 7,611 LOC）** 與 **生命週期 = `Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`**。
  - 結合雙子代理（Auditor A / Auditor B）獨立盲測共識，產出完整基線盤點、`Mode A` 轉發層/別名/死代碼清除清冊、`D1~D5` 分級問題單（`P0/P1/P2`）、9 大核心模組之 `S1` 業務階段拆解與 `S2` 無狀態邏輯剝離藍圖，以及 `S3~S6` 具體重構處方。

### 1.1 `core` 模組基線盤點表 (21 檔 / 7,611 LOC)

| 檔案路徑 (`ys_codebase/source/core/...`) | 行數 (LOC) | 核心職責與主要類別/函式 | 入向耦合 (`core` 內 / 跨模組) | 診斷熱點等級 |
| :--- | :---: | :--- | :--- | :---: |
| `core/engine.py` | 1,066 | `AtomicEngine`：模組倉庫抓取、Staging 原子替換、組態部署、交易鎖 | `installer`、`cli`、`dispatcher` | **P0 / P1** |
| `core/installer.py` | 850 | `Installer`：模組安裝/更新/移除/重載/還原、`fetch_and_extract_zip` | `cli`、`yscb.py` | **P1** |
| `core/locale.py` | 757 | 多層顯式退避語系引擎、`t()` 二階遞迴插值、`validate_module_locales` | 全生態系模組 | **P1** |
| `core/uri.py` | 721 | 統一資源定位符解析、沙盒邊界校驗、尾部 15 個 VFS I/O 轉發函式 | 全生態系模組（1,000+ 處） | **P0 / P1** |
| `core/commands/dispatcher.py` | 696 | CLI 命令路由、動態進程掛載、常駐 Server 自動喚醒與熱派發 | `yscb.py`、`cli` | **P1** |
| `scripts/cli.py` | 581 | `core` 內建 CLI 命令處理器（`config`/`pip`/`contributes`/`locale` 等） | `dispatcher`、`tests/` | **P1** |
| `core/contributes.py` | 548 | `ContributesAggregator`：跨模組 `contributes/*.json` 掃描、校驗與熱自癒 | `engine`、`dispatcher`、`locale` | **P1** |
| `core/validator.py` | 436 | 宣告式型別簽名解析 (`parse_type_signature`) 與遞迴驗證 (`validate_node`) | `contributes`、`contributes_cmd`、`dev` | **P1** |
| `core/vfs.py` | 357 | 虛擬檔案系統抽象 (`VFSBackend` / `OSBackend`) 與標準 I/O 公開入口 | `uri`、`core`、`dev`、`server`、`kdb` | **P2** |
| `core/config.py` | 333 | `ConfigManager`：雙層組態讀寫與環境變數覆寫 | `uri`、`locale`、`cli`、`kdb` | **P1** |
| `core/pip_manager.py` | 304 | `PipManager`：模組 Python 依賴同步、`.venv` 管理與 `.gitignore` 維護 | `engine`、`installer`、`cli` | **P1** |
| `core/commands/contributes_cmd.py` | 236 | `contributes check` / `list` CLI 實作與多空間 Schema + Locale 檢驗 | `scripts/cli.py` | **P1** |
| `core/ide_projector.py` | 223 | `IdeProjector`：同步 `.vscode/settings.json` 與 `pyrightconfig.json` | `engine`、`installer`、`cli` | **P1** |
| `core/telemetry.py` | 155 | CLI 飛行紀錄器 (`record_cli_execution`) 與滾動截斷 | `dispatcher` | **P1** |
| `core/events.py` | 111 | `EventBus`：行程內同步事件廣播 (`subscribe` / `broadcast`) | `engine`、`server`、`kdb` | **P1** |
| `core/__init__.py` | 78 | PEP 562 頂層延遲載入門面 (`__getattr__`) | 全生態系模組 | **P2** |
| `core/commands/help_renderer.py` | 73 | 統一 CLI Help 渲染器 (`HelpRenderer.render_command_help`) | `dispatcher`、`scripts/cli.py` | Clean |
| `core/update_checker.py` | 64 | 模組更新版本檢查 (`check_updates`) | `installer` | **P2** |
| `core/symbols.py` | 15 | 模組公開符號查找 (`get_symbol`) | `tests/` | **P2** |
| `core/exceptions.py` | 5 | `YSCBError` 基底例外定義 | `core` | Clean |
| `core/commands/__init__.py` | 1 | Package init | `core` | Clean |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

針對 `Mode A` 下 `core` 模組的重構推進範圍（特別是 `uri.<io>` 15 個 VFS 薄轉發函式在跨模組 `dev` 與 `agents-workflow` 尚有約 85~89 處調用點），評估以下三種落地方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：`core` 單模組先行收斂 + 跨模組分階段遷移**<br/>*(Scoped Full Track + Follow-up Sub-plans)* | 於 `sub_01` 內徹底完成 `core` 內部 21 支檔案的 `S1~S6` 重構、死代碼/舊別名物理清除，並將 `core` 內部 ~165 處 `uri.<io>` 100% 改為 `vfs.<io>`；跨模組（`dev`、`agents-workflow`）之 `uri.<io>` 則於同主計畫後續 `sub_02` 遷移後刪除 `uri.py` 轉發層（或於 `sub_01` 一併完成跨模組機械替換）。 | 單次 PR 變更聚焦於 `core`，易於驗證 `core` 206 項單元測試 100% 通過；風險隔離清晰。 | 若不在同一計畫同步替換 `dev`（42 處）與 `agents-workflow`（43 處）的 `uri.<io>`，`uri.py:650-720` 需暫留至 `sub_02` 才能物理刪除。 | ⭐⭐⭐⭐ |
| **方案 B：`core` 深度重構 + 全倉 `Mode A` 單一正統入口一步到位**<br/>*(Recommended — Full Track with Cross-Module Call-Site Sync)* | 於 `sub_01` 升級為 `Full Track` 時，除完成 `core` 內部 `D1~D5` 重構與 `S1~S6` 拆解外，同步對全倉 `dev`、`agents-workflow`、`knowledge-db` 執行 `uri.<io> -> vfs.<io>` 與 `Config -> ConfigManager` 調用點機械收斂，當場物理刪除 `uri.py:650-720` 全部 15 個轉發函式與所有相容別名。 | 100% 貫徹 `Mode A`「單一正統入口、零薄轉發層、零循環依賴」目標，一步斬斷 `uri <-> vfs` 循環耦合，不留過渡期技術債。 | 需同時跑過 `core`、`dev`、`agents-workflow`、`knowledge-db`、`server` 全生態系測試守門（`dev test --all -q`）。 | ⭐⭐⭐⭐⭐ **(推薦)** |
| **方案 C：僅做檔案內局部提取（不動公開與內部入口）** | 僅拆分長函式，保留所有 `uri.<io>` 轉發、別名與死方法。 | 修改範圍最小。 | 違背 `Mode A` 破壞性收斂原則，`uri <-> vfs` 循環耦合與死代碼依然殘留。 | ⭐ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `Mode A` 公開入口收斂、薄轉發層、相容別名與死代碼清除清冊 (`S5`)

| 編號 | 檔案與行號座標 | 冗餘轉發 / 相容別名 / 死代碼 | 調用方盤點（`core` 內部 / 跨模組 / `tests/`） | `Mode A` 物理清除與收斂處方 (`S5`) |
| :---: | :--- | :--- | :--- | :--- |
| **M-01** | `core/uri.py:650-720` | 15 個 VFS 薄轉發函式：`exists`, `isfile`, `is_file`, `isdir`, `is_dir`, `remove`, `read_text`, `write_text`, `read_json`, `write_json`, `makedirs`, `listdir`, `copy`, `move`, `rmtree` | • `core` 內部 ~165 處（`engine.py` 84、`contributes.py` 34、`installer.py` 15、`contributes_cmd.py` 12、`update_checker.py` 5、`locale.py` 4、`events.py` 3、`symbols.py` 1）<br/>• 跨模組 ~85 處（`agents-workflow` 43、`dev` 42）<br/>• `core/tests/test_uri.py` 等測試檔 | **物理刪除 `uri.py:650-720`**（同步消除 `isfile`/`isdir` 與 `is_file`/`is_dir` 雙重命名），將所有 I/O 調用點統一收斂至正統入口 `vfs.<op>`，徹底根除 `uri <-> vfs` 循環依賴。 |
| **M-02** | `core/engine.py:459-513` | `AtomicEngine._seed_or_update_config` | **0 callers**（已被 `L623` `_deploy_and_strip_single_module_config` 取代） | **[!] 隱藏 Bug 修復 + 物理刪除**：將死方法內 `L505-512` 針對 `core` 首次安裝寫入 `locale` 預設值的邏輯提取整合至活躍方法 `_deploy_and_strip_single_module_config`，隨後物理刪除 `_seed_or_update_config`。 |
| **M-03** | `core/engine.py:1031-1065` | `AtomicEngine.act_get_installed_commands_summary` | **0 callers**（已被 `contributes.py:510` `get_installed_commands_summary()` 取代） | 直接物理刪除 `engine.py:1031-1065`。 |
| **M-04** | `core/uri.py:42-54` & `L496-504` | `_DEPRECATED_SCHEME_REDIRECTS: Dict[str, str] = {}` 空表與 `resolve()` 內之分支 | **0 作用**（字典為空，分支永遠為 False） | 直接物理刪除 `L42-54` 常數與 `L496-504` 分支。 |
| **M-05** | `core/uri.py:110`<br/>`core/uri.py:230` | `get_execution_context = get_module_context`<br/>`_find_host_config = _get_host_config` | 生產代碼 **0 callers**（僅 `core/tests/test_uri.py` 測試舊名） | 物理刪除兩處別名，並將 `test_uri.py` 改測正統函式名 `get_module_context` 與 `_get_host_config`。 |
| **M-06** | `core/config.py:332` | `Config = ConfigManager` | `core` 內 **0 callers**；跨模組僅 `knowledge_db/config.py:81` 1 處 | 將 `knowledge_db/config.py:81` 與 `core/tests/test_config.py` 改為 `ConfigManager`，物理刪除 `Config = ConfigManager`。 |
| **M-07** | `core/events.py:110` | `emit = broadcast` | 全倉 **0 callers** | 直接物理刪除 `events.py:110`。 |
| **M-08** | `core/locale.py:27, 39` & `L549` | `_MODULE_DECL_CACHE`（只宣告與 `.clear()`、從未讀寫之死快取）與 `translate = t` 別名 | 全倉 **0 callers** | 物理刪除 `_MODULE_DECL_CACHE` 與 `translate = t`。 |
| **M-09** | `core/commands/contributes_cmd.py:208-235` | `cmd(cmd_bags)` 模組級入口 | 全倉 **0 callers**（實際 CLI 入口為 `scripts/cli.py:cmd_contributes`） | 直接物理刪除 `contributes_cmd.py:208-235`。 |
| **M-10** | `scripts/cli.py:437-439` & `L534-580`<br/>`core/commands/dispatcher.py:622` | `cli.py` 內 `bootstrap` 廢棄子命令分支、底部 12 個 `cmd_*` 舊測試相容轉發函式，以及 `dispatcher.py:622` `getattr(cli_mod, f"cmd_{command_name}")` | 生產代碼由 `scripts/cli.py:main()` 統一路由；底部 `cmd_*` 僅 `core/tests/` 引用 | 更新 `core/tests/` 直接調用 `Installer` / `AtomicEngine` / `main()` 正統入口，物理刪除 `scripts/cli.py:437-439`、`L534-580` 與 `dispatcher.py:622` fallback。 |
| **M-11** | `core/contributes.py:269` | `scan_and_inject(self, clean: bool = False)` 之未使用參數 `clean` | 函式體內完全未讀取 `clean` | 移除無作用之 `clean` 參數（或對齊實際行為），同步清理調用端。 |

---

### 3.2 五維度靜態診斷問題單 (`D1~D5` × `P0/P1/P2`)

| 編號 | 維度 | 嚴重度 | 座標 (`file:line`) | 病徵描述与根因剖析 | 對應重構策略 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | **D2** | **P0** | `core/uri.py:650-720`<br/>`core/vfs.py:10` | **核心基座雙向循環依賴 (`uri <-> vfs`)**：`vfs.py` 頂層匯入 `uri` 解析虛擬路徑，而 `uri.py` 為維持歷史相容於 `L650-720` 包裝 15 個 `vfs` I/O 函式，破壞單向依賴拓撲（`vfs -> uri`）。 | **S5** (`M-01`) |
| **F-02** | **D2 / D4** | **P0** | `core/engine.py:459-513` & `L623-729` | **死方法殘留活躍業務邏輯**：`_seed_or_update_config` 已被 `_deploy_and_strip_single_module_config` 取代（0 callers），但 `L505-512` 首次部署 `core` 時初始化 `locale` 的邏輯卻遺留在死方法內。 | **S5 + S1** (`M-02`) |
| **F-03** | **D4** | **P1** | `core/installer.py:604-624` & `L654-707` | **全域交易鎖缺乏確定性釋放保證 (`Scoped Resource Lifecycle`)**：`cmd_reload` 與 `cmd_restore` 呼叫 `self.engine.act_lock("global", ...)` 後，未使用涵蓋全流程之 `try...finally: self.engine.act_unlock("global")`（或 Context Manager），且 `L608, 658` 以 `except Exception: pass` 靜默吞噬鎖異常。 | **S4**（提供 `@contextmanager def transaction_lock("global")`） |
| **F-04** | **D1 / D3** | **P1** | `core/engine.py:31-1065` | **`AtomicEngine` 巨型類別 (1,066 LOC)**：僅持有 2 個實例屬性（`contributes_aggregator`、`_active_locks`），卻塞入 7 個完全不讀寫 `self` 的無狀態工具函式，以及 4 個超過 80~120 行的多階段長方法。 | **S1 + S2**（詳見 §3.3） |
| **F-05** | **D1 / D3** | **P1** | `core/installer.py:88-850` | **`Installer` 職責混雜與長方法 (763 LOC)**：同時承擔業務編排、終端表格/Onboarding UI 渲染、Zip 解壓校驗與備份還原；`fetch_and_extract_zip` (`L137-143`) 與 `engine.py` 重複實作 Zip-Slip 檢查。 | **S1 + S2 + S3**（詳見 §3.3） |
| **F-06** | **D1 / D3** | **P1** | `core/locale.py:552-756` | **`validate_module_locales` 205 行單體驗證巨函式**：6 層巢狀結構同時處理路徑正規化、`definition.json` 解析、語系檔掃描、孤兒鍵 `difflib` 比對與 `{placeholder}` 正則集合差集。 | **S1 + S2**（詳見 §3.3） |
| **F-07** | **D1 / D3** | **P1** | `core/uri.py:315-599` | **`reconcile_undefined_uri` (118 LOC) 與 `resolve` (166 LOC) 抽象層級混雜**：`reconcile_undefined_uri` 在核心路徑解析模組內直接執行 `sys.stdin.isatty()` 與 `input()` CLI 互動選單；`resolve` 混雜多 Scheme 分派、Anchor 展開與沙盒邊界檢查。 | **S1 + S2**（詳見 §3.3） |
| **F-08** | **D1 / D3** | **P1** | `core/commands/dispatcher.py:189-695` | **`dispatcher.py` 長函式與雙軌路由重複**：`dispatch` (210 LOC)、`dispatch_local` (135 LOC)、`_maybe_auto_spawn_server` (108 LOC) 控制流深層巢狀，且 `dispatch` 與 `dispatch_local` 重複實作命令解析與參數綁定。 | **S1 + S2**（詳見 §3.3） |
| **F-09** | **D3** | **P1** | `core/validator.py:69-404` | **`validate_node` (225 LOC, 圈複雜度 ~38) 與 `parse_type_signature` (109 LOC)**：以單一巨型 `if/elif` 分支處理所有複合型別（`dict_shape`/`list`/`tuple`/`union`/`literal`/純量）。 | **S1 + S3**（依 `kind` 拆分為分派表） |
| **F-10** | **D1 / D3** | **P1** | `core/contributes.py:269-445`<br/>`core/commands/contributes_cmd.py:42-206` | **`scan_and_inject` (168 LOC) 與 `check_contributes` (165 LOC) 重複樣板**：`check_contributes` 在 `L108-115`、`L159-167`、`L182-190` 連續三次複製貼上完全相同的 `validate_module_locales` 錯誤收集迴圈。 | **S1 + S2 + S3**（詳見 §3.3） |
| **F-11** | **D3 / D2** | **P1** | `pip_manager.py:291`、`ide_projector.py:29`、`telemetry.py:139`、`dispatcher.py:173`、`config.py:18` | **5 處重複實作 `_resolve_yscb_root` / `_get_yscb_root`**：5 支模組各自走訪檔案系統或 `uri._get_yscb_dir()` 尋找 `.yscb_root`，缺乏單一正統查詢入口。 | **S5 + S6**（統一收斂至 `uri.get_yscb_dir()`） |
| **F-12** | **D3 / D5** | **P1** | `core/installer.py:15-86`<br/>`core/pip_manager.py:246-288` | **2 處重複且規則不一致的 `.gitignore` 合併實作**：`installer._merge_yscb_gitignore` 包含 `*.bak` 等 5 條規則，`pip_manager._ensure_yscb_gitignore` 卻僅硬編碼 4 條規則（漏掉 `*.bak`）。 | **S5 + S6**（收斂為單一正統 `_ensure_yscb_gitignore`） |
| **F-13** | **D3** | **P2** | `scripts/cli.py:216, 331, 467, 509` | **4 處同構群組子命令 Help 渲染表**：`cmd_config`、`cmd_pip`、`cmd_contributes`、`cmd_locale` 重複建構 ANSI 群組子命令說明框。 | **S3**（提取 `_render_subcommand_group_help`） |
| **F-14** | **D4** | **P2** | `core/__init__.py:1-78`<br/>多檔未引用 `import` | **`core/__init__.py` 缺少 `if TYPE_CHECKING:` 靜態型別宣告**，且 `engine.py`、`installer.py`、`contributes.py`、`dispatcher.py` 存在未引用之死匯入。 | **S4 + S5** |

---

### 3.3 `S1` 業務階段邏輯聚合與 `S2` 無狀態邏輯剝離藍圖（9 大核心檔案）

#### 1. `core/engine.py` (`AtomicEngine`, 1,066 LOC $\to$ 預估 ~680 LOC)
* **`S2` 無狀態邏輯剝離**（完全不依賴 `self`，提取為模組級純函式或靜態工具）：
  - `_parse_dependencies(deps_raw: Any) -> Dict[str, str]`（原 `L249-266`）
  - `_deep_infill_dict(target: Dict, template: Dict) -> Tuple[Dict, bool]`（原 `L427-457`）
  - `_force_rmtree_with_retry(target_path: str) -> None`（原 `L515-549`）
  - `_cleanup_stale_swap_dirs(parent_dir: str, mod_name: str) -> None`（原 `L551-566`）
  - `_atomic_swap_dir(staging_dir: str, target_dir: str, mod_name: str) -> None`（原 `L569-621`）
  - `_clean_module_cache(mod_name: str) -> None`（原 `L755-765`）
  - `_extract_zip_safely(zip_path: str, dest_dir: str) -> None`（收斂 `engine.py:846-851` 與 `installer.py:137-143` 重複之 Zip-Slip 安全解壓邏輯）
* **`S1` 業務階段拆解**：
  - `act_download`（原 `L111-230`，120 LOC）$\to$ 拆解為：
    1. `_resolve_download_source_and_version(mod_name, version)`
    2. `_download_from_local_or_remote(mod_name, target_ver, source_info, dest_zip)`
    3. `_prune_module_mirror_archives(mod_name, keep_max=3)`
  - `_get_module_manifest_from_provider_or_local`（原 `L268-376`，109 LOC）$\to$ 拆解為：
    1. `_read_manifest_from_installed_or_mirror(mod_name, version_constraint)`
    2. `_fetch_manifest_from_provider(mod_name, version_constraint)`
  - `_deploy_and_strip_single_module_config`（原 `L623-729`，107 LOC）$\to$ 拆解為：
    1. `_seed_or_infill_module_config(mod_name, staging_dir)`（併入原死方法 `L505-512` 之 `core` 預設 `locale` 初始化）
    2. `_apply_yscbignore_and_strip_templates(staging_dir)`
  - `act_reload`（原 `L807-890`，84 LOC）$\to$ 拆解為：
    1. `_LocateAndStageModuleArchive`（定位鏡像、建立 `.staging_*` 與安全解壓）
    2. `_deploy_and_strip_single_module_config` + `_atomic_swap_dir`
    3. `_post_reload_hooks_and_sync`（Contributes 重建、Python 依賴同步、IDE 投影更新）

#### 2. `core/installer.py` (`Installer`, 850 LOC $\to$ 預估 ~560 LOC)
* **`S2` 無狀態邏輯剝離**：
  - `_print_onboarding_guide(host_dir: str) -> None`（原 `L210-236`）
  - `_restore_module_package(mod_name: str, backup_mod_dir: str, ...) -> bool`（原 `L709-800`，改為接收顯式參數之獨立輔助函式）
* **`S1` 業務階段拆解**：
  - `cmd_update`（原 `L296-406`，111 LOC）$\to$ 拆為 `_resolve_update_candidates`、`_execute_batch_module_updates`、`_finalize_update_summary`。
  - `cmd_list`（原 `L458-555`，98 LOC）$\to$ 拆為 `_collect_module_inventory` 與 `_render_module_inventory_table`。
  - `cmd_restore`（原 `L626-707`，82 LOC）$\to$ 搭配 `transaction_lock("global")` Context Manager，拆為 `_select_restore_snapshot` 與 `_execute_snapshot_restore`。

#### 3. `core/locale.py` (`validate_module_locales`, `L552-756`, 205 LOC $\to$ 3 個清晰階段函式)
* **`S1 + S2` 階段拆解**：
  1. `_validate_locales_decl_header(module_name, locales_decl, module_root) -> Tuple[Optional[str], Dict[str, str], List[str]]`（驗證 `definition` 必填鍵與路徑越界防護）
  2. `_load_and_validate_definition_contract(module_name, def_abs_path) -> Tuple[Optional[Dict[str, Set[str]]], List[str]]`（解析 `definition.json`、檢查 `description` 非空並預提取每個 key 的 `{placeholder}` 集合）
  3. `_validate_single_lang_file(module_name, lang_id, lang_abs_path, def_placeholders) -> List[str]`（驗證單一語系檔 JSON 格式、`difflib` 孤兒鍵提示與佔位符集合一致性）

#### 4. `core/uri.py` (721 LOC $\to$ 移除尾部 VFS 轉發與拆解後預估 ~480 LOC)
* **`S1 + S2` 階段拆解**：
  - `reconcile_undefined_uri`（原 `L315-432`，118 LOC）$\to$ 拆為 `_discover_undefined_uri_candidates`（純探測邏輯）、`_prompt_uri_reconciliation_choice`（CLI 互動選單）、`_persist_reconciled_uri_to_config`（JSON 寫入）。
  - `resolve`（原 `L434-599`，166 LOC）$\to$ 拆為 `_normalize_and_split_uri`、`_dispatch_scheme_resolution`（處理 `project`/`module`/`storage`/`workspace`/`config`/`cache`）、`_expand_anchors_and_enforce_sandbox`。

#### 5. `core/commands/dispatcher.py` (696 LOC $\to$ 預估 ~470 LOC)
* **`S1 + S2` 階段拆解**：
  - `_maybe_auto_spawn_server`（原 `L189-296`，108 LOC）$\to$ 剝離 `_is_server_code_stale` 與 `_wait_for_server_daemon_ready` 無狀態 helper。
  - `dispatch`（原 `L486-695`，210 LOC）與 `dispatch_local`（原 `L350-484`，135 LOC）$\to$ 抽取共用之 `_resolve_command_target_and_bind_options` 與 `_mount_module_runtime_paths`，消除本地派發與常駐 Worker 派發之間的重複路由解析代碼。

#### 6. `core/validator.py` (436 LOC $\to$ 預估 ~310 LOC)
* **`S1 + S3` 分派表重構**：
  - 將 `validate_node`（原 `L180-404`，225 LOC）依 `node_spec["kind"]` 拆解為 `_validate_dict_shape_node`、`_validate_list_node`、`_validate_tuple_node`、`_validate_union_node`、`_validate_literal_node`、`_validate_scalar_node`，以 `_KIND_VALIDATORS` 字典分派取代 225 行單體條件分支。

#### 7. `core/contributes.py` & `core/commands/contributes_cmd.py`
* **`S1 + S2 + S3` 拆解與去重**：
  - `ContributesAggregator._deep_merge`（`contributes.py:438-445`）剝離為模組級純函式；`scan_and_inject`（`L269-436`，168 LOC）拆為 `_load_core_schemas`、`_collect_donor_files`、`_validate_and_merge_donors`、`_write_aggregated_cache` 四階段。
  - `contributes_cmd.py:check_contributes`（`L42-206`，165 LOC）抽取 `_append_locale_validation_errors(mod_name, locales_decl, mod_root, errors)` 消除 3 處重複迴圈，並將 `core` / `modules` / `source` 三段掃描合一。

#### 8. `core/ide_projector.py` (`sync_vscode_settings`, `L73-222`, 150 LOC)
* **`S1 + S2` 階段拆解**：拆為 `_collect_module_extra_paths`、`_sync_vscode_settings_json`、`_sync_pyrightconfig_json` 三個獨立階段函式。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  - 採納 **方案 B（`core` 深度重構 + 全倉 `Mode A` 單一正統入口一步到位）**，於後續啟動實作時將本子計畫 `sub_01_core_code_optimization` 原地升級為 **標準開發計畫 (`Full Track`, `P01~P07`)**。
  - **預估量化收益**：
    1. 物理清除 **15 個 VFS 薄轉發函式** + **10 處歷史相容別名/死方法/死常數**，預計淨減約 **650~850 LOC** 冗餘與重複樣板代碼。
    2. 徹底斬斷 `uri <-> vfs` 雙向循環依賴，達成 `vfs -> uri` 100% 單向無環依賴（ADP）。
    3. 修復 `engine.py:_seed_or_update_config` 死方法內遺留之 `core` 初次 `locale` 初始化缺口，以及 `installer.py` 全域鎖 `try...finally` 對稱釋放。
    4. 將 `core` 內最大函式行數由 **225 LOC** 壓降至 **$\le 60$ LOC**，最大圈複雜度由 **~38** 壓降至 **$\le 10$**。
- **後續行動與 P00 銜接（Step 3 三大流轉出口）**：
  1. **出口 ① 立即/後續升級實作（推薦）**：將 `R01_code_optimization_audit.md` 標記為 `Concluded`，並於 `sub_01_core_code_optimization` 原地追加 `P01~P07` 升級為 `Full Track` 實作計畫。
  2. **出口 ② 轉入長期技術儲備**：轉入 `/roadmap` 或 `/todo` 分批排程。
  3. **出口 ③ 結案存檔**：僅保留調研診斷報告備查。

