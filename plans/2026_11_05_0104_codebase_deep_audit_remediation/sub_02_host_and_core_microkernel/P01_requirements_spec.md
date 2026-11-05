# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_host_and_core_microkernel  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.uri` 執行緒本地化與子路徑安全邊界加固 | 1. 將 `core/uri.py` 之 `_active_host_dir`、`_active_yscb_dir`、`_active_module_context`、`_reconciling_tokens` 遷移至 `threading.local()`（含 `_ThreadLocalSet` 代理維持集合操作語意），消除多執行緒平行沙盒 `host_scope` / `yscb_scope` / `module_scope` 跨執行緒狀態污染。<br/>2. 於 `uri.resolve()` 解析出 `target_base` 後（嚴禁在展開 `sval` 前攔截 `..`，確保 `project://` 之 `"yscb://.."` 正常運作），對非空子路徑 `rel` 執行 `_ensure_safe_subpath(target_base, rel, raw_uri)`，攔截 `..` 逃逸與 Windows 磁碟機重置並拋出 `PermissionError`。<br/>3. 於 `VFS.open()` 補齊 `self.assert_safe_path(path_or_uri)` 與文字寫入模式預設 `newline="\n"`；於 `OSBackend._safe_copytree()` 與 `copy()` 先檢查 `os.path.islink()` 以符號連結方式安全複製。<br/>4. 將 `core/contributes.py` 與 `core/update_checker.py` 對宿主設定檔與入口腳本之探測統一優先使用 `yscb.host://`。 | P0 | [P00:DR-01] |
| **FR-02** | Localhost IPC 無代理通道、重置異常判定與程序/探針鎖加固 | 1. 於 `core/commands/dispatcher.py` 與 `core/installer.py` 對 `127.0.0.1` 請求使用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))`，避免被環境變數 `HTTP_PROXY` 劫持。<br/>2. 維持 `dispatcher._hot_dispatch_attempt` 之 `except urllib.error.URLError:` 在 `except OSError:` 之前，並將 `isinstance(e.reason, (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError))` 判為 `accepted=True`；於 `_strict_hot_dispatch_or_block` 僅在 `result.accepted or result.exit_code is not None` 時跳出等待迴圈。<br/>3. 於 `core/platform/process.py` 為 Windows `taskkill` 補齊 `timeout=max(1.0, float(timeout_sec))` 與異常保護，並於 POSIX 無 `/proc` 環境透過 `ps -o stat= -p <pid>` 識別 `Z`/`X` 殭屍進程為非存活。<br/>4. 於 `core/platform/daemon_probe.py` 以 `InterProcessLock` 保護 `spawn_probe.json` 之讀改寫週期。 | P0 | [P00:DR-02] |
| **FR-03** | 快照回滾、套件還原、多工作區快取鍵與驗證器/解析器收斂 | 1. 於 `AtomicEngine.act_snapshot` 建立前若 `snap_dir` 已存在則先清除；於 `Installer.cmd_rollback` 按 `(mtime, name)` 排序選取最新快照。<br/>2. 於 `Installer._restore_module_package` 與 `yscb.py` 之 `_extract_and_cache_mirror` 先將來源壓縮包複製至 `.mirror` 後再對 `.mirror` 檔案執行 SHA-256 校驗與解壓（校驗失敗則清理 `.mirror` 檔案）。<br/>3. 於 `AtomicEngine.act_lock` / `act_unlock` 支援同操作名重入計數與死鎖檔案自癒；於 `act_reload` 連動清空 `config`、`locale`、`symbols`、`contributes`、`uri` 快取。<br/>4. 將 `yscb_root` 納入 `ConfigManager`、`locale._MODULE_BASE_DIR_CACHE`、`symbols._RESOLVED_CALLABLE_CACHE` 快取鍵（不對 `contributes.get` 無條件 `deepcopy`）。<br/>5. 於 `ContributesValidator._validate_primitive_or_container_rule` 對 `dict` 型別跳過 `__*__` 元資料鍵；於 `OptionResolver` 支援負數位置/選項參數；於 `core/scripts/cli.py` 之 `_parse_cli_scalar_or_json` 支援帶號整數與浮點數解析。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `project://` 基底定義為 `"yscb://.."`，同時使用者傳入 `project://../../etc/passwd` 或 `project://C:/Windows` | 基底 `sval` 之 `"yscb://.."` 正常解析至專案根目錄；子路徑 `rel` 經 `_ensure_safe_subpath` 檢查發現超出 `target_base` 或磁碟機改變時立即拋出 `PermissionError`。 |
| **EC-02** | 現有單元測試透過 `unittest.mock.patch("core.commands.dispatcher.urllib.request.urlopen")` 模擬熱派發回應 | `_open_localhost_no_proxy` 偵測當 `urllib.request.urlopen` 被替換為非標準函式（Mock）時自動委派予 `urlopen`，正常環境則使用 `ProxyHandler({})` Opener，兼顧無代理保護與測試相容性。 |
| **EC-03** | 單一安裝流程中 `cmd_update` 已取得 `act_lock("install")` 後內部呼叫 `cmd_install` 再次請求同名鎖，或殘留死鎖檔 | 同實例同操作名透過 `_lock_counts` 計數重入；跨實例遇鎖被拒時檢查鎖檔內 `pid`，若進程已死亡則自動清理陳舊鎖檔並重試取鎖。 |
| **EC-04** | 同毫秒內連續建立多個快照，或同名快照重複建立 | `act_snapshot` 先清理既有同名快照目錄防止殘留舊模組檔案；`cmd_rollback` 以 `(mtime, name)` 複合排序穩定選取最新快照。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴與相容性 | 100% Python 標準庫實作（Zero Third-Party Dependency），嚴格維持公開 API 向下相容。 |
| **NFR-02** | 效能與執行緒安全 | `contributes.get()` 維持零無條件 `deepcopy` 開銷；`core.uri` 狀態 100% 執行緒隔離（Thread-Local Storage）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 防回歸紅線 3~6（引自 `R01_codebase_deep_audit.md` §2）**：
  - 紅線 3：嚴禁在 `uri.resolve` 解析 `sval` 前直接封殺 `".."`，僅對解析出 `target_base` 後之非空 `rel` 驗證 `os.path.commonpath([base_norm, joined_norm]) == base_norm`。
  - 紅線 4：`dispatcher.py` 必須維持 `except urllib.error.URLError:` 在 `except OSError:` 之前，因為 `URLError` 為 `OSError` 子類。
  - 紅線 5：`contributes.get()` 嚴禁無條件 `copy.deepcopy`。
  - 紅線 6：`core/uri.py` 必須將 `_active_host_dir`、`_active_yscb_dir`、`_active_module_context`、`_reconciling_tokens` 全數遷移至 `threading.local()`。
- **`[!NOTE]` 模組開發規範**：`core/scripts/cli.py` 頂層不可放置執行期賦值語句（如 `re.compile` 頂層常數），須封裝於函式內以符合 `yscb dev check core` AST 靜態守門規範。
