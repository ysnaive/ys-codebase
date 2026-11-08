# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_core_runtime_context_and_namespace_loader  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `RuntimeContext` 與 `bind_runtime_context` 隔離 `virtual_cwd`、`env`、`host_dir`、`yscb_dir` 與 `module_name`；驗證 4 執行緒併發下 `get_virtual_cwd()`、`get_env()`、`get_env_snapshot()`、`uri.get_module_context()`、`uri.get_host_dir()`、`uri.get_yscb_root()` 互不干擾且不污染實體 `os.environ`；驗證 `reset_runtime_context()` 原位清空快取並保持容器實例參考穩定。 | FR-01, FR-02, EC-05, NFR-03 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft01_runtime_context_isolation_and_concurrent_thread_scopes`) |
| **FT-02** | 單元測試 | 驗證 `core.loader.load_module_from_path` 受保護命名空間載入器之 `(st_mtime_ns, st_size)` 世代指紋快取命中與檔案修改後自動熱重載。 | FR-04, NFR-01 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback`) |
| **FT-03** | 靜態與結構測試 | 以 AST 掃描 `ys_codebase/source/core/` 下全部非測試 `.py` 生產檔案，斷言達成 0 `global` 敘述、0 頂層可變容器字面量賦值 (`C8`)、0 非 `frozen=True` 之 `@dataclass` (`C9`)、0 `input()` (`A2`)、0 非啟動器 `sys.exit()` (`B3`)、除 `core/context.py` 外 0 `os.getcwd()`/`Path.cwd()` (`B4`)、除 `core/loader.py` 外 0 `spec_from_file_location` (`D10`)。 | FR-02, FR-03, FR-04, NFR-02 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses`) |
| **FT-04** | 單元測試 | 驗證 `uri.reconcile_undefined_uri` 移除 `input()` 與 `sys.exit()` 並統一拋出 `UndefinedURIError`；驗證 `guard.guard_dispatch` 於未授權呼叫時透過 `get_env` 檢查並拋出 `SystemExit(126)`。 | FR-02 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft04_et03_uri_reconcile_undefined_and_guard_system_exit`) |
| **ET-01** | 邊界測試 | 驗證 `load_module_from_path` 當目標模組於 `exec_module` 期間拋出例外時，100% 原子回滾 `sys.modules` 快照（新載入失敗不殘留半初始化模組，重載失敗自動還原前一版健康模組）。 | EC-03, FR-04 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback`) |
| **ET-02** | 邊界測試 | 驗證 `load_module_from_path` 對非 `_yscb_mod_` 前綴之 `module_key` 拋出 `ValueError` 攔截。 | FR-04 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback`) |
| **ET-03** | 邊界測試 | 驗證 `uri.reconcile_undefined_uri` 於執行緒內重入解析同一語意 Token 時拋出 `CyclicURIDependencyError`。 | EC-04, FR-02 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft04_et03_uri_reconcile_undefined_and_guard_system_exit`) |
| **ET-04** | 邊界測試 | 驗證 PEP 562 模組級 `__getattr__` 與 Metaclass 屬性代理（`from core.symbols import _RESOLVED_CALLABLE_CACHE`, `uri._SCHEMES_CACHE`, `ConfigManager._cache`, `contributes._MERGED_MEMORY_CACHE`, `locale._LOCALE_FILE_CACHE`, `validator._SIGNATURE_PARSE_CACHE`, `dispatcher._MODULE_CACHE` 等）與 `RuntimeContext` 狀態槽共享同一實例。 | EC-01, FR-02 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses`) |
| **ET-05** | 邊界測試 | 驗證 `core` 全數 12 個 `@dataclass(frozen=True)`（`ExecutionContext`, `RuntimeScope`, `LogExecutionScope`, `ArgSpec`, `OptionSpec`, `CommandSpec`, `ModuleSpec`, `SpaceConfig`, `FileFingerprint`, `ScanDiffDetail`, `ScanDiffResult`, `SnapshotState`）外部屬性修改均拋出 `FrozenInstanceError`，且 `ExecutionContext(args=None)` 保持 `None` 相容。 | EC-02, FR-01, FR-03 | `python yscb.py dev test --target=core:TestCoreRuntimeContextAndLoader -q` (`test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses`) |
| **RT-01** | 回歸測試 | 執行 `module:core` 模組規範檢查與全量 281 項單元/邊界/整合回歸測試套件，驗證所有既有子系統 100% 相容無退化。 | FR-01 ~ FR-04, NFR-01 ~ NFR-03 | `python yscb.py dev check core`、`python yscb.py dev test core -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft01_runtime_context_isolation_and_concurrent_thread_scopes` 通過，4 執行緒併發隔離與 `reset_runtime_context()` 原位清空斷言正常。 | 2026-11-08 |
| **FT-02** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback` 通過，`(mtime_ns, size)` 指紋快取命中與熱重載斷言正常。 | 2026-11-08 |
| **FT-03** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses` 通過，`core` 全模組非測試 `.py` 檔 0 C8/C9/A2/B3/B4/D10 違規。 | 2026-11-08 |
| **FT-04** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft04_et03_uri_reconcile_undefined_and_guard_system_exit` 通過，`UndefinedURIError` 與 `SystemExit(126)` 斷言正常。 | 2026-11-08 |
| **ET-01** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback` 通過，`exec_module` 異常時 `sys.modules` 原子回滾正常。 | 2026-11-08 |
| **ET-02** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback` 通過，非 `_yscb_mod_` 前綴拋出 `ValueError`。 | 2026-11-08 |
| **ET-03** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft04_et03_uri_reconcile_undefined_and_guard_system_exit` 通過，重入 Token 拋出 `CyclicURIDependencyError`。 | 2026-11-08 |
| **ET-04** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses` 通過，PEP 562 屬性代理與 `from core.symbols import _RESOLVED_CALLABLE_CACHE` 相容斷言正常。 | 2026-11-08 |
| **ET-05** | `Passed` | `TestCoreRuntimeContextAndLoader.test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses` 通過，12 個 `@dataclass(frozen=True)` 均拋出 `FrozenInstanceError`。 | 2026-11-08 |
| **RT-01** | `Passed` | `dev check core` (PASSED)、`dev test core -q --sync` (Pass: 281, Fail: 0, Skip: 1) 全數通過並同步安裝 `core@1.2.7.build`。 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於本機已同步 `core@build` 環境執行 CLI 指令（如 `python yscb.py uri list`、`python yscb.py config list --mod=core`、`python yscb.py fs status`），確認 `RuntimeContext` 與 `core.loader` 切換後命令派發與輸出正常無異常。 | `[測試通過]` | 2026-11-08 本機 `core@1.2.7.build` 實機調用驗收通過 |
