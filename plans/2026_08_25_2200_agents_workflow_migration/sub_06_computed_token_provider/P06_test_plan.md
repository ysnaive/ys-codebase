# 測試計畫書 (Phase 6: Test Plan)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 測試案例清單 (Test Cases)

| 測試編號 | 對應需求 (FR/EC) | 測試名稱與目標 | 測試步驟與預期輸出 | 測試層級 | 執行狀態 |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **ST-01** | FR-01, FR-02 | `code.func://` 正常載入測試 | 載入標準模組函式，驗證返回 Callable 並可成功執行。 | 單元測試 | `PASSED` |
| **ST-02** | EC-01 | 無效 URI 格式防禦測試 | 輸入格式缺少 `:` 或前綴錯誤，驗證拋出 `InvalidSymbolURIError`。 | 單元測試 | `PASSED` |
| **ST-03** | EC-02 | 函式不存在與非 Callable 防禦 | 指向不存在的函式或變數，驗證拋出 `SymbolNotFoundError`。 | 單元測試 | `PASSED` |
| **ST-04** | FR-03, FR-04 | Computed Token 工廠編譯測試 | 於編譯器配置 `type: "computed"`，驗證即時調用 Provider 替換 Token。 | 整合測試 | `PASSED` |
| **ST-05** | EC-03, EC-04 | Provider 例外與非字串回傳防護 | 模擬 Provider 拋出例外與回傳非字串，驗證錯誤處理與字串強制轉型。 | 整合測試 | `PASSED` |
| **ST-06** | FR-05 | `agents-workflow` 路徑地圖產出測試 | 執行編譯 `ContextInit.md`，驗證 Markdown 表格包含活躍 URI 清單。 | 端對端測試 | `PASSED` |

---

## 2. 實機執行日誌 (CLI Execution Logs)

### 2.1 全量單元與合約測試 (`python yscb.py dev test --all`)
```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: agents-workflow                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (18/18)
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (57/57)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (25/25)
----------------------------------------------------------------------
Summary : 109 Total, 109 Passed, 0 Failed, 0 Skipped (15.158s)
Status  : PASSED (100% Ready)
======================================================================
```

### 2.2 物化產物驗證 (`modules/agents-workflow/exports/workflows/ContextInit.md`)
```markdown
> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | `./ys_codebase` | `[ACTIVE]` |
> | **`plans://`** | `./plans` | `[!UNDEFINED]` |
> | **`archive://`** | `./archive` | `[!UNDEFINED]` |
> | **`docs://`** | `./docs` | `[!UNDEFINED]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb.py uri resolve <uri>`（例：`python yscb.py uri resolve project://AGENTS.md`）
```
