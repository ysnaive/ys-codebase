# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_core_bootstrap_and_space_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `AtomicEngine.act_reload` 自動重置 `SpaceRegistry` 單例與 `invalidate_host_caches`、`1.2.8.x.py` 清理 `file-space` 殘留，以及 `dispatcher._load_registry` 支援單檔 `contributes.json` 與 `(mtime_ns, size)` 熱更新 | FR-01 | `python3 yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_pre_1970_negative_mtime_clamping_batch_walk_session_and_128_migration` |
| **FT-02** | 單元測試 | 驗證 `AtomicEngine.act_lock`/`act_unlock` 同進程跨 `operation` 嵌套呼叫不拋出 `BlockingIOError`、`is_transaction_locked` 狀態精準、Zip Slip 攔截、`atomic_swap_directory` 失敗回滾、`_rotate_lines_file` 對 `core.log` 與 `core.jsonl` 不互相覆寫，以及 `PipManager` 離線複製宿主 `pip` (`EC-01`, `EC-02`) | FR-02, FR-03, EC-01, EC-02 | `python3 yscb.py dev test --target=core:TestCoreInstaller.test_remediated_lock_reentrancy_zip_slip_pip_fallback_and_log_rotation` |
| **FT-03** | 單元測試 | 驗證 `bind_runtime_context` 內呼叫 `uri.set_host_dir`/`host_scope`/`yscb_scope`/`module_scope` 與 `RuntimeScope` 雙向同步 (`EC-03`)、`symbols.resolve_callable` 檔案修改熱重載、`events.broadcast` 非破壞性 `sys.path` 清理與 `BaseServiceWorkerContract` 狀態機/受管執行緒 | FR-05, EC-03 | `python3 yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader.test_ft05_runtime_scope_uri_unification_cache_invalidation_and_service_contract` |
| **ET-01** | 邊界測試 | 驗證 `OSBackend._safe_copytree` 在 Linux 保留大小寫相異檔案與安全複製 Symlink，以及 `SpaceRegistry`/`SpaceScanner` 對負值 `mtime_ns` 統一夾限為 `0` 與 `batch_walk_session` 批次去重 | FR-03 | `python3 yscb.py dev test --target=core:TestVFS.test_vfs_open_boundary_guard_lf_newline_and_symlink_copy` |
| **RT-01** | 回歸與效能測試 | 驗證 `contributes._deep_merge` 大型列表 $O(N)$ 去重、`cli.py` `file_space`/`fs` 子命令轉發與 `installer.cmd_restore` 單次解壓；執行 `dev check` 與 `dev test --m core` 100% 通過 | FR-04, NFR-01, NFR-02 | `python3 yscb.py dev check && python3 yscb.py dev test --m core` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `1.2.8.x.py` 完整移除 `yscb.config.json` 與 `.modules`/`.mirror`/`.cache`/`.storage.local`/`.config.local` 下之 `file-space` 殘留；`act_reload` 同步刷新 `SpaceRegistry` 與全域快取 | 2026-11-09 |
| **FT-02** | `Passed` | `TestCoreInstaller.test_remediated_lock_reentrancy_zip_slip_pip_fallback_and_log_rotation` 通過（耗時 `0.26s`），驗證跨操作鎖重入、Zip Slip 攔截、`atomic_swap_directory` 回滾與日誌輪替副檔名隔離 | 2026-11-09 |
| **FT-03** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft05_runtime_scope_uri_unification_cache_invalidation_and_service_contract` 通過（耗時 `0.17s`），驗證 `RuntimeScope` 同步、`symbols` 世代重載與 `BaseServiceWorkerContract` | 2026-11-09 |
| **ET-01** | `Passed` | `TestVFS` 與 `TestCoreSpaceAtomicEngine` 全數通過，Epoch 前負值 `mtime_ns` 夾限為 `0` 後二次掃描 100% 命中 Stage 1 (`modified_count=0`) | 2026-11-09 |
| **RT-01** | `Passed` | `python3 yscb.py dev check` 9/9 模組 `PASSED (0 Warnings, 0 Failed)`；`python3 yscb.py dev test --m core` 共 `287 Total, 287 Passed, 0 Failed, 0 Skipped (36.980s)`，且 `SpaceScanner.scan(force=True)` 實測由 `2253.41 ms` 降至 `534.96 ms` (`-76.26%`) | 2026-11-09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python3 yscb.py dev check` 與 `python3 yscb.py dev test --m core`，確認 0 違規且全部 287 項測試 100% 通過 | `[測試通過]` | 於隔離沙盒 `/working_dir/c_3fdac06fe2853f20/track_workspaces/sub_01` 實機驗證 9/9 模組 `dev check` 通過、287/287 測試 100% 通過 |
