# 需求規格說明書 (Requirements Specification) — sub_03_server_dev_and_workflow

> 功能名稱：sub_03_server_dev_and_workflow  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 優先級 | 詳細規格與驗收條件 (Acceptance Criteria) |
| :---: | :--- | :---: | :--- |
| **FR-01** | **Master 握手執行緒非 JSON 雜訊容錯 (`SRV-01`)** | `P0` | **Given**: `server/master.py:_read_handshake()` 在讀取 Worker 子進程啟動期間之 `stdout` 管道。<br/>**When**: 原生 C 擴充套件或底層啟動過程在 `worker_alive` / `worker_ready` 前後於 FD 1 寫入非 JSON 雜訊行（或非 `dict` 之 JSON 值）。<br/>**Then**: 迴圈內逐行以 `try ... except ValueError: continue` 略過非 JSON 行並拒絕非 `dict` 解析結果，持續讀取後續合法的 `worker_alive` 與 `worker_ready` 封包，避免握手執行緒提前退出導致 Worker 啟動誤判死鎖。 |
| **FR-02** | **Worker 未捕獲例外串流順序與 `error` 欄位傳遞 (`SRV-02`)** | `P0` | **Given**: `server/worker.py:execute_task()` 與 `_dispatch_command_with_captured_streams()` 在 `DebouncedIOStreamer` 上下文內執行模組命令。<br/>**When**: 命令執行期間拋出未預期之 `Exception`。<br/>**Then**: 在 `with streamer:` 結束並關閉擷取器（`_is_closed = True`）之前，先將 `[Server Worker Error] <ExcType>: <msg>\n` 寫入 `stderr` 緩衝區以確保隨 `stop_capture()` 刷出；同時將錯誤訊息以 `error=err_text` 傳入 `streamer.send_task_finish(exit_code=exit_code, duration_ms=duration_ms, error=err_text)`，消除異常靜默吞沒。 |
| **FR-03** | **Worker 子進程 UTF-8 I/O 編碼強制加固 (`SRV-03`)** | `P1` | **Given**: `server/master.py:_spawn_worker_locked()` 衍生 Worker 子進程，以及 `server/worker.py:worker_main()` 初始化標準串流。<br/>**When**: 宿主系統預設 Locale 為非 UTF-8（例如 Windows `cp950` / `cp1252`）且命令或事件輸出非 ASCII 字元。<br/>**Then**: `_spawn_worker_locked()` 強制於子進程環境變數設定 `env["PYTHONIOENCODING"] = "utf-8"`；`worker_main()` 對預設標準串流（`orig_stdout`、`sys.stderr`、`sys.stdin`）具備 `reconfigure` 能力者呼叫 `reconfigure(encoding="utf-8", errors="replace")`，杜絕 `UnicodeEncodeError`。 |
| **FR-04** | **`/api/dispatch` 請求載荷前置結構驗證 (`SRV-04`)** | `P1` | **Given**: `server/master.py:_handle_post_dispatch()` 接收 HTTP `POST /api/dispatch` 請求。<br/>**When**: 請求載荷非 JSON 物件（例如陣列或純量）、缺少必填非空字串 `"module"`、或 `"args"` 非 `list`。<br/>**Then**: 在發送 `HTTP 200` 串流標頭之前完成結構校驗，若不合法立即回傳 `HTTP 400 Bad Request` 與結構化 `{"error": ...}`，防止發送 `200 OK` 後才因 `TypeError` / `KeyError` 中斷連線。 |
| **FR-05** | **Server 活躍度刷新節流與執行緒安全加固 (`SRV-05`)** | `P2` | **Given**: `server/service.py:touch_activity()` 與 `server/master.py:MasterSupervisor.touch_activity()` 在高頻背景任務下被調用。<br/>**When**: 傳入或未傳入顯式 `yscb_root` 且在 `1.0s` 節流視窗內連續呼叫 `touch_activity()`，或多執行緒併發刷新 `_last_active_time`。<br/>**Then**: `server/service.py:touch_activity()` 以執行緒鎖保護 `_LAST_TOUCH_TS`，且無論是否傳入 `yscb_root`（除非 `force=True`）均生效 `1.0s` 節流短路；`MasterSupervisor` 更新與讀取 `_last_active_time` 保持單調安全。 |
| **FR-06** | **Workspace Root 跨平台路徑正規化比對 (`SRV-06`)** | `P2` | **Given**: `server/master.py:_handle_post_dispatch()` 比對請求之 `yscb_root` 與守護進程之 `supervisor.yscb_root`。<br/>**When**: 在大小寫不敏感檔案系統（Windows）或透過符號連結 / Junction 路徑發起請求。<br/>**Then**: 統一透過 `_normalize_root_path()`（結合 `os.path.normcase(os.path.realpath(os.path.abspath(...)))`）正規化比對 `supervisor.yscb_root` 及其父目錄，消除誤報 `400 Workspace Root Mismatch`。 |
| **FR-07** | **平行沙盒建置與清理鎖粒度最佳化 (`DEV-01` 配合項)** | `P0` | **Given**: `sub_02` 已將 `core.uri` 覆寫堆疊改為 `threading.local()`，`dev/testing/sandbox.py` 支援多執行緒平行建立與銷毀測試沙盒。<br/>**When**: 多個 Worker 執行緒同時呼叫 `SandboxProvisioner.create_sandbox()` 與 `cleanup_sandbox()`。<br/>**Then**: 嚴格遵守防回歸紅線 6，`_SANDBOX_LOCK` 僅保護輕量記憶體集合（`_ACTIVE_SANDBOXES`）與目錄命名分配，**絕不**包裹耗時之檔案複製、Zip 解壓、`on_test_setup` / `on_test_teardown` 事件廣播或 `vfs.robust_rmtree()` 物理刪除，確保平行沙盒吞吐量不退化。 |
| **FR-08** | **`YSCBTestCase` 環境變數差量還原與 Builder 原子覆寫 (`DEV-03`)** | `P1` | **Given**: `dev/testing/case.py:YSCBTestCase.tearDown()` 還原測試期間異動之環境變數，以及 `dev/builder.py:Builder._create_module_archive_atomic()` 寫入目標 Zip 包。<br/>**When**: 背景執行緒正讀取 `os.environ`，或外部程序正存取目標 `.zip` 套件。<br/>**Then**: `tearDown()` 廢除 `os.environ.clear()`，改採差量比對還原（移除新增鍵、恢復修改與刪除鍵），確保 `os.environ` 永不出現瞬間清空視窗；`_create_module_archive_atomic()` 移除前置 `os.remove(target_zip_path)`，直接以 `os.replace(tmp_zip_path, target_zip_path)` 原子替換目標檔。 |
| **FR-09** | **CLI 與沙盒測試子進程樹逾時強殺防護接線 (`DEV-04`)** | `P1` | **Given**: `dev/testing/runner.py` 已定義 `run_subprocess_with_tree_timeout()`，而 `dev/testing/case.py:run_cli()` 與 `dev/tester.py:_execute_single_module_in_sandbox()` 衍生測試子進程。<br/>**When**: 被測 CLI 命令或模組沙盒測試發生無限迴圈或死鎖逾時。<br/>**Then**: `run_cli()`（新增可選 `timeout: float = 60.0` 參數）與 `_execute_single_module_in_sandbox()`（新增可選 `timeout_sec: float = 300.0` 參數）全面改接 `run_subprocess_with_tree_timeout()`，逾時自動遞迴終止整棵子進程樹並回傳相容之 `subprocess.CompletedProcess`。 |
| **FR-10** | **`dev check` 自訂規則連字號與底線模組雙向正規化 (`DEV-05`)** | `P2` | **Given**: `dev/checker.py:Checker._check_custom_rules()` 解析 `code.func://<donor>/...` 或 `<donor_pkg>.<mod>:<func>` 自訂檢查規則。<br/>**When**: 貢獻模組目錄名稱含連字號（如 `agents-workflow`）而 Python 套件名稱含底線（如 `agents_workflow`），或反之。<br/>**Then**: 解析 `module://` 實體目錄與 `priority_module` 時自動嘗試連字號與底線雙向正規化候選，載入 Python 模組時亦支援將首段套件名正規化為底線，確保自訂規則穩定載入且不污染 `sys.path`。 |
| **FR-11** | **移除 `publisher.py` 死代碼分支 (`AW-01`)** | `P2` | **Given**: `agents_workflow/publisher.py:_check_short_circuit()` 內殘留未物化之 `agent_rules` 檢查迴圈。<br/>**When**: 執行 Stage 0 指紋短路檢查。<br/>**Then**: 徹底移除 `_check_short_circuit()` 中 `t_cfg.get("agent_rules", [])` 死代碼分支，使短路檢查邏輯與實際物化管線 100% 對齊。 |
| **FR-12** | **落實 `[DN-AW-05]` 舊版 `workflow` 轉譯與遺留目錄自動清理 (`AW-02`)** | `P1` | **Given**: 知識庫 `[DN-AW-05]` 規範舊版 `type: "workflow"` 匯出宣告之無痛轉譯與遺留目錄清理契約。<br/>**When**: `ArtifactCompiler` 編譯匯出項目或解析描述，以及 `ReleasePublisher` 執行發布清理。<br/>**Then**: `compiler.py` 於記憶體中將 `type` 為 `"workflow"` / `"workflows"` 之匯出項目無痛正規化轉譯為 `"skill"`（含 `folder_map` 與 `resolve_export_description`）；`publisher.py` 在專案層級發布清理時自動偵測並物理移除遺留之 `<project_root>/.agents/workflows/` 與 `<project_root>/.claude/commands/` 目錄；全過程嚴禁任何 `sys.path` 變動。 |
| **FR-13** | **`promote_todos` 寫入順序保護與 `verifier.py` 合併檔相容 (`AW-04`)** | `P1` | **Given**: `agents_workflow/roadmap.py:TodoManager.promote_todos()` 打包提取待辦事項至新計畫目錄，以及 `agents_workflow/plans/verifier.py:_check_nested_depth_and_structure()` 檢核計畫階段檔。<br/>**When**: 目標計畫目錄寫入 `todo.md` 失敗，或受檢計畫採用 `/auto` 合併檔（如 `P01-05_auto.md`）。<br/>**Then**: `promote_todos()` 必須先成功寫入目標 `dest_todo`（`todo.md`）與 `changelog.md`，最後才更新扣除原 `self.todo_file`（`TODO.md`），杜絕寫入異常時待辦遺失；`verifier.py` 改透過 `PlanStatusResolver.resolve_phase_file(plan_dir, "P01").is_file()` 與 `resolve_phase_file(plan_dir, "P07").is_file()` 判定階段檔存在性。 |
| **FR-14** | **CLI `_normalize_bags` 空白分隔參數解析與 `list_sessions` 單次掃描 (`AW-05`、`AW-06`)** | `P1` | **Given**: `agents-workflow/scripts/cli.py:_normalize_bags()` 接收 `list`/`tuple` 形式之命令列參數，以及 `agents_workflow/plans/session_trace.py:list_sessions()` 掃描歷史對話 `.jsonl`。<br/>**When**: 傳入空白分隔之帶值選項（如 `["--scope", "dev", "--note", "fix"]`），或呼叫 `list_sessions()` 列出對話摘要。<br/>**Then**: `_normalize_bags()` 正確識別帶值選項並將後續 token 綁定為選項值（同時保持布林旗標如 `--list`、`--force`、`--json` 不誤吞位置參數）；`_trace_parser.py:parse_transcript_file()` 在單次串流掃描中同步提取首條使用者訊息作為 `t1_stats["topic"]`，使 `list_sessions()` 免除二次開檔重掃 `.jsonl`。 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 觸發情境與邊界條件 | 預期防禦行為與回退契約 |
| :---: | :--- | :--- |
| **EC-01** | **Worker 握手期間混合輸出多行非 JSON 文字與 JSON 純量 (`123`, `"str"`, `[]`)** | `_read_handshake()` 捕捉 `ValueError` 後繼續迴圈，且對 `not isinstance(data, dict)` 亦安全 `continue`，直到收到合法 `{"type": "worker_alive"}` / `{"type": "worker_ready"}` 或 EOF。 |
| **EC-02** | **HTTP `/api/dispatch` 傳入負數或非數字 `Content-Length`、空載荷或非 `dict` JSON** | `_handle_post_dispatch()` 安全捕獲解析錯誤並正規化 `content_len >= 0`，於發送 `HTTP 200` 前攔截回傳 `HTTP 400 Bad Request` 與明確錯誤原因。 |
| **EC-03** | **多執行緒併發執行 `create_sandbox()` 與 `cleanup_sandbox()`，或執行測試期間背景執行緒密集讀取 `os.environ`** | `_SANDBOX_LOCK` 不包裹磁碟 I/O 與事件廣播，平行建置無鎖競爭阻塞；`YSCBTestCase.tearDown()` 差量更新 `os.environ`，背景執行緒永不觀測到空環境變數表。 |
| **EC-04** | **`run_cli()` 或沙盒測試子進程衍生孫進程並陷入死鎖逾時** | `run_subprocess_with_tree_timeout()` 觸發逾時強殺整棵進程樹，回傳退出碼 `124` 與包含 `[TimeoutError]` 之 `stderr`，不殘留孤兒進程。 |
| **EC-05** | **`promote_todos()` 建立目標目錄或寫入 `todo.md` 遭遇 `OSError` / 權限拒絕** | 因尚未改寫來源 `TODO.md`，例外拋出或中止時來源 `TODO.md` 維持 100% 原始內容無損。 |
| **EC-06** | **`_normalize_bags()` 遇到 `--opt=val`、`--opt val`、布林旗標 `--force` 與短旗標 `-l` / `-f` 混用** | 帶值選項（`scope`、`note`、`slug`、`model`、`plan`、`status`、`add`、`remove`、`phase`、`log`、`type`、`transcript`、`since`、`limit`、`year`、`month`、`path-plans`、`path-archived`、`path-docs`）正確提取下一參數值；布林旗標設定 `params=True` 且不吞沒後續位置參數。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 維度編號 | 品質維度 | 具體指標與工程約束 |
| :---: | :--- | :--- |
| **NFR-01** | **零非 `core` 之 `sys.path` 變動** | `server`、`dev`、`agents-workflow` 所有非測試業務源碼 100% 通過 `python yscb.py dev check <mod>`（含 AST `_find_sys_path_mutations` 零豁免守門）。 |
| **NFR-02** | **零工單與審計編號註解污染** | 嚴格遵循 `CodeQualityStandards.md` §1.4，業務源碼註解與 Docstring 嚴禁出現 `SRV-XX`、`DEV-XX`、`AW-XX`、`FR-XX`、`EC-XX`、`DR-XX` 等追蹤代號。 |
| **NFR-03** | **單次 I/O 掃描與高併發效率** | `SessionTraceEngine.list_sessions()` 對每份 `.jsonl` 僅執行單次檔案讀取；`SandboxProvisioner` 在平行測試下維持無全域 I/O 鎖瓶頸。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[DN-SRV-01]` (`docs/server/DESIGN_NOTES.md`)**：Windows 與跨平台檔案鎖及管道通訊下，子進程與執行緒鎖順序必須避免死鎖，且 IPC 管道必須防禦非預期輸出與編碼差異。
- **`[DN-DEV-01]` ~ `[DN-DEV-03]` (`docs/dev/DESIGN_NOTES.md`)**：`dev check` 強制檢核模組契約與反模式；自訂規則透過 `core.platform.ensure_installed_modules_path` 載入並於 `finally` 還原 `sys.path`。
- **`[DN-AW-05]` (`docs/agents-workflow/DESIGN_NOTES.md`)**：明確規範 `compiler.py` 記憶體無痛轉譯 `type: "workflow"` 為 `"skill"`，以及 `publisher.py` 於發布清理時自動移除 `.agents/workflows/` 與 `.claude/commands/`。
