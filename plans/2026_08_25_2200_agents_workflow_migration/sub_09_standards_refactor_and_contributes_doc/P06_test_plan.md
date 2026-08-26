# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `compile_stage1()` 能成功解算 `AgentsStandards.md` 與 `DevelopmentStandards.md` 雙資產 | FR-01, FR-03 | `python yscb.py dev test agents-workflow -k test_compile` |
| **FT-02** | 單元測試 | 驗證 `ReleasePublisher._soft_merge_agents_md()` 僅提取 `AgentsStandards.md` 內容軟合併至 `AGENTS.md` | FR-02 | `python yscb.py dev test agents-workflow -k test_publisher_soft_merge` |
| **FT-03** | 單元測試 | 驗證 `enable_agents_md: false` 時發布完全跳過 `AGENTS.md` 軟合併 | FR-04, EC-03 | `python yscb.py dev test agents-workflow -k test_publisher_disable_agents_md` |
| **FT-04** | 單元測試 | 驗證 `release_targets: []` 時執行 `release_all()` 不拋錯並安全完成 | FR-05, EC-02 | `python yscb.py dev test agents-workflow -k test_publisher_empty_targets` |
| **FT-05** | 靜態稽核 | 驗證 `contributes.format.md` 存在且包含所有擴充點宣告說明 | FR-06 | 檔案存在性與內容檢查 |
| **ET-01** | 邊界測試 | 驗證既有包含舊版整份規範的 `AGENTS.md` 被精確替換為極簡版且自定義特化章節無損 | EC-01 | `python yscb.py dev test agents-workflow -k test_agents_md_replacement` |
| **RT-01** | 回歸測試 | 全模組沙盒端到端測試 100% 通過（113/113 Passed） | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `compile_stage1()` 成功物化 24 項資產，包含 `AgentsStandards.md` 與 `DevelopmentStandards.md` 雙標準 | 2026-08-26 22:37 |
| **FT-02** | `Passed` | `_soft_merge_agents_md()` 正則替換成功，僅提取 `AgentsStandards.md` 內文注入至標籤內部 | 2026-08-26 22:37 |
| **FT-03** | `Passed` | `enable_agents_md: false` 時 `release_all()` 完全跳過 `AGENTS.md` 軟合併 | 2026-08-26 22:37 |
| **FT-04** | `Passed` | `release_targets: []` 時 `release_all()` 不拋出異常，安全完成並回傳 `published_count: 0` | 2026-08-26 22:37 |
| **FT-05** | `Passed` | 靜態稽核 `contributes.format.md` 完整定義 `export`, `token`, `insert`, `release_target` 與 `uri_schemes` | 2026-08-26 22:36 |
| **ET-01** | `Passed` | 邊界測試通過：包含舊版全文之 `AGENTS.md` 成功被置換為極簡版，外部 `## 4. Custom` 100% 保留 | 2026-08-26 22:37 |
| **RT-01** | `Passed` | 全模組沙盒端到端測試 100% Passed (114/114 Passed, 47.081s) | 2026-08-26 22:38 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：檢查專案根目錄 `AGENTS.md` 軟合併後的排版與字數，確認僅包含核心防呆紀律，專案特化規則未被覆蓋。
- [ ] **UX-02**：檢查 `source/agents-workflow/contributes.format.md` 閱讀體驗清晰易懂。
