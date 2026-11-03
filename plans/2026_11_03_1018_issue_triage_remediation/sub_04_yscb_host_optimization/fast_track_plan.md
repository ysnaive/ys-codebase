# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：唯一宿主 `yscb.py` 五維度靜態診斷與收斂重構  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（以高密度刪減死代碼與聚合重複樣板為主，新增提取之通用輔助函式 $< 50$ 行，淨減約 `100+` 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出，`Mode B` 保留 `main`, `cmd_init`, `cmd_self_update`, `cmd_restore`, `load_config`, `dispatch_module` 及公開常數）。
- [x] **依賴邊界守門**：零跨模組新依賴引入（維持 100% Python 標準庫）。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：依據 [R01_code_optimization_audit.md](./R01_code_optimization_audit.md) 診斷處方箋，在「對外函式 `Mode B`、對內函式 `Mode A`」基準下：
  1. **`[FP-01:DR-01]` 拔除死代碼與 1 行過時轉發殼（`D2 / Mode A`）**：移除未使用的 `import difflib`、`import importlib.util`、`INTERNAL_IGNORE_BEGIN`、`INTERNAL_IGNORE_END`，以及 `0` 生產呼叫之 `_generate_internal_gitignore`、`cmd_event`、`_ensure_jit_lifecycle_pre`、`_ensure_jit_lifecycle_post`、`_suggest_command`、`_print_global_help`，並將函式內重複 `import errno, stat, time` 提升至頂層；同步將 `test_events_pipeline.py`、`test_cli_router.py`、`test_core_commands.py` 指向正統入口。
  2. **`[FP-01:DR-02]` 同構聚合 HTTP Proxy Bypass 與 Provider `index.json` 載入（`D3 / S3`）**：提煉 `_http_get_bytes(url, timeout=5)`（統一內建 `127.0.0.1`/`localhost` `ProxyHandler({})`）與 `_load_provider_index_dict(provider, module_name, base_dir=None)`，消除 `_resolve_same_triplet_fallback_version`、`_discover_latest_core`、`_lookup_provider_release_sha256`、`_fetch_companion_sha256_token` 與 `cmd_self_update` 5 處重複樣板；提煉 `_verify_and_extract_zip_file` 收斂 `_fetch_and_extract_zip` 重複之 SHA-256 校驗分支。
  3. **`[FP-01:DR-03]` 扁平化過長階段與清理工單編號註解（`D1 / D5 / S1 / S4`）**：於 `_inplace_atomic_sync_dir` 提煉 `_force_writable(path)` 與備份/回滾輔助，於 `_bootstrap_package_from_provider` 提煉 `.build` 提取階段，並清理 `L1516` 之 `# FR-12:` 工單編號前綴。
- **影響範圍**：`yscb.py`、`ys_codebase/source/core/tests/{test_events_pipeline,test_cli_router,test_core_commands}.py`。

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `yscb.py` 執行處方 1~3（`D2` 死代碼與轉發殼拔除、`S3` `_http_get_bytes` / `_load_provider_index_dict` / `_verify_and_extract_zip_file` 同構聚合、`S1/S4` 階段收斂與工單註解清理）。
- [x] **TASK-02**：同步更新 `ys_codebase/source/core/tests/{test_events_pipeline,test_cli_router,test_core_commands}.py` 指向正統入口，並執行 `dev check core` 與 `dev test core -q`。
- **測試案例清冊**：
  - [x] **FT-01**：驗證 `yscb.py` 重構後 `test_distribution_lifecycle.py`、`test_remote_zip_bootstrap.py`、`test_cli_router.py`、`test_core_commands.py`、`test_events_pipeline.py` 全數通過，且 `dev check --all` 0 警告。
  - [x] **RT-01**：全模組既有單元測試 100% 回歸通過。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  1. **`[FP-01:DR-01]` 拔除死代碼與 1 行過時轉發殼（`D2 / Mode A`）**：移除未使用的 `import difflib`、`import importlib.util`、`INTERNAL_IGNORE_BEGIN`、`INTERNAL_IGNORE_END`，以及 `0` 生產呼叫之 `_generate_internal_gitignore`、`cmd_event`、`_ensure_jit_lifecycle_pre`、`_ensure_jit_lifecycle_post`、`_suggest_command`、`_print_global_help`，並將函式內重複 `import errno, stat, time` 提升至頂層；同步將 `test_events_pipeline.py`、`test_cli_router.py`、`test_core_commands.py` 指向正統入口 `yscb.main` 與 `core.commands.dispatcher`。
  2. **`[FP-01:DR-02]` 同構聚合 HTTP Proxy Bypass 與 Provider `index.json` 載入（`D3 / S3`）**：提煉 `_http_get_bytes(url, timeout=5)` 與 `_load_provider_index_dict(provider, module_name, base_dir=None)`，消除 `_resolve_same_triplet_fallback_version`、`_discover_latest_core`、`_lookup_provider_release_sha256`、`_fetch_companion_sha256_token` 與 `cmd_self_update` 5 處重複樣板；提煉 `_verify_and_extract_zip_file` 收斂 `_fetch_and_extract_zip` 重複之 SHA-256 校驗分支。
  3. **`[FP-01:DR-03]` 扁平化過長階段與清理工單編號註解（`D1 / D5 / S1 / S4`）**：於 `_inplace_atomic_sync_dir` 提煉 `_force_writable`、`_backup_dir_files` 與 `_rollback_dir_from_backup`（`108 -> 53` LOC），於 `_bootstrap_package_from_provider` 提煉 `_try_bootstrap_dot_build_package`（`117 -> 95` LOC，零超過 100 行函式），於 `cmd_self_update` 提煉 `_download_and_verify_self_update`，並清理 `# FR-12:` 工單編號前綴註解。

### 2.1 靜態診斷重構前後對比表 (Before vs. After Metrics)

| 衡量指標 | 重構前 (Before) | 重構後 (After) | 變化幅度 |
| :--- | :---: | :---: | :---: |
| **總代碼行數 (LOC)** | `1,526` | `1,458` | `-68` LOC (`-4.5%`，且含新增 6 個模組級階段輔助函式) |
| **單一函式最大行數** | `117` (`_bootstrap_package_from_provider`) | `95` (`_bootstrap_package_from_provider`) | 全檔 `0` 個超過 100 行之函式 (`_inplace_atomic_sync_dir`: `108 -> 53`) |
| **最大控制流縮排深度** | `6` 層 (`_inplace_atomic_sync_dir`) | `3` 層 | `-3` 層 |
| **清理死代碼 / 過時轉發殼數** | `10` 項 | `0` 項 | 拔除 2 個未使用匯入、2 個未使用常數、6 個零生產引用轉發殼 |

- **實機測試日誌**：
  - `python yscb.py dev check --all`：`7 Total, 7 Passed, 0 Warnings, 0 Failed`
  - `python yscb.py dev test core -q`：`Pass: 243(100.0%), Fail: 0, Skip: 0`

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `CHANGELOG.md` 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

