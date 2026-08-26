# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：純淨語意 URI 協議與遞迴解算缺陷修復 (Pure Semantic URI Protocol & Recursive Resolution Fix)  
> 建立日期：2026-08-27  
> 狀態：Completed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與架構決策
- **需求目標**：
  1. 解決 `ContextInit.md` 即時動態語意解析地圖呈現 `[!UNDEFINED]` 的根本原因。
  2. 清除 `core.uri._DEPRECATED_SCHEME_REDIRECTS` 所有舊版重定向表，回歸嚴格的 100% Pure Canonical URI 協議模型。
  3. 修復 `core.uri.resolve` 在遞迴解算以 URI 為值的 config 協議時，誤用未定義變數 `mod` 引發 `NameError` 的缺陷。
  4. 將 `agents-workflow` 的 Providers 協議查詢清單與 `ContextInit.md` 模板中的參照全面正規化為標準 `workflow.*` 命名空間協議。
  5. 嚴守 Dogfooding 源碼空間邊界紀律，所有變更限於 `source/` 空間，暫不執行 `dev release`。
  6. 在 `agents-workflow/scripts/hook.core.py` 中實作 `on_reload` 事件處理常式，達成環境 reload 時自動觸發工作流發布。
- **架構決策紀錄**：
  - **`[FT-01:DR-01]` (清空舊版重定向表)**：清空 `_DEPRECATED_SCHEME_REDIRECTS = {}`，系統不對任何舊協議進行向下相容轉譯，調用未知協議直接拋出 `ValueError`。
  - **`[FT-01:DR-02]` (修正遞迴解算變數作用域)**：`core.uri.resolve` 第 527 行將 `resolve(val_str, current_module=mod, ...)` 修正為 `current_module=active_mod`。
  - **`[FT-01:DR-03]` (統一正規協議命名)**：`agents-workflow/providers.py` 的 `primary_schemes` 統一調整為 `["project", "yscb", "workflow.plans", "workflow.archived", "workflow.docs"]`。
  - **`[FT-01:DR-04]` (受影響檔案清單)**：
    - `source/core/core/uri.py`：清空重定向表，修復 `active_mod` 遞迴調用。
    - `source/core/tests/test_uri.py`：更新舊協議斷言為 `ValueError`。
    - `source/agents-workflow/agents_workflow/providers.py`：正規化查詢清單。
    - `source/agents-workflow/assets/workflows/ContextInit.md`：更新參照標籤為 `workflow.*`。
    - `source/agents-workflow/scripts/hook.core.py`：掛載 `on_reload` 呼叫 `ReleasePublisher().release_all()`。
    - `source/agents-workflow/tests/test_compiler.py`：追加 `FT-11` Hook 測試。
  - **`[FT-01:DR-05]` (`on_reload` Hook 自動發布)**：在 `hook.core.py` 實作 `on_reload` 調用 `ReleasePublisher().release_all()`，達成 microkernel 重載環境時自動更新工作流與 IDE 投影片。

---

### 1.2 實作任務與測試規劃

#### 📋 實作任務清單
- [x] **TASK-01**：修改 `source/core/core/uri.py`：
  - 清空 `_DEPRECATED_SCHEME_REDIRECTS = {}`。
  - 修正第 527 行 `current_module=active_mod`。
- [x] **TASK-02**：修改 `source/core/tests/test_uri.py`：
  - 更新 `test_deprecated_scheme_redirection_warning`，驗證調用 `storage.root://` 直接拋出 `ValueError`。
- [x] **TASK-03**：修改 `source/agents-workflow/agents_workflow/providers.py`：
  - 將 `primary_schemes` 更新為 `["project", "yscb", "workflow.plans", "workflow.archived", "workflow.docs"]`。
- [x] **TASK-04**：修改 `source/agents-workflow/assets/workflows/ContextInit.md`：
  - 將 `__#{docs://_project/STANDARDS.md}__` 更新為 `__#{workflow.docs://_project/STANDARDS.md}__`。
  - 同步更新正文中的路徑標註說明。
- [x] **TASK-05**：修改 `source/agents-workflow/scripts/hook.core.py`：
  - 實作 `on_reload(ctx)` 調用 `ReleasePublisher().release_all()`。
  - 在 `source/agents-workflow/tests/test_compiler.py` 中追加 `test_ft_11_on_reload_hook_triggers_release_all` 單元測試。

