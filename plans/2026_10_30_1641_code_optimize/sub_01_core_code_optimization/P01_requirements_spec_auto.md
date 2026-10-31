# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_core_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 斬斷 `uri <-> vfs` 雙向循環依賴與清除 VFS 薄轉發層 (`M-01` / `F-01`) | 物理刪除 `ys_codebase/source/core/core/uri.py:650-720` 共 15 個 VFS I/O 薄轉發函式（`exists`、`isfile`、`is_file`、`isdir`、`is_dir`、`remove`、`read_text`、`write_text`、`read_json`、`write_json`、`makedirs`、`listdir`、`copy`、`move`、`rmtree`），並將 `core` 模組內部（含 `engine.py`、`contributes.py`、`installer.py`、`contributes_cmd.py`、`update_checker.py`、`locale.py`、`events.py`、`symbols.py`）與 `core/tests/` 所有 `uri.<io>` 調用點 100% 遷移至正統入口 `vfs.<io>`，確立 `vfs -> uri` 單向依賴。 | P0 | [P00:DR-01] |
| **FR-02** | 修復 `core` 初次安裝 `locale` 初始化缺口並清除 `AtomicEngine` 死方法 (`M-02` / `M-03` / `F-02`) | 將 `core/engine.py:_seed_or_update_config` 死方法內針對 `core` 模組首次部署寫入 `locale` 預設值的邏輯提取整合至活躍方法 `_deploy_and_strip_single_module_config`（子階段 `_seed_or_infill_module_config`），隨後物理刪除 0 調用之 `_seed_or_update_config` 與 `act_get_installed_commands_summary`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 物理清除歷史相容別名、廢棄空表、死快取與冗餘參數 (`M-04` ~ `M-11`) | 依 `Mode A` 零容忍清除策略：<br/>1. 刪除 `uri.py` 之 `_DEPRECATED_SCHEME_REDIRECTS` 空表與分支 (`M-04`)、`get_execution_context` 與 `_find_host_config` 別名 (`M-05`)。<br/>2. 刪除 `config.py:332` 之 `Config = ConfigManager` (`M-06`)、`events.py:110` 之 `emit = broadcast` (`M-07`)、`locale.py` 之 `_MODULE_DECL_CACHE` 死快取與 `translate = t` 別名 (`M-08`)。<br/>3. 刪除 `contributes_cmd.py:208-235` 未引用之 `cmd(cmd_bags)` (`M-09`)、`scripts/cli.py` 之 `bootstrap` 廢棄分支與底部 12 個 `cmd_*` 舊測試轉發及 `dispatcher.py:622` fallback (`M-10`)。<br/>4. 移除 `contributes.py:scan_and_inject` 未使用之 `clean` 參數 (`M-11`)，並同步更新 `core/tests/` 改調用正統入口。 | P0 | [P00:DR-01] |
| **FR-04** | 全域交易鎖確定性釋放保護 (`F-03` / `S4`) | 於 `AtomicEngine` 提供 `@contextmanager def transaction_lock(self, target_name: str, operation: str = "unknown")` 上下文管理器，封裝 `act_lock` 與 `try...finally: act_unlock`，並於 `installer.py` 之 `cmd_reload` 與 `cmd_restore` 全面套用，消除異常退場時鎖殘留與靜默吞異常之風險。 | P1 | [P00:DR-02] |
| **FR-05** | 統一收斂跨檔重複工具：`.yscb_root` 解析、`.gitignore` 合併與 CLI 群組 Help (`F-11` ~ `F-13` / `S3` / `S5` / `S6`) | 1. 將 `pip_manager.py`、`ide_projector.py`、`telemetry.py`、`dispatcher.py`、`config.py` 共 5 處重複的 `_resolve_yscb_root` / `_get_yscb_root` 統一收斂至 `uri.get_yscb_dir()` 公開入口 (`F-11`)。<br/>2. 將 `installer.py` 與 `pip_manager.py` 重複且規則不一致之 `.gitignore` 合併邏輯統一收斂為單一正統 `ensure_yscb_gitignore(yscb_root: str)`（完整涵蓋 `.venv/`、`.cache/`、`.mirror/`、`.snapshots/`、`*.bak` 共 5 條規則）(`F-12`)。<br/>3. 於 `scripts/cli.py` 提取 `_render_subcommand_group_help` 統一渲染 `config`、`pip`、`contributes`、`locale` 4 組子命令說明 (`F-13`)。 | P1 | [P00:DR-02] |
| **FR-06** | `AtomicEngine` 與 `Installer` 巨型類別之 `S1` 階段拆解與 `S2` 無狀態邏輯剝離 (`F-04` / `F-05`) | 1. 將 `engine.py` 7 個不依賴 `self` 的無狀態方法（`_parse_dependencies`、`_deep_infill_dict`、`_force_rmtree_with_retry`、`_cleanup_stale_swap_dirs`、`_atomic_swap_dir`、`_clean_module_cache`、`_extract_zip_safely`）剝離為模組級純函式/工具函式，並與 `installer.py:fetch_and_extract_zip` 共用 `_extract_zip_safely`。<br/>2. 將 `engine.py` 之 `act_download`、`_get_module_manifest_from_provider_or_local`、`_deploy_and_strip_single_module_config`、`act_reload` 及 `installer.py` 之 `cmd_update`、`cmd_list`、`cmd_restore` 拆解為職責單一之階段輔助方法，並剝離 `_print_onboarding_guide` 與 `_restore_module_package`。 | P1 | [P00:DR-02] |
| **FR-07** | `locale.py`、`uri.py`、`dispatcher.py` 長函式之 `S1/S2` 拆解 (`F-06` ~ `F-08`) | 1. 將 `locale.py:validate_module_locales` (205 LOC) 拆解為 `_validate_locales_decl_header`、`_load_and_validate_definition_contract`、`_validate_single_lang_file` 三階段函式 (`F-06`)。<br/>2. 將 `uri.py:reconcile_undefined_uri` 與 `resolve` 拆解為探測/互動/持久化與正規化/Scheme 分派/Anchor 展開沙盒校驗等子函式 (`F-07`)。<br/>3. 將 `dispatcher.py` 之 `_maybe_auto_spawn_server` 剝離無狀態 helper，並抽取 `dispatch` 與 `dispatch_local` 共用之路由解析與環境掛載邏輯 (`F-08`)。 | P1 | [P00:DR-02] |
| **FR-08** | `validator.py`、`contributes.py`、`contributes_cmd.py`、`ide_projector.py` 拆解去重與靜態匯入純化 (`F-09`、`F-10`、`F-14`) | 1. 將 `validator.py:validate_node` (225 LOC) 改為依 `kind` 分派之 `_KIND_VALIDATORS` 映射表 (`F-09`)。<br/>2. 將 `contributes.py:_deep_merge` 剝離為模組級純函式，拆解 `scan_and_inject` 四階段；抽取 `contributes_cmd.py:_append_locale_validation_errors` 消除 3 處重複迴圈 (`F-10`)。<br/>3. 將 `ide_projector.py:sync_vscode_settings` 拆解為路徑收集與雙設定檔同步三階段函式。<br/>4. 於 `core/__init__.py` 補齊 `if TYPE_CHECKING:` 靜態型別宣告並清理各檔案未引用之死匯入 (`F-14`)。 | P1 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `cmd_reload` 或 `cmd_restore` 執行中途發生未預期 I/O 或解壓例外 | `transaction_lock("global")` 之 `finally` 區塊確保必定呼叫 `act_unlock("global")` 釋放全域鎖；若解鎖過程本身發生檔案系統異常，記錄診斷警告而不掩蓋原始業務例外。 |
| **EC-02** | Zip 壓縮包內含 `../` 或絕對路徑之惡意條目 (Zip-Slip) | 共用之 `_extract_zip_safely` 於解壓前逐一比對 `os.path.abspath` 是否以目標目錄為前綴，若越界立即拋出 `ValueError("Security Error: Zip-Slip detected")` 並中止解壓。 |
| **EC-03** | `core` 模組初次部署時 `config/core/config.json` 尚未設定 `locale` | `_seed_or_infill_module_config` 自動讀取 `core/manifest.json` 之 `default_locale`（預設 `en-US`）並注入 `data["locale"]`，確保首次初始化語系完整。 |
| **EC-04** | `.yscb_root` 下的 `.gitignore` 已存在部分自訂忽略規則或空白行 | `ensure_yscb_gitignore` 以保留既有行順序之方式進行差集追加，僅補齊缺失的標準規則（含 `*.bak`），不覆蓋使用者既有自訂條目。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴拓撲 (ADP) | `core/uri.py` 對 `core/vfs.py` 之匯入（含頂層與函式內延遲匯入）必須降為 **0**，100% 確立 `vfs -> uri` 單向無環依賴。 |
| **NFR-02** | 複雜度與可維護性 | 重構後 `validator.py:validate_node`、`locale.py:validate_module_locales` 等原本超過 150~225 LOC 的單體長函式，主控入口函式長度須壓降至 **$\le 65$ LOC**，單一函式圈複雜度 **$\le 12$**。 |
| **NFR-03** | 並行邊界與無損相容 | 實體修改嚴格限制於 `ys_codebase/source/core/`（含 `core/`、`scripts/cli.py`、`tests/`），所有修改後之 Python 檔案必須 100% 通過 `py_compile` 語法編譯校驗且行為無損。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `core/uri.py` 為全生態系最底層路徑解析基座，在移除 `L650-720` 的 15 個 VFS 轉發函式時，務必保留 `uri.py` 原生的路徑解析與沙盒函式（如 `resolve`、`to_uri`、`get_module_context`、`get_yscb_dir`、`is_within_sandbox` 等），並將 `_get_yscb_dir` 公開為 `get_yscb_dir`（同時保留 `_get_yscb_dir = get_yscb_dir` 供內部模組過渡或直接將 `core` 內部統一為 `get_yscb_dir`）。
- **`[!CAUTION]`** `core/tests/` 內部分單元測試會透過 `unittest.mock.patch` 替換內部屬性或輔助方法（例如 `AtomicEngine` 內部方法或 `uri` 內部狀態），剝離 `S2` 無狀態函式時若測試有直接 `self.engine._xxx` 呼叫，可在 `AtomicEngine` 上保留靜態方法綁定或同步更新 `core/tests/` 測試案例以維持 100% 測試相容。
