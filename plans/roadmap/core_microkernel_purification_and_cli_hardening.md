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
