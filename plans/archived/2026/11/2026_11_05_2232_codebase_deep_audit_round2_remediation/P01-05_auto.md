# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：全專案第二輪八維度深度審計與反向溯源收斂修復 (Codebase Deep Audit Round 2 Remediation)
> 建立日期：2026-11-05
> 所屬主計畫：N/A
> 狀態：Completed
> 模型：Unknown
> 依據 P00：[P00_discuss.md](./P00_discuss.md)
> 模板版本：v1.0

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :---: | :--- | :--- | :---: | :---: |
| **FR-01** | `core` 跨行程鎖 Inode 核對與過期鎖探測 (`AUD-01`) | `InterProcessLock.acquire` 於 POSIX 取得 `flock` 後比對 `fstat(fd)` 與 `stat(lock_file)` 之 `(st_dev, st_ino)`；`AtomicEngine.act_lock` 於過期時先釋放本進程 `_active_locks` 再以非阻塞 `probe.acquire(blocking=False)` 確認無外部活躍進程持鎖後才刪除過期鎖檔。 | P1 | [P00:DR-01] |
| **FR-02** | `core` Win32 `IsProcessInJob` 4-byte `BOOL` 對齊 (`AUD-02`) | `process.py:can_spawn_background_daemon` 使用 `wintypes.HANDLE` 與 `wintypes.BOOL`（4 bytes）取代 1-byte `ctypes.c_bool`。 | P1 | [P00:DR-01] |
| **FR-03** | `core` 指令註冊表與模組快取重載失效 (`AUD-03`) | `dispatcher.py` 新增 `clear_cache()` 並由 `engine.py:act_reload` 同步呼叫；`_load_registry` 對 `os.listdir(modules_dir)` 排序（`"core"` 優先）並對別名衝突輸出 `stderr` 警告。 | P1 | [P00:DR-01] |
| **FR-04** | `core` macOS `gitignore` `realpath` 對齊與 `ensurepip` 防護 (`AUD-04`) | `gitignore.py` 與 `installer.py` 在計算相對路徑與根目錄比對時統一使用 `os.path.realpath`；`pip_manager.py:_bootstrap_pip` 防護 `getattr(ensurepip, "_WHEEL_PKG_DIR", None)` 為 `None` 並探測 `_bundled` 與 `/usr/share/python-wheels`。 | P1 | [P00:DR-01] |
| **FR-05** | `core` `_is_source_tree_path` 相對化與 `OSBackend.copy` 同源守衛 (`AUD-05`) | `venv.py:_is_source_tree_path` 支援自動解析 `yscb_root` 並僅對工作區內相對路徑判斷 `source/`；`os_backend.py:copy` 攔截同源路徑與子目錄遞迴複製。 | P1 | [P00:DR-01] |
| **FR-06** | `dev` `create_mock_source_module` 自訂檔案落盤 (`AUD-06`) | `case.py:L261` 將跳過清單收斂為 `("manifest.json", "scripts/cli.py")`，保留預設 `test_dummy.py` 建立並允許自訂 `contributes/*` 與 `tests/*` 正常寫入。 | P1 | [P00:DR-02] |
| **FR-07** | `dev` 序列與預設測試模式 `--sync` 部署 (`AUD-07`) | `tester.py:_run_test` 在 `cfg.is_all or not cfg.target_param` 時以 `TestDiscovery.discover_modules(None)` 補齊 `tested_mods`。 | P1 | [P00:DR-02] |
| **FR-08** | `agents-workflow` Umbrella 子計畫自癒管線對齊 (`AUD-08`) | `verifier.py:verify_plan` 遍歷 `sub_*` 時先驗證主體 Markdown，若無新增 FAIL、啟用自癒且含非種子檔案（`has_non_seed_md`）則呼叫 `_auto_heal_companions` 並補驗新建 `P06_test_plan.md`，最後執行結構與追溯性檢核。 | P1 | [P00:DR-02] |
| **FR-09** | `dev` 與 `agents-workflow` Git 子進程 UTF-8 編碼與超時 (`AUD-09`) | `releaser.py:_run_git_cmd` 與 `session_trace.py:_get_git_changed_files` 補齊 `encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL` 與 `timeout`。 | P1 | [P00:DR-02] |
| **FR-10** | `knowledge-db` Windows 工作者狀態檔退避替換與暫存清理 (`AUD-10`) | `knowledge_db/service.py:write_worker_state` 為 `os.replace` 加上 5 次短指數退避重試（`0.005 * 2**attempt`）並於 `except` 刪除殘留 `.tmp` 檔。 | P1 | [P00:DR-03] |
| **FR-11** | `core` SemVer 預發布守衛、雙算符合併與 `installed_modules` 防護 (`AUD-11`) | `semver.py` 三段式匹配檢查雙方無 `prerelease` 與 `is_build`；`engine.py:act_solve_deps` 支援雙範圍約束合併；`engine.py` 與 `installer.py` 補齊 `isinstance(meta, dict)`。 | P2 | [P00:DR-01] |
| **FR-12** | `core` `dict[K, V]` 括號平衡解析與 `contributes.get` 隔離 (`AUD-12`) | `validator.py` 以 `_split_top_level_comma` 解析 `dict[K, V]` 並統一寫入 `_SIGNATURE_PARSE_CACHE`；`contributes.get()` 對最終回傳子項執行 `copy.deepcopy` 並對齊單檔 `contributes.json` 處理。 | P2 | [P00:DR-01] |
| **FR-13** | `agents-workflow` `P00` 階段檔動態解析與 `init` 選項補齊 (`AUD-13`, `AUD-14`) | `status.py:_resolve_p00_next_action` 改用 `cls.resolve_phase_file(p, "P00")`；`contributes/core.json` 與 `scripts/cli.py` 補齊 `init` 之 `default` 與 `path-roadmap` 等選項。 | P2 | [P00:DR-02] |
| **FR-14** | `dev` 沙盒清理順序與 `server` 無鎖 PID 快照及閒置鎖探測優化 (`AUD-15`, `AUD-16`, `AUD-20`) | `sandbox.py:cleanup_sandbox` 將 `_ACTIVE_SANDBOXES.discard` 移至活躍沙盒守門後並於守門比對時使用 `normcase`；`server/master.py` 以區域變數 `proc` 讀取 `.pid`；`server/watcher.py` 將 `_is_core_transaction_locked()` 移入快照差異分支內。 | P2 | [P00:DR-02] |
| **FR-15** | `knowledge-db` 清理游標重置、`retrieval` C# 鍵值、`file-space` 與 `ast` 打磨及零工單註解合規 (`AUD-17 ~ AUD-19`, `AUD-21 ~ AUD-24`) | `knowledge_db/engine.py:clean` 委派 `self.pipeline._reset_consumer_cursor(space_name=None)`；`retrieval.py:_cs_type_key` 支援 `"csharp"` 與 `is_partial`；`file_space/service.py` 採 O(1) 純字串前綴剝離；`file_space/manager.py` 單檔 `include` 檢查 `is_file_included`；`ast_engine/linker.py` 讀取 `line_number`；`bundler.py` 移除 `_parse_and_dedup_file`；清理 12 個檔案生產註解工單編號並補強 `resolver.py` 與 `core/scripts/cli.py`。 | P2 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :---: | :--- | :--- |
| **EC-01** | 同進程模擬過期鎖自癒與 `act_unlock` 鎖檔清理（`test_engine.py:L114-L129, L668`） | `act_lock` 於過期時先釋放本進程 `_active_locks` 再執行非阻塞 `probe.acquire(blocking=False)`；`act_unlock` 維持在無活躍鎖時移除 `.yscb.lock`。 |
| **EC-02** | `test_core_commands.py` 斷言執行期錯誤訊息含 `EC-02 ~ EC-08` | 清理 `core` 註解時嚴格保留所有執行期字串常數內的 `(EC-02)` ~ `(EC-08)`，確保外部錯誤語意 100% 等價。 |
| **EC-03** | 沙盒測試執行 `KnowledgeEngine.clean(space="demo_space")` 時之宿主游標隔離 | 透過 `self.pipeline._reset_consumer_cursor(space_name=None)` 重置沙盒 `self.scanner` 游標，避免直接呼叫全域 `file_space.reset_cursor(space_name=None)` 誤刪宿主真實 `cursors/knowledge-db.json`。 |
| **EC-04** | Umbrella 計畫含 `Seeded` 子計畫（僅有 `roadmap.md` 或 `todo.md`） | `verifier.py` 檢查 `has_non_seed_md`，不為尚未立項的 Seeded 子計畫誤建 `changelog.md` 或 `P06_test_plan.md`。 |
| **EC-05** | `FileSpaceWatcherServiceWorker.notify_file_event` 收到大量 `.git` 雜訊事件 | 採用純記憶體 O(1) 字串前綴比對（Windows `lower()` 與 macOS `/private/` 雙向剝離），絕不呼叫 `Path.resolve()` 觸發磁碟 I/O。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :---: | :---: | :--- |
| **NFR-01** | 零第三方核心依賴 | `core`、`server`、`dev`、`agents-workflow`、`file-space` 維持 100% Python 標準庫實作。 |
| **NFR-02** | 跨平台一致性 | 同時相容 Linux (POSIX)、Windows (NTFS / Win32) 與 macOS (APFS / `/private/var` 軟連結)。 |
| **NFR-03** | 零工單編號註解 | 受影響之 40 個業務源碼檔案之 `#` 註解與 Docstring 達成 0 工單/審計編號污染。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **[!NOTE] Windows 句柄鎖與大小寫正規化**：在 Windows 下執行 `os.replace` 替換高頻讀取之狀態檔須具備 `PermissionError` 退避重試；`_ACTIVE_SANDBOXES` 集合鍵值須維持 `os.path.abspath` 原大小寫以相容既有單元測試斷言。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

