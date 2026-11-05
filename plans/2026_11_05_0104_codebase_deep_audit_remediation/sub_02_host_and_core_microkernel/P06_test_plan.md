# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_host_and_core_microkernel  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core/uri.py` 多執行緒 `host_scope` / `module_scope` TLS 隔離，以及 `uri.resolve` 對子路徑 `..` 逃逸與磁碟機重置拋出 `PermissionError` 且不誤傷 `project://` (`sval="yscb://.."`) | FR-01, EC-01, NFR-02 | `test_uri.py::TestURISchemes::test_thread_local_scope_isolation_and_subpath_traversal_guard` |
| **FT-02** | 單元測試 | 驗證 `VFS.open()` 執行 `assert_safe_path` 邊界攔截與寫入預設 `newline="\n"`，以及 `OSBackend.copy` 安全複製符號連結而不展開目標目錄 | FR-01, NFR-01 | `test_vfs.py::TestVFS::test_vfs_open_boundary_guard_lf_newline_and_symlink_copy` |
| **FT-03** | 單元測試 | 驗證 `OptionResolver` 支援負數參數、`dispatcher._hot_dispatch_attempt` 對 `ConnectionResetError` / `BrokenPipeError` 判為 `accepted=True`，以及 `_strict_hot_dispatch_or_block` 重試行為 | FR-02, FR-03, EC-02 | `test_core_commands.py::TestCoreCommands::test_negative_number_arguments_and_proxy_bypass` |
| **FT-04** | 單元測試 | 驗證 `process.is_process_alive` 於無 `/proc` 環境透過 `ps -o stat=` 識別 Zombie 進程為 `False`，以及 `daemon_probe` 跨進程鎖保護 | FR-02 | `test_platform.py::TestPlatform::test_posix_zombie_detection_without_procfs` |
| **FT-05** | 單元測試 | 驗證 `Installer._restore_module_package` 先複製壓縮包至 `.mirror` 再驗 SHA-256、以及 `AtomicEngine.act_snapshot` 清理同名舊快照與 `act_lock` 同操作名重入 | FR-03, EC-03, EC-04 | `test_installer.py::TestInstaller::test_rollback_mtime_sorting_and_restore_mirror_before_sha256`、`test_engine.py::TestAtomicEngine::test_snapshot_collision_cleanup_and_lock_reentrancy` |
| **FT-06** | 單元測試 | 驗證 `ConfigManager`、`locale._MODULE_BASE_DIR_CACHE`、`symbols._RESOLVED_CALLABLE_CACHE` 以 `yscb_root` 隔離快取，`cli._parse_cli_scalar_or_json` 解析帶號整數/浮點數，`validator.py` 略過 `dict` 之 `__*__` 鍵，以及 `contributes.py` / `update_checker.py` 對齊 `yscb.host://` | FR-01, FR-03 | `test_config.py`、`test_locale.py`、`test_symbols.py`、`test_validator.py`、`test_contributes.py`、`test_update_checker.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **STATIC-01** | `Passed` | `python -m py_compile` 全部 29 個修改之源碼與測試檔案 100% 編譯通過；`python yscb.py dev check core` 輸出 `Status : PASSED`（零合規違規）。 | 2026-11-05 |
| **FT-01 ~ FT-06** | `Passed` | `dev test core -q --sync` 沙盒測試 100% 通過 (Pass: 256, Fail: 0, Skip: 0)，已同步 `core@1.2.7.build`。 | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 主代理於 4 個子計畫完成後統一執行全倉沙盒測試回歸（`python yscb.py dev test core`） | `[測試通過]` | 開發者確認推進統一沙盒測試驗收，`core` (256/256) 100% 通過並同步 `@build` |
