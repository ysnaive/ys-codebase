# 技術路線圖：微內核架構純化與 CLI 驗證／派發加固 (`core-microkernel-purification-and-cli-hardening`) (Roadmap)

> 主題：微內核架構純化與 CLI 驗證／派發加固 (`core-microkernel-purification-and-cli-hardening`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在對 `ys-codebase / module:core`（`v1.1.0.6`）進行全模組原始碼、契約宣告（`contributes/`）與測試套件審查後，確認存在 **6 項架構純度與執行期邊界問題（`C-01` ～ `C-06`）**：

1. **`C-01` 舊版未分化之跨模組耦合殘留於 `core`（Architecture Impurity）**：
   - `core/providers.py`（L158–292）仍殘留專屬於 `agents-workflow` 階段概念的 `get_phase_cli_guide` 及 `get_phase00_cli_guide` ～ `get_research_cli_guide` 共 11 個函式，且 `tests/test_cli_router.py`（L17–20, L148–230）亦包含對應測試。
   - `tests/test_events_pipeline.py`（L184）硬編碼了 `with patch("agents_workflow.publisher.ensure_jit_release", return_value=False):`，若在未安裝 `agents-workflow` 的純 `core` 獨立環境執行單元測試，會直接拋出 `ModuleNotFoundError`。
   - `core/uri.py` 的 `format_undefined_uri_hint()`（L77–80）與 `tests/test_uri.py`（L261–269）硬編碼了 `if prov == "agents-workflow" or scheme.startswith("workflow."):` 特例分支，違反微內核對上層業務模組零感知的純淨原則。
2. **`C-02` CLI `contributes check` 漏檢專案級 `config://<target>/contribute.json` 且單檔模式誤判目標模組（Validation Blind Spot）**：
   - 執行 `python yscb.py contributes check [module]` 時，`core/commands/contributes_cmd.py`（L96–135）僅掃描 `module://<donor>/contributes/*.json`，完全未檢驗專案層級的 `config://<target>/contribute.json`。
   - 若顯式指定單檔 `python yscb.py contributes check config://<target>/contribute.json`，`contributes_cmd.py`（L72–79）以 `fname[:-5]` 取檔名，將 `target_mod` 誤判為 `"contribute"`（而非父目錄 `<target>`），導致印出 `Target module 'contribute' does not define a _format.json schema` 並回傳 Exit Code `0`（假陽性放行），且未比照 `ContributesAggregator` 支援 `data.get(target_mod, data)` 剝殼。
3. **`C-03` 多層子指令熱派發 (`_try_hot_dispatch`) 參數序列化缺陷（Hot-IPC Subcommand Failure）**：
   - 在 `core/commands/dispatcher.py`（L408, L469）中，當執行 `server_compatible: true` 的多層子指令（如 `uri resolve project://AGENTS.md`、`config get core project_root`、`contributes check`）時，`cmd_disp_name` 被組合成含空白的單一字串（如 `"uri resolve"`）。
   - `_try_hot_dispatch`（L127）將 HTTP Payload 組裝為 `"args": [cmd_name] + args`（即 `["uri resolve", "project://AGENTS.md"]`），導致常駐 `server` 端收到後將第一個 Token 視為 `"uri resolve"`，無法在指令樹中匹配 `"uri"` 節點。
4. **`C-04` `yscb.py list --remote` 死選項缺口（Unimplemented CLI Option）**：
   - `contributes/core.json`（L111）與 `scripts/cli.py`（L297–303）皆定義並傳遞了 `--remote`（`-r`）與 `--provider`（`-p`）參數至 `Installer.cmd_list(remote=remote, provider=provider)`，但 `core/installer.py`（L400–416）內部完全忽略這兩個參數，永遠只列印本地已安裝模組。
5. **`C-05` 組態管理 CLI `config list --local` 死選項與底層 SDK 能力未暴露（Config CLI Observability Gap）**：
   - `contributes/core.json`（L266）為 `config list` 宣告了 `--local` 選項，但 `scripts/cli.py:config_list()`（L45–83）完全未讀取該選項。
   - `core/config.py` 已完整實作 `ConfigManager.inspect(module, key)`（探測有效值、來源層級 `local/project/both/none` 與 `is_overridden` 遮蔽狀態）及 `ConfigManager.delete(module, key, local)`，但 CLI 尚未暴露對應子指令。
6. **`C-06` 群組根指令因 `scripts/cli.py` 同名分發函式繞過 `HelpRenderer` 與拼寫建議（Help & Fuzzy Suggestion Bypass）**：
   - 當使用者輸入群組根指令 `python yscb.py uri`（未帶子指令）或 `python yscb.py uri checkk`（子指令拼寫錯誤）時，`core/commands/dispatcher.py`（L439–466）因偵測到 `scripts/cli.py` 存在 `def uri(` 同名函式（`has_fn = True`），直接跳過 `HelpRenderer.render_cmd_help` 與 `_suggest_command` 模糊拼寫建議，退化為 `scripts/cli.py` 內的手寫簡易輸出。

### 1.2 現況與影響範圍評估
- **架構定調：執行 `core` 微內核 100% 純化去耦合，並一次性補齊 Contributes 驗證、Hot-IPC 子指令路由與 CLI 契約一致性**：
  1. **嚴格微內核邊界（Zero Upper-Module Coupling）**：`core` 僅提供通用機制（URI VFS、Config、Contributes、Commands Dispatcher、Lifecycle Engine、Event Bus、Pip/IDE Projector），徹底清零對 `agents-workflow` 或其他上層模組的名稱與業務邏輯硬編碼。
  2. **宣告與實作 100% 對齊（Zero Dead Options & Full Schema Coverage）**：凡於 `contributes/core.json` 宣告之 CLI 選項與 `core/config.py`、`core/contributes.py` 已支援之核心行為，皆在 CLI 端完整打通並通過自動化測試驗證。

### 1.3 核心根因
1. **模組分化演進過程的歷史遺留**：早期版本在單體結構中實驗了階段感知 CLI 導引與 JIT 生命週期測試，模組分化為獨立 `core` 與 `agents-workflow` 後，部分輔助函式、測試 Mock 與 URI 修復提示特例未隨之剝離。
2. **聚合器與檢驗器演進不同步**：`ContributesAggregator.scan_and_inject()` 後續擴充了階層 ② `config://<target>/contribute.json` 覆蓋機制，但 CLI `contributes_cmd.py:check_contributes()` 仍停留在僅掃描 `module://<donor>/contributes/*.json` 的初期邏輯。
3. **單層指令向多層子指令樹（`FR-12`）升級時的介面落差**：`CommandsRegistry.resolve_command_path()` 升級支援遞迴子指令樹並回傳 `cmd_path: List[str]` 後，`dispatch_local` 已改用 `cmd_path` 陣列，但 `_try_hot_dispatch` 仍沿用字串拼接後的 `cmd_disp_name`，且 `scripts/cli.py` 保留了舊版手動分發函式（`def uri`, `def config`），進而干擾了 `dispatcher.py` 的純分支判定。

---

## 2. 候選架構方案對比 (Candidate Solutions)

針對 `C-01`（微內核跨模組解耦）與 `C-06`（指令樹群組路由與 Help 渲染統一），對比以下三種架構方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：保守修補（保留遺留函式與手寫群組分發，僅修 Bug）** | 保留 `providers.py` 的 `get_phase*_cli_guide` 與 `uri.py` 的 `agents-workflow` 特例；僅修補 `contributes check` 與 `_try_hot_dispatch`。 | 改動行數最少 | `core` 持續夾帶上層模組業務邏輯，違反模組分化原則；`scripts/cli.py` 手寫 Help 與 `HelpRenderer` 雙軌分歧依舊存在 | ⭐️⭐️ |
| **方案 2：硬刪所有群組函式（破壞舊測試相容別名）** | 除移除 `get_phase*_cli_guide` 外，直接刪除 `scripts/cli.py` 中的 `config()`、`uri()`、`event()`、`contributes()` 與 `cmd_*` 相容函式。 | `scripts/cli.py` 最精簡 | 會直接破壞 `tests/test_core_commands.py`、`tests/test_contributes_cmd.py` 等直接呼叫 `cli.uri(bags)` 或 `cli.cmd_event(["list"])` 的既有單元測試相容性 | ⭐️⭐️⭐️ |
| **方案 3：微內核純化移除 ＋ Dispatcher 宣告式群組優先路由（推薦採納）** | 1. **徹底純化 `core`**：移除 `get_phase*_cli_guide`、`test_events_pipeline.py` 的跨模組 `patch` 與 `uri.py` 的 `agents-workflow` 硬編碼特例。<br/>2. **宣告式群組優先**：在 `dispatcher.py` 中，只要 `cmd_spec.cmd` 非空（宣告為擁有子指令樹的群組節點），未帶參數時一律由 `HelpRenderer.render_cmd_help` 渲染，帶未知子指令時一律觸發 `_suggest_command` 報錯；同時保留 `scripts/cli.py` 內的 `uri()`、`config()` 供單元測試直接呼叫時回退使用。 | 100% 達成微內核純化、統一全系統 CLI Help 與模糊建議體驗，同時 100% 向下相容既有單元測試呼叫介面 | 需同步更新 `test_cli_router.py`、`test_uri.py` 與 `test_events_pipeline.py` 內共 3 處舊版耦合斷言 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：保守修補 | 方案 2：硬刪所有群組函式 | 方案 3：微內核純化 ＋ 宣告式群組優先（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 中（需重寫大量既有單元測試呼叫點） | **極高**（100% 標準庫內閉環修改，不引入新相依） |
| **後續維護難度 (Maintenance)** | 高（跨模組遺留與雙軌 Help 持續造成認知負擔） | 低 | **極低**（職責單一，微內核與上層業務模組完全解耦） |
| **可靠性 (Reliability)** | 中（純 `core` 環境跑 `test_events_pipeline` 仍會崩潰） | 中 | **極高**（消除跨模組測試崩潰、假陽性驗證與熱派發斷鏈） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（聚焦於 6 個檔案的精準重構與單元測試補齊） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 `C-01` 微內核跨模組耦合純化 (`core/providers.py`, `core/uri.py`, `tests/`)
1. **純化 `core/providers.py`**：
   - 移除 `get_phase_cli_guide` 及 `get_phase00_cli_guide` ～ `get_research_cli_guide`（L158–292），僅保留 100% 由 `contributes.core.commands` 驅動的通用 `get_agents_cli_guide()`。
   - 同步自 `tests/test_cli_router.py` 移除對 `get_phase*_cli_guide` 的匯入與測試案例。
2. **純化 `core/uri.py:format_undefined_uri_hint()`**：
   - 移除 L77–80 針對 `prov == "agents-workflow" or scheme.startswith("workflow.")` 的硬編碼特例，統一以通用格式回傳：
     ```python
     def format_undefined_uri_hint(
         scheme: str,
         provider: Optional[str] = None,
         binding: Optional[str] = None,
     ) -> str:
         prov = provider or "core"
         bind = binding or ("project_root" if scheme == "project" else "unknown")
         if scheme == "project" or (prov == "core" and bind == "project_root"):
             return "python yscb.py config set core project_root ./"
         return f"python yscb.py config set {prov} {bind} <path>"
     ```
   - 同步更新 `tests/test_uri.py`（L261–269）中對 `format_undefined_uri_hint` 與 `UndefinedURIError` 的斷言。
3. **純化 `tests/test_events_pipeline.py`**：
   - 移除 L184 的 `with patch("agents_workflow.publisher.ensure_jit_release", return_value=False):` 外層包裝，直接對 `events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")` 進行微內核基準效能測試，確保純 `core` 環境可 100% 獨立通過測試。

### 4.2 `C-02` `contributes check` 補齊專案級 `config://<target>/contribute.json` 檢驗 (`core/commands/contributes_cmd.py`)
1. **修正單檔模式目標模組推導與剝殼邏輯（L61–94）**：
   - 當輸入路徑檔名為 `contribute.json`（例如 `config://agents-workflow/contribute.json` 或實體路徑 `.../config/agents-workflow/contribute.json`）時，取其**父目錄名稱**作為 `target_mod`（即 `os.path.basename(os.path.dirname(p))`），而非 `fname[:-5]`。
   - 比照 `ContributesAggregator.scan_and_inject()`（`core/contributes.py` L285），若 `isinstance(data, dict)` 且 `target_mod in data` 且 `isinstance(data[target_mod], dict)`，自動提取 `payload = data[target_mod]` 再送入 `ContributesValidator.validate(..., donor_mod="project")`（為 `skill-creator` 與 `how-to-config-yscb` 的三步編譯守門提供真實的 Schema 檢驗地基）。
2. **全量與模組級模式同步納管 `config://<target>/contribute.json`（L96–142）**：
   - 於 `check_contributes(target_or_uri)` 掃描完 `module://<donor>/contributes/*.json` 後，同步掃描 `config://` 下對應模組（包含指定單一模組名如 `python yscb.py contributes check agents-workflow` 或全模組無參數模式）是否存在 `config://<target>/contribute.json`，若存在則自動執行剝殼與 Schema 驗證（`donor_mod="project"`）並計入 `checked_files_count`。

### 4.3 `C-03` 多層子指令熱派發參數修復 (`core/commands/dispatcher.py`)
1. **保留完整指令路徑 Token 清單**：
   - 將 `_try_hot_dispatch(module_name: str, cmd_path: List[str], args: List[str], yscb_abs: str) -> Optional[int]` 的第二個參數由拼接字串 `cmd_disp_name` 改為列表 `cmd_path: List[str]`。
   - 組裝 HTTP Payload 時改為 `"args": list(cmd_path) + list(args)`（例如 `["uri", "resolve", "project://AGENTS.md"]`），確保常駐 Server Worker 端的 `dispatch()` 能精準走訪多層指令樹。

### 4.4 `C-04` 實作 `yscb.py list --remote` 遠端與本地 Provider 套件清冊查詢 (`core/installer.py`)
1. **補齊 `Installer.cmd_list(remote=..., provider=...)` 分支**：
   - 當 `remote=False` 時維持現有行為（列印 `yscb.config.json` 之 `installed_modules`）。
   - 當 `remote=True` 時，讀取指定 `provider` 或 `default_provider`，探測可用模組及其最新版本（支援本地 Provider 目錄掃描 `*/index.json`、`release/*/index.json` 或遠端 `index.json`），並標示本地是否已安裝（`Installed (vX.Y.Z)` vs. `Available`）。

### 4.5 `C-05` 補齊 `config list --local`、`config inspect` 與 `config unset` (`scripts/cli.py`, `contributes/core.json`)
1. **打通 `config list --local`**：
   - 於 `scripts/cli.py:config_list()` 檢查 `local_only = cmd_bags.has_option("local")`；當啟用 `--local` 時，透過 `core_config.get_raw(m, local=True)` 僅列出存在本機覆蓋設定之模組與鍵值。
2. **暴露 `config inspect <module> <key> [--json]` 與 `config unset <module> <key> [--local]`（對齊 `dev check` 1:1 葉節點函式契約）**：
   - 於 `contributes/core.json` 的 `commands.cmd.config.cmd` 註冊 `inspect` 與 `unset` 子命令，並於 `core/scripts/cli.py` 明確定義對應頂層葉節點函式 `def config_inspect(cmd_bags: CmdBags) -> int:`（呼叫 `core_config.inspect(mod_name, key)`，清晰輸出 `effective`、`source`、`project_value`、`local_value` 與 `is_overridden`）與 `def config_unset(cmd_bags: CmdBags) -> int:`（呼叫 `core_config.delete(mod_name, key, local=local_flag)`），確保 100% 通過 `python yscb.py dev check core` 靜態合規檢查。

### 4.6 `C-06` 宣告式指令群組 Help 渲染與拼寫建議統一 (`core/commands/dispatcher.py`, `scripts/cli.py`)
1. **區分「步驟 8 未知子命令攔截」與「步驟 7 無參數預設行為保護（防呆）」**：
   - **步驟 8（未知子命令攔截，如 `yscb uri checkk`）**：在 `core/commands/dispatcher.py` L557 中，只要 `cmd_spec and cmd_spec.cmd and not cmd_spec.args` 為真（代表該節點不接受自由位置參數，僅接受 `cmd` 定義之子命令），當使用者帶入非 `-` 開頭之未知 Token 時，**移除 `if not has_fn:` 繞過分支**，一律透過 `_suggest_command(bad_sub, list(cmd_spec.cmd.keys()))` 輸出標準未知子命令錯誤與拼寫建議並回傳 `1`。
   - **步驟 7（未帶子命令時保護跨模組預設行為，如 `agents-workflow plan / roadmap / todo`）**：注意在 `agents-workflow` 等模組中，輸入 `python yscb.py agents-workflow plan`（未帶子命令）時，其 `scripts/cli.py` 的 `def plan()` 設計為預設自動執行 `plan_status`（`roadmap` / `todo` 亦預設執行 `list`）。若在 `dispatcher.py` 步驟 7 一刀切移除 `has_fn` 強制印 Help，將破壞此類模組的無參數預設動作。因此步驟 7 保持 `if not has_fn:` 邏輯，同時將 `core/scripts/cli.py` 內的 `config()`、`uri()`、`event()`、`contributes()` 四個群組函式內部的無參數 fallback 由原本的手寫簡易 `print("Usage: ...")` 改為直接呼叫 `HelpRenderer.render_cmd_help("core", ...)`，既讓 `yscb uri / config / event / contributes` 100% 呈現標準 `HelpRenderer` 輸出並相容舊單元測試，又完全不破壞其他模組群組命令的無參數預設行為。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 在不改變 `core` 對外既有穩定 API 與 100% Python 標準庫零依賴原則的前提下，以單次版本迭代（如 `v1.1.0.7` 或 `v1.1.1.0`）完成微內核純化與 CLI 驗證／派發加固。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：微內核純化去耦合（`C-01`）**
   - 清理 `core/providers.py` 的階段導引函式與 `core/uri.py` 的 `agents-workflow` 特例分支。
   - 更新 `tests/test_cli_router.py`、`tests/test_uri.py` 與 `tests/test_events_pipeline.py`，驗證純 `core` 獨立測試 100% 零跨模組依賴。
2. **Stage 2：Contributes 驗證器與 Dispatcher 雙軌派發修復（`C-02`、`C-03`、`C-06`）**
   - 升級 `core/commands/contributes_cmd.py:check_contributes()` 支援 `config://<target>/contribute.json` 全量與單檔驗證。
   - 修正 `core/commands/dispatcher.py` 的 `_try_hot_dispatch` 子指令路徑陣列傳遞與群組節點 `HelpRenderer` / `_suggest_command` 優先攔截。
3. **Stage 3：CLI 組態與套件列表能力補齊（`C-04`、`C-05`）**
   - 實作 `core/installer.py:cmd_list(remote=True)`。
   - 於 `scripts/cli.py` 與 `contributes/core.json` 打通 `config list --local`、`config inspect` 與 `config unset`，並執行 `contributes check` 與單元測試全數驗收通過。

---

# Part 合流路線圖：技術路線圖：核心測試集純化、碎片收斂與高風險路徑補盲 (`core-test-suite-purification-roadmap`) (Roadmap)

> 來源路線圖：core_test_suite_purification_roadmap.md

# 技術路線圖：核心測試集純化、碎片收斂與高風險路徑補盲 (`core-test-suite-purification-roadmap`) (Roadmap)

> 主題：核心測試集純化、碎片收斂與高風險路徑補盲 (`core-test-suite-purification-roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
對 `ys-codebase / module:core`（`v1.1.0.6`）下的 `tests/` 目錄（共 **28 個測試檔案、137 個 `test_*` 測試方法**）執行全量逐行體檢後，發現因歷次開發計畫採「隨案增量新建 `test_<plan_topic>.py`」模式，累積了 **6 大類測試病灶（`T-01` ～ `T-06`）**：

1. **`T-01` 虛假測驗與寬容放行（Vacuous & Lenient-Pass Tests，共 5 處）**：
   - **`test_venv_core.py::test_ft_08_installer_sync_pip_dependencies`（L188）＆ `test_pip_manager_sdk.py::test_rt_01_...`（L98）**：將 `PipManager.install_packages` 與 `IdeProjector.sync_vscode_settings` 全數 `patch` 掉，呼叫 `installer.sync_pip_dependencies()` 後僅斷言 `self.assertIsNotNone(installer)`，工作區未配置任何 `pip_dependencies`，`mock_install` 實際被呼叫 0 次卻綠燈放行。
   - **`test_remote_zip_bootstrap.py::test_corrupted_zip_fails_safely`（L41）**：Docstring 宣稱驗證損毀 Zip 不污染 `mirror/` 或 `modules/`，實際僅寫入亂碼並呼叫 Python 標準庫 `self.assertFalse(zipfile.is_zipfile(bad_zip))`，完全未調用 `engine.act_download()` 或 `fetch_and_extract_zip()`。
   - **`test_migration_ladder.py::test_migration_ladder_step_through`（L27）**：建立 `1.1.x.py` 與 `1.3.x.py`（僅 `return True`），宣告 `called = []` 卻未使用，僅斷言 `self.assertTrue(engine.act_migrate(...))`。因 `act_migrate()` 在找不到任何腳本時亦回傳 `True`（`engine.py:553`），即使遷移腳本完全未執行也會綠燈放行。
   - **`test_build_git_decoupling.py::test_ft_05_standards_doc_check`（L112）**：向上 8 層尋找外部 `docs/_project/STANDARDS.md`，並包在 `if found:` 內做字串檢查，找不到時直接靜默跳過並 `mark_passed()`。
   - **`test_installer.py::test_status_health_reporting`（L14）**：呼叫 `res = self.installer.cmd_status()` 後僅斷言 `self.assertIn(res, (0, 1))`，無論健康（`0`）或損毀（`1`）皆算通過。
2. **`T-02` 跨檔重複測驗與檔案碎片化（Duplicate & Fragmented Tests，共 7 組）**：
   - **`.gitignore` 內部區塊軟合併重複測 4 次**：散落於 `test_build_git_decoupling.py`、`test_restore_and_jit_modules.py`、`test_distribution_lifecycle.py` 與 `test_venv_core.py`。
   - **`yscb._resolve_self_update_target_url` 100% 複製貼上 2 次**：散落於 `test_cli_router.py`（L227）與 `test_distribution_lifecycle.py`（L34，且連寫兩行 `self.mark_passed()`）。
   - **`yscb._discover_latest_core` 遠端防偽造重複測 2 次**：散落於 `test_distribution_lifecycle.py` 與 `test_restore_and_jit_modules.py`。
   - **`PipManager` 路徑計算與 `sys.path` 注入分散於 3 檔**：`test_venv_core.py`、`test_pip_manager_sdk.py` 與 `test_platform.py`。
   - **`IdeProjector` 軟合併與還原分散於 2 檔**：`test_venv_core.py`（`test_ft_06`, `test_ft_07`）與 `test_ide_projector_cross_platform.py`。
   - **VFS CRUD、Scope 與雙層快照分散於 3 檔**：`test_uri.py`、`test_vfs.py` 與 `test_robustness.py`（`test_robustness.py` 內 5 個測試全數與前兩檔及 `test_engine.py` 重疊）。
   - **`events.broadcast` 執行與異常隔離重複測 3 次**：散落於 `test_engine.py`、`test_events_pipeline.py` 與 `test_config_and_hook_observability.py`。
3. **`T-03` 冗餘、過時與歷史墓碑測驗（Obsolete & Tombstone Tests，共 4 處）**：
   - **`test_contributes_help.py`（整檔測試死代碼）**：測試 `core.contributes.print_global_help()`，但現行 CLI 全域說明早已改由 `core.commands.help.HelpRenderer.render_global_help()` 接管，`print_global_help()` 在生產環境已無任何呼叫者。
   - **`test_build_git_decoupling.py::test_ft_03_builder_outputs_to_dot_build`（L68）**：匯入 `from dev.builder import Builder` 卻完全未使用，僅重複呼叫一次 `uri.resolve("module.build://mock_mod")`。
   - **歷史重構墓碑斷言（Tombstone Assertions）**：`test_events_pipeline.py`（L51–55）專門檢查舊屬性 `hasattr(AtomicEngine, "act_broadcast_event")` 已刪除；`test_core_commands.py::test_ft09_all_modules_cli_contract`（L287–306）跨出 `core` 掃描其餘 4 個模組的 `scripts/cli.py` 是否刪除舊 `process()` 函式。
4. **`T-04` 跨模組越界耦合（Cross-Module Coupling in `core/tests`，共 4 處）**：
   - `test_cli_router.py` 測試專屬於 `agents-workflow` 的 `get_phase*_cli_guide`；`test_events_pipeline.py`（L184）硬 `patch("agents_workflow.publisher.ensure_jit_release")`；`test_build_git_decoupling.py`（L70）匯入 `dev.builder`；`test_core_commands.py`（L290）硬讀取外部模組目錄。此外，有 5 個測試檔各自重複手寫 15 行 `spec_from_file_location` 載入 `yscb.py`。
5. **`T-05` 真實環境污染與狀態洩漏（Workspace State Pollution & Missing `tearDown`，共 3 處）**：
   - `test_config.py` 未標註 `ISOLATED_SANDBOX` 且無 `tearDown` 清理，執行後在 `config://` 殘留 `test_mod_get`、`test_mod_override` 等 **7 個幽靈設定目錄**。
   - `test_contributes.py::test_contribute_json_override_and_local_ignored`（L68）與 `test_events_pipeline.py`（L22, L142, L160）直接覆寫 `config://core/contribute.json` 或 `module://mock_*`，但清理程式碼未包入 `try...finally`，一旦中途斷言失敗即永久污染工作區。
6. **`T-06` 高風險真實邏輯漏測（Critical Coverage Gaps，共 4 處）**：
   - 漏測 `contributes check` 對錯誤 Schema 的負向攔截與 `config://<target>/contribute.json` 驗證（導致 `C-02` 潛伏）。
   - 漏測 `dispatcher._try_hot_dispatch` 內部 HTTP JSON Lines 串流解析與多層子指令參數組裝（導致 `C-03` 潛伏）。
   - 漏測 `Installer.cmd_update` 的同 Major 升級、Major Lock 攔截與自動觸發 `act_migrate` 端到端閉環。
   - 漏測 `OptionResolver` 的 `--` 終止符與 `--flag=false/0/no` 布林反轉解析。

### 1.2 現況與影響範圍評估
- **架構定調：將 `core/tests/` 由「28 個按歷史任務命名的碎片檔」收斂為「20 個按微內核子系統對齊的高內聚測試檔」，達成 100% 真實斷言、100% 沙盒自清理、0 跨模組耦合**：
  1. **一子系統一測試檔（1-to-1 Subsystem Alignment）**：裁撤並吸收 8 個歷史碎片測試檔，消除跨檔重複 I/O 與環境初始化開銷。
  2. **真實驗證閉環（Zero Vacuous Assertions）**：所有測試必須觸發真實目標函式並驗證可觀測副作用（檔案內容、回傳結構、Mock 呼叫參數），嚴禁 `if found:` 條件式放行或空殼 `assertIsNotNone`。
  3. **嚴格 `try...finally` / `tearDown` 狀態隔離**：任何對 `config://`、`module://`、`cache://`、`storage://` 的寫入，100% 保證於異常或完成時清零。

### 1.3 核心根因
1. **任務導向命名導致測試結構碎片化**：過往每次執行 Fast Track 或 Full Track 計畫時，傾向為該次迭代新建專屬測試檔（如 `test_build_git_decoupling.py`、`test_config_and_hook_observability.py`），而非將案例歸入對應子系統主測試檔（`test_uri.py`、`test_config.py`）。
2. **缺乏負向斷言（Negative Testing）與副作用驗證要求**：部分測試僅追求「呼叫不崩潰（No-Crash Smoke Test）」，忽略了驗證錯誤輸入是否被攔截（如 `contributes check`）或內部腳本是否實際執行（如 `act_migrate`、`sync_pip_dependencies`）。

---

## 2. 候選架構方案對比 (Candidate Solutions)

針對 `core/tests/` 的純化與組織方式，對比以下三種方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：僅原地修補 5 個虛假測驗，維持 28 檔現狀** | 不變動檔案結構，僅修改 `test_venv_core.py`、`test_migration_ladder.py` 等 5 處虛假斷言。 | 變更檔案數最少 | 7 組跨檔重複測試、死代碼測試（`test_contributes_help.py`）與歷史碎片檔依然殘留，日後維護仍搞不清應加在哪個檔案 | ⭐️⭐️ |
| **方案 2：極端單檔化（全部塞入單一 `test_core_all.py`）** | 將 28 個檔案全數合併為單一巨型測試檔。 | 只有 1 個檔案 | 超過 3,000 行難以閱讀與定位，且單一子系統失敗時不便單獨針對性跑測 | ⭐️⭐️ |
| **方案 3：按微內核子系統對齊收斂（28 檔 $\rightarrow$ 20 檔）＋ 六維度純化補盲（推薦採納）** | 裁撤 8 個歷史任務碎片檔並無損併入對應子系統主測試檔；同步清除死代碼與跨模組耦合、修復 5 處虛假測驗、加固 `tearDown` 清理，並補齊 4 大高風險漏測路徑。 | 測試檔與 `core/*.py` 子系統清晰對應、消除約 30% 重複測試執行開銷、100% 獨立於上層模組運行 | 需同步清理 `core/contributes.py:print_global_help` 死代碼並搬移合併 8 個碎片測試檔 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：原地小修維持 28 檔 | 方案 2：極端單檔化 | 方案 3：子系統對齊收斂 20 檔 ＋ 六維度純化（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高**（全部在 `core/tests/` 與死代碼清理範圍內完成） |
| **後續維護難度 (Maintenance)** | 高（碎片檔持續膨脹） | 高（單檔過大難維護） | **極低**（每個 `core/<subsys>.py` 皆有唯一明確對應的 `test_<subsys>.py`） |
| **可靠性 (Reliability)** | 中（漏測與環境污染仍在） | 中 | **極高**（補齊負向與邊界測試，且 100% 確保測試後環境零殘留） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（結構化整併與精準斷言替換，可與 `core` 主路線圖同步或獨立推進） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 測試集檔案結構收斂映射表（28 檔 $\rightarrow$ 20 檔）
裁撤以下 **8 個歷史碎片／過時測試檔**，將其有效測試案例整併至對應的子系統主測試檔：

| 序號 | 裁撤之碎片／過時測試檔 | 處置方式與併入目標檔 | 具體整併與去重內容 |
| :---: | :--- | :--- | :--- |
| **1** | `test_contributes_help.py` | **直接刪除**（連同 `core/contributes.py:print_global_help` 死代碼一併移除） | 全域 Help 測試已由 `test_cli_router.py` 與 `test_core_commands.py`（`HelpRenderer`）完整覆蓋。 |
| **2** | `test_config_and_hook_observability.py` | 拆併入 **`test_config.py`** 與 **`test_events_pipeline.py`** | • `test_config_local_no_unwanted_creation...` 併入 `test_config.py`<br/>• `test_hook_observability_execution_and_traceback` 併入 `test_events_pipeline.py` |
| **3** | `test_robustness.py` | 拆併入 **`test_uri.py`** 與 **`test_engine.py`** | • URI 格式防禦與 `module_scope`/`host_scope` 異常復原併入 `test_uri.py`<br/>• `ExecutionContext` 不可變性與雙層快照還原併入 `test_engine.py` |
| **4** | `test_build_git_decoupling.py` | 拆併入 **`test_uri.py`** 與 **`test_distribution_lifecycle.py`** | • 刪除 `test_ft_03_builder_outputs_to_dot_build`（無用 `dev.builder` 匯入）與 `test_ft_05_standards_doc_check`（外部文檔 grep）<br/>• `module.build://` 解析與效能測試併入 `test_uri.py`；`_restore_module_package` 優先 `.build/` 併入 `test_distribution_lifecycle.py` |
| **5** | `test_restore_and_jit_modules.py` | 併入 **`test_distribution_lifecycle.py`** | • 消除重複的 `.gitignore` 軟合併與 `_discover_latest_core` 測試<br/>• 保留 `_is_modules_dirty`、Fresh Clone 自動自舉與遺失來源阻斷測試於 `test_distribution_lifecycle.py` |
| **6** | `test_installer_restore.py` | 併入 **`test_installer.py`** | • 將 `fetch_and_extract_zip` 與 `Installer.cmd_restore` 測試統一歸入 `test_installer.py` |
| **7** | `test_pip_manager_sdk.py` | 併入 **`test_venv_core.py`** | • 統一測試 `PipManager` SDK 匯出、`parse_pip_dependencies`、路徑計算與 Wheel-Only 安裝旗標<br/>• 將 `test_venv_core.py` 內的 `IdeProjector` 測試移交給 `test_ide_projector_cross_platform.py`，實現 `PipManager` 與 `IdeProjector` 職責完全分離 |
| **8** | `test_cli_router.py`（重複項清理） | 原地純化 **`test_cli_router.py`** | • 移除與 `test_distribution_lifecycle.py` 100% 重複的 `test_self_update_url`<br/>• 配合 `C-01` 移除 `get_phase*_cli_guide` 測試 |

### 4.2 5 處虛假測驗 (`T-01`) 實質化改寫規格
1. **重寫 `Installer.sync_pip_dependencies` 整合測試（於 `test_venv_core.py`）**：
   - 於測試沙盒建立 `module://mock_pip_mod/manifest.json`（含 `"pip_dependencies": {"pkg_alpha": ">=1.2.0", "pkg_beta": ""}`）並註冊至 `installed_modules`，同時建立 `project://.vscode` 目錄。
   - 執行 `installer.sync_pip_dependencies()`，明確斷言 `mock_install.assert_called_once_with(["pkg_alpha>=1.2.0", "pkg_beta"])` 且 `mock_sync.assert_called_once()`。
2. **重寫損毀 Zip 防護測試（於 `test_remote_zip_bootstrap.py`）**：
   - 將非 Zip 亂碼檔與 CRC 損毀 Zip 檔分別傳入 `fetch_and_extract_zip()` 與模擬 HTTP 回應的 `engine.act_download()`，斷言必定拋出 `RuntimeError`，且 `module.mirror://` 下自動清理無殘留破檔。
3. **重寫 `act_migrate` 遷移階梯執行驗證（於 `test_migration_ladder.py`）**：
   - 在 `1.1.x.py` 與 `1.3.x.py` 中將 `(ctx["old_version"], ctx["target_version"], "1.1")` 寫入 `os.path.join(ctx["storage_dir"], "mig_trace.json")`。
   - 呼叫 `engine.act_migrate(self.test_mod, "1.0.0.0", "1.3.0.0")` 後，讀取 `mig_trace.json` 斷言執行順序確為 `["1.1", "1.3"]`（證明 `1.2` 被安全跳過且 `1.1`、`1.3` 皆實際執行），並額外測試 Major 跨版（`1.0.0.0` $\rightarrow$ `2.0.0.0`）時不執行 `1.x` 腳本。
4. **重寫 `Installer.cmd_status` 雙分支診斷測試（於 `test_installer.py`）**：
   - 分別測試「所有已註冊模組皆具備 `manifest.json` 與 `scripts/cli.py` $\rightarrow$ 回傳 `0` 且輸出含 `HEALTHY (100% Ready)`」與「註冊了一枚缺少 `scripts/cli.py` 的模組 $\rightarrow$ 回傳 `1` 且輸出含 `Incomplete` 與 `DEGRADED`」。

### 4.3 跨模組解耦 (`T-04`) 與環境零殘留加固 (`T-05`)
1. **消除跨模組依賴與重複 `yscb.py` 載入樣板**：
   - 自 `test_core_commands.py` 移除跨目錄讀取 `server`、`dev`、`knowledge-db`、`agents-workflow` 之 `test_ft09_all_modules_cli_contract`（僅檢查 `core` 自身 `scripts/cli.py` 契約）。
   - 自 `test_events_pipeline.py` 移除 `patch("agents_workflow.publisher.ensure_jit_release")`。
   - 將散落於 `test_restore_and_jit_modules.py`、`test_build_git_decoupling.py`、`test_cli_router.py` 等處重複手寫 15 行的 `spec_from_file_location` 載入 `yscb.py` 邏輯，於收斂入 `test_distribution_lifecycle.py` 時抽離為單一 `_load_yscb_script()` 輔助方法。
2. **補齊 `@require` 沙盒隔離裝飾器、`tearDown` 與 `try...finally` 清理守門**：
   - 為 `test_config.py` 的 `TestConfigManager` 補齊頂部 `@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)` 裝飾器，並於 `tearDown` 遍歷 `config://test_mod_*` 全數執行 `uri.rmtree()` 及呼叫 `config.reload()`，雙重保障沙盒隔離與零幽靈目錄殘留。
   - 於 `test_contributes.py` 與 `test_events_pipeline.py` 將所有對 `config://core/contribute*.json` 及 `module://mock_*` 的建立與移除全部包入 `try...finally` 區塊。

### 4.4 4 大高風險漏測路徑 (`T-06`) 補盲規格
1. **補齊 `test_contributes_cmd.py` 負向與專案級覆蓋測試**：
   - 新增 `test_contributes_check_invalid_payload_returns_error`（驗證傳入未知擴充點或型別錯誤時回傳 `1` 並印出 `[FAIL]` 與近似拼寫建議）。
   - 新增 `test_contributes_check_project_override_file`（驗證 `check_contributes("config://core/contribute.json")` 正確推導目標模組為 `core` 並攔截非法欄位）。
2. **補齊 `test_core_commands.py` 之 `_try_hot_dispatch` 與 `OptionResolver` 邊界測試**：
   - 新增 `test_hot_dispatch_subcommand_payload_and_stream`：Mock `urllib.request.urlopen` 回傳 `terminal_stream` 與 `task_finish` JSON Lines，斷言 `_try_hot_dispatch("core", ["uri", "resolve"], ["project://a"], ...)` 發送之 JSON Payload 中 `"args"` 為 `["uri", "resolve", "project://a"]`，且正確將串流寫入 `stdout`/`stderr` 並返回 `exit_code`。
   - 新增 `test_option_resolver_double_dash_and_bool_false`：驗證 `["--flag=false", "--", "--not-an-option", "pos"]` 解析出 `opts["flag"].params is False` 且 `positional_args == ["--not-an-option", "pos"]`。
3. **補齊 `test_installer.py` 之 `cmd_update` 端到端升級與 Major Lock 測試**：
   - 在本地 Mock Provider 放置 `1.0.0.0`、`1.2.0.0`（含 `scripts/migrations/1.1.x.py` 與 `1.2.x.py`）與 `2.0.0.0`，驗證已安裝 `1.0.0.0` 時執行 `cmd_update` 會升級至 `1.2.0.0`（受 Major Lock 保護不升上 `2.0.0.0`）並觸發遷移腳本。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- **雙路線圖強制綁定／合併立項建議**：由於本路線圖之 `T-02` / `T-04` 與 `core_microkernel_purification_and_cli_hardening.md` 之 `C-01` 高度重疊於 `test_cli_router.py`、`test_uri.py`、`test_events_pipeline.py`，且本路線圖之 `T-06` 新增測試（`test_contributes_check_project_override_file`、`test_hot_dispatch_subcommand_payload_and_stream`）直接依賴 `C-02` 與 `C-03` 的實作，**立項時應將兩份 `core` 路線圖合併為單一 `core` 升級計畫（Full Track 或雙子計畫 Umbrella）同步交付**，避免分開執行造成測試紅燈或重複修改同批測試檔。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：清理死代碼、跨模組耦合與裁撤 8 個碎片測試檔（`T-02`、`T-03`、`T-04`）**
   - 移除 `core/contributes.py:print_global_help` 與 `tests/test_contributes_help.py`。
   - 將 `test_config_and_hook_observability.py`、`test_robustness.py`、`test_build_git_decoupling.py`、`test_restore_and_jit_modules.py`、`test_installer_restore.py`、`test_pip_manager_sdk.py` 按映射表無損整併至對應主測試檔並刪除舊檔。
2. **Stage 2：改寫 5 處虛假測驗與加固沙盒 `tearDown` 零殘留（`T-01`、`T-05`）**
   - 實質化改寫 `sync_pip_dependencies`、損毀 Zip、`act_migrate` 與 `cmd_status` 測試斷言。
   - 為 `test_config.py`、`test_contributes.py`、`test_events_pipeline.py` 補齊 `try...finally` 與 `tearDown` 狀態清理。
3. **Stage 3：補齊 4 大高風險漏測路徑並全量驗收（`T-06`）**
   - 新增 `contributes check` 負向與專案覆蓋測試、`_try_hot_dispatch` 串流與子指令測試、`OptionResolver` 邊界測試及 `cmd_update` 升級測試，執行 `python yscb.py dev test core` 確保 20 個測試檔 100% 綠燈通過且工作區 `git status` 完全乾淨。
