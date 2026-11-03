# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：可靠性強化與工程治理修復  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `index.json` SHA-256 SSOT、確定性壓縮與舊版全量回填 | 1. 以 `ys_codebase/release/<mod>/index.json` 之 `releases[<ver>]["sha256"]` 為 SSOT，從 `origin/releases` 讀取現存 7 個模組全部 `active` 版本 `.zip` 計算真實 SHA-256 並一次性回填。<br/>2. `dev/builder.py:_create_module_archive_atomic`、`core/engine.py:package_local_source_if_exact_match`、`yscb.py:_package_source_to_zip_if_exact_version` 與 `.github/workflows/release-publish.yml` 採用確定性壓縮（Deterministic Zip：檔案與目錄依字典序走訪、固定 `ZipInfo.date_time = (2020, 1, 1, 0, 0, 0)`、`external_attr = (0o644 & 0xFFFF) << 16`、文字檔換行符正規化為 LF），確保相同源碼內容跨平台/跨環境打包之 SHA-256 恆等。<br/>3. `dev/builder.py:_update_release_index` 與 `release-publish.yml` 在更新 `index.json` 時自動計算並寫入 `releases[<ver>]["sha256"]`。 | P1 | [P00:DR-02] |
| **FR-02** | 模組下載與 `self-update` 強制 SHA-256 驗證與 `--ignore-sha256` 逃生閥 | 1. 正式版（非 `@build` / `*.build`）於 `core/engine.py`（`act_download` / `_download_from_remote_tier` / `_download_from_release_tier`）與 `yscb.py`（`init` / `_bootstrap_package_from_provider`）下載或提取模組 `.zip` 時，強制要求 `index.json` 對應版本具備非空 `sha256` 且與 `.zip` 實際 SHA-256 完全一致；若缺失或不符立即拋出 `RuntimeError` 中斷並清理暫存檔。<br/>2. 於 `yscb.py`（`init` / `self-update` / `restore`）與 `core` CLI（`install` / `update` / `restore`）支援 `--ignore-sha256` 參數；顯式傳入時印出 `[WARN]` 安全警告並跳過 SHA-256 驗證。<br/>3. `@build` / `*.build` 本地開發版自部署完全豁免 SHA-256 檢查。<br/>4. `yscb.py self-update` 除 `ast.parse` 語法檢查外，驗證必備頂層符號（`__version__` 與 `def main`），並支援 `--sha256 <hex>` 或伴隨 `<url>.sha256` 校驗（以及 `--ignore-sha256`）。 | P1 | [P00:DR-02] |
| **FR-03** | `WarmWorker` 差量環境變數還原與執行環境保護 | `server/worker.py:WarmWorker.execute_task` 移除 `os.environ.clear()`，新增 `_restore_env_diff(orig_env)` 僅刪除新增鍵並還原被修改/移除鍵，杜絕背景常駐服務執行緒（`file-space-watcher`、`knowledge-db-worker`）在任務切換瞬間遺失 `PATH` / `HOME` / `YSCB_*`；同時以任務執行鎖 `_task_lock` 與 `core.uri.host_scope` / `yscb_scope` 包覆前台任務執行。 | P1 | [P00:DR-03] |
| **FR-04** | `OSBackend.atomic_write` 移除非原子破壞性回退 | `core/vfs/os_backend.py:OSBackend.atomic_write` 於 Windows `os.replace(tmp_path, norm_target)` 10 次重試耗盡後，移除 `os.remove(norm_target)` + `shutil.copy2` 非原子回退，直接拋出最後一次 `(PermissionError, OSError)`，保全原目標檔並由 `finally` 刪除 `tmp_path`。 | P1 | [P00:DR-04] |
| **FR-05** | `OSBackend.remove` 精確錯誤傳遞 | `core/vfs/os_backend.py:OSBackend.remove` 移除 `shutil.rmtree(norm_path, ignore_errors=missing_ok)`，改為透過自訂 `onerror` 處理器：當 `missing_ok=True` 時僅忽略 `FileNotFoundError`（`errno.ENOENT`），遇到唯讀檔嘗試 `os.chmod` 後重試，其餘 `PermissionError` / `OSError` 一律正常拋出。 | P2 | [P00:DR-04] |
| **FR-06** | GitHub Actions 自動化 CI 工作流 | 新增 `.github/workflows/ci.yml`，於 `push` / `pull_request` 至 `main` 及 `workflow_dispatch` 時，執行 `python yscb.py dev check --all`、`python yscb.py contributes check` 與全模組 pytest 測試套件。 | P1 | [P00:DR-05] |
| **FR-07** | 靜默 `except Exception: pass` 收斂與 `dev check` 裸 `except:` 檢查 | 1. 於 `dev/checker.py:Checker._check_source_files` 新增 AST 規則：檢測到裸 `except:`（`ast.ExceptHandler.type is None`）時發出 `CheckSeverity.WARN`（`category="ANTIPATTERN"`）。<br/>2. 收斂 `core`、`server` 與 `yscb.py` 非清理路徑之靜默 `except Exception: pass`（改為精確例外型別或補充診斷紀錄）。 | P2 | [P00:DR-05] |
| **FR-08** | `yscb.py` 版本遞增與同版本號 SHA-256 內容漂移偵測 | 遞增 `yscb.py` `__version__` 至 `"1.2.2.0"`；於 `core/update_checker.py:UpdateChecker._check_host_script_update` 比對本機與來源端 `yscb.py`：除 `semver.compare_semver(latest_ver, cur_ver) > 0` 外，當 `latest_ver == cur_ver` 但正規化換行符（LF）後之 SHA-256 不一致時，回傳含 `"is_drift": True` 之更新提示字典並於 `get_tips()` 提示腳本內容漂移。 | P2 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 本機從 `source/<mod>` 動態自給自足打包正式版 `.zip`（如母倉測試或未先執行 `dev release`） | 若從本地同版 `source/<mod>` 即時確定性打包，而 `index.json` 已存在且記錄的是前一次打包的舊 `sha256`（源碼修改尚未跑 `dev release`），只有在下載外部/既有 `.zip` 時強制比對 `index.json` 之 `sha256`；若 `index.json` 缺少該版本 `sha256` 或下載之 `.zip` 與 `index.json` 記錄不符，且未傳入 `--ignore-sha256`，則拋出 `RuntimeError` 阻斷並提示可使用 `--ignore-sha256` |
| **EC-02** | 安裝或還原 `@build` / `*.build` 開發版模組 | `_is_build_version_request(version)` 為 `True` 時完全跳過 `sha256` 檢查，100% 不影響日常熱調試與沙盒測試 |
| **EC-03** | `self-update` 下載到 HTML 錯誤頁或不含 `main()` / `__version__` 之任意合法 Python 腳本 | AST 結構驗證檢查頂層必須同時定義 `__version__` 與 `def main`，否則印出錯誤並拒絕覆寫 `yscb.py` |
| **EC-04** | Windows 下目標檔案被其他程序長時間鎖定導致 `atomic_write` 10 次 `os.replace` 皆失敗 | 拋出 `PermissionError` / `OSError`，`finally` 自動刪除 `.tmp` 暫存檔，原目標檔案內容 100% 完好無損 |
| **EC-05** | `OSBackend.remove(dir_path, missing_ok=True)` 刪除目錄時子檔案遭權限拒絕 (`PermissionError`) | `onerror` 先嘗試 `os.chmod(func_path, stat.S_IWRITE | stat.S_IREAD)` 重試一次；若仍因權限或鎖定失敗則立即拋出 `PermissionError`，不因 `missing_ok=True` 而靜默吞錯 |
| **EC-06** | 本機 `yscb.py` 與遠端 `yscb.py` 僅因 Windows `CRLF` 與 Linux `LF` 換行符不同 | `UpdateChecker._compute_script_sha256` 先將內容 `.replace("\r\n", "\n")` 正規化後再計算 SHA-256，避免誤報內容漂移 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 確定性與安全性 | 相同模組源碼於不同時間或不同 OS 執行確定性壓縮產出之 `.zip` SHA-256 100% 一致；所有現存 `active` 發行版 100% 具備真實 SHA-256 |
| **NFR-02** | 零外部依賴 | `yscb.py` 與 `core` 維持 100% Python 標準庫實現，不引入任何第三方套件 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `yscb.py` 是零依賴自舉入口，絕對不可頂層 `import core`；所有確定性壓縮與 SHA-256 校驗輔助函式在 `yscb.py` 內必須以純標準庫獨立實現。
- **`[!NOTE]`** 現有單元測試（如 `core/tests/test_engine_and_installer.py`）在沙盒中會動態建立模擬 Provider 目錄與假 `index.json` / `.zip` 來測試 `install` / `update` / `restore`；因此當測試建立的模擬 `.zip` 進行安裝時，為避免破壞既有測試或確保測試合規，我們需檢查既有測試如何構造 `index.json`，並同步在測試 helper 中填入對應 `sha256`（或於本地無 `releases` 帳本之簡易測試 fixture 確認其結構）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[T-03] Deterministic Zip & SHA-256 Verification
  ├─ Producer: dev/builder.py & release-publish.yml
  │    ├─ _write_deterministic_zip(source_dir, zip_path, ignores, manifest_override)
  │    │    ├─ sorted dirs & files
  │    │    ├─ ZipInfo(filename, date_time=(2020,1,1,0,0,0)), external_attr=0o644<<16
  │    │    └─ normalize text files (\r\n -> \n)
  │    └─ compute_file_sha256(zip_path) -> write to index.json["releases"][ver]["sha256"]
  ├─ Consumer: core/engine.py & core/installer.py & yscb.py
  │    ├─ if is_build_version(ver) or ignore_sha256: skip sha256 check
  │    └─ else: lookup expected_sha256 from index.json["releases"][ver]["sha256"]
  │         ├─ missing -> raise RuntimeError("Missing sha256 in index.json ... use --ignore-sha256 to bypass")
  │         └─ mismatch -> raise RuntimeError("SHA-256 mismatch ...")
  └─ Self-Update: yscb.py cmd_self_update
       ├─ ast.parse + check top-level __version__ & def main
       └─ verify --sha256 or companion .sha256 (unless --ignore-sha256)

