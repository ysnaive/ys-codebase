# 技術調研報告：Core 微內核模組五維度靜態診斷與無損重構審計 (R02_code_optimization_audit.md)

> 調研主題：Core 微內核模組 (`ys_codebase/source/core/`) 業務代碼五維度靜態診斷與重構處方箋  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

### 1.1 定錨基準與範圍摘要
- **檢視範圍 (`Scope`)**：**單一模組 (`Module Scope`)** —— `ys_codebase/source/core/`（排除 `tests/`，共計 26 個 Python 生產原始碼檔案，總計約 7,522 行 LOC）。
- **生命週期模式 (`Lifecycle Mode`)**：**`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`** —— 強制收斂為單一正統入口（Single Canonical Entry），零容忍物理刪除相容別名、薄轉發層、過時回退分支與重複實作，並同步更新所有內部與跨模組調用點。
- **核心問題與痛點**：
  1. **巨型職責混雜 (`D1`)**：`core/engine.py`（1,020 LOC）與 `core/installer.py`（819 LOC）承載了壓縮包三階尋址、依賴拓撲求解、組態模板鑲嵌、雙層快照備份、版號遷移階梯與 CLI 終端互動等多重正交職責，且兩者在壓縮包提取、遠端/本地 Provider 探測及 `.gitignore` 區塊同步上存在顯著雙軌重複。
  2. **跨檔案邏輯重複與過渡轉發殘留 (`D2` / `D3`)**：`.gitignore` 託管區塊生成於 `installer.py` 與 `pip_manager.py` 重複實作；`yscb_root` / `host_dir` 探測邏輯散落於 `uri.py`、`config.py`、`telemetry.py`、`dispatcher.py`、`ide_projector.py`、`pip_manager.py` 共 6 處；`AtomicEngine` 與 `ContributesAggregator` 內部殘留多處歷史相容之 `staticmethod` 轉發屬性與向後相容別名（如 `uri._get_yscb_root`）。
  3. **繞過 VFS 基礎設施與深層控制流 (`D3` / `D4` / `D5`)**：`core` 內部多個子模組（如 `config.py`、`dispatcher.py`、`installer.py`、`locale.py`）在已具備 `core.vfs` 的情況下仍直接混用原生 `open()` / `json.load()` / `tempfile.mkstemp()`，且 `dispatcher.py`、`engine.py`、`locale.py` 存在超過 80~170 行之長程序與深層巢狀分支。
- **調研目標**：
  依循 `/code-optimizer` 之 `D1~D5` 靜態診斷矩陣與 `Mode A` 收斂準則，全面盤點 `ys_codebase/source/core/` 之契約邊界、分級病灶座標（`P0 / P1 / P2`）與 `S1~S6` 外科手術重構處方箋。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 Mode A 契約邊界與內部工具函式查驗表

在 `Mode A（收斂期 / 允許破壞性清理）` 下，針對 `core` 模組之冗餘別名、重複入口、相容分支與純內部工具函式進行全空間調用圖譜查驗：

