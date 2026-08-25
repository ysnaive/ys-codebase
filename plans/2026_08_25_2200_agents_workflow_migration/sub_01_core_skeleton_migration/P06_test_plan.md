# 測試與驗證計畫 (Test Plan & Verification)

> 功能名稱：agents-workflow 核心骨架與 SOP 本體遷移 (Core Skeleton & SOP Body Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：`Passed` (Phase 6 驗證通過)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 16 項自導出資產 (`export`) 與 `token` 宣告能被微內核正確解析收集 | FR-01, FR-02 | `agents-workflow/tests/test_compiler.py` |
| **FT-02** | 單元測試 | 驗證工廠編譯器 `ArtifactCompiler` 執行多輪遞迴狀態機解算，精準完成 `PHASEXX_STANDARD_HEADER` replace 自注入 | FR-03, FR-07 | `agents-workflow/tests/test_compiler.py` |
| **FT-03** | 單元測試 | 驗證多模組以 `mode: "below"` / `"above"` 向同一 Token 連續追加注入與 Step 3 乾淨移除錨點標籤 | FR-03 | `agents-workflow/tests/test_compiler.py` |
| **FT-04** | 單元測試 | 驗證 `<!-- __URI(...)__ -->` 標籤在物化解算階段保持原樣不解算 | FR-04 | `agents-workflow/tests/test_compiler.py` |
| **FT-05** | CLI 整合測試 | 驗證 `agents-workflow compile`、`tokens`、`list` 指令終端格式化輸出與執行正確性 | FR-05 | `agents-workflow/tests/test_compiler.py` |
| **FT-06** | Hook 測試 | 驗證 `scripts/hook.core.py:on_reload` 事件能自主調用編譯器完成物化更新 | FR-06 | `agents-workflow/tests/test_compiler.py` |
| **ET-01** | 邊界測試 | 驗證無匹配 Insert 時 Token 錨點被安全清理，不拋出例外崩潰 | EC-01 | `agents-workflow/tests/test_compiler.py` |
| **ET-02** | 邊界測試 | 驗證單一注入包含自身同名 Token 時禁止自指無窮遞迴 | EC-02 | `agents-workflow/tests/test_compiler.py` |
| **ET-03** | 邊界測試 | 驗證在無第三方擴充模組之全新純淨環境下 `compile` 物化產物 100% 完整合規 | EC-03 | `agents-workflow/tests/test_compiler.py` |
| **ET-04** | 邊界測試 | 驗證損毀/不全之 insert 宣告輸出警告並安全跳過 | EC-04 | `agents-workflow/tests/test_compiler.py` |
| **RT-01** | 全域回歸 | 全模組單元測試與 Auto-Contract 測試 100% 綠燈 Passed | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 成功發現 16 項自導出資產與 3 大 token (`PHASEXX_STANDARD_HEADER`, `PROJECT_SPECIFIC_STANDARDS`, `DYNAMIC_CONTEXT_MAP`) | 2026-08-26 00:07:15 |
| **FT-02** | `Passed` | 成功完成 `PHASEXX_STANDARD_HEADER` replace 替換展開，標籤乾淨抹除 | 2026-08-26 00:07:15 |
| **FT-03** | `Passed` | 成功驗證 below/above 多模組有序追加與 Step 3 清除殘留錨點標籤 | 2026-08-26 00:07:15 |
| **FT-04** | `Passed` | 成功驗證 `<!-- __URI(...)__ -->` 在物化解算階段原樣保留 | 2026-08-26 00:07:15 |
| **FT-05** | `Passed` | 成功執行 `compile`, `tokens`, `list` CLI 指令，格式化表格輸出正確 | 2026-08-26 00:07:15 |
| **FT-06** | `Passed` | 成功觸發 `scripts/hook.core.py:on_reload` 自主調用編譯物化 | 2026-08-26 00:07:15 |
| **ET-01** | `Passed` | 無匹配 Insert 時 Token 錨點被安全清理，不拋錯不殘留 | 2026-08-26 00:07:15 |
| **ET-02** | `Passed` | 成功驗證子 Token 多輪遞迴收斂展開與自指死鎖防護 | 2026-08-26 00:07:15 |
| **ET-03** | `Passed` | 成功完成全量 16 項導出資產物化寫入至 `module://exports/` | 2026-08-26 00:07:15 |
| **ET-04** | `Passed` | 損毀/格式不全之 insert 宣告安全略過，不中斷整體物化 | 2026-08-26 00:07:15 |
| **RT-01** | `Passed` | 全模組回歸測試 93/93 案例 100% Passed (15.463s) | 2026-08-26 00:09:57 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01（CLI 交互體驗）**：實機執行 `python yscb.py agents-workflow tokens` 與 `list`，檢驗表格對齊美觀度與說明可讀性。
- [ ] **UX-02（物化輸出體驗）**：檢驗 `module://exports/templates/P01_requirements_spec.md` 物化產物，確認 Header 已完美替換展開且無多餘殘留標籤。