[T-04] WarmWorker Thread-Safe Environment Isolation (server/worker.py)
  └─ execute_task(module, args, cwd, env):
       ├─ with self._task_lock:
       ├─ save orig_cwd, orig_env = dict(os.environ)
       ├─ apply cwd + uri.host_scope + diff env update
       └─ finally: _restore_env_diff(orig_env) + os.chdir(orig_cwd)

[T-06 & T-14] OSBackend Atomic Write & Directory Remove (core/vfs/os_backend.py)
  ├─ atomic_write: retry os.replace on win32 up to 10 times; on exhaustion re-raise OSError (no os.remove+copy2)
  └─ remove: shutil.rmtree(norm_path, onerror=_handle_remove_error) -> ignore ENOENT when missing_ok=True, chmod retry on EACCES, re-raise others
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/release/*/index.json` | Modify | FR-01：回填 `origin/releases` 現存全部 7 個模組 `active` 版本 `.zip` 之真實 `sha256` |
| `.github/workflows/release-publish.yml` | Modify | FR-01：採用確定性壓縮打包新增版本，並將所有 active `.zip` 之 `sha256` 同步寫入 `index.json` |
| `.github/workflows/ci.yml` | New | FR-06：新增 GitHub Actions 自動化 CI 工作流（執行 `dev check --all`、`contributes check` 與全模組 pytest） |
| `yscb.py` | Modify | FR-01/02/07/08：`__version__ = "1.2.2.0"`、確定性壓縮、冷自舉/init 支援 `sha256` 校驗與 `--ignore-sha256`、`self-update` 結構檢查與 `--sha256`/`--ignore-sha256`、收斂靜默吞錯 |
| `ys_codebase/source/core/core/engine.py` | Modify | FR-01/02/07：確定性壓縮、`_verify_package_sha256`、`act_download` / `act_prepare` / `act_reload` 支援 `ignore_sha256`、收斂靜默吞錯 |
| `ys_codebase/source/core/core/installer.py` | Modify | FR-02：`cmd_install` / `cmd_update` / `cmd_restore` 支援 `ignore_sha256: bool = False` 傳遞 |
| `ys_codebase/source/core/scripts/cli.py` | Modify | FR-02：`install` / `update` / `restore` 解析 `--ignore-sha256` 選項並傳入 `Installer` |
| `ys_codebase/source/core/contributes/core.json` | Modify | FR-02：於 `install`、`update`、`restore` 命令宣告新增 `ignore-sha256` 選項 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | FR-04/05：`atomic_write` 移除破壞性回退；`remove` 僅忽略 `FileNotFoundError` 並保留 `PermissionError` 拋出 |
| `ys_codebase/source/core/core/update_checker.py` | Modify | FR-08：`_check_host_script_update` 支援同版本號 SHA-256 內容漂移偵測與提示 |
| `ys_codebase/source/server/server/worker.py` | Modify | FR-03/07：`WarmWorker` 差量環境變數還原 `_restore_env_diff`、`_task_lock` 與 `uri.host_scope` 保護 |
| `ys_codebase/source/dev/dev/builder.py` | Modify | FR-01：`_create_module_archive_atomic` 改為確定性壓縮，`_update_release_index` 自動計算並寫入 `sha256` |
| `ys_codebase/source/dev/dev/checker.py` | Modify | FR-07：`_check_source_files` 新增裸 `except:` (`ast.ExceptHandler.type is None`) 靜態告警 |
| `ys_codebase/source/core/tests/test_vfs.py` | Modify | 測試 FR-04、FR-05、EC-04、EC-05 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 測試 FR-01、FR-02、EC-01、EC-02 與更新測試 fixture `sha256` |
| `ys_codebase/source/core/tests/test_remote_zip_bootstrap.py` | Modify | 測試 `yscb.py` `self-update` 結構/雜湊驗證、冷自舉 `sha256` 校驗與 `--ignore-sha256` |
| `ys_codebase/source/core/tests/test_update_checker.py` | Modify | 測試 FR-08、EC-06 (`yscb.py` 同版本號內容漂移偵測) |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 測試 FR-03 (`WarmWorker` 差量環境變數還原與併發執行緒讀取 `os.environ` 零清空) |
| `ys_codebase/source/dev/tests/test_builder.py` | Modify | 測試 FR-01 (確定性壓縮與 `index.json` `sha256` 寫入) |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 測試 FR-07 (裸 `except:` 靜態檢查) |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 確定性壓縮（Deterministic Zip）統一規格：所有模組打包路徑（`dev/builder.py`、`core/engine.py`、`yscb.py`、`release-publish.yml`）皆以 UTF-8 LF 正規化寫入 `.py`/`.json`/`.md`/`.txt`/`.yaml`/`.yml`/`.toml`/`.yscbignore`/`.gitignore` 等文字檔，二進位檔原樣寫入，且所有項目依 `arcname` 字典序排序、固定 `ZipInfo.date_time = (2020, 1, 1, 0, 0, 0)`、`compress_type = zipfile.ZIP_DEFLATED`、`external_attr = (0o644 & 0xFFFF) << 16`。
- **[P02:DR-02]** 當ローカル Provider 使用未打包目錄（例如 `provider/<mod>/<ver>/manifest.json`）或本地同版 `source/<mod>` 即時打包時：若目標來源本身即為本地同版 `source/<mod>` 動態自舉打包（或測試中未建立 `releases` 字典之純目錄來源），則以確定性壓縮產出；凡從遠端或 `release/<mod>/<ver>.zip` 下載且非 `@build` 版本，一律強制核對 `index.json["releases"][<ver>]["sha256"]`（除非 `ignore_sha256=True`）。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/dev/dev/builder.py
def compute_file_sha256(file_path: str) -> str: ...
def _create_module_archive_atomic(
    source_dir: str,
    target_zip_path: str,
    ignores: List[str],
    manifest_data: Dict[str, Any],
    target_version: str,
) -> int: ...

# ys_codebase/source/core/core/engine.py
def compute_file_sha256(file_path: str) -> str: ...
class AtomicEngine:
    def act_download(
        self,
        module_name: str,
        version: str,
        provider_url: str,
        ignore_sha256: bool = False,
    ) -> str: ...
    def act_prepare(
        self,
        target_list: List[Tuple[str, str]],
        provider_url: str,
        force: bool = False,
        ignore_sha256: bool = False,
    ) -> None: ...

# ys_codebase/source/core/core/installer.py
class Installer:
    def cmd_install(
        self,
        module_name: Union[str, Sequence[str]],
        version: Optional[str] = None,
        provider: Optional[str] = None,
        force: bool = False,
        ignore_sha256: bool = False,
    ) -> int: ...
    def cmd_update(
        self,
        module_name: Optional[Union[str, Sequence[str]]] = None,
        provider: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> int: ...
    def cmd_restore(
        self,
        force: bool = False,
        provider: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> int: ...

# ys_codebase/source/server/server/worker.py
def _restore_env_diff(orig_env: Dict[str, str]) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `AtomicEngine.act_download`：當版本非 `@build` 且 `ignore_sha256=False` 時，若 `index.json` 缺少 `releases[<ver>]["sha256"]` 或與下載之 `.zip` SHA-256 不一致，立即刪除問題 `.zip` 並拋出 `RuntimeError`（訊息明確提示可使用 `--ignore-sha256` 跳過）。
  - `OSBackend.atomic_write`：Windows 重試耗盡後直接拋出底層 `OSError` / `PermissionError`，不破壞原檔。
  - `OSBackend.remove`：`missing_ok=True` 僅忽略 `FileNotFoundError`，遇到 `PermissionError` 照常拋出。
- **階段決策紀錄**：`[P03:DR-01]` 所有新增之 `ignore_sha256: bool = False` 參數均具向下相容預設值 `False`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-08 皆已於介面簽名與實作規劃中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - 既有測試（如 `test_engine_and_installer.py`）中有許多測試案例在臨時目錄建立模擬 Provider 與 `.zip` 檔，若這些測試未在 `index.json` 填寫 `sha256`，強制檢查是否會導致舊測試失敗？→ 我們將盤點所有構造假 `.zip` 與 `index.json` 的測試案例，為其補上真實 `sha256`，並專門新增測試驗證「缺少 `sha256` 時預設報錯阻斷、傳入 `--ignore-sha256` 時告警放行、`sha256` 不符時報錯阻斷、`@build` 版本免檢放行」。
  - `self-update` 的 SHA-256 來源為何？→ 支援顯式 `--sha256 <hex>`；若未指定 `--sha256` 且未傳入 `--ignore-sha256`，則嘗試讀取伴隨 `<target_url>.sha256` 或本地母倉對應檔案計算校驗，同時強制通過 AST 語法與頂層符號（`__version__`、`def main`）結構驗證。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md`, `docs/dev/README.md`, `docs/server/README.md` | Modify | 更新 `index.json` SHA-256 強制驗證、`--ignore-sha256`、確定性壓縮、`dev check` 裸 `except:` 規則與 Worker 環境差量還原說明 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新介面契約與異常契約 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_03` 可靠性與工程治理變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認三層文檔衝擊範圍，於 Phase 07 同步更新。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：從 `origin/releases` 提取現存 7 個模組全部 `active` 版本 `.zip` 的真實 SHA-256 並一次性回填至 `ys_codebase/release/*/index.json`（FR-01）
- [x] **TASK-02**：於 `dev/builder.py` 與 `.github/workflows/release-publish.yml` 實作確定性壓縮與 `index.json` `sha256` 自動寫入；於 `dev/checker.py` 實作裸 `except:` AST 靜態告警，並新增單元測試（FR-01, FR-07）
- [x] **TASK-03**：於 `core/vfs/os_backend.py` 修正 `atomic_write`（移除破壞性回退）與 `remove`（僅忽略 `FileNotFoundError`），並於 `core/update_checker.py` 實作 `yscb.py` 同版本號 SHA-256 內容漂移偵測及單元測試（FR-04, FR-05, FR-08, EC-04 ~ EC-06）
- [x] **TASK-04**：於 `core/engine.py`、`core/installer.py`、`core/scripts/cli.py`、`core/contributes/core.json` 與 `yscb.py` 實作確定性壓縮、正式版強制 `sha256` 驗證、`--ignore-sha256` 逃生閥、`@build` 豁免、`self-update` 結構與雜湊驗證、收斂非清理路徑靜默吞錯及單元測試（FR-01, FR-02, FR-07, FR-08, EC-01 ~ EC-03）
- [x] **TASK-05**：於 `server/worker.py` 實作 `WarmWorker` 差量環境變數還原 `_restore_env_diff`、`_task_lock` 與 `uri.host_scope` 保護及單元測試（FR-03, FR-07）
- [x] **TASK-06**：建立 `.github/workflows/ci.yml` 自動化 CI 工作流（FR-06）
- [x] **TASK-DOC**：同步更新微觀代碼 Docstrings 並通過 `dev check --all` 與 `contributes check`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-02~05** | Minor | 單元測試依各模組既有測試檔命名（`test_builder.py`、`test_checker.py`、`test_server.py`、`test_distribution_lifecycle.py`、`test_remote_zip_bootstrap.py`）直接擴充，避免建立冗餘測試檔 | 已回寫 §2.2 |

