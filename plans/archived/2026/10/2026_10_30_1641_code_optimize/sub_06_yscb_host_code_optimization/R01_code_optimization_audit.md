# 專題調研與分析報告：yscb.py 引導宿主五維度靜態診斷與 Mode A 重構處方 (R01_code_optimization_audit.md)

> 調研主題：yscb.py 超薄引導宿主五維度靜態診斷與 Mode A 收斂處方  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize / sub_06_yscb_host_code_optimization  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 在完成 `sub_01`（`core`）至 `sub_05`（`agents-workflow`）五大生態系模組之 `/code-optimizer`（`Mode A`）重構與收斂後，專案根目錄微核心引導宿主 [`yscb.py`](../../../yscb.py)（`793` LOC）尚未經歷同等標準之靜態診斷與歷史包袱清理。
  - 依據 [`docs/core/cli_commands_architecture.md`](../../../docs/core/cli_commands_architecture.md)（§1.1 `DN-21`），`yscb.py` 的唯一法定職責為 **100% Python 標準庫之超薄引導宿主 (Ultra-Thin Host Bootstrapper)**：
    1. **冷啟動自舉命令**：攔截 `init` 與 `self-update`（因執行時 `.modules/core` 尚未存在或需直接原子替換宿主腳本）。
    2. **運行環境探測與安全令牌注入**：注入 `.venv` 路徑、生成一次性 `YSCB_HOST_DISPATCH_TOKEN`、強制僅將 `.modules/` 掛載入 `sys.path`（嚴禁退化讀取 `source/`）。
    3. **Fresh Clone 自癒與全權委派**：當 `yscb.config.json` 存在但 `.modules/` 缺失或髒污時，透過 `_auto_bootstrap_and_restore_if_needed` 引導下載 `core` 並觸發 `restore`，隨後 **100% 委派予 `core.commands.dispatch(argv)`**。
  - 然而歷次將 CLI 路由、事件廣播、命令拼寫建議與 `restore` 實作遷入 `core` 模組時，為避免修改既有單元測試，在 `yscb.py` 中殘留了未引用之標準庫匯入、廢棄常數、全域快取字典與 **8 個僅供舊測試直接點名呼叫的歷史相容轉發殼層 (Pass-through Shims)**，同時內部存在 HTTP 下載/Proxy 繞過邏輯分裂與長函式認知負載過高等問題。
- **調研目標與範疇**：
  - **檢視範圍 (`File Scope`)**：根目錄 [`yscb.py`](../../../yscb.py)（`793` LOC，共 38 個頂層常數與函式符號）及其在 `ys_codebase/source/core/` 與 `ys_codebase/source/dev/` 之所有入向引用點。
  - **生命週期模式 (`Mode A：收斂期 / 允許破壞性清理`)**：對 0 調用死代碼與歷史轉發殼層採取零容忍清除策略，精確盤點 `core/tests/` 受影響之測試案例行號，並開立 `S1~S6` 行為無損重構處方箋。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 `Mode A` 死代碼與未引用符號清冊（`yscb.py` 內部與全倉 `0` 實質使用）

以下符號在 `yscb.py` 內部與全倉 `ys_codebase/source/` 均無任何實質調用，`Mode A` 處置為**直接物理移除**：

| 符號 / 語句 | `yscb.py` 行號 | 外部引用數 | 根因剖析與 `Mode A` 清除依據 |
| :--- | :---: | :---: | :--- |
| `import difflib` | `L7` | `0` | 早期 `_suggest_command` 實作於 `yscb.py`，遷入 `core.commands.dispatcher` 後遺留之無用匯入。 |
| `import importlib.util` | `L8` | `0` | 早期動態載入模組 CLI 遷入 `core.commands.dispatcher` 後遺留之無用匯入。 |
| `INTERNAL_IGNORE_BEGIN`<br/>`INTERNAL_IGNORE_END` | `L22-L23` | `0` | `.gitignore` 託管區塊標記已由 `core/installer.py:21-22` 定義並維護，宿主內 `0` 引用。 |
| `CORE_COMMANDS: Set[str]` | `L25-L29` | `0` | 核心命令集合已由 `core.commands.registry` 管理，宿主內 `0` 引用（且清單已過時，漏列 `contributes`、`locale`）。 |
| `_MODULE_CACHE: Dict[str, Any]` | `L31` | `0` | 模組動態載入快取已由 `core.commands.dispatcher._MODULE_CACHE` 接管，宿主內 `0` 引用。 |
| `_resolve_self_update_target_url` 之 `provider` 參數 | `L207-L209` | 僅 `test_distribution_lifecycle.py:48` 測試「被忽略」 | 函式簽名為 `(provider: Optional[str] = None, custom_url: Optional[str] = None)`，函式體僅 `return custom_url if custom_url else DEFAULT_SELF_UPDATE_URL`，完全未使用 `provider`。應收斂簽名為 `_resolve_self_update_target_url(custom_url: Optional[str] = None) -> str`。 |

---

### 2.2 `Mode A` 歷史相容轉發殼層清冊（生產路徑 `0` 調用，僅舊測試直接點名）

