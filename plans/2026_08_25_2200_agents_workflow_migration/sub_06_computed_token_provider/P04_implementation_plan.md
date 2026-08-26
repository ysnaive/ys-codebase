# 實作計畫說明書 (Phase 4: Implementation Plan)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 實作任務與工作分解 (Work Breakdown Structure)

依據 [P03_api_spec.md](./P03_api_spec.md) 定義之依賴拓撲順序分解實作步驟：

### 步驟 1：實作 `core.symbols` 符號定位與加載器 (`source/core/core/symbols.py`)
- 實作 `parse_code_func_uri(uri_str)`：解析模組名、相對路徑與函式符號。
- 實作 `resolve_callable(uri_str, context=None)`：支援雙軌載入（Package Import + VFS 檔案加載），帶載入快取。
- 建立異常類別 `SymbolError`、`InvalidSymbolURIError`、`SymbolNotFoundError`。
- 在 `core/__init__.py` 導出 `symbols` 與 `resolve_callable`。
- 撰寫單元測試 `source/core/tests/test_symbols.py`。

### 步驟 2：擴充編譯器解算器支援 `type: "computed"` (`source/core/core/compiler.py` 與 `source/agents-workflow/agents_workflow/compiler.py`)
- 在 `resolve_single_artifact` 中新增 `type: "computed"` 處理分支。
- 透過 `resolve_callable` 取得函式並傳入 `CompilerContext` 執行，獲得回傳值。
- 嚴格落實型別安全轉換（`None` 轉為 `""`，其他強制轉為 `str`）。
- 依 `mode: "replace" | "append"` 替換/追加佔位符。

### 步驟 3：實作 `agents_workflow.providers` (`source/agents-workflow/agents_workflow/providers.py`)
- 實作 `get_dynamic_context_map(context)`：即時自 `uri` 獲取已啟用的語意 URI 協議與路徑，渲染為 Markdown 表格。

### 步驟 4：更新 `agents-workflow/manifest.json`
- 在 `insert` 中宣告 `DYNAMIC_CONTEXT_MAP` 的 Computed Insert，指向 `code.func://agents-workflow/providers:get_dynamic_context_map`。

### 步驟 5：端對端整合驗證與全量回歸測試
- 更新 `source/agents-workflow/tests/test_compiler.py`，新增 Computed Token 端對端解算與動態地圖產出斷言。
- 執行 Canonical Pipeline（`build` ➔ `install --force` ➔ `reload` ➔ `dev test --all`）驗證 104+ 測試無損。

---

## 2. 知識庫文檔衝擊清單 (Documentation Impact Plan)

依據 7 大抽象知識維度預排文檔交付項目：

| 判定依據 (P03/P05/P06) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: symbols.py API` | 維度 4 (介面合約) | `docs/core/API_REFERENCE.md` | 登記 `code.func://` 協議規格與 `resolve_callable` 簽名。 |
| `P02: 符號雙軌尋址架構` | 維度 3 (中觀機制) | `docs/core/symbol_resolution.md` | [NEW] 符號解析與動態模組載入之雙軌尋址專題手冊。 |
| `P01: Computed Token 宣告` | 維度 2 (配置與使用) | `docs/agents-workflow/README.md` | 說明 `DYNAMIC_CONTEXT_MAP` 動態注入機制與工作流熱啟動整合。 |

---

## 3. 架構靈魂拷問 (Stress Test & Edge Case Defense)

- **Q1 (模組相對導入相容性)**：若 Provider 函式檔案內部使用了相對導入（例如 `from .utils import helper`），透過 `spec_from_file_location` 載入時是否會引發 `relative import beyond top-level package` 錯誤？
  - **防禦設計**：在 `SymbolResolver` 中，為每個加載的模組分配獨立且正確的 package namespace（例如 `yscb_mod_{module_name}`），並在執行前將模組父目錄安全掛載至 `sys.path`，確保模組內部所有相對或絕對導入均能 100% 正常解析。

---

## 4. 依據需求 (Traceability)

- 本計畫直接落實 [P01_requirements_spec.md](./P01_requirements_spec.md)、[P02_architecture_plan.md](./P02_architecture_plan.md) 與 [P03_api_spec.md](./P03_api_spec.md)。