本計畫聚焦於七大模組的局部缺陷收斂與跨平台邊界加固，不改變各模組既有公開架構拓撲，透過精確點位修補消除雙軌狀態失步、跨平台路徑/鎖定競態與規格註解殘留。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | POSIX `flock` 取得後比對 `fstat` 與 `stat` 之 `(st_dev, st_ino)` (`AUD-01`) |
| `ys_codebase/source/core/core/platform/process.py` | Modify | `IsProcessInJob` 改用 4-byte `wintypes.BOOL` 與 `wintypes.HANDLE` (`AUD-02`) |
| `ys_codebase/source/core/core/platform/venv.py` | Modify | `_is_source_tree_path` 相對化於工作區根目錄判斷 `source/` (`AUD-05`) |
| `ys_codebase/source/core/core/platform/daemon_probe.py` | Modify | 清理註解與 Docstring 內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 新增 `clear_cache()`、排序 `os.listdir`、輸出別名衝突警告並清理規格編號註解 (`AUD-03`, `AUD-24`) |
| `ys_codebase/source/core/core/commands/registry.py` | Modify | 清理註解與 Docstring 內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/core/core/commands/resolver.py` | Modify | 排除單一連字號 `"-"` 誤判為空選項並清理規格編號註解 (`AUD-24`) |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | `copy` 攔截同源路徑與子目錄遞迴並強化 `_safe_copytree` symlink 容錯 (`AUD-05`) |
| `ys_codebase/source/core/core/engine.py` | Modify | `act_lock` 外部鎖探測、`act_reload` 呼叫 `dispatcher.clear_cache()`、`act_solve_deps` 雙算符合併與 `isinstance(meta, dict)` 防護 (`AUD-01`, `AUD-03`, `AUD-11`) |
| `ys_codebase/source/core/core/gitignore.py` | Modify | `normalize_pattern`、`_resolve_roots` 與 `_cleanup_obsolete_nested_gitignores` 對齊 `realpath` (`AUD-04`) |
| `ys_codebase/source/core/core/installer.py` | Modify | `generate_internal_gitignore` 對齊 `realpath` 並補齊 `isinstance(meta, dict)` 防護 (`AUD-04`, `AUD-11`) |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | `_bootstrap_pip` 防護 `_WHEEL_PKG_DIR = None` 並探測 `_bundled` 與 `/usr/share/python-wheels` (`AUD-04`) |
| `ys_codebase/source/core/core/semver.py` | Modify | `_match_single_clause` 三段式匹配檢查雙方無 `prerelease` 與 `is_build` (`AUD-11`) |
| `ys_codebase/source/core/core/validator.py` | Modify | 新增 `_split_top_level_comma` 解析 `dict[K, V]` 並統一寫入 `_SIGNATURE_PARSE_CACHE` (`AUD-12`) |
| `ys_codebase/source/core/core/contributes.py` | Modify | `get()` 對最終回傳子項執行 `deepcopy` 並對齊單檔 `contributes.json` 驗證與指令/語系收集 (`AUD-12`) |
| `ys_codebase/source/core/core/locale.py` | Modify | 清理註解與 Docstring 內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 於 `install/update/remove/list/rollback/restore` 補齊 `_normalize_bags` (`AUD-24`) |
| `ys_codebase/source/server/server/master.py` | Modify | 以區域變數 `proc` 讀取 `.pid` 並清理規格編號註解 (`AUD-16`, `AUD-24`) |
| `ys_codebase/source/server/server/watcher.py` | Modify | 將 `_is_core_transaction_locked()` 移入快照差異分支內 (`AUD-20`) |
| `ys_codebase/source/server/server/worker.py` | Modify | 清理註解內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 清理註解內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | 收斂 `create_mock_source_module` 跳過清單為 `("manifest.json", "scripts/cli.py")` (`AUD-06`) |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `cleanup_sandbox` 將 `discard` 移至活躍沙盒守門後並於守門比對加 `normcase` (`AUD-15`) |
| `ys_codebase/source/dev/dev/tester.py` | Modify | `_run_test` 補齊序列與預設模式之 `tested_mods` (`AUD-07`) |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | `_run_git_cmd` 補齊 UTF-8 編碼、`DEVNULL` 與 `timeout=30.0` (`AUD-09`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `verify_plan` 對齊 `sub_*` 子計畫三步自癒管線 (`AUD-08`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | `_get_git_changed_files` 補齊 UTF-8 編碼與 `DEVNULL` 並清理規格編號註解 (`AUD-09`, `AUD-24`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | `_resolve_p00_next_action` 改用 `cls.resolve_phase_file(p, "P00")` (`AUD-13`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` | Modify | 清理註解內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Modify | 清理註解內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Modify | 清理註解內殘留之規格編號 (`AUD-24`) |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | `init.options.auto` 補齊 `default` 與 `path-*` 選項宣告 (`AUD-14`) |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | `init` 補齊 `path-roadmap` 選項解析與映射 (`AUD-14`) |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | `notify_file_event` O(1) 純字串前綴正規化支援 Windows 大小寫與 macOS `/private/` (`AUD-19`) |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | `file_belongs_to_space` 單檔 `include` 補檢驗 `cfg.is_file_included(inc_root.name)` (`AUD-21`) |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | `_compute_symbols_map_fingerprint` 改讀 `line_number` (`AUD-22`) |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 移除零引用孤兒方法 `_parse_and_dedup_file` (`AUD-23`) |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | `write_worker_state` 補齊 Windows `PermissionError` 退避重試與 `.tmp` 清理 (`AUD-10`) |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `clean` 委派 `self.pipeline._reset_consumer_cursor(space_name=None)` (`AUD-17`) |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `_cs_type_key` 支援 `"csharp"` 與 `is_partial` (`AUD-18`) |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 100% 行為等價與單元測試契約優先保護**：所有處方均經過盲眼 Devil's Advocate 對照全倉 63 個測試檔案進行反向驗證，確保修復邊界問題的同時不破壞任何既有測試斷言或引發效能退化。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/commands/dispatcher.py
def clear_cache() -> None: ...

