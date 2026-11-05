# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log) — sub_03_server_dev_and_workflow

> 功能名稱：sub_03_server_dev_and_workflow  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.0  

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[module:server]
  MasterSupervisor._spawn_worker_locked()
    |-- env["PYTHONIOENCODING"] = "utf-8"
    +-- _read_handshake(proc.stdout)
          +-- try: json.loads(line) -> ignore ValueError / non-dict -> handle worker_alive & worker_ready
  MasterHTTPHandler._handle_post_dispatch()
    |-- Validate Content-Length >= 0 & isinstance(req_data, dict)
    |-- Validate non-empty str "module" & list "args" BEFORE HTTP 200
    +-- Normalize yscb_root via os.path.normcase(os.path.realpath(os.path.abspath(...)))
  worker.py:_dispatch_command_with_captured_streams()
    +-- Inside `with streamer:` catch Exception -> write stderr & return (1, err_text)
          +-- streamer.send_task_finish(exit_code, duration_ms, error=err_text)

[module:dev]
  SandboxProvisioner.cleanup_sandbox()
    |-- Acquire _SANDBOX_LOCK only for _ACTIVE_SANDBOXES.discard() & safety check
    +-- Outside lock: broadcast("on_test_teardown") + vfs.robust_rmtree(sandbox_dir)
  YSCBTestCase.tearDown() / run_cli() & Tester._execute_single_module_in_sandbox()
    |-- Incremental os.environ key diff restore (no os.environ.clear())
    +-- Delegate subprocess execution to run_subprocess_with_tree_timeout()
  Builder._create_module_archive_atomic() & Checker._check_custom_rules()
    |-- Direct os.replace(tmp_zip_path, target_zip_path) without prior os.remove()
    +-- Bidirectional hyphen/underscore normalization for custom rule donor modules

