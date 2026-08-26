# 測試計畫書 (Phase 6: Test Plan)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 測試案例清單 (Test Cases)

| 測試編號 | 對應需求 (FR/EC) | 測試名稱與目標 | 測試步驟與預期輸出 | 測試層級 | 執行狀態 |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **ST-01** | FR-01 | 快取中繼輸出測試 | 執行 Stage 1 解算，驗證產物物化寫入 `cache.root://.../resolved_contents/` 且不再生成 `exports/`。 | 單元測試 | `PASSED` |
| **ST-02** | FR-02, EC-04 | `release_target` 與 Header 巨集插值測試 | 驗證解析 `release_target` 宣告，並測試純文字/陣列 Header 模板插值與 KeyError 容錯。 | 單元測試 | `PASSED` |
| **ST-03** | FR-03, EC-01 | `config.project.json` 與 Orphan Target 測試 | 驗證 `release_targets` 欄位讀寫，以及對未註冊 Target 標註 `[ORPHAN / NOT FOUND]`。 | 單元測試 | `PASSED` |
| **ST-04** | FR-04, EC-02 | 三層 URI 重映射與相對路徑計算測試 | 測試 Tier 1 拓撲表、Tier 2 Core 專案協議與 Tier 3 未知降級之 `os.path.relpath` 計算與 `/` 格式。 | 整合測試 | `PASSED` |
| **ST-05** | FR-05, EC-03, EC-05 | 4 步原子 `release` 交易與清理測試 | 測試過往清理、提前解算防污染、`storage://` 持久清單更新與實體目錄落地。 | 整合測試 | `PASSED` |
| **ST-06** | FR-05 | `AGENTS.md` 軟合併無損測試 | 驗證 `<!-- YSCB_AGENTS_BEGIN/END -->` 正確覆蓋且開發者自定義區域 100% 保留。 | 整合測試 | `PASSED` |
| **ST-07** | FR-06 | CLI 指令體系測試 | 執行 `release`, `release-target --list\|--add\|--remove`，驗證終端交互與自動發布觸發。 | 整合測試 | `PASSED` |
| **ST-08** | FR-07 | 核心資產端對端路徑轉譯驗證 | 執行全量發布，驗證最終 `.agents/workflows/` 中所有 `__#{uri}__` 成功替換為有效相對路徑。 | 端對端測試 | `PASSED` |

---

## 2. 實機執行日誌 (CLI Execution Logs)

### 2.1 模組專屬沙盒測試 (Sandboxed Module Test)
```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: agents-workflow                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (15/15)
----------------------------------------------------------------------
Summary : 18 Total, 18 Passed, 0 Failed, 0 Skipped (1.086s)
Status  : PASSED (100% Ready)
======================================================================
```

### 2.2 全專案全模組回歸測試 (Full System Regression)
```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: agents-workflow                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (15/15)
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (57/57)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (25/25)
----------------------------------------------------------------------
Summary : 106 Total, 106 Passed, 0 Failed, 0 Skipped (15.924s)
Status  : PASSED (100% Ready)
======================================================================
```

### 2.3 CLI 發布與目標查詢實機驗證
```text
$ python yscb.py agents-workflow release
[agents-workflow] Starting 4-step atomic release transaction...
[agents-workflow] Release completed successfully!
  • Published files: 16
  • Active targets:  antigravity

$ python yscb.py agents-workflow release-target --list
Available Release Targets (1):
--------------------------------------------------------------------------------
TARGET NAME          STATUS               DESCRIPTION
--------------------------------------------------------------------------------
antigravity          [ENABLED]            Google Antigravity IDE 原生 Slash Commands 與標準規範輸出
--------------------------------------------------------------------------------
```
