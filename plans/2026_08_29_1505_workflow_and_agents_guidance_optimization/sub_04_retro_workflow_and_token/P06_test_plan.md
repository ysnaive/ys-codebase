# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Retro.md` 經 `ArtifactCompiler` Stage 1 & Stage 2 編譯後無語法錯誤、動態 context 展開正常 | FR-01, FR-06 | `python yscb.py dev test agents-workflow` |
| **FT-02** | 單元測試 | 驗證 `RETRO_CHECK_ITEMS` 錨點在無 Donor 注入時自動 Purge，無殘留標籤行 | FR-03, EC-01 | `python yscb.py dev test agents-workflow` |
| **FT-03** | 單元測試 | 驗證 `RETRO_CHECK_ITEMS` 錨點在有 Donor 注入時（如模擬 knowledge-db / core 項目）能正確替換/插入內容 | FR-03, FR-04 | `python yscb.py dev test agents-workflow` |
| **FT-04** | 契約測試 | 驗證 `agents-workflow` 模組 manifest 與 contributes schema 100% 合規 | FR-05, NFR-02 | `python yscb.py dev test agents-workflow` |
| **RT-01** | 全量回歸測試 | 驗證 `agents-workflow` 全模組測試 100% Passed (100% Ready) | NFR-02 | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_sub_08_retro_workflow_export_and_token`: Stage 1 編譯成功，`Retro.md` 正確解析 | 2026-08-29 19:41 |
| **FT-02** | `Passed` | `test_sub_08_retro_workflow_export_and_token`: 未注入時 `__@{RETRO_CHECK_ITEMS}__` 標籤自動 Purge (0 殘留) | 2026-08-29 19:41 |
| **FT-03** | `Passed` | `test_sub_08_retro_workflow_export_and_token`: 模擬 Donor 注入內容正確渲染至 `Retro.md` | 2026-08-29 19:41 |
| **FT-04** | `Passed` | `BaseModuleContractTestCase`: manifest 與 contributes schema 契約測試通過 (3/3) | 2026-08-29 19:41 |
| **RT-01** | `Passed` | `agents-workflow`: 43 Total, 43 Passed, 0 Failed (100% Ready) | 2026-08-29 19:41 |

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Mode: Default (LOGIC + ENV) | Target: agents-workflow | Build: Hermetic Build
----------------------------------------------------------------------
[*] Module: agents-workflow (8.62s)                             [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (40/40)
----------------------------------------------------------------------
Summary : 43 Total, 43 Passed, 0 Failed, 0 Skipped (8.624s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：檢查編譯發布至 `.agents/workflows/Retro.md` 的 Markdown 結構是否完整、CommonMark 連結與 Frontmatter 是否完全合規。
