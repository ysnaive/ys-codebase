# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 測試策略與驗證維度 (Test Strategy)

- **單元測試**：使用 `YSCBTestCase` 針對 `dev.checker.Checker` 的 5 步檢核流水線逐項驗證。
- **守門阻斷測試**：驗證 `dev.releaser.Releaser` 在遭遇 `[FAIL]` 時是否能剛性阻斷發布並回傳錯誤。
- **沙盒回歸測試**：對全生態系 4 大核心模組執行 `python yscb.py dev test --all`，維持 100% Passed。

---

## 2. 測試案例清單 (Test Cases)

| 測試 ID | 測試類型 | 驗證目標 | 預期行為 | 實機測試狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 功能測試 | Manifest 欄位與 Core 依賴校驗 | 缺少 `dependencies: ["core"]` 或版本非 SemVer 時標記 `[FAIL]` | `Passed` |
| **FT-02** | 功能測試 | Core 注入完備性檢核 | 缺少 `contributes/core.json` 或缺少 `commands` 宣告時標記 `[WARN]` | `Passed` |
| **FT-03** | 功能測試 | 空間穿透防禦檢測 | 非 `dev` 模組出現 `module.source://` 或 `source/` 探測時標記 `[FAIL]` | `Passed` |
| **FT-04** | 功能測試 | 檔案結構與模板散落檢測 | 缺少 `scripts/cli.py` 或根目錄散落 `config.*.json` 時標記 `[FAIL]` | `Passed` |
| **FT-05** | 功能測試 | 文檔合規提示檢核 | 缺少 `contributes.format.md` 時標記 `[WARN]` | `Passed` |
| **FT-06** | 功能測試 | 反模式靜態靶向攔截 | 業務代碼中出現 `"config.project.json"` 或 `"contributes.merged.json"` 標記 `[FAIL]` | `Passed` |
| **FT-07** | 功能測試 | Release 剛性阻斷與 Build 容錯 | 存在 `[FAIL]` 時 `dev release` 阻斷中斷，但 `dev build` 正常完成 | `Passed` |
| **ET-01** | 異常測試 | Python AST 語法錯誤隔離 | 遇到 SyntaxError 檔案時安全標記 `[FAIL]`，不導致程序崩潰 | `Passed` |
| **ET-02** | 異常測試 | Core 模組與測試目錄豁免 | `source/core/` 與 `tests/` 目錄不誤報反模式 | `Passed` |
| **RT-01** | 回歸測試 | 全模組沙盒回歸跑測 | 4 大核心模組單元測試 100% 通過 (178/178 Passed) | `Passed` |

---

## 3. 測試執行紀錄 (Execution Log)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Mode: Default (LOGIC + ENV) | Target: All | Build: Hermetic Build
----------------------------------------------------------------------
[*] Module: agents-workflow (19.60s)                            [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (29/29)
[*] Module: core (2.30s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (54/54)
[*] Module: dev (13.45s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (46/46)
[*] Module: knowledge-db (20.33s)                               [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (37/37)
----------------------------------------------------------------------
Summary : 178 Total, 178 Passed, 0 Failed, 0 Skipped (21.623s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI 彩色診斷輸出與 --json 格式手感驗證)**：
  - 實機執行 `python yscb.py dev check --all` 與 `python yscb.py dev check --all --json`，確認終端排版清晰、分級顏色分明、無歧異（開發者已實機確認通過）。


