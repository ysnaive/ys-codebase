# 測試計畫與驗證報告 (Test Plan & Verification) — sub_03_server_dev_and_workflow

> 功能名稱：sub_03_server_dev_and_workflow  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `MasterSupervisor._read_handshake()` 忽略非 JSON 雜訊行與非 `dict` JSON，且 `_spawn_worker_locked()` 自動注入 `PYTHONIOENCODING=utf-8` | FR-01, FR-03, EC-01 | `test_server.py:TestServerLifecycle.test_handshake_ignores_non_json_noise_and_sets_utf8_env` |
| **FT-02** | 單元測試 | 驗證 `_dispatch_command_with_captured_streams()` 於 `with streamer:` 內捕獲未預期例外、寫入 `stderr` 緩衝區，並透過 `send_task_finish(..., error=err_text)` 傳遞錯誤原因 | FR-02 | `test_server.py:TestServerLifecycle.test_worker_unhandled_exception_streams_stderr_and_finish_error` |
| **FT-03** | 單元測試 | 驗證 `_handle_post_dispatch()` 前置攔截無效 JSON 結構（回傳 HTTP 400）、`_normalize_root_path()` 路徑正規化，以及 `service.touch_activity()` 執行緒安全節流 | FR-04, FR-05, FR-06, EC-02 | `test_server.py:TestServerLifecycle.test_dispatch_payload_validation_root_normalization_and_touch_throttling` |
| **FT-04** | 單元測試 | 驗證 `SandboxProvisioner.cleanup_sandbox()` 在呼叫 `on_test_teardown` 廣播與 `vfs.robust_rmtree()` 時已釋放 `_SANDBOX_LOCK`，不阻塞平行沙盒 | FR-07, EC-03, NFR-03 | `test_sandbox.py:TestSandboxProvisioner.test_cleanup_sandbox_releases_lock_before_teardown_and_rmtree` |
| **FT-05** | 單元測試 | 驗證 `YSCBTestCase.tearDown()` 差量還原 `os.environ`（不呼叫 `clear()`），且 `run_cli()` 串接 `run_subprocess_with_tree_timeout` | FR-08, FR-09, EC-03, EC-04 | `test_case.py:TestYSCBTestCaseContract.test_incremental_env_restore_and_run_cli_tree_timeout` |
| **FT-06** | 單元測試 | 驗證 `Builder._create_module_archive_atomic()` 直接以 `os.replace` 原子覆寫目標 Zip，不預先刪除舊檔；`Tester._execute_single_module_in_sandbox()` 串接進程樹逾時保護 | FR-08, FR-09, EC-04 | `test_builder.py:TestBuilder.test_atomic_archive_replaces_existing_without_pre_remove`、`test_tester.py:TestTester.test_execute_single_module_in_sandbox_uses_tree_timeout` |
| **FT-07** | 單元測試 | 驗證 `Checker._check_custom_rules()` 支援連字號與底線模組名稱雙向正規化解析，且靜態合規檢查確保非 `core` 零 `sys.path` 變動與零工單註解污染 | FR-10, NFR-01, NFR-02 | `test_checker.py:TestChecker.test_custom_rule_hyphenated_donor_module_normalization`、`python yscb.py dev check {server,dev,agents-workflow}` |
| **FT-08** | 單元測試 | 驗證 `ArtifactCompiler` 將舊版 `type: "workflow"` 無痛轉譯為 `"skill"`，且 `ReleasePublisher._prune_orphaned_managed_files()` 自動清理遺留 `.agents/workflows/` 與 `.claude/commands/` | FR-11, FR-12 | `test_compiler.py:TestArtifactCompiler.test_legacy_workflow_export_translation_and_cli_normalize_bags`、`test_publisher.py:TestReleasePublisher.test_prune_removes_legacy_workflows_and_commands_dirs` |
| **FT-09** | 單元測試 | 驗證 `TodoManager.promote_todos()` 在目標 `todo.md` 寫入失敗時保持來源 `TODO.md` 100% 無損，以及 `PlanVerifier` 對 `P01-05_auto.md` 合併檔之結構識別 | FR-13, EC-05 | `test_roadmap.py:TestRoadmapAndTodo.test_roadmap_promote_consume_and_model_no_backfill`、`test_plans_toolchain.py:TestPlansStatusAndBoundaries.test_audit_remediation_regressions` |
| **FT-10** | 單元測試 | 驗證 `cli._normalize_bags()` 支援空白分隔 `--key <val>` 選項解析，且 `SessionTraceEngine.list_sessions()` 透過單趟 `parse_transcript_file()` 提取 `topic` | FR-14, EC-06, NFR-03 | `test_compiler.py:TestArtifactCompiler.test_legacy_workflow_export_translation_and_cli_normalize_bags`、`test_plans_toolchain.py:TestPlansStatusAndBoundaries.test_audit_remediation_regressions` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **STATIC-01** | `Passed` | `python -m py_compile` 涵蓋 `server`、`dev`、`agents-workflow` 全部 25 個修改之源碼與測試檔 100% 通過 (`PY_COMPILE_OK`) | 2026-11-05 |
| **STATIC-02** | `Passed` | `python yscb.py dev check server`、`python yscb.py dev check dev`、`python yscb.py dev check agents-workflow` 三模組靜態合規檢查（含非 `core` 零 `sys.path` 變動 AST 守門）100% `[PASS]` | 2026-11-05 |
| **FT-01 ~ FT-10** | `Passed` | 沙盒動態測試 100% 通過：`server` (Pass: 59, Fail: 0)、`dev` (Pass: 91, Fail: 0)、`agents-workflow` (Pass: 144, Fail: 0)，均已同步安裝 `@build` | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 主代理於 4 個子計畫完成後統一執行全量模組沙盒測試 (`python yscb.py dev test`) 並確認 `server`、`dev`、`agents-workflow` 全數通過 | `[測試通過]` | 開發者確認推進統一沙盒測試驗收，`server` (59/59)、`dev` (91/91)、`agents-workflow` (144/144) 100% 通過並同步 `@build` |