以下 **8 個函式**在 `yscb.py` 正常 CLI 生命週期（`main()` 及其下游）中 **調用次數為 `0`**，唯一存在理由是舊單元測試直接以 `yscb.<func>()` 呼叫。在 `Mode A` 下應**全數自 `yscb.py` 拔除**，並將對應測試對齊至 `core` 模組之權威實作入口：

| 宿主轉發殼層函式 | `yscb.py` 行號 | 宿主內部生產調用 | 權威實作位置 (SSOT) | 需同步更新之 `core/tests/` 座標與遷移方式 |
| :--- | :---: | :---: | :--- | :--- |
| `_suggest_command(unknown_cmd, candidate_pool)` | `L722-L725` | `0` | `core.commands.dispatcher._suggest_command` | - `test_cli_router.py:74-80`：改測 `core.commands.dispatcher._suggest_command`。<br/>- `test_core_commands.py:258, 261-262`：移除對 `yscb._suggest_command` 的過時相容斷言。 |
| `_print_global_help()` | `L728-L731` | `0` | `core.commands.dispatcher.dispatch(["--help"])` | - `test_cli_router.py:50`：改呼 `dispatch(["--help"])` 或 `yscb.main(["--help"])`。<br/>- `test_core_commands.py:259`：移除 `hasattr(yscb, "_print_global_help")` 斷言。 |
| `cmd_event(argv)` | `L677-L678` | `0` | `core.commands.cmd_event.execute` / `dispatch(["event", ...])` | - `test_events_pipeline.py:103, 108`：改呼 `dispatch(["event", "list"])`（或 `yscb.main(["event", "list"])`）。 |
| `_ensure_jit_lifecycle_pre(cmd)`<br/>`_ensure_jit_lifecycle_post(cmd, exit_code)` | `L681-L696` | `0` | `core.commands.dispatcher.dispatch_local` 內建 `pre_cli_dispatch` / `post_cli_dispatch` 廣播；自舉命令（`init`、`self-update`）在 `yscb.main` 直接攔截天然不經過 `dispatch_local` | - `test_events_pipeline.py:83-98, 167-178`：改為驗證透過 `dispatch` / `dispatch_local` 執行一般命令時觸發 `pre_cli_dispatch` 與 `post_cli_dispatch`，而 `yscb.main(["init", "--help"])` / `yscb.main(["self-update", "--help"])` 短路不觸發 `core.events.broadcast`。 |
| `cmd_restore(argv)`<br/>`_restore_module_package(...)`<br/>`_generate_internal_gitignore(yscb_dir)` | `L651-L674`<br/>`L586-L592`<br/>`L501-L507` | `0`（`main()` 收到 `restore` 時，由 `_auto_bootstrap_and_restore_if_needed` 引導 `core` 就緒後，交由 `dispatch(["restore"])` $\to$ `Installer.cmd_restore` 執行） | `core.installer.Installer.cmd_restore`<br/>`Installer._restore_module_package`<br/>`core.installer.generate_internal_gitignore` | - `test_distribution_lifecycle.py:341`：改呼 `Installer().cmd_restore()` 或 `yscb.main(["restore"])`。<br/>- `test_distribution_lifecycle.py:459`：改呼 `Installer()._restore_module_package(...)`（註：`_bootstrap_package_from_provider` 仍保留於 `yscb.py` 供 `core` 冷啟動自癒使用，`test_distribution_lifecycle.py:397` 繼續測試 `_bootstrap_package_from_provider`）。 |

---

### 2.3 五維度靜態診斷矩陣 (`D1 ~ D5`)

