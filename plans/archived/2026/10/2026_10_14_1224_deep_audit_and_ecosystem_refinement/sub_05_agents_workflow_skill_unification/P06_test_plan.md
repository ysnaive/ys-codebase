# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_agents_workflow_skill_unification  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_format.json` 與編譯器支援純 Skill 類型與相容轉譯 | FR-01 | `python yscb.py dev test agents-workflow -k test_compiler` |
| **FT-02** | 單元測試 | 驗證 8 大工作流作為 Skill 正常編譯與物化至 `.agents/skills/<name>/` | FR-02, FR-03 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-03** | 單元測試 | 驗證專案級 `bump-revision` 正常物化至 `.agents/skills/bump-revision/` | FR-04 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-04** | 整合測試 | 驗證發布交易自動清理專案中舊 `.agents/workflows/` 目錄 | FR-05 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **RT-01** | 全量回歸 | 驗證 `agents-workflow` 模組全量單元測試 100% 通過 | NFR-02 | `python yscb.py dev test agents-workflow` |
| **RT-02** | 生態系回歸 | 驗證全生態系 550 項單元測試 100% 通過 | NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** ~ **FT-04** | `Passed` | 單元與整合測試通過（編譯器相容轉譯、8 大工作流遷移為 Skill、專案級 bump-revision 遷移、舊 workflows 目錄自動清理） | 2026-10-14 14:14 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow`：79/79 通過 (100.0%) | 2026-10-14 14:15 |
| **RT-02** | `Passed` | `python yscb.py dev test --all --quiet`：Pass: 550(100.0%), Fail: 0, Skip: 0 | 2026-10-14 14:16 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py agents-workflow list`，確認所有工作流均呈現為 `skill` 類型且無 `workflow` | `[測試通過]` | 實機驗證通過：目錄純化為 standard, template, skill 三大類型 |
| **UX-02** | 檢查專案根目錄 `.agents/`，確認不存在 `workflows/` 目錄，所有技能均位於 `skills/` 下 | `[測試通過]` | 實機驗證通過：`.agents/workflows/` 已被 publisher 徹底自動清理刪除 |