| 類別 | 符號 / 入口座標 | 當前狀態與調用圖譜查驗結果 | Mode A 處置策略（單一正統入口收斂） |
| :--- | :--- | :--- | :--- |
| **相容別名與類別轉發屬性** | `core/uri.py:190` (`_get_yscb_root = resolve_yscb_root`) | 歷史私有別名；全專案 `source` 空間 0 外部跨模組引用（`server/scripts/cli.py` 定義的是自身同名局部函式）。 | **物理刪除**，統一使用正統公開 API `uri.resolve_yscb_root()`。 |
| **相容別名與類別轉發屬性** | `core/engine.py:258-264`<br>(`AtomicEngine._parse_dependencies`, `_deep_infill_dict`, `_force_rmtree_with_retry`, `_cleanup_stale_swap_dirs`, `_atomic_swap_dir`, `_clean_module_cache`, `_extract_zip_safely`) | 模組級純函式在 `AtomicEngine` 類別身上的 `staticmethod` 重複掛載；`engine.py` 與 `installer.py` 均直接匯入頂層函式。 | **物理刪除類別層級 `staticmethod` 重複綁定**（若測試有引用則同步更新測試調用點至模組正統函式）。 |
| **相容別名與類別轉發屬性** | `core/contributes.py:273`<br>(`ContributesAggregator._deep_merge = staticmethod(_deep_merge)`) | 頂層已有 `_deep_merge` 純函式，類別內亦直接呼叫 `_deep_merge`。 | **物理刪除** `ContributesAggregator._deep_merge` 靜態轉發屬性。 |
| **重複功能入口 (雙軌實作)** | `core/pip_manager.py:33-68` (`ensure_yscb_gitignore`) vs.<br>`core/installer.py:33-86` (`generate_internal_gitignore`) | 兩者皆管理 `yscb://.gitignore` 的 `# === YSCB INTERNAL IGNORE BEGIN ===` 區塊且常數清單 `INTERNAL_IGNORE_PATTERNS` 100% 重複；`installer` 版本支援舊版標記升級與正则替換，卻未走 `vfs.write_text`；`pip_manager` 版本走 `vfs` 卻用簡單 `split`。 | **合併為單一正統函式**（保留正規表達式區塊替換並改由 `vfs.write_text(..., atomic=True)` 寫入），物理刪除 `pip_manager.ensure_yscb_gitignore` 與重複常數，令 `PipManager._ensure_gitignore` 直接調用單一正統實作。 |
| **重複功能入口 (雙軌實作)** | `core/pip_manager.py:149-180` (`get_site_packages_dir`) vs.<br>`core/platform/venv.py:10-37` (`ensure_private_venv`) | 兩處重複編寫 `py{major}{minor}` 與 Windows (`Lib/site-packages`) / POSIX (`lib/pythonX.Y/site-packages`) 路徑拼接邏輯。 | 於 `core/platform/venv.py` 收斂跨平台 `site-packages` 路徑計算純函式，供 `PipManager` 與 `ensure_private_venv` 共用。 |
| **重複功能入口 (雙軌實作)** | `core/config.py:125-149` (`ConfigManager._atomic_write_json`) | 當 `vfs` 存在時委派 `vfs.write_json`，但下方仍保留 20 行 `tempfile.mkstemp` + `json.dump` 死分支（`core.vfs` 為微內核標準配備，恆不為 `None`）。 | **物理刪除 `try...except ImportError` 與 `tempfile` 備援死分支**，100% 委派 `core.vfs.write_json` 與 `core.vfs.read_json`。 |
| **過渡期 CLI 包裝與手動路由** | `scripts/cli.py:48-70` (`_normalize_bags`) 及 `config()` / `uri()` / `event()` / `contributes()` 手動分支分派 | `dispatcher.py` 已全面落實 `OptionResolver.resolve` 產出結構化 `CmdBags` 並直接派發至精確底線函式（如 `config_list`、`uri_resolve`），且具備無子指令自動渲染 Help 能力；`scripts/cli.py` 卻仍保留手動解析 `list/tuple` 的 `_normalize_bags` 與四個群組手動 `if-elif` 分派器。 | 簡化群組入口與移除過渡期重複解析分支（若單元測試直接傳入 `list` 調用 CLI 函式，則將測試或輕量轉接統一收斂）。 |
| **過時 Schema 相容分支** | `core/commands/registry.py:138-144, 176-180` (`case_pros` / `case_cons` 及扁平 `commands_data` 相容分支)<br>`core/events.py:133-161` (三種 `events` 格式相容分支) | 全系統 `contributes/*.json` 已由 `_format.json` 剛性約束為統一格式（`usage: {pros, cons}`、`cmd: {...}`、`events: list[dict[str, str]]`）。 | 在 `Mode A` 下**物理移除 `case_pros` / `case_cons` 舊欄位分支**與冗餘格式相容分支，對齊 `_format.json` 單一契約。 |
| **0 外部調用之內部死代碼** | `core/commands/registry.py:287` (`CommandsRegistry.all_modules`)<br>`core/contributes.py:207` (`get_for_current_module`) | 經 `knowledge-db` 全空間檢索，生產代碼 0 調用（`list_modules` + `get_module` 已涵蓋需求；`contributes.get` 為唯一正統查詢入口）。 | **物理刪除**無調用之冗餘方法/函式（同步確認測試無依賴或一併清理）。 |

