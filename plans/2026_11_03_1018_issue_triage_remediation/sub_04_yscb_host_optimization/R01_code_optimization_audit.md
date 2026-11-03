# 專題調研與分析報告：唯一宿主 `yscb.py` 五維度靜態診斷與無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：唯一宿主 `yscb.py` 五維度靜態診斷與收斂評估  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  歷經 `v1.2.1` ~ `v1.2.2` 多輪發布治理（同三元組 `pruned` 自動補位、本地同版 `source/` 確定性動態打包、`virtiofs`/Windows 目錄鎖定三階段鑑別與就地原子同步、`index.json` SHA-256 強制驗證與 `--ignore-sha256`、`self-update` AST 結構與伴隨 `.sha256` 校驗），唯一單檔自舉宿主 [yscb.py](../../yscb.py) 已成長至 **1,526 行（43 個頂層函式、10 個模組級常數）**。需要透過 `/code-optimizer` 進行系統性五維度（`D1~D5`）體檢，盤點哪些屬於不可削減之零依賴自舉核心能力，哪些屬於歷史遺留死代碼、跨函式重複樣板（`D3`）或超長多階段程序（`D1`/`D3`）。
- **調研目標與範疇**：
  ### 1.1 定錨基準與範圍摘要
  - **檢視範圍**：`File Scope` — 唯一宿主單檔 [yscb.py](../../yscb.py)（1,526 LOC）。
  - **生命週期與相容性模式**：**混合雙軌定錨（對外函式 `Mode B` ／ 對內函式 `Mode A`）**
    - **對外公開介面（`Mode B` 維護期 — 嚴守向下相容）**：CLI 與外部模組契約入口（`main`、`cmd_init`、`cmd_self_update`、`cmd_restore`、`load_config`、`dispatch_module` 及頂層常數 `__version__`、`CONFIG_FILENAME`、`DEFAULT_PROVIDER_URL`、`LEGACY_PROVIDER_URLS`、`DEFAULT_SELF_UPDATE_URL`）保持 100% 簽名與行為等價。
    - **對內私有函式與歷史過渡殼層（`Mode A` 收斂期 — 允許破壞性清理）**：所有內部輔助函式（`_*`）及零生產調用之過時轉發殼層，強制收斂為單一正統實現並清除冗餘包裝，必要時同步更新 `ys_codebase/source/core/tests/` 直接點名舊內部函式之測試。
  - **代理執行軌道**：`[軌道 1：純主代理內聯執行]`（0 子代理冷啟動開銷）。
  - **現行測試基線狀態**：`core` (243/243 Passed)、`dev` (86/86 Passed)、`server` (53/53 Passed)。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- **核心分析與實證內容**：

### 2.1 契約邊界與內部工具函式查驗表

經全倉 AST 符號掃描與 `knowledge-db search`（涵蓋全部生產代碼 `ys_codebase/source/*` 與測試集 `tests/`）雙重查驗，`yscb.py` 頂層符號分類如下：

#### (A) 對外公開契約入口與常數（`Mode B` — 強制凍結簽名與行為）
| 符號名稱 | 行號區間 | 外部/CLI 契約角色 | 處置原則 (`Mode B`) |
| :--- | :---: | :--- | :--- |
| `__version__`, `CONFIG_FILENAME`, `DEFAULT_PROVIDER_URL`, `LEGACY_PROVIDER_URLS`, `DEFAULT_SELF_UPDATE_URL` | `L20-L29` | 宿主版本與預設 Provider 常數（受 `dev check`、`update_checker` 與測試檢驗） | **100% 原樣保留** |
| `load_config(start_dir=None)` | `L168-L193` | 宿主組態讀取與舊 Provider URL 無感遷移 API | **保留公開簽名** |
| `cmd_self_update(argv)` | `L749-L833` | `python yscb.py self-update` 原生自舉入口 | **保留公開簽名**（內部依 `S1/S3` 拆解階段） |
| `cmd_init(argv)` | `L1005-L1095` | `python yscb.py init` 原生自舉入口 | **保留公開簽名**（內部依 `S1/S3` 拆解階段） |
| `cmd_restore(argv)` | `L1376-L1405` | 冷自舉環境還原公開函式（被 `test_distribution_lifecycle.py` 與 `test_installer.py` 直接呼叫驗證無 `core` 時之獨立還原能力） | **保留公開簽名** |
| `dispatch_module(module_name, args)` | `L1465-L1468` | 宿主對 `core.commands.dispatcher.dispatch` 之公開委派門面（被 `cmd_init`、`_auto_bootstrap_and_restore_if_needed`、`cmd_restore` 與多個測試 Mock/呼叫） | **保留公開簽名** |
| `main(argv=None)` | `L1471-L1522` | 唯一 CLI 主入口（受 `self-update` AST 結構檢查與全倉測試保護） | **100% 原樣保留** |

