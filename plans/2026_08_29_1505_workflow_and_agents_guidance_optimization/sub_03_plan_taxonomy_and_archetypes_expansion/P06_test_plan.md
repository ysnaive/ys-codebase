# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `RoadmapManager` 能精準提取 `roadmap/*.md` 之 Header 元資料（狀態、更新日期）與「# 1. 問題陳述與根因量化」區塊摘要 | FR-06, FR-07 | `pytest test/test_agents_workflow.py -k test_roadmap_manager` |
| **FT-02** | CLI 測試 | 執行 `python yscb.py agents-workflow roadmap` 驗證格式化輸出正確，並在目錄為空時安全提示不崩潰 | FR-07, EC-03 | `pytest test/test_agents_workflow.py -k test_cli_roadmap` |
| **FT-03** | 模板測試 | 驗證新增之 `roadmap.md` 與 `P00_discuss.md` 模板語法合規、無 HTML 註解殘留 | FR-06, FR-09, NFR-03 | `pytest test/test_agents_workflow.py -k test_templates_integrity` |
| **FT-04** | 編譯物化 | 執行 `dev build agents-workflow` 驗證編譯物化 0 報錯、`contributes` 導出無損 | NFR-01 | `python yscb_cli.py dev build agents-workflow` |
| **FT-05** | 工作流測試 | 驗證 `/NewPlan`、`/Roadmap`、`/Research` 工作流內之語意 URI 佔位符 100% 根目錄直達解算 | FR-08, FR-10 | `pytest test/test_agents_workflow.py -k test_workflow_placeholders` |
| **ET-01** | 容錯測試 | 驗證 `RoadmapManager` 面對非標準 Header / 格式混亂的 markdown 檔案時能自動 fallback 預覽不崩潰 | EC-04 | `pytest test/test_agents_workflow.py -k test_roadmap_fallback` |
| **RT-01** | 全量回歸 | 執行全系統回歸測試，確認全生態系 4 大模組 100% 通過 | NFR-01 | `python test/run_regression.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestRoadmapManager.test_standard_roadmap_parsing` 驗證成功，正確解析 H1、Header 與問題摘要 | 2026-08-29 18:36 |
| **FT-02** | `Passed` | `TestRoadmapManager.test_cli_roadmap_invocation` 驗證成功，`cmd_roadmap` 正確格式化輸出 | 2026-08-29 18:36 |
| **FT-03** | `Passed` | 驗證 `roadmap.md`、`P00_discuss.md` 模板語法合規，HTML 指引註解於導出時正確剝除 | 2026-08-29 18:36 |
| **FT-04** | `Passed` | `dev build agents-workflow` 打包 49 個檔案 0 報錯，成功產出 `1.0.2.5.zip` | 2026-08-29 18:37 |
| **FT-05** | `Passed` | 自動發布至 `.agents/workflows/`，`Roadmap.md` 與 `NewPlan.md` 佔位符 100% 根目錄直達解算 | 2026-08-29 18:37 |
| **ET-01** | `Passed` | `TestRoadmapManager.test_non_standard_roadmap_fallback` 容錯驗證通過，非標準文檔自動 fallback | 2026-08-29 18:36 |
| **RT-01** | `Passed` | 全模組迴歸測試 209/209 100% Passed（core, dev, knowledge-db, agents-workflow） | 2026-08-29 18:37 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機在終端執行 `python yscb.py agents-workflow roadmap`，檢視格式化輸出是否清晰美觀。
- [x] **UX-02**：實機檢視生成的 `.agents/workflows/Roadmap.md` 與 `NewPlan.md` 工作流指引體驗。