### 2.2 重構深度候選方案對比

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：局部表層清理 (`S2 + S4` 輕量收斂)** | 僅刪除死代碼與重複之 `.gitignore` 函式、拉平局部深層巢狀，不拆分 `engine.py` 與 `installer.py`，亦不抽離共用輔助層。 | 改動行數少，短期合併速度快。 | `engine.py`（1,020 行）與 `installer.py`（819 行）依然維持 God File 狀態；Provider 尋址與 `yscb_root` 探測邏輯仍散落多檔，無法根治 `P0` 架構腐化。 | ⭐⭐ |
| **方案 B：全維度外科手術重構 (`S1 ~ S6` 完整落地 + `Mode A` 單一入口收斂)** | 1. 針對巨型檔案 `engine.py` 與 `installer.py` 執行 `S6` 職責拆解與 `S3` Provider/Zip 管線收斂；<br>2. 將散落 6 檔的 `yscb_root` / `host_dir` 探測統一收斂至 `core.uri` 單一正統入口（`D5`）；<br>3. 全面消除繞過 `core.vfs` 的原生檔案操作；<br>4. 對 `dispatcher.py`、`locale.py`、`validator.py` 長函式執行 `S1` 階段拆解與 `S4` 表驅動/衛語句扁平化；<br>5. 依 `Mode A` 徹底拔除相容別名與死分支。 | 徹底消除 `P0` 巨型檔案與雙軌實作破窗，確立 `core.uri` $\to$ `core.vfs` $\to$ 上層服務的乾淨單向 DAG 拓撲，大幅降低認知複雜度與維護成本。 | 涉及 `core` 內部多個檔案協同調整，需透過完整回歸測試套件嚴格驗證行為與異常語意 100% 無損。 | ⭐⭐⭐⭐⭐<br>**(推薦)** |

### 3.1 `D1 ~ D5` 五維度分級靜態診斷矩陣

以下為 `ys_codebase/source/core/` 全模組靜態掃描之完整分級病灶座標表（共計 **P0：3 項**、**P1：11 項**、**P2：4 項**）：