#### (B) 零生產調用之歷史遺留死代碼 / 1 行轉發殼層（`Mode A` — 雙重查證確認，建議物理拔除）
| 符號名稱 | 行號區間 | `yscb.py` 內部呼叫數 | 全倉生產代碼呼叫數 | 僅存測試引用座標（需同步清理/改寫） | 診斷結論 (`Mode A`) |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `INTERNAL_IGNORE_BEGIN`, `INTERNAL_IGNORE_END` | `L30-L31` | `0` | `0`（`core/installer.py` 自有獨立定義） | `0` | **純孤兒死常數**（早年 `_generate_internal_gitignore` 遷入 `core/installer.py` 後遺留），物理刪除 |
| ` difflib`, `importlib.util` (頂層 import) | `L7, L10` | `0` | `0` | `0` | **未使用之頂層 `import`**（早年命令建議與動態載入遷入 `core.commands` 後遺留），物理刪除 |
| `_generate_internal_gitignore(yscb_dir)` | `L1111-L1117` | `1`（僅 `cmd_restore` L1382） | `0` | `0` | **冗餘跨層回呼包裝**：當 `.modules/core` 存在時 `cmd_restore` L1387 直接轉派 `core restore`（內部已生成 gitignore）；當 `.modules/core` 不存在時 `from core.installer import ...` 必拋 `ImportError` 被靜默吞掉，屬 **100% 無效死邏輯**，物理刪除 |
| `cmd_event(argv)` | `L1408-L1409` | `0` | `0`（由 `core/scripts/cli.py:event_list` 處理） | `core/tests/test_events_pipeline.py:L103-L108` | **過時 1 行轉發殼層**（`main()` 根本不呼叫 `cmd_event`），物理刪除並將測試改為呼叫 `yscb.main(["event", "list"])` 或 `dispatch(["event", "list"])` |
| `_ensure_jit_lifecycle_pre(cmd)` / `_ensure_jit_lifecycle_post(cmd, exit_code=0)` | `L1412-L1427` | `0` | `0`（已由 `core/commands/dispatcher.py` 統一對稱廣播） | `core/tests/test_events_pipeline.py:L83-L98` | **過時死代碼**（`yscb.py` 內部 0 呼叫，真實廣播早已移入 `dispatcher.py:dispatch` 且已有 `test_ft10_symmetric_lifecycle_hooks` 覆蓋），物理刪除並同步清理舊墓碑測試 |
| `_suggest_command(unknown_cmd, candidate_pool)` | `L1453-L1456` | `0` | `0`（權威實作位於 `core.commands.dispatcher._suggest_command`） | `core/tests/test_cli_router.py:L74-L80`, `test_core_commands.py:L258-L262` | **過時 1 行轉發殼層**，物理刪除並將測試直接指向 `core.commands.dispatcher._suggest_command` |
| `_print_global_help()` | `L1459-L1462` | `0` | `0`（權威實作位於 `core.commands.dispatcher.dispatch(["--help"])`） | `core/tests/test_cli_router.py:L50`, `test_core_commands.py:L259` | **過時 1 行轉發殼層**，物理刪除並將測試改為呼叫 `yscb.main(["--help"])` |

---

### 2.2 D1 ~ D5 五維度分級診斷矩陣