| 嚴重度 | 診斷維度 | `yscb.py` 座標 | 症狀描述與根因剖析 | 對應處方 (`S1~S6`) |
| :---: | :---: | :--- | :--- | :--- |
| **P0** | **D2 死代碼與相容債** | `L7-L8`, `L22-L31`, `L207`, `L501-L507`, `L586-L592`, `L651-L696`, `L722-L731` | 共計 **2 個無用匯入、4 個死常數/快取、1 個冗餘參數、8 個歷史相容轉發殼層**（約 `130` LOC），使 `yscb.py` 混入大量已遷入 `core` 的舊職責殘影。 | **`S6` 死代碼與相容殼層物理清除** + 同步更新 `core/tests/` 4 支測試檔。 |
| **P1** | **D3 跨處重複邏輯** | `L168-L169` (`_fetch_and_extract_zip`)<br/>`L270-L280` (`cmd_self_update`)<br/>`L377-L378` (`_discover_latest_core`) | **HTTP 請求建構與 Localhost Proxy 繞過不一致**：`cmd_self_update` 針對 `localhost` / `127.0.0.1` 建立 `ProxyHandler({})` opener 並帶入 `User-Agent: yscb-host/2.0`，但 `_fetch_and_extract_zip` 與 `_discover_latest_core` 卻直接呼叫 `urllib.request.urlopen(req)`，在本機 HTTP Provider 測試或企業 Proxy 環境下行為不一致且重複造輪子。 | **`S2` 提煉無狀態 HTTP 輔助函式 `_fetch_url_bytes(url: str, timeout: int = 15) -> bytes`**：統一封裝 `User-Agent` 標頭與 `localhost / 127.0.0.1` 免 Proxy opener，三處統一調用。 |
| **P1** | **D3 內部重複探測** | `L599-L606` (`_auto_bootstrap_and_restore_if_needed`) vs `L699-L706` (`_read_module_manifest_version`) | `_auto_bootstrap_and_restore_if_needed` 內部手寫 7 行 `try...json.load` 讀取 `.modules/core/manifest.json` 的 `version`，與下方現成的 `_read_module_manifest_version(core_dest)` 完全重複。 | **`S2` 內部復用**：直接以 `_read_module_manifest_version(core_dest) == expected_core_ver` 取代手寫 JSON 讀取區塊。 |
| **P1** | **D1 認知複雜度與長函式** | `_discover_latest_core` (`L334-L388`, `55` LOC, 巢狀 5 層)<br/>`cmd_self_update` (`L252-L312`, `61` LOC)<br/>`cmd_init` (`L424-L485`, `62` LOC) | - `_discover_latest_core` 將「本地目錄 3 種格式探索 (`index.json` / `.zip` 檔名掃描 / 子目錄 `manifest.json`)」與「遠端 HTTP `index.json` 探索」耦合於單一 5 層巢狀函式。<br/>- `cmd_self_update` 混雜旗標解析、本地/遠端下載、AST 語法檢驗、`.tmp/.bak` 原子替換與 `UpdateChecker` 快取失效。<br/>- `cmd_init` 混雜旗標解析、既有組態健康檢查、`core` 探索解壓、組態落盤與首次 `reload`。 | **`S1 / S3` 業務階段聚合拆解與衛句扁平化**：<br/>1. `_discover_latest_core` 拆分為 `_discover_core_from_local_dir(cand_dir)` 與 `_discover_core_from_remote_index(url)`。<br/>2. `cmd_self_update` 提取 `_load_self_update_source_bytes(target_url)` 與 `_atomic_swap_host_script(script_path, new_bytes)`。<br/>3. `cmd_init` 提取 `_parse_init_args(argv)`，主流程保持清晰的四階段編排。 |
| **P2** | **D5 寬泛異常捕捉** | `L180`, `L354`, `L371`, `L385`, `L705` | 多處 `except Exception:` 捕捉 JSON 解析或檔案讀取錯誤，可收斂為明確的 `(OSError, ValueError, KeyError, zipfile.BadZipFile)`，提升靜態型別與異常精確度。 | **`S5` 異常精確化**：將已知 I/O 與解析邊界收斂為具體標準庫例外元組。 |

---

### 2.4 `S1 ~ S6` 外科手術重構處方與量化預估

1. **剛性架構防線（100% 嚴禁觸碰或弱化）**：
   - **100% Python 標準庫約束**：`yscb.py` 頂層與熱路徑嚴禁引入任何第三方套件，僅在 `_activate_runtime_env()` 完成後動態載入 `.modules/core`。
   - **嚴禁載入 `source/` 鐵律**（`L769-L774`）：`_activate_runtime_env` 僅能掛載 `.modules/`，嚴禁新增任何指向 `ys_codebase/source/` 的 fallback。
   - **宿主分發安全令牌**：`main()` 必須維持生成 `YSCB_HOST_DISPATCH_TOKEN` 並注入 `os.environ`。
2. **重構前後規模預估**：
   - **重構前**：`793` LOC，頂層定義 `38` 個符號（含 5 個死常數/快取、8 個歷史相容殼層）。
   - **重構後預估**：約 **`590 ~ 620` LOC（淨減約 `-170 ~ -200` LOC，`~23%` 縮減）**，所有業務函式控制在 `40` LOC 以內，職責 100% 純化為「冷啟動自舉 (`init` / `self-update`) + Fresh Clone `core` 自癒 + 薄路由委派 (`dispatch`)」。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  - `yscb.py` 作為微核心超薄引導宿主，目前仍有約 **23% (`~180` LOC)** 的篇幅屬於早期架構演進遺留之死常數、未引用匯入與僅供舊測試呼叫的轉發殼層，且存在 3 處 HTTP 請求建構邏輯分裂與 3 個超過 55 行的多階段複合函式。
  - 透過 `Mode A` 拔除上述死代碼與 8 個歷史轉發殼層、提煉 `_fetch_url_bytes` 共用輔助函式並執行 `S1` 業務階段拆解，可使 `yscb.py` 徹底回歸 `DN-21` 超薄宿主設計定位，同時消除 `core/tests/` 對過時宿主內部符號的耦合。
- **後續建議（選填）**：
  - 下次透過 `/continue` 恢復 `sub_06_yscb_host_code_optimization` 時，建議直接將本計畫升級為 **`Full Track`（搭配 `/auto`）或 `Fast Track`**，依本報告 §2.1 ~ §2.4 處方同步重構 `yscb.py` 與 `ys_codebase/source/core/tests/` 下 4 支測試檔，並執行 `python yscb.py dev test core` 完成 100% 測試與覆蓋率驗收。

