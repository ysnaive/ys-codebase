# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)


| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 動態模板章節標題鏡像對齊檢核 | FR-01 | `test_plan_verifier_dynamic_header_alignment` |
| **FT-02** | 單元測試 | 測試規劃與標準 ID 格式合規檢核 | FR-02 | `test_plan_verifier_id_matrix_and_test_plan` |
| **FT-03** | 單元測試 | Header 元數據與子計畫所屬主計畫校驗 | FR-03 | `test_plan_verifier_header_metadata_and_sub_plan` |
| **FT-04** | 單元測試 | 雙星伴隨與 changelog 合規檢核 | FR-04 | `test_plan_verifier_changelog_guard` |
| **FT-05** | 單元測試 | 巢狀層級與 Umbrella 主計畫結構稽核 | FR-05 | `test_plan_verifier_nested_depth_and_umbrella` |
| **FT-06** | 單元測試 | 佔位符與嚴禁殘留 HTML 註解檢核 | FR-06 | `test_plan_verifier_placeholders_and_html_comments` |
| **FT-07** | 單元測試 | 歸檔剛性守門阻斷與 `--force` 放行 | FR-07 | `test_plan_archiver_rigid_gate_and_force` |
| **ET-01** | 異常測試 | 動態模板快取目錄缺失容錯解析 | EC-01 | `test_plan_verifier_dynamic_header_alignment` |
| **ET-02** | 異常測試 | 空目錄與非 Markdown 檔案安全處置 | EC-02 | `test_plan_verifier_empty_and_non_markdown` |
| **RT-01** | 回歸測試 | 全生態系 4 大模組沙盒回歸測試 | NFR-01 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 成功驗證缺漏標題時安全回傳 FAIL 且正常時 PASS | 2026-08-28 20:21 |
| **FT-02** | `Passed` | 成功驗證缺少 FT/ET 前綴時正確識別 | 2026-08-28 20:21 |
| **FT-03** | `Passed` | 成功驗證子計畫缺少「所屬主計畫」時標記 FAIL | 2026-08-28 20:21 |
| **FT-04** | `Passed` | 成功驗證缺少 changelog.md 時標記 FAIL | 2026-08-28 20:21 |
| **FT-05** | `Passed` | 成功驗證缺少 umbrella_overview.md 時標記 FAIL | 2026-08-28 20:21 |
| **FT-06** | `Passed` | 成功驗證 HTML 註解與未替換佔位符偵測 | 2026-08-28 20:21 |
| **FT-07** | `Passed` | 成功驗證 PlanIncompleteError 阻斷與 force 覆蓋 | 2026-08-28 20:21 |
| **ET-01** | `Passed` | 成功驗證動態回退解析 | 2026-08-28 20:21 |
| **ET-02** | `Passed` | 成功驗證空目錄與非 Markdown 安全略過 | 2026-08-28 20:21 |
| **RT-01** | `Passed` | 全生態系 4 大核心模組沙盒測試 178/178 100% Passed (12.008s) | 2026-08-28 20:21 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (Noise-Free CLI 終端排版手感驗證)**：
  - 實機執行 `python yscb.py agents-workflow plan check` 與 `python yscb.py agents-workflow plan check --json`，確認 Pass 檔案自動靜音、僅展示 Fail 違規項目、排版清晰無雜訊（開發者已確認指示免測通過）。