| 編號 | 檔案路徑與行號區間 | 維度 | 嚴重度 | 具體結構病徵描述 | 對應策略 |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **F-01** | `core/engine.py:1-1020`<br>`core/installer.py:1-819` | `D1` | **P0** | **巨型破窗檔案與跨檔雙軌實作 (God Files & Dual-Track Duplication)**：`engine.py` (1,020 LOC) 混雜底層目錄原子交換、Zip 安全解壓、3-Tier 套件下載、SemVer 依賴求解、組態模板深度鑲嵌、快照備份還原與版本遷移階梯共 7 大正交職責；且 `installer.py` (819 LOC) 的 `fetch_and_extract_zip` (L89-145)、`_restore_module_package` (L678-770)、`_discover_available_versions_for_module` (L147-186) 與 `engine.py` 的 `act_download` / `_get_module_manifest_from_provider_or_local` 存在高度重複的本地/遠端 Provider 尋址與解壓邏輯。 | `S1`, `S3`, `S6` |
| **F-02** | `core/installer.py:15-86`<br>`core/pip_manager.py:17-68` | `D2` / `D3` | **P0** | **`.gitignore` 託管區塊雙重實作與行為分歧**：`installer.generate_internal_gitignore` 與 `pip_manager.ensure_yscb_gitignore` 重複定義完全相同的 12 項忽略清單常數，卻分別採用「正则替換 + 原生 `open()`」與「字串 `split` + `vfs.write_text()`」兩套實作，極易在維護時產生狀態不一致。 | `S3`, `S5` |
| **F-03** | `core/config.py:18-27, 36-44, 109-149`<br>`core/telemetry.py:16-39`<br>`core/commands/dispatcher.py:44-59`<br>`core/ide_projector.py:37-43`<br>`core/pip_manager.py:85-92` | `D5` | **P0** | **繞過 `core.uri` / `core.vfs` 基礎設施抽象與重複尋根**：<br>1. `telemetry._discover_yscb_root`、`dispatcher._get_yscb_root`、`config._get_yscb_root`、`ide_projector._resolve_yscb_root`、`pip_manager._resolve_yscb_root` 各自重複手寫 `YSCB_HOST_DIR` 與 `yscb.config.json` 讀取邏輯，未統一調用 `uri.resolve_yscb_root()` / `uri._get_host_config()`；<br>2. `config.py` 頂部以 `try: from core import uri, vfs except ImportError` 防禦並保留 25 行 `tempfile.mkstemp` 原子寫入備援死代碼，違反微內核內部確定性依賴契約。 | `S3`, `S5`, `S6` |
| **F-04** | `core/commands/dispatcher.py:496-706` (`dispatch`)<br>`core/commands/dispatcher.py:346-481` (`dispatch_local`) | `D1` / `D3` | **P1** | **長程序與多階段職責交織**：`dispatch()` 長達 210 行，混雜標準流重組、環境變數注入、核心快捷指令路由、模組別名解析、模糊拼寫建議 + Telemetry 紀錄、三層 `--help` 攔截、純分支檔案原始碼字串嗅探 (`f"def {func_name}(" in content`)、熱派發與背景 Daemon 喚醒；`dispatch_local()` 長達 135 行，混雜 Hook 觸發、參數解析、`sys.path` 掛載、動態模組載入與執行異常處理。 | `S1`, `S3`, `S4` |
| **F-05** | `core/commands/dispatcher.py:111-185` (`_try_hot_dispatch`) | `D1` / `D3` | **P1** | **IPC 串流解析與連線探測耦合**：`_try_hot_dispatch` (75 行) 同時負責 `daemon.json` 讀取與殭屍進程清理、HTTP 請求建構、NDJSON chunk 緩衝區切割與 `terminal_stream` / `task_finish` 封包分派，縮排達 5 層。 | `S1`, `S4` |
| **F-06** | `core/contributes.py:293-403`<br>(`_collect_donor_contributes`, `_apply_project_overrides_and_persist`) | `D3` | **P1** | **深層巢狀與重複校驗日誌樣板**：`_collect_donor_contributes` 與 `_apply_project_overrides_and_persist` 縮排達 5~6 層，且兩處重複編寫「調用 `validate()` $\to$ 走訪 `val_res.errors` 輸出 `logger.warning` $\to$ 處理 `core` 之 `commands`/`locales` `__modules__` 注入 $\to$ `_deep_merge`」的同構樣板。 | `S1`, `S3`, `S4` |
| **F-07** | `core/commands/contributes_cmd.py:70-198`<br>(`_check_single_file_mode`, `_check_modules_mode`) | `D3` | **P1** | **模組與專案覆寫校驗迴圈重複**：`_check_modules_mode` (84 行) 內部對 `module://<donor>/contributes/*.json` 與 `config://<donor>/contribute.json` 執行高度重複的「讀取 JSON $\to$ 取得 `target_format` $\to$ `ContributesValidator.validate` $\to$ 若 `target == 'core'` 附加 `_append_locale_validation_errors` $\to$ 渲染報告」流程，且與 `_check_single_file_mode` 邏輯重疊。 | `S1`, `S3` |
| **F-08** | `core/locale.py:194-236, 281-330, 449-515` | `D1` / `D3` | **P1** | **語系尋址與遞迴插值複雜度過高**：`_get_module_locales_decl` (50 行) 在 `base_dir` 與 `resolved_base` 兩處重複編寫完全相同的 `contributes/core.json` 讀取與底線鍵過濾邏輯；`_interpolate_template` (67 行) 內嵌閉包 `_replace_match` 處理候選模組展開與遞迴插值，認知負擔高。 | `S1`, `S3` |
| **F-09** | `core/update_checker.py:92-150, 181-290` | `D3` | **P1** | **本地與遠端版本探測邏輯散落**：`check_updates`、`_fetch_latest_host_script_version` 與 `_fetch_latest_version` 中重複處理「判斷是否為 `http(s)://` $\to$ 解析本地相對路徑 $\to$ 發起 `urllib.request.Request` 讀取」的模式，且與 `engine.act_fetch` 職責重疊。 | `S1`, `S3` |
| **F-10** | `core/vfs/os_backend.py:231-312` (`atomic_write`) | `D1` / `D3` | **P1** | **原子寫入上下文管理器過長且巢狀過深**：`OSBackend.atomic_write` (82 行) 將暫存檔命名、檔案開啟、flush/fsync、Windows 10 次重試回退替換與 `finally` 清理全部塞在單一函式內，Windows 重試區塊縮排達 6 層。 | `S1`, `S4` |
| **F-11** | `core/commands/resolver.py:42-161` (`OptionResolver.resolve`) | `D3` | **P1** | **單一迴圈承載三大解析階段**：`OptionResolver.resolve` (120 行) 在單一 `while` 迴圈中同時處理選項字串切分、正交群組互斥檢查、帶參選項值提取與 `choice` 驗證、以及末尾的位置參數必填/列舉檢查，縮排達 5 層。 | `S1`, `S4` |
| **F-12** | `core/commands/help.py:132-228` (`HelpRenderer.render_cmd_help`) | `D3` | **P1** | **選項渲染重複與長函式**：`render_cmd_help` (97 行) 中針對 `cmd_spec.groups` (L187-197) 與 `cmd_spec.canonical_options` (L201-208) 重複編寫完全相同的單一 `OptionSpec` 格式化字串拼接邏輯（`takes_value` 佔位符與 `alias` 前綴拼接）。 | `S1`, `S3` |
| **F-13** | `core/events.py:110-163` (`get_contributed_events`)<br>`core/commands/registry.py:105-220` (`register_module`, `_parse_command_spec`) | `D2` / `D3` | **P1** | **Mode A 過時格式相容分支殘留**：`events.get_contributed_events` 保留對 `dict` 及 `{"name": ..., "description": ...}` 等非標準格式的相容解析；`registry._parse_command_spec` 保留對舊版 `case_pros` / `case_cons` 與頂層扁平命令結構的相容分支。 | `S4` |
| **F-14** | `core/engine.py:258-264`<br>`core/contributes.py:207, 273`<br>`core/uri.py:190`<br>`core/commands/registry.py:287` | `D2` | **P1** | **Mode A 冗餘別名與零調用死代碼**：`AtomicEngine` 類別頂部 7 個 `staticmethod` 別名、`ContributesAggregator._deep_merge` 別名、`uri._get_yscb_root` 別名、`contributes.get_for_current_module` 與 `CommandsRegistry.all_modules` 均屬過渡期產物或零調用死代碼。 | `S2` |
| **F-15** | `core/pip_manager.py:149-180`<br>`core/platform/venv.py:10-37` | `D3` | **P2** | **Python 版本標籤與 `site-packages` 路徑計算重複**：`PipManager.get_site_packages_dir`、`get_cross_platform_site_packages_dirs` 與 `venv.ensure_private_venv` 重複解析 `py{major}{minor}` 並拼接平台專屬路徑。 | `S3` |
| **F-16** | `scripts/cli.py:1-518` | `D1` / `D3` | **P2** | **CLI 入口重複樣板與手動子指令分派**：`scripts/cli.py` 內 20 個指令處理函式重複調用 `_normalize_bags`，且 `config()`、`uri()`、`event()`、`contributes()` 四個群組函式手動編寫 `if-elif` 子命令路由表（與 `dispatcher.py` 樹狀路由重複）。 | `S3`, `S4` |
| **F-17** | `core/semver.py:163-221` (`_match_single_clause`) | `D3` | **P2** | **長鏈式 `if-elif` 運算子分派**：`_match_single_clause` 對 `==`、`!=`、`>`、`>=`、`<`、`<=`、`~=`、`^=` 採用長鏈式分支判斷，可透過比較運算子映射表簡化。 | `S4` |
| **F-18** | `core/platform/process.py:38-80, 103-136` | `D3` | **P2** | **Windows Process Creation Flags 重複組裝**：`can_spawn_background_daemon` 與 `spawn_detached` 重複組裝 `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB` 旗標。 | `S3`, `S5` |

