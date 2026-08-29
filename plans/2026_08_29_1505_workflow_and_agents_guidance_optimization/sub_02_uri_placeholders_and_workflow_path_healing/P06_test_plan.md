# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `compiler.resolve_stage2_uri` 對純佔位符（`__#{...}__` / `__${...}__`）能完全替代並剝除反引號 | FR-01 | `python yscb_cli.py dev test agents-workflow -k test_resolve_stage2_uri_standalone` |
| **FT-02** | 單元測試 | 驗證 `compiler.resolve_stage2_uri` 對行內穿插佔位符（如命令列）能替換內部路徑並保留外層反引號 | FR-01 | `python yscb_cli.py dev test agents-workflow -k test_resolve_stage2_uri_inline` |
| **FT-03** | 單元測試 | 驗證 Markdown 超連結 `[Link](`__#{...}__`)` 解算後為無反引號之標準合法 Markdown | FR-01, FR-02 | `python yscb_cli.py dev test agents-workflow -k test_resolve_stage2_markdown_link` |
| **FT-04** | 回歸測試 | 驗證全生態系 4 大模組全量單元測試 100% Passed (208+ 測試) | NFR-01 | `python test/run_regression.py` |
| **FT-05** | 整合驗證 | 驗證發布物化後 `.agents/workflows/ContextInit.md` 中所有讀檔路徑均為專案根目錄可讀路徑 | FR-02, FR-03 | `python yscb_cli.py agents-workflow --ide-antigravity` + 靜態路徑檢查 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_12` & `test_sub_02` Standalone 佔位符完全替代且剝除反引號通過 | 2026-08-29 16:16 |
| **FT-02** | `Passed` | `test_ft_13` Inline 佔位符替換並保留外層反引號通過 | 2026-08-29 16:16 |
| **FT-03** | `Passed` | `test_sub_02` Markdown 超連結輸出無反引號之標準格式驗證通過 | 2026-08-29 16:16 |
| **FT-04** | `Passed` | `dev test --all` 209/209 Passed (8.518s)，全生態系 4 大模組 100% Ready | 2026-08-29 16:16 |
| **FT-05** | `Passed` | `.agents/workflows/ContextInit.md` 物化為 `AGENTS.md`、`CHANGELOG.md`、`docs/_project/STANDARDS.md` 專案根目錄直達路徑 | 2026-08-29 16:16 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：在全新 Session 中執行 `/ContextInit`，驗證 Agent 能直接透過 `view_file` 秒讀所有指引檔案，不觸發 404 與 fallback search。