# ys_codebase/source/core/core/validator.py
class ContributesValidator:
    @staticmethod
    def _split_top_level_comma(inner: str) -> Optional[Tuple[str, str]]: ...

# ys_codebase/source/dev/dev/releaser.py
class Releaser:
    def _run_git_cmd(self, args: List[str], cwd: Optional[str] = None, timeout: float = 30.0) -> Tuple[int, str, str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `InterProcessLock.acquire` 與 `AtomicEngine.act_lock` 於外部活躍進程持鎖超時時拋出 `BlockingIOError`。
  - `OSBackend.copy` 於目標目錄為來源目錄之子目錄時拋出 `ValueError`。
  - `core` 模組之 CLI 路由與解析異常字串完整保留 `(EC-02)` ~ `(EC-08)` 代號契約。
- **階段決策紀錄**：[P03:DR-01] 公開 API 簽名維持 100% 向後相容，僅新增內部輔助函式與選填預設參數。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-15（涵蓋 `AUD-01 ~ AUD-24`）皆已於介面簽名與實作清單中完整對齊。
- **邊界防護**：EC-01 ~ EC-05 皆具備明確之單元測試相容守衛與降級策略。
- **依賴純淨**：100% 符合 NFR-01 ~ NFR-03 指標約束。
- **靈魂拷問與防護解法**：
  - *問：清理 `core` 註解中的 `EC-XX` 是否會影響 `test_core_commands.py`？*
  - *答*：已透過 AST 與行號精確定位，僅修改 `#` 註解與 `"""` Docstring，所有 `raise` 與 `print` 雙引號字串常數保持 100% 原樣。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `docs/README.md` | N/A | 內部邊界加固與相容性修正，無外部模組結構異動 |
| **專題手冊** | `docs/_project/STANDARDS.md` | N/A | 遵循既有三平台與零工單註解標準 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 無新增架構妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 清理 12 個檔案殘留之規格工單編號，保留純粹架構 Why 說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄第二輪審計收斂摘要 |

- **決策定稿**：**[P04:DR-01]** 確認規格無誤，進入 Phase 05 實作與驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core` 跨平台鎖、Win32 ABI、重載快取、macOS `gitignore` `realpath`、`ensurepip` 防護、`_is_source_tree_path` 相對化與 `OSBackend.copy` 同源守衛（`AUD-01 ~ AUD-05`, `FR-01 ~ FR-05`）
- [x] **TASK-02**：實作 `core` SemVer 預發布守衛、雙算符合併、`installed_modules` 防護、`validator.py` 括號平衡切分與 `contributes.get` 隔離（`AUD-11 ~ AUD-12`, `FR-11 ~ FR-12`）
- [x] **TASK-03**：實作 `dev`、`agents-workflow` 與 `server` 雙軌同步、子計畫自癒、Git 子進程 UTF-8 編碼、沙盒清理順序與 Watcher 鎖探測優化（`AUD-06 ~ AUD-09`, `AUD-13 ~ AUD-16`, `AUD-20`, `FR-06 ~ FR-09`, `FR-13 ~ FR-14`）
- [x] **TASK-04**：實作 `knowledge-db`、`file-space` 與 `ast` 狀態檔退避替換、全空間游標重置、C# 分部鍵值、O(1) 事件前綴剝離、單檔 `include` 過濾、`line_number` 指紋與孤兒方法移除（`AUD-10`, `AUD-17 ~ AUD-19`, `AUD-21 ~ AUD-23`, `FR-10`, `FR-15`）
- [x] **TASK-05**：清理 `core`、`server` 與 `agents-workflow` 共 12 個檔案生產註解與 Docstring 規格編號，並完成 `resolver.py` 單一 `"-"` 防護與 `core/scripts/cli.py` `_normalize_bags` 補齊及全套單元測試與雲端受控 CoW 同步（`AUD-24`, `FR-15`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
