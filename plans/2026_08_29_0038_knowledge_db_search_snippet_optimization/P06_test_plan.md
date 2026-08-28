# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SnippetExtractor.extract` 能正確讀取目標檔案並提取行號區間（含前後上下文行與行號排版）。 | FR-02 | `test_retrieval.py::TestSnippetExtractor::test_extract_basic` |
| **FT-02** | 單元測試 | 驗證 `KnowledgeEngine.search(..., snippet=True)` 在結果中正確填入 `CodeSnippet`。 | FR-02 | `test_retrieval.py::TestSnippetExtractor::test_engine_search_snippet` |
| **FT-03** | CLI 測試 | 驗證 `python yscb.py knowledge-db search <query> --snippet` 輸出包含 Docstring、檔案路徑與程式碼區塊。 | FR-01, FR-03 | `test_cli.py::TestSearchCLI::test_search_snippet_flag` |
| **FT-04** | CLI 測試 | 驗證 `python yscb.py knowledge-db search <query> -s --json` 輸出之 JSON 結構包含 `code_snippet` 與 `docstring` 欄位。 | FR-05 | `test_cli.py::TestSearchCLI::test_search_snippet_json` |
| **FT-05** | 整合測試 | 驗證 Workspace 相對路徑正規化正確移除冗餘前綴，輸出正確相對路徑。 | FR-04 | `test_retrieval.py::TestSnippetExtractor::test_workspace_path_normalization` |
| **FT-06** | 整合測試 | 驗證 `KnowledgeAgentsStandards.md`、`phase00_guild.md` 等注入資產中包含 `--snippet` 語法指引。 | FR-06 | `test_retrieval.py::TestSnippetExtractor::test_assets_snippet_guidelines` |
| **ET-01** | 邊界測試 | 驗證當目標檔案不存在時，`SnippetExtractor` 優雅降級為 `[Snippet Unavailable: File not found]`，不拋出未捕捉例外。 | EC-01 | `test_retrieval.py::TestSnippetExtractor::test_extract_file_not_found` |
| **ET-02** | 邊界測試 | 驗證符號行號小於等於 0 或大於檔案行數時，能安全截斷在合法邊界內。 | EC-02 | `test_retrieval.py::TestSnippetExtractor::test_extract_out_of_bounds_lines` |
| **ET-03** | 邊界測試 | 驗證超長函式代碼能被限制在 `max_lines`（預設 12 行）以內，並標註截斷提示。 | EC-03 | `test_retrieval.py::TestSnippetExtractor::test_extract_max_lines_truncation` |
| **ET-04** | 邊界測試 | 驗證非 UTF-8 或含有特殊二進位位元組之檔案在讀取時透過 replace 容錯不崩潰。 | EC-04, NFR-01 | `test_retrieval.py::TestSnippetExtractor::test_extract_encoding_fallback` |
| **RT-01** | 全域回歸 | 執行全生態系四大模組沙盒測試，確認所有既有功能 100% Passed。 | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `SnippetExtractor.extract` 成功提取目標程式碼切片與行號對齊排版 | 2026-08-29 00:58 |
| **FT-02** | `Passed` | `KnowledgeEngine.search` 正確返回包含 `CodeSnippet` 物件之搜尋結果 | 2026-08-29 00:58 |
| **FT-03** | `Passed` | CLI `--snippet` / `-s` / `--preview` 成功觸發預覽模式並輸出檔案與代碼片段 | 2026-08-29 00:58 |
| **FT-04** | `Passed` | CLI `--json -s` 成功於 JSON 物件中包含 `code_snippet` 結構化資料 | 2026-08-29 00:58 |
| **FT-05** | `Passed` | Workspace 相對路徑解算正規化通過，正確消除冗餘路徑前綴 | 2026-08-29 00:58 |
| **FT-06** | `Passed` | `KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 注入資產更新完成 | 2026-08-29 00:58 |
| **ET-01** | `Passed` | 目標檔案不存在時優雅降級為 `[Snippet Unavailable: File not found]`，不拋出未處理異常 | 2026-08-29 00:58 |
| **ET-02** | `Passed` | 目標行號超出檔案範圍時安全截斷於合法行號邊界 | 2026-08-29 00:58 |
| **ET-03** | `Passed` | 超長程式碼區塊正確受 `max_lines`（預設 12 行）截斷並附帶提示 | 2026-08-29 00:58 |
| **ET-04** | `Passed` | 非 UTF-8 / 二進位位元組檔案讀取使用 replace 容錯不崩潰 | 2026-08-29 00:58 |
| **RT-01** | `Passed` | 全生態系四大模組沙盒回歸測試 186/186 Passed (100% Ready) | 2026-08-29 00:58 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在終端執行 `python yscb.py knowledge-db search "PIDController" --snippet`，確認排版清晰包含行號與代碼片段（開發者指示免測通過）。
- [x] **UX-02**：在終端執行 `python yscb.py knowledge-db search "狀態機" -s`，確認中文檢索與 Snippet 提取完美結合（開發者指示免測通過）。
