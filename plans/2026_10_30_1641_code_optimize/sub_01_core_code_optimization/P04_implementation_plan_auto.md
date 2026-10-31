# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_core_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 `P03_api_spec_auto.md` 中皆有對應介面與重構簽名定義
- [x] **邊界防護**：EC-01 ~ EC-04（交易鎖釋放、Zip-Slip 防護、`core` 初次語系種子化、`.gitignore` 差集合併）具備明確防禦策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 單向無環依賴（`vfs -> uri`）、函式複雜度壓降與並行隔離邊界約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 於主計畫 Phase 7 結案時統一核對 `core` 公開 API 描述（移除已廢棄別名說明） |
| **專題手冊** | `docs/ARCHITECTURE.md` | Modify | 於主計畫 Phase 7 結案時確認 `vfs -> uri` 單向依賴說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 於主計畫 Phase 7 視需要記錄 `Mode A` 單一正統入口收斂決策 |
| **微觀註解** | `ys_codebase/source/core/` 源碼 Docstrings | Modify | 同步更新重構後之公開與內部階段函式 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫 Phase 7 結案時記錄 `core` 模組五維度優化與死代碼清除摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：`AtomicEngine.transaction_lock` 若在已持有鎖的情況下（例如鎖超時或被其他進程佔用，`act_lock` 回傳 `False`）進入 `finally` 區塊，是否會誤把別人持有的鎖解開？  
> [*] **防護解法**：在 `transaction_lock` 內部以區域變數 `acquired = self.act_lock(target_name, operation)` 紀錄實際獲取狀態，`finally` 區塊內僅當 `if acquired:` 為真時才呼叫 `self.act_unlock(target_name)`，徹底杜絕未取得鎖卻誤刪他進程鎖檔的競爭風險 (`EC-01`)。

> [?] **尖銳問題 2**：將 `AtomicEngine` 與 `ContributesAggregator` 的無狀態方法剝離為模組級函式後，若 `core/tests/` 內既有單元測試直接呼叫 `engine._parse_dependencies(...)` 或 `aggregator._deep_merge(...)`，是否會引發 `AttributeError`？  
> [*] **防護解法**：依 `Mode A` 單一正統入口收斂規範（`R02`），徹底移除 `AtomicEngine` 類別上的 7 個 `staticmethod` 轉發綁定、`ContributesAggregator._deep_merge` 靜態綁定、`uri._get_yscb_root` 私有別名、`contributes.get_for_current_module` 與 `CommandsRegistry.all_modules`，並同步將 `core/tests/` 內所有測試調用點更新為直接匯入模組級別正統函式，兼顧零 `self` 耦合、零冗餘綁定與測試 100% 對齊 (`[P02:DR-02]`)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`uri.py` & 底層尋根收斂)**：物理刪除 `uri.py:650-720` 共 15 個 VFS 薄轉發函式、`_DEPRECATED_SCHEME_REDIRECTS` 空表、`get_execution_context`、`_find_host_config` 與 `_get_yscb_root` 別名；公開 `resolve_yscb_root()`；完成 `reconcile_undefined_uri` 與 `resolve` 之 `S1/S2` 階段拆解，並將 `config.py`、`telemetry.py`、`dispatcher.py`、`ide_projector.py`、`pip_manager.py` 的尋根邏輯統一委派至 `uri.resolve_yscb_root()` (`FR-01`, `FR-03`, `FR-05`, `FR-07`)。
2. **TASK-02 (`config.py` / `events.py` / `locale.py` / `validator.py` 重構)**：刪除 `Config = ConfigManager`、`emit = broadcast`、`_MODULE_DECL_CACHE` 與 `translate = t`；移除 `config.py` 頂部 `try...except ImportError` 與 `_atomic_write_json` 之 `tempfile.mkstemp` 死分支，100% 委派 `vfs.write_json` / `vfs.read_json`；完成 `locale.py:validate_module_locales` 三階段拆解與 `validator.py:validate_node` 階段化重構 (`FR-01`, `FR-03`, `FR-07`, `FR-08`)。
3. **TASK-03 (`pip_manager.py` / `ide_projector.py` / `contributes.py` 重構)**：將 `installer.py:generate_internal_gitignore` 改用 `vfs.write_text(..., atomic=True)`，並讓 `pip_manager.py:ensure_yscb_gitignore` 直接委派呼叫 `generate_internal_gitignore` 消除重複規則常數；拆解 `ide_projector.py:sync_vscode_settings` 為階段函式；移除 `contributes.py:scan_and_inject` 之 `clean` 參數、`get_for_current_module` 與 `ContributesAggregator._deep_merge` 綁定，剝離頂層 `_deep_merge` 並完成四階段拆解 (`FR-01`, `FR-03`, `FR-05`, `FR-08`)。
4. **TASK-04 (`engine.py` & `installer.py` 深度重構)**：修復 `engine.py` 初次部署 `core` 之 `locale` 初始化邏輯並物理刪除 `_seed_or_update_config` 與 `act_get_installed_commands_summary`；實作 `transaction_lock` 並套用至 `installer.py`；剝離 7 個無狀態工具函式（移除 `AtomicEngine` 類別尾端冗餘 `staticmethod` 綁定）並完成 `engine.py` 與 `installer.py` 長方法 `S1` 階段拆解與 `vfs.<io>` 遷移 (`FR-01`, `FR-02`, `FR-04`, `FR-06`)。
5. **TASK-05 (`dispatcher.py` / `registry.py` / `contributes_cmd.py` / `scripts/cli.py` / `__init__.py` & `tests/` 同步)**：移除 `registry.py` 之 `all_modules` 與 `case_pros` / `case_cons` 舊分支；刪除 `contributes_cmd.py:cmd()` 並抽取 `_append_locale_validation_errors`；刪除 `dispatcher.py:622` fallback 並抽取 Server 喚醒 helper；刪除 `scripts/cli.py` 之 `bootstrap` 分支與底部 12 個 `cmd_*` 轉發並提取 `_render_subcommand_group_help`；補齊 `core/__init__.py` 之 `TYPE_CHECKING`；同步更新 `core/tests/` 所有測試檔 (`FR-03`, `FR-05`, `FR-07`, `FR-08`, `NFR-03`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 並行子計畫測試與靜態驗證策略**：
  - 依主計畫並行執行規範，本子代理僅修改 `ys_codebase/source/core/` 與本子計畫目錄 `plans/2026_10_30_1641_code_optimize/sub_01_core_code_optimization/`，代碼與 `core/tests/` 實作完成後以 `python -m py_compile` 驗證全部修改之 Python 檔案語法 100% 無誤，並執行 `plan verify` 確保計畫結構與剛性追溯鏈 100% 合規，全系統沙盒測試留待 5 個子計畫全數抵達 P06 後由主 Agent 統一執行。
