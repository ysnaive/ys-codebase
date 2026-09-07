# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 型別表達式解析 (`str!`, `int?`, `bool? = false`, `enum(...)`) 正確性 | FR-02 | `python yscb.py dev op-test core -k test_validator_types` |
| **FT-02** | 單元測試 | 物件陣列清單與通配符 `"*"` 字典映射校驗斷言 | FR-02 | `python yscb.py dev op-test core -k test_validator_containers` |
| **FT-03** | 單元測試 | 遞迴結構 (`$CommandNode`) 與 `_types` 別名深度走訪校驗 | FR-02, EC-03 | `python yscb.py dev op-test core -k test_validator_recursive` |
| **FT-04** | 單元測試 | 未知欄位 Levenshtein 近似拼寫診斷 (Did you mean) 斷言 | FR-03 | `python yscb.py dev op-test core -k test_validator_did_you_mean` |
| **FT-05** | 單元測試 | 跨目標越權注入阻斷與單向邊界隔離檢核 | FR-06, EC-02 | `python yscb.py dev op-test core -k test_validator_cross_target` |
| **FT-06** | 整合測試 | 核心 CLI `contributes list` 與 `contributes check` 執行與返回碼 | FR-04 | `python yscb.py dev op-test core -k test_contributes_cli` |
| **FT-07** | 整合測試 | 運行期 `ContributesAggregator` 髒資料過濾與 `_` 特殊檔排除 | FR-01, FR-06 | `python yscb.py dev op-test core -k test_contributes_aggregator` |
| **FT-08** | 整合測試 | `dev check` 靜態合規阻斷與 `dev create` 骨架生成包含 `_format/_manifest` | FR-06, FR-07 | `python yscb.py dev op-test dev -k test_contributes_check` |
| **FT-09** | 全生態系回歸 | 5 大模組全部單元測試與契約測試 100% 通過 | FR-08, NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_validator.py`: 基本型別標記、可選值與預設值、列舉約束驗證全數通過 | 2026-09-07 15:33 |
| **FT-02** | `Passed` | `test_validator.py`: 物件陣列清單與通配符 `"*"` 映射校驗全數通過 | 2026-09-07 15:33 |
| **FT-03** | `Passed` | `test_validator.py`: 遞迴結構 (`$CommandNode`) 與 `_types` 別名深度走訪通過 | 2026-09-07 15:33 |
| **FT-04** | `Passed` | `test_validator.py`: Levenshtein 近似拼寫診斷 (Did you mean) 斷言通過 | 2026-09-07 15:33 |
| **FT-05** | `Passed` | `test_validator.py`: 跨目標越權注入阻斷與單向依賴邊界隔離檢核通過 | 2026-09-07 15:33 |
| **FT-06** | `Passed` | `test_contributes_cmd.py`: `contributes list` 與 `contributes check` 命令執行成功 | 2026-09-07 15:33 |
| **FT-07** | `Passed` | `test_contributes.py`: 聚合快照過濾 `_` 特殊檔案，JIT 快照包含 `_format.json` 通過 | 2026-09-07 15:34 |
| **FT-08** | `Passed` | `test_scaffold.py`: 腳手架生成 `_format.json` 與 `_manifest.md`，合規檢查通過 | 2026-09-07 15:37 |
| **FT-09** | `Passed` | `dev test --all --quiet`: 5 大模組全部 441 個單元測試 100% 通過 (Fail: 0) | 2026-09-07 15:38 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py contributes list`，確認輸出表格清楚列出各模組擴充點與說明 | `[測試通過]` | 開發者實機執行 `python yscb.py contributes list` 輸出 14 點表格無誤 |
| **UX-02** | 執行 `python yscb.py contributes check module.source://dev/contributes/core.json`，確認返回成功無誤 | `[測試通過]` | 開發者實機驗證通過 |
| **UX-03** | 故意在某模組 `contributes/core.json` 寫錯一個 key（如 `pros` 代替 `case_pros`），執行 check 確認看到 `Did you mean 'case_pros'?` 提示 | `[測試通過]` | 開發者實機驗證通過 |
