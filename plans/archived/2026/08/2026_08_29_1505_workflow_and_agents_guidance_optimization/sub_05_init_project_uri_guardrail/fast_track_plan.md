# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：agents-workflow init 前置驗證 project:// 防呆機制  
> 建立日期：2026-08-29  
> 所屬主計畫：workflow_and_agents_guidance_optimization  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  - `FR-01`：`agents-workflow` 的一鍵初始化流程（`WorkflowInitializer.run_init_default`）於執行路徑探測與建立前，必須顯式驗證依賴協議 `project://` 是否已定義（`core.project_root` 非空且非 `!undefined`）。
  - `EC-01`：若 `project://` 未定義或解析失敗（例：拋出 `UndefinedURIError` 或回傳為空），立即終止初始化流程，輸出鮮明警示訊息，並提供建議修復指令（如 `python yscb.py config set core project_root <path>`）。
  - `[FT:DR-01]`：徹底重構 `WorkflowInitializer._resolve_physical_path`，嚴格落實《`project://` 零 Fallback 鐵律》，移除對 `os.getcwd()` 的隱式退化處理。
- **影響範圍**：
  - `source/agents-workflow/agents_workflow/initializer.py`
  - `source/agents-workflow/tests/test_initializer.py`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：重構 `WorkflowInitializer` 加入 `project://` 依賴驗證與防呆警示引導，移除 `_resolve_physical_path` 中的隱式 Fallback。
- [x] **TASK-02**：於 `test_initializer.py` 新增單元測試案例，驗證 `project://` 未定義時的阻斷與提示訊息行為。
- **測試案例**：
  - `FT-01`：當 `project://` 已正確配置時，`run_init_default` 正常探測並完成初始化。
  - `ET-01`：當 `project://` 未配置或為 `!undefined` 時，`run_init_default` 立即攔截阻斷，回傳失敗並輸出警示與建議指令。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. 於 `source/agents-workflow/agents_workflow/initializer.py` 實作 `check_project_protocol()`，透過 `core.uri.resolve("project://", interactive=False)` 驗證專案根目錄是否已定義。
  2. 於 `run_init_default()` 入口加入前置守門，未定義時輸出醒目警示方塊與修復指令指引，並安全返回 `success=False`。
  3. 清除 `_resolve_physical_path()` 中對 `os.getcwd()` 的隱式退化處理，解析失敗時返回空字串。
  4. 於 `source/agents-workflow/tests/test_initializer.py` 新增 `test_ft_05_check_project_protocol_valid` 與 `test_et_02_project_protocol_undefined_guardrail` 測試案例。
- **實機測試日誌**：
  - 執行 `python yscb.py dev test agents-workflow`：43/43 測試 100% Passed (8.90s)。
  - 執行 `python yscb.py dev test --all`：全生態系 4 大模組 211/211 測試 100% Passed (13.51s)。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_1505_workflow_and_agents_guidance_optimization` 驗證 100% Passed。
- **結案狀態**：`Completed`