---

### 3.2 `S1 ~ S6` 外科手術重構處方箋 (Refactoring Blueprint)

針對上述診斷結果，在 `Mode A` 下制定以下六大無損重構處方：

#### 1. `S6` 正交職責之物理模組拆分與架構邊界收斂（解決 `F-01`, `F-02`, `F-03`）
- **拆分 `core/engine.py` (1,020 LOC) 與收斂 `core/installer.py` (819 LOC)**：
  - 將底層無狀態檔案系統交換、Zip 安全提取與 `.gitignore` 託管區塊管理，或 Provider 套件尋址與下載邏輯，提取為職責專一的內部輔助模組（或清晰分層子模組，例如將共用之壓縮包安全提取 `_extract_zip_safely`、目錄原子交換 `_atomic_swap_dir`、`.gitignore` 軟合併 `generate_internal_gitignore`、以及本地/遠端 Provider 版本與套件探測邏輯集中收斂），徹底消除 `installer.py` (`fetch_and_extract_zip` / `_restore_module_package` / `_discover_available_versions_for_module`) 與 `engine.py` (`act_download` / `_get_module_manifest_from_provider_or_local`) 之間的雙軌重複實作。
  - 保持 `from core.engine import AtomicEngine` 與 `from core.installer import Installer, generate_internal_gitignore`（以及 `core/__init__.py` 懶載入映射）的正統匯出契約。