| 檔案路徑:行號區間 | 維度 | 嚴重度 | 具體結構病徵 | 對應策略 |
| :--- | :---: | :---: | :--- | :---: |
| `yscb.py:L367-L403`, `L855-L914`, `L929-L979`, `L729-L742`, `L769-L776` | **`D3`** | **`P1`** | **Provider HTTP 讀取與本地 `index.json` 探測樣板高度重複（DRY 違規）**：<br>1. **HTTP 讀取與 Localhost Proxy Bypass 不一致重複**：`_fetch_companion_sha256_token` (`L732-L740`)、`cmd_self_update` (`L769-L776`) 與 `_lookup_provider_release_sha256` (`L958-L966`) 重複手寫 8 行 `if "127.0.0.1" in url or "localhost" in url: build_opener(ProxyHandler({})) else: urlopen(...)`，而 `_resolve_same_triplet_fallback_version` (`L396-L398`) 與 `_discover_latest_core` (`L903-L905`) 卻漏加 Localhost Proxy Bypass。<br>2. **Provider `index.json` 雙模（本地 3 候選路徑 + 遠端 URL）載入邏輯重複 3 次**：在 `_resolve_same_triplet_fallback_version` (`L378-L405`)、`_discover_latest_core` (`L862-L870`, `L901-L906`) 與 `_lookup_provider_release_sha256` (`L941-L972`) 中重複編寫幾乎完全相同的本地/遠端 `index.json` 解析骨架。 | **`S3`** |
| `yscb.py:L1172-L1287` (`116` LOC)、`L469-L576` (`108` LOC)、`L1005-L1095` (`91` LOC)、`L749-L833` (`85` LOC) | **`D1` / `D3`** | **`P1`** | **4 個超長多階段函式混雜高階編排與底層 I/O 細節（違反 SLAP，縮排達 4~5 層）**：<br>1. `_bootstrap_package_from_provider` (`116` LOC) 內嵌閉包 `_resolve_zip_expected_sha` 並串接 5 個獲取階層（`.build`、`.mirror`、本地 Provider、本地 `source/` 即時打包、遠端 HTTP 與 `pruned` 遞迴降級）。<br>2. `_inplace_atomic_sync_dir` (`108` LOC) 將「建立備份」、「覆寫目標與清除唯讀」、「清理多餘舊檔與空目錄」、「異常還原備份」四個階段塞入單一雙層 `try...except` 巨型函式。<br>3. `cmd_init` (`91` LOC) 與 `cmd_self_update` (`85` LOC) 混雜參數解析、網路下載、SHA-256 校驗與檔案原子替換。 | **`S1`, `S4`** |
| `yscb.py:L599-L605`, `L616-L622` | **`D3`** | **`P1`** | **`_fetch_and_extract_zip` 內 SHA-256 校驗與解壓邏輯重複**：在 HTTP 下載分支 (`L599-L606`) 與本地 `.zip` 分支 (`L616-L623`) 重複編寫相同的 `actual_sha = _compute_file_sha256(...)` 比對與 `RuntimeError` 拋出代碼。 | **`S3`** |
| `yscb.py:L7, L10, L30-L31, L1111-L1117, L1408-L1427, L1453-L1462` | **`D2`** | **`P1`** | **歷史遺留死代碼與 1 行無效轉發殼層未清理**：頂層未使用的 `import difflib`、`import importlib.util`、`INTERNAL_IGNORE_BEGIN/END`，完全無效的 `_generate_internal_gitignore`，以及 `0` 生產呼叫的 `cmd_event`、`_ensure_jit_lifecycle_pre/post`、`_suggest_command`、`_print_global_help` 轉發殼。 | **`S2`** (Mode A 死代碼拔除) |
| `yscb.py:L436-L437`, `L471-L472`, `L1516` | **`D5`** | **`P2`** | **函式內延遲匯入標準庫與工單編號註解殘留**：<br>1. `_is_dir_handle_locked_for_rename` 與 `_inplace_atomic_sync_dir` 內部重複 `import errno, stat, time`（皆為輕量標準庫，應統一置於檔案頂部）。<br>2. `L1516` 留有 `# FR-12: 僅攔截 core 入口本身之 ImportError...` 工單編號註解（違反 `CodeQualityStandards.md` §1.4 零工單編號註解鐵律）。 | **`S4`** |
| **正交職責邊界 (`S6`)** | **`D1` / `D5`** | **`Pass` (`P0=0`)** | **符合 `CodeQualityStandards.md` §3.6 免拆守門 ③**：`yscb.py` 作為單檔零依賴自舉入口，所有保留功能皆圍繞「冷自舉與環境修復 (`init` / `self-update` / `restore` / `auto-bootstrap`) + 運行時派發 (`main`)」單一核心使命，無 `P0` 級正交職責混雜或資源洩漏，**嚴禁物理拆分為多檔案**。 | **免拆 (`S6=0`)** |

---

### 2.3 S1 ~ S6 外科手術重構處方箋 (Refactoring Blueprint)

若採納重構，預計可為 `yscb.py` **淨減約 `130 ~ 160` 行冗餘/死代碼（約 `-9% ~ -11%` LOC）**，同時消除所有 $> 80$ 行的巨型函式並將最大縮排深度壓回 $\le 3$ 層：

