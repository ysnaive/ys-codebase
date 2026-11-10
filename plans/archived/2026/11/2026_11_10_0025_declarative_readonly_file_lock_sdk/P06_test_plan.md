# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_10_0025_declarative_readonly_file_lock_sdk  
> 建立日期：2026-11-10  
> 狀態：Completed
> 模型：Gemini 3.1 Pro  

> 依據 P01-05：[P01-05_auto.md](./P01-05_auto.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SpaceRegistry` 匯聚靜態 `spaces.readonly`（`core/readonly`, `vscode-support/readonly`, `agents-workflow/readonly`）與動態 `on_register_file_spaces` Hook 至 `/readonly` 聯集空間，且 `collapse_wildcard=False` 不污染 `project://` 普通源碼檔案。 | FR-01, NFR-01 | `python3 yscb.py dev test core --no-build` |
| **FT-02** | 單元測試 | 驗證 `core.file_lock` 之 `apply_lock_bits`、`strip_lock_bits`、`is_file_readonly`、`is_protected`、`inspect_path`、`sync`、`status`、`lock_path`、`unlock_path` 在一般檔案、可執行腳本（保留 `0o555` 執行位元）、符號連結（安全跳過）與 `__pycache__/*.pyc`（排除不鎖）上之跨平台行為與零寫入短路跳過 (`already_locked_count`)。 | FR-02, EC-02, EC-04, NFR-02, NFR-03 | `python3 yscb.py dev test core --no-build` |
| **FT-03** | 整合測試 | 驗證受保護檔案上鎖後，直接使用 Python 原生 `open(path, "w")` 會被作業系統攔截並拋出 `PermissionError`；而透過 `vfs.write_text`、`vfs.write_bytes`、`vfs.atomic_write`、`vfs.robust_replace`、`vfs.copy`、`vfs.move` 與 `vfs.open(path, "w")` 寫入皆能自動解鎖覆寫並在寫後自動恢復唯讀鎖（`is_file_readonly(path) is True`）。 | FR-03, EC-01, NFR-03 | `python3 yscb.py dev test core --no-build` |
| **FT-04** | 單元測試 | 驗證 `with file_lock.writable_scope(path):` 支援巢狀重入（內部多次呼叫 `vfs.write_text` 不提前上鎖，退場時自動復鎖）與例外退場安全復鎖。 | FR-02, FR-03, EC-03 | `python3 yscb.py dev test core --no-build` |
| **FT-05** | 整合測試 | 驗證 `yscb core file-lock status --json`、`yscb core file-lock sync --json`、`yscb core file-lock unlock <path> --json` 與 `yscb core file-lock lock <path> --json` CLI 指令輸出與回傳碼。 | FR-04, NFR-01 | `python3 yscb.py dev test core --no-build` |
| **FT-06** | 跨模組整合測試 | 驗證 `vscode-support` (`_sync_all_schemas_impl`)、`agents-workflow` (`release_all`, `archive_plan`, `roadmap.sync_roadmap`)、`dev` (`builder`, `sandbox`) 與 `gdrive-support` (`transport`, `sandbox_transport`, `coordinator`) 在受保護檔案已上鎖下 100% 正常運作且無 `PermissionError`，且沙盒遠端副本與 `.conflict.*.bak` 自動剝除唯讀位元。 | FR-04, FR-05, EC-05 | `python3 yscb.py dev test --no-build` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestDeclarativeReadonlyFileLock.test_ft01_space_registry_readonly_union_and_wildcard_isolation` 100% 通過，確認 `/readonly` 聯集與萬用字元隔離正常。 | 2026-11-10 |
| **FT-02** | `Passed` | `TestDeclarativeReadonlyFileLock.test_ft02_apply_strip_lock_bits_exec_preserve_and_symlink_skip` 100% 通過，確認可執行位元保留、符號連結跳過與零寫入短路跳過 (`already_locked_count`)。 | 2026-11-10 |
| **FT-03** | `Passed` | `TestDeclarativeReadonlyFileLock.test_ft03_vfs_transparent_tunneling_and_raw_open_rejection` 100% 通過，原生 `open(..., "w")` 拋出 `PermissionError`，VFS 寫前解鎖與寫後復鎖正常。 | 2026-11-10 |
| **FT-04** | `Passed` | `TestDeclarativeReadonlyFileLock.test_ft04_writable_scope_nested_reentrancy_and_exception_recovery` 100% 通過，巢狀 `writable_scope` 與例外復鎖正常。 | 2026-11-10 |
| **FT-05** | `Passed` | `TestDeclarativeReadonlyFileLock.test_ft05_cli_file_lock_commands_json_and_human_output` 100% 通過。 | 2026-11-10 |
| **FT-06** | `Passed` | 5 模組全量測試套件（`core` 298/298、`dev` 113/113、`vscode-support` 23/23、`agents-workflow` 147/147、`gdrive-support` 37/37，共 618/618 測試）與 `dev check --all`（9/9 模組）100% 通過。 | 2026-11-10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python3 yscb.py core file-lock sync` 與 `python3 yscb.py core file-lock status`，確認 `.yscb/.modules/**`、`.vscode/schemas/**`、`.agents/**`（排除 `AGENTS.md`/`CLAUDE.md`）、`plans/**/changelog.md`、`plans/archived/**` 與 `plans/roadmap/TODO.md` 自動施加唯讀鎖，且原生覆寫被拒絕、CLI 維護指令無痛穿透。 | `[測試通過]` | 實機驗證 3692 個受保護檔案 100% 同步上鎖 (`in_sync=True`)，準備執行 P06 三輪靶向深度審計 |