- **統一 `yscb_root` 與 `host_dir` 尋根單一事實來源 (`core.uri`)**：
  - 於 `core/uri.py` 提供正統尋根介面（`resolve_yscb_root()` 與 `resolve_host_dir()` / `_get_host_config()`），將 `config.py`、`telemetry.py`、`dispatcher.py`、`ide_projector.py`、`pip_manager.py` 中各自手寫的 `yscb.config.json` 探測邏輯統一收斂委派至 `core.uri`，消除 6 處重複尋根代碼。
- **全面貫徹 `core.vfs` 存取契約 (`core/config.py` 等)**：
  - 移除 `core/config.py` 中冗餘的 `try...except ImportError` 與 `_atomic_write_json` 內的 `tempfile.mkstemp` 備援分支，100% 透過 `vfs.read_json` / `vfs.write_json(..., atomic=True)` 操作設定檔。

#### 2. `S1` 業務階段拆解與主幹管線化（解決 `F-04`, `F-05`, `F-10`, `F-11`）
- **`core/commands/dispatcher.py` 管線化拆解**：
  - 將 `dispatch()` (210 行) 拆解為職責明確的內部階段函式：
    1. `_prepare_dispatch_env(argv)`：處理 stdio UTF-8 重組、環境變數與 Registry 載入；
    2. `_resolve_target_module_and_tokens(registry, argv, yscb_abs)`：處理快捷指令、模組別名解析與未知模組模糊建議；
    3. `_check_and_render_help_or_subcommand_error(...)`：處理模組/指令級 `--help`、純分支無子指令檢查與未知子指令報錯；
    4. `_execute_dual_track_dispatch(...)`：執行熱派發嘗試、按需背景喚醒 Server 與本地冷派發，並統一於單一出口記錄 `record_cli_event` 與觸發更新檢查。
  - 將 `_try_hot_dispatch()` (75 行) 拆解為 `_read_active_daemon_endpoint(yscb_abs)` 與 `_stream_hot_dispatch_response(req, timeout_sec)`，使縮排深度控制在 $\le 3$ 層。
- **`core/vfs/os_backend.py` 之 `atomic_write` 拆解**：
  - 將 Windows 平台專屬的「漸進重試與回退替換」邏輯提取為內部輔助方法 `_replace_file_with_retry(tmp_path, norm_target)`，讓 `atomic_write` 主幹僅保留清晰的「建立暫存檔 $\to$ `yield` 寫入並 `fsync` $\to$ `_replace_file_with_retry` $\to$ `finally` 清理」四步結構。
- **`core/commands/resolver.py` 之 `OptionResolver.resolve` 拆解**：
  - 提取 `_consume_option_token(cmd_spec, raw_args, idx, seen_groups, resolved_options)` 與 `_validate_positional_args(cmd_spec, positional_args)`，使 `resolve()` 主幹退化為簡潔的雙階段編排器。

#### 3. `S2` 狀態依賴分析與 Mode A 冗餘入口/死代碼剝離（解決 `F-14`）
- 物理移除 `AtomicEngine` 類別頂部 7 個無狀態 `staticmethod` 轉發屬性（`_parse_dependencies` 等）與 `ContributesAggregator._deep_merge` 靜態屬性。
- 物理移除 `core/uri.py:190` 之 `_get_yscb_root` 別名、`core/contributes.py:207` 之 `get_for_current_module` 與 `core/commands/registry.py:287` 之 `CommandsRegistry.all_modules`（並同步檢查/更新測試調用點）。
- 針對 `AtomicEngine` 內部未讀寫 `self` 狀態之方法（如 `_find_manifest_in_build_tier`、`_find_manifest_in_local_provider`、`_infill_single_template`），剝離為模組級私有純函式或下沉至專職輔助模組。