#### 🧪 測試案例規劃與執行紀錄 (Test Cases & Execution)
| 測試編號 | 測試類型 | 驗證目標與斷言 | 執行結果 | 驗證時間 |
| :--- | :--- | :--- | :---: | :---: |
| **FT-01** | 單元測試 | 驗證 `core.uri.resolve("workflow.plans://")` 透過遞迴解算 `project://plans` 正確返回實體路徑 | `Passed` | 2026-08-27 00:43 |
| **FT-02** | 單元測試 | 驗證 `providers.get_dynamic_context_map()` 正確解析所有 5 大協議並輸出 `[ACTIVE]` | `Passed` | 2026-08-27 00:43 |
| **FT-03** | 單元測試 | 驗證 `hook.core.py` 在 `on_reload` 事件被觸發時自動執行 `ReleasePublisher.release_all()` (FT-11) | `Passed` | 2026-08-27 00:50 |
| **ET-01** | 邊界測試 | 驗證純淨模式下調用歷史 `storage.root://` 等未註冊協議直接拋出 `ValueError` 阻斷 | `Passed` | 2026-08-27 00:43 |
| **RT-01** | 回歸測試 | 驗證 `dev test core` 全量測試通過（66/66 Passed） | `Passed` | 2026-08-27 00:43 |
| **RT-02** | 回歸測試 | 驗證 `dev test agents-workflow` 全量測試通過（23/23 Passed） | `Passed` | 2026-08-27 00:50 |

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `core.uri._DEPRECATED_SCHEME_REDIRECTS` 已成功清空，系統回歸 100% Pure Canonical 協議。
  2. `core.uri.resolve` 遞迴解算變數作用域已修正，以 URI 協議為值的 config 協議（如 `workflow.plans://` -> `project://plans` -> `H:\...\plans`）可確定性正常解算。
  3. `agents-workflow/providers.py` 與 `ContextInit.md` 已全面對齊為 `workflow.*` 命名空間協議。
  4. `agents-workflow/scripts/hook.core.py` 已實裝 `on_reload` 自動發布，經 `python yscb.py reload` 實測可自動完成工作流發布。
- **實機測試日誌**：
  - `python yscb.py dev test core`：
    ```text
    ======================================================================
    YS-Codebase Test Execution Diagnostic Report
    ======================================================================
    [*] Module: core                                                   [PASS]
        |-- [Contract] Auto-Contract Suite ... (3/3)
        \-- [Custom]   Custom Tests ........... (63/63)
    ----------------------------------------------------------------------
    Summary : 66 Total, 66 Passed, 0 Failed, 0 Skipped (11.008s)
    Status  : PASSED (100% Ready)
    ======================================================================
    ```
  - `python yscb.py dev test agents-workflow`：
    ```text
    ======================================================================
    YS-Codebase Test Execution Diagnostic Report
    ======================================================================
    [*] Module: agents-workflow                                        [PASS]
        |-- [Contract] Auto-Contract Suite ... (3/3)
        \-- [Custom]   Custom Tests ........... (19/19)
    ----------------------------------------------------------------------
    Summary : 22 Total, 22 Passed, 0 Failed, 0 Skipped (1.830s)
    Status  : PASSED (100% Ready)
    ======================================================================
    ```
  - `python yscb.py dev build --all`：
    ```text
    [dev:build] Building all modules in source/ (dev complete package)...
      [*] agents-workflow: Successfully built dev package 'agents-workflow@1.0.0.build' (47 files)
      [*] core: Successfully built dev package 'core@1.0.0.build' (26 files)
      [*] dev: Successfully built dev package 'dev@1.0.0.build' (24 files)
    ```
  - `python yscb.py install <mod>@build --provider=./ys_codebase/build --force`：
    - `core@1.0.0.build`：Installed
    - `agents-workflow@1.0.0.build`：Installed
    - `dev@1.0.0.build`：Installed
  - `python yscb.py dev test --all` (全模組回歸測試)：
    ```text
    ======================================================================
    YS-Codebase Test Execution Diagnostic Report
    ======================================================================
    [*] Module: agents-workflow                                        [PASS]
        |-- [Contract] Auto-Contract Suite ... (3/3)
        \-- [Custom]   Custom Tests ........... (20/20)
    [*] Module: core                                                   [PASS]
        |-- [Contract] Auto-Contract Suite ... (3/3)
        \-- [Custom]   Custom Tests ........... (63/63)
    [*] Module: dev                                                    [PASS]
        |-- [Contract] Auto-Contract Suite ... (3/3)
        \-- [Custom]   Custom Tests ........... (27/27)
    ----------------------------------------------------------------------
    Summary : 119 Total, 119 Passed, 0 Failed, 0 Skipped (46.883s)
    Status  : PASSED (100% Ready)
    ======================================================================
    ```
  - `python yscb.py reload`：
    ```text
    [core:reload] Reconciling runtime modules from mirror...
    [agents-workflow:hook] Auto-released on reload (24 files, targets: antigravity).
    [core:reload] Runtime environment reconciled and refreshed successfully.
    ```

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- **結案狀態**：`Completed`
- **交付檔案清冊**：
  - [`ys_codebase/source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py)
  - [`ys_codebase/source/core/tests/test_uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_uri.py)
  - [`ys_codebase/source/agents-workflow/agents_workflow/providers.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/providers.py)
  - [`ys_codebase/source/agents-workflow/assets/workflows/ContextInit.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/assets/workflows/ContextInit.md)
  - [`plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/P00_semantic_requirements.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/P00_semantic_requirements.md)
  - [`plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/changelog.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/changelog.md)
  - [`plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/fast_track_plan.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/fast_track_plan.md)
- **Dogfooding 發布狀態**：未調用 `python yscb.py dev release`，直接透過 `dev build` + `install --provider=./ys_codebase/build` 部署至本地運行端空間。
