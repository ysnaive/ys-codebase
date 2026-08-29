# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_get_storage_root()` 於有效指定 `storage_dir` 或有效 `cache://` 下正常解析 | FR-01 | `test_space.py:test_ft_11_cache_storage_root_resolution` |
| **FT-02** | 單元測試 | 驗證 `KnowledgeEngine.to_file_uri()` 正確產生 `file:///` 格式與 `#L{line}` 錨點 | FR-02, EC-01 | `test_engine.py:test_ft_07_to_file_uri_and_formatting` |
| **FT-03** | 單元測試 | 驗證 `KnowledgeEngine.format_file_link()` 正確格式化 Markdown 檔案連結 | FR-02, EC-03 | `test_engine.py:test_ft_07_to_file_uri_and_formatting` |
| **FT-04** | 單元測試 | 驗證 CLI `search` 簡易模式、詳細模式、預覽模式輸出包含 `file:///` 超連結 | FR-03 | `test_cli.py:test_cli_search_modes` |
| **FT-05** | 單元測試 | 驗證 CLI `search --json` 輸出各項目包含 `file_uri` 欄位 | FR-03 | `test_cli.py:test_cli_search_modes` |
| **ET-01** | 邊界測試 | 驗證無 `core` 且無 `storage_dir` 時拋出 `InvalidSpaceConfigError` 且不產生 `.cache` 目錄 | EC-02 | `test_space.py:test_et_04_zero_fallback_cache_root_guardrail` |
| **RT-01** | 回歸測試 | 全生態系全量跑測 `dev test --all` 100% Passed (零副作用、零破壞) | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_11_cache_storage_root_resolution`: 顯式指定 storage_dir 成功解析 | 2026-08-30 01:05 |
| **FT-02** | `Passed` | `test_ft_07_to_file_uri_and_formatting`: to_file_uri 成功產生標準 `file:///` 與 `#L42` 錨點 | 2026-08-30 01:05 |
| **FT-03** | `Passed` | `test_ft_07_to_file_uri_and_formatting`: format_file_link 單行與跨行 `[L10-25](file:///...#L10)` 驗證通過 | 2026-08-30 01:05 |
| **FT-04** | `Passed` | `test_cli_search_modes`: 簡易、詳細、預覽 3 大模式輸出 100% 包含 `](file:///` 連結 | 2026-08-30 01:05 |
| **FT-05** | `Passed` | `test_cli_search_modes`: JSON 模式與 JSON+Snippet 模式各結果項目皆帶 `file_uri` | 2026-08-30 01:05 |
| **ET-01** | `Passed` | `test_et_04_zero_fallback_cache_root_guardrail`: 模擬無 core 環境下精確拋出 `InvalidSpaceConfigError` | 2026-08-30 01:05 |
| **RT-01** | `Passed` | 全生態系 4 大模組全量回歸測試：**230/230 Passed (100% Ready)** | 2026-08-30 01:05 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者指示免測，實機 CLI 自動化輸出確認包含標準 Markdown `[file:line](file:///...)` 連結，且宿主根目錄 0 殘留。