[module:agents-workflow]
  ArtifactCompiler & ReleasePublisher
    |-- Translate legacy export type "workflow"/"workflows" -> "skill" in memory
    |-- Remove dead agent_rules loop in _check_short_circuit()
    +-- Prune legacy .agents/workflows/ and .claude/commands/ directories during release
  TodoManager.promote_todos() & PlanVerifier._check_nested_depth_and_structure()
    |-- Write target todo.md and changelog.md BEFORE updating source TODO.md
    +-- Check P01/P07 existence via PlanStatusResolver.resolve_phase_file()
  scripts/cli.py:_normalize_bags() & SessionTraceEngine.list_sessions()
    |-- Parse space-separated --key <val> options for value-taking flags
    +-- Extract session topic in single-pass parse_transcript_file()
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/master.py` | Modify | `_read_handshake` 容錯非 JSON 雜訊、`_spawn_worker_locked` 注入 `PYTHONIOENCODING=utf-8`、`_handle_post_dispatch` 前置載荷驗證與路徑正規化、`touch_activity` 執行緒鎖保護 (`FR-01`, `FR-03`~`FR-06`) |
| `ys_codebase/source/server/server/worker.py` | Modify | `_dispatch_command_with_captured_streams` 於 `with streamer:` 內捕獲例外並回傳 `(exit_code, err_text)` 供 `send_task_finish(..., error=err_text)` 傳遞、`worker_main` 強制標準串流 UTF-8 (`FR-02`, `FR-03`) |
| `ys_codebase/source/server/server/service.py` | Modify | `touch_activity` 以執行緒鎖與依路徑節流表保護 `1.0s` 節流視窗 (`FR-05`) |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增 `SRV-01`~`SRV-06` 單元與邊界測試案例 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `cleanup_sandbox` 將 `on_test_teardown` 廣播與 `vfs.robust_rmtree` 移出 `_SANDBOX_LOCK` 鎖外 (`FR-07`) |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | `tearDown` 環境變數差量還原、`run_cli` 串接 `run_subprocess_with_tree_timeout` (`FR-08`, `FR-09`) |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `_create_module_archive_atomic` 移除前置 `os.remove`，直接 `os.replace` 原子覆寫 (`FR-08`) |
| `ys_codebase/source/dev/dev/tester.py` | Modify | `_execute_single_module_in_sandbox` 串接 `run_subprocess_with_tree_timeout` (`FR-09`) |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_custom_rules` 雙向正規化連字號與底線模組名 (`FR-10`) |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 新增 `cleanup_sandbox` 鎖外執行 `robust_rmtree` 與事件廣播之驗證測試 |
| `ys_codebase/source/dev/tests/test_case.py` | Modify | 新增環境變數差量還原與 `run_cli` 樹狀逾時強殺驗證測試 |
| `ys_codebase/source/dev/tests/test_builder.py` | Modify | 新增 `_create_module_archive_atomic` 無前置刪除之原子替換驗證測試 |
| `ys_codebase/source/dev/tests/test_tester.py` | Modify | 新增 `_execute_single_module_in_sandbox` 樹狀逾時防護驗證測試 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 新增連字號模組名稱自訂規則解析驗證測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 記憶體無痛轉譯 `type: "workflow"` 為 `"skill"` (`FR-12`) |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 移除 `_check_short_circuit` 中 `agent_rules` 死代碼、支援舊版 `workflow` 投影相容、清理遺留 `.agents/workflows/` 與 `.claude/commands/` (`FR-11`, `FR-12`) |
| `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Modify | `TodoManager.promote_todos` 改為先寫入目標 `todo.md` 與 `changelog.md`，再更新 `TODO.md` (`FR-13`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `_check_nested_depth_and_structure` 改以 `PlanStatusResolver.resolve_phase_file` 檢查 `P01`/`P07` (`FR-13`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_trace_parser.py` | Modify | 單趟串流解析同步提取首條使用者訊息 `topic` 至 `t1_stats` (`FR-14`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | `list_sessions` 直接取用 `t1.get("topic")`，免除二次開檔重讀 (`FR-14`) |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | `_normalize_bags` 支援空白分隔 `--key <val>` 選項解析 (`FR-14`) |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 新增 `type: "workflow"` 記憶體轉譯與 `cli._normalize_bags` 空白分隔參數測試 |
| `ys_codebase/source/agents-workflow/tests/test_publisher.py` | Modify | 新增遺留 `.agents/workflows/` 與 `.claude/commands/` 自動清理測試 |
| `ys_codebase/source/agents-workflow/tests/test_roadmap.py` | Modify | 新增 `promote_todos` 寫入失敗時保護來源 `TODO.md` 無損之測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `P01-05_auto.md` 結構判定與 `list_sessions` 單趟解析 `topic` 測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `SandboxProvisioner` 鎖粒度設計：由於 `sub_02` 已將 `core.uri` 覆寫改為執行緒本地儲存（TLS），`create_sandbox` 與 `cleanup_sandbox` 僅在存取 `_ACTIVE_SANDBOXES` 時持有 `_SANDBOX_LOCK`，磁碟複製、解壓、事件廣播與 `robust_rmtree` 均在鎖外執行，確保平行沙盒零阻塞。
- **[P02:DR-02]** `SessionTraceEngine.list_sessions` 單趟提取：於 `_TranscriptParseState` 新增 `topic: str = ""`，在 `_extract_step_content_and_role` 處理使用者訊息時一併擷取前 60 字元（排除 `/context-init`），將 `.jsonl` 讀取次數由 2 次降至 1 次。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/server/server/worker.py
def _dispatch_command_with_captured_streams(
    module_name: str,
    args: list,
    streamer: DebouncedIOStreamer,
    stdin_sock: Optional[socket.socket] = None,
) -> Tuple[int, Optional[str]]: ...

# ys_codebase/source/dev/dev/testing/case.py
def run_cli(
    self,
    *args: str,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess: ...

# ys_codebase/source/dev/dev/tester.py
def _execute_single_module_in_sandbox(
    self,
    mod_name: str,
    sandbox_dir: str,
    extra_env: Optional[Dict[str, str]] = None,
    specific_files: Optional[List[str]] = None,
    timeout_sec: float = 300.0,
) -> Tuple[int, List[Dict[str, Any]], float, str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `MasterHTTPHandler._handle_post_dispatch()`：當 `req_data` 非 `dict`、`module` 非非空字串或 `args` 非 `list` 時，於發送串流標頭前立即回傳 `HTTP 400` JSON 錯誤。
  - `TodoManager.promote_todos()`：若目標 `todo.md` 或 `changelog.md` 寫入拋出 `OSError`，來源 `TODO.md` 保證維持原狀不被截斷或扣除。
- **階段決策紀錄**：`[P03:DR-01]` `_execute_single_module_in_sandbox` 透過比對 `subprocess.run is _ORIG_SUBPROCESS_RUN`，在預設環境走 `run_subprocess_with_tree_timeout` 並封裝為 `subprocess.CompletedProcess`，同時保持單元測試對 `subprocess.run` 之 mock 相容性。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-14 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-03 指標約束（零非 `core` 之 `sys.path` 變動、零工單代號註解）
- **靈魂拷問與防護解法**：
  - *問：若舊版測試傳入 `projections: {"workflow": ...}` 且匯出項目 `type: "workflow"` 被 `compiler.py` 轉譯為 `"skill"`，`publisher.py` 能否找到投影規則？*
  - *解*：`publisher.py:build_deployment_map()` 在 `projections` 查無 `"skill"` 時，自動回退查詢 `projections.get("workflow") or projections.get("workflows")`，確保向後相容。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/{server,dev,agents-workflow}/README.md` | N/A | 將於主計畫 Phase 07 結案時統一對齊三層文檔 |
| **設計決策** | `docs/{server,dev,agents-workflow}/DESIGN_NOTES.md` | N/A | 已對齊既有 `[DN-AW-05]` 契約，主計畫 Phase 07 統一審校 |
| **微觀註解** | `server` / `dev` / `agents-workflow` 源碼 Docstrings | Modify | 同步更新關鍵函式契約說明（不含工單編號） |

- **決策定稿**：**[P04:DR-01]** 所有變更均在各模組既有公開契約內進行無損加固，靜態合規檢查 `dev check` 100% 通過。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 `module:server` 修復（`master.py`、`worker.py`、`service.py`）與 `tests/test_server.py` 單元測試擴充（對應 `FR-01`~`FR-06`、`EC-01`~`EC-02`）
- [x] **TASK-02**：完成 `module:dev` 修復（`sandbox.py`、`case.py`、`builder.py`、`tester.py`、`checker.py`）與 `tests/test_{sandbox,case,builder,tester,checker}.py` 單元測試擴充（對應 `FR-07`~`FR-10`、`EC-03`~`EC-04`）
- [x] **TASK-03**：完成 `module:agents-workflow` 修復（`compiler.py`、`publisher.py`、`roadmap.py`、`verifier.py`、`_trace_parser.py`、`session_trace.py`、`scripts/cli.py`）與 `tests/test_{compiler,publisher,roadmap,plans_toolchain}.py` 單元測試擴充（對應 `FR-11`~`FR-14`、`EC-05`~`EC-06`）
- [x] **TASK-04**：執行 `py_compile` 與 `python yscb.py dev check {server,dev,agents-workflow}` 靜態檢查、產出 `P06_test_plan.md` 並完成 `plan verify` 驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
