# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：優化 knowledge-db 輸出搜尋結果時的格式  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證預設簡易模式 (Simple Mode) 輸出格式僅包含 `#01 <path>:<line>` 單行 | FR-01 | `tests/test_cli.py::TestCLI.test_cli_search_modes` |
| **FT-02** | 單元測試 | 驗證 `--detail` / `-d` / `--verbose` 詳細模式輸出包含多行詳細欄位 | FR-02 | `tests/test_cli.py::TestCLI.test_cli_search_modes` |
| **FT-03** | 單元測試 | 驗證 `--json` 模式輸出符合 JSON 規格且可成功反序列化 | FR-03 | `tests/test_cli.py::TestCLI.test_cli_search_modes` |
| **ET-01** | 邊界測試 | 驗證搜尋查無結果時 (0 筆) 各模式之優雅提示與 JSON 回傳 | EC-01 | `tests/test_cli.py::TestCLI.test_cli_search_modes` |
| **ET-02** | 邊界測試 | 驗證未提供查詢字串時回傳 exit code 1 與 stderr 錯誤提示 | EC-02 | `tests/test_cli.py::TestCLI.test_cli_all_commands` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 實機斷言通過：預設輸出 `#01 file_path:line` 單行排版，無冗餘欄位 | 2026-08-28 21:48 |
| **FT-02** | `Passed` | 實機斷言通過：`--detail`, `-d`, `--verbose` 均成功輸出多行卡片與命中詞 | 2026-08-28 21:48 |
| **FT-03** | `Passed` | 實機斷言通過：`--json` 輸出乾淨 JSON，欄位包含 query, total, results | 2026-08-28 21:48 |
| **ET-01** | `Passed` | 實機斷言通過：0 結果時文字模式提示「未找到符合的結果」，JSON total 為 0 | 2026-08-28 21:48 |
| **ET-02** | `Passed` | 實機斷言通過：未提供 query 時 stderr 輸出錯誤且 exit code 為 1 | 2026-08-28 21:48 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：開發者於控制台實機執行 `python yscb.py knowledge-db search config` 檢驗預設簡易單行排版清晰度與路徑跳轉手感。
- [ ] **UX-02**：開發者於控制台實機執行 `python yscb.py knowledge-db search config --detail` 檢驗完整卡片式排版。