1. **處方 1（`D2 / Mode A` 死代碼與 1 行轉發殼層拔除，約 `-45` LOC）**：
   - 物理移除未使用的 `import difflib`、`import importlib.util`、`INTERNAL_IGNORE_BEGIN`、`INTERNAL_IGNORE_END`，並將 `errno`、`stat`、`time` 提至頂層匯入。
   - 物理移除 `_generate_internal_gitignore`、`cmd_event`、`_ensure_jit_lifecycle_pre`、`_ensure_jit_lifecycle_post`、`_suggest_command`、`_print_global_help`。
   - 同步更新 3 個測試檔（`test_events_pipeline.py`、`test_cli_router.py`、`test_core_commands.py`）中針對上述舊轉發殼的呼叫點，改測正統入口 `yscb.main(...)` 與 `core.commands.dispatcher._suggest_command`。
2. **處方 2（`S3` 網路與 Provider `index.json` 存取同構聚合，約 `-65` LOC）**：
   - 提取通用標準庫輔助函式 `_http_get_bytes(url: str, timeout: int = 5) -> bytes`（內建 `User-Agent: yscb-host/2.0` 與 `127.0.0.1`/`localhost` `ProxyHandler({})` 自動繞過），統一供 `_fetch_and_extract_zip`、`_fetch_companion_sha256_token`、`cmd_self_update` 與索引讀取共呼（順手補齊 `_resolve_same_triplet_fallback_version` 與 `_discover_latest_core` 原本缺少的 Localhost Proxy Bypass）。
   - 提取通用 `_load_provider_index_dict(provider: str, module_name: str, base_dir: Optional[str] = None) -> Optional[Dict[str, Any]]`，一次收斂 `_resolve_same_triplet_fallback_version`、`_discover_latest_core` 與 `_lookup_provider_release_sha256` 三處重複的本地/遠端 `index.json` 探測邏輯。
   - 於 `_fetch_and_extract_zip` 提取 `_verify_and_extract_zip_file(zip_path: str, staging_dir: str, source_label: str, expected_sha256: Optional[str]) -> None`，消除 HTTP 暫存檔與本地 `.zip` 兩分支重複的 SHA-256 比對碼。
3. **處方 3（`S1 / S4` 四大長函式業務階段扁平化與工單註解清理，約 `-30` LOC）**：
   - **`_inplace_atomic_sync_dir` (`108 -> ~45` LOC)**：將檔案備份與異常還原提煉為 `_backup_dir_files(target_abs, backup_dir) -> Set[str]` 與 `_rollback_dir_from_backup(target_abs, backup_dir, existing_rel_files) -> None`，並提取 `_force_writable(path: str) -> None` 消除 3 處重複的 `try: os.chmod(...) except Exception: pass`。
   - **`_bootstrap_package_from_provider` (`116 -> ~55` LOC)**：將 `.build` 優先提取拆為 `_try_bootstrap_dot_build_package(...)`，將本地 Provider 與 `source/<mod>` 動態打包拆為 `_try_bootstrap_local_or_source(...)`，使主函式成為清晰的 5 步衛語句管線。
   - **`cmd_self_update` (`85 -> ~45` LOC)**：將腳本下載與 AST/SHA-256 驗證提煉為 `_download_and_verify_self_update(target_url, opts) -> Optional[str]`。
   - 清理 `L1516` 之 `# FR-12:` 工單編號前綴，僅保留架構原因說明。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  ### 3.1 風險評估與推薦流轉出口
  - **診斷統計**：**`P0` 共 `0` 項**、**`P1` 共 `4` 項**、**`P2` 共 `1` 項**。
  - `yscb.py` 的核心膨脹原因來自兩方面：① 為達成「無 `.zip` 二進位追蹤下之跨平台冷自舉、確定性打包、SHA-256 強制驗證與目錄鎖定自癒」所必備的純標準庫基礎設施（此部分屬高價值核心韌性，不可刪減）；② 歷史演進留下的 **6 個零生產調用轉發殼/死代碼**、**3 處重複的 Provider `index.json` / HTTP Proxy 讀取樣板**，以及 **4 個超過 85~116 行的多階段長函式**。
  - **推薦流轉出口**：
    1. **出口 ① 立即原地升級實作（推薦）**：將 `R01` 標記為 `Concluded`，於 `sub_04_yscb_host_optimization` 原地升级為 **Full Track**（搭配 `/auto` 快速推進），執行上述處方 1~3 無損重構（預計淨減 `~140` LOC，消除全部死代碼與重複樣板），並通過 `core` / `dev` / `server` 全量回歸測試。
    2. **出口 ② 轉入技術儲備**：將處方箋登錄至 `/todo`，標記 `R01` 為 `Concluded`，先推進原 P3 子計畫。
    3. **出口 ③ 維持現狀結案**：因 `P0 = 0`（無高危破窗），若認為現狀可接受，可直接標記 `R01` 與 `P00` 為 `Concluded` / `Completed` 結案。

