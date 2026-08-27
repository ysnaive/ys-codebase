# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元/編碼測試 | 驗證 `subprocess.run` 捕獲與輸出端在非 UTF-8/特殊字元下安全替換不拋例外 | FR-01, EC-01 | `test_tester.py` (`test_safe_print_handles_unicode_and_mock_encoding`) |
| **FT-02** | 測試分類驗證 | 驗證預設回歸排除 WORKFLOW，而在 `--workflow` 或 `--all-types` 時正常收集執行 | FR-02, EC-03 | `test_case.py` / `test_sandbox.py` |
| **FT-03** | 單元 Mock 驗證 | 驗證 `test_run_test_all_success_cleans_sandboxes` 在 Mock 子進程下正確驗證清理邏輯 | FR-03 | `test_tester.py` (`test_run_test_all_success_cleans_sandboxes`) |
| **FT-04** | Mock 模組建置 | 驗證 Builder 與 ReleasePipeline 對 Mock 模組進行 build、package、purge 與 index.json 更新 | FR-04, EC-02 | `test_builder.py` / `test_release_pipeline.py` |
| **ET-01** | 邊界防禦測試 | 模擬含有 `\ufffd` 及非 cp950 字元之日誌輸出，確認控制台輸出安全無崩潰 | EC-01 | `test_tester.py` |
| **RT-01** | 全模組回歸 | 全系統 `dev test --all` 通過率 100% (100% Ready) | NFR-02 | `python yscb.py dev test --all` (118/118 Passed) |
| **PT-01** | 效能指標量測 | 量測 `dev test dev` 單模組耗時壓至 3.81s（加速 >68%） | NFR-01 | `python yscb.py dev test dev` (3.81s) |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_safe_print_handles_unicode_and_mock_encoding` 通過，模擬 cp950 無法編碼 `\ufffd` 時成功 replace 替換不崩潰 | 2026-08-27 20:26 |
| **FT-02** | `Passed` | `dev test --workflow dev` (3 案例, 5.42s) 與 `dev test --all-types dev` (44 案例, 10.45s) 全數綠燈 | 2026-08-27 20:28 |
| **FT-03** | `Passed` | `test_run_test_all_success_cleans_sandboxes` 成功透過 Mock 隔離 Worker 子進程，毫秒級完成清理斷言 | 2026-08-27 20:26 |
| **FT-04** | `Passed` | `test_builder.py` (4 案例) 與 `test_release_pipeline.py` (4 案例) 100% 透過 Mock 模組完成建置、打包與發布驗證 | 2026-08-27 20:26 |
| **ET-01** | `Passed` | 邊界替換字元安全轉譯驗證通過 | 2026-08-27 20:26 |
| **RT-01** | `Passed` | 全系統回歸跑測 `dev test --all` 達成 118/118 Passed (100% Ready) | 2026-08-27 20:27 |
| **PT-01** | `Passed` | `dev test dev` 由 12.08s 壓縮至 **3.81s**（加速超過 68%） | 2026-08-27 20:26 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在 Windows 控制台執行 `python yscb.py dev test dev` 與 `python yscb.py dev test --workflow dev`，確認輸出流暢無 cp950 編碼報錯，且單模組回歸總耗時明顯縮短至秒級體驗。 (開發者確認驗收通過)