#### 4. `S3` 跨方法同構模式聚合與樣板抽離（解決 `F-02`, `F-06`, `F-07`, `F-08`, `F-09`, `F-12`, `F-15`）
- **`.gitignore` 單一實作聚合**：將 `pip_manager.ensure_yscb_gitignore` 整併至 `installer.generate_internal_gitignore`（或下沉至共用工具並由 `installer` 重匯出），統一使用正则區塊替換與 `vfs.write_text(..., atomic=True)`。
- **`Contributes` 驗證與注入樣板聚合 (`core/contributes.py` & `contributes_cmd.py`)**：
  - 於 `contributes.py` 提取 `_validate_and_merge_target_payload(target, raw_data, donor_label, aggregated, core_modules_commands, core_modules_locales)`，消除 `_collect_donor_contributes` 與 `_apply_project_overrides_and_persist` 的重複校驗與日誌樣板。
  - 於 `contributes_cmd.py` 提取 `_validate_and_report_payload(target_mod, donor_mod, data, file_label, base_dir)`，消除 `_check_single_file_mode` 與 `_check_modules_mode` 內部的三處重複校驗區塊。
- **`Locale` 宣告載入與 `Help` 選項格式化聚合**：
  - 於 `core/locale.py` 提取 `_read_locales_map_from_dir(dir_path)`，消除 `_get_module_locales_decl` 的重複讀檔過濾邏輯。
  - 於 `core/commands/help.py` 提取 `_format_option_line(opt_name, opt_spec, indent)`，消除 `render_cmd_help` 中分組與非分組選項的重複格式化代碼。
- **跨平台 `venv` 路徑計算聚合**：於 `core/platform/venv.py` 提供 `get_venv_site_packages_dir(yscb_root, py_tag, system_name)`，供 `PipManager` 與 `ensure_private_venv` 共用。

#### 5. `S4` 控制流扁平化與表驅動分派（解決 `F-13`, `F-16`, `F-17`）
- **`scripts/cli.py` 表驅動子命令分派**：將 `config()`、`uri()`、`event()`、`contributes()` 四個群組函式改為通用表驅動分派輔助函式 `_dispatch_subcommand_group(cmd_name, cmd_bags, handlers_map)`，消除四段重複的 `if-elif-else` 分支。
- **`core/semver.py` 比較運算子映射表**：將 `_match_single_clause` 中的 `!=`, `>`, `>=`, `<`, `<=` 分支收斂為比較結果謂詞映射表 `_CMP_PREDICATES`，降低圈複雜度。
- **`Mode A` 過時 Schema 相容分支清理**：移除 `registry._parse_command_spec` 中的 `case_pros` / `case_cons` 分支，並精簡 `events.get_contributed_events` 的非標準格式相容分支。

#### 6. `S5` 資料團塊封裝與常數集中化（解決 `F-02`, `F-18`）
- 將 `.gitignore` 內部忽略標記與清單常數集中定義於單一模組位置，消除跨檔常數複製。
- 於 `core/platform/process.py` 提取 `_get_win32_detached_creation_flags(include_no_window: bool)` 輔助函式與常數 `CREATE_BREAKAWAY_FROM_JOB = 0x01000000`，消除兩處重複的位元旗標組裝。

---

## 3. 結論 (Conclusion)

- **診斷總結**：
  - `ys_codebase/source/core/` 整體架構邊界清晰、100% 遵循標準庫零第三方依賴原則，但在多次功能迭代後累積了 **3 項 `P0`**（`engine.py` / `installer.py` 巨型檔案與雙軌下載解壓、`.gitignore` 雙重實作、6 處重複尋根與局部繞過 `vfs`）、**11 項 `P1`**（長程序、深層巢狀、同構校驗樣板與過渡期別名殘留）與 **4 項 `P2`**（局部重複與長分支鏈）。
- **推薦落地策略**：
  - 採納 **方案 B（全維度外科手術重構 `S1~S6` + `Mode A` 單一正統入口收斂）**。
- **推薦流轉出口與軌道建議**：
  - 若選擇 **「出口 ① 立即原地升級實作」**：由於檢視範圍為 `Module Scope`（涵蓋 `core` 模組多個核心檔案之 `S1~S6` 深度重構與物理職責拆解，預估變更行數 $> 100$ 行），建議依 `/code-optimizer` 步驟 4 規範，於當前子計畫目錄走 **Full Track**（建立/推進 `P01`~`P07`）分階段執行無損重構，並透過 `python yscb.py dev check core` 與 `python yscb.py dev test core` 驗證 100% 回歸通過。
