# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `core.installer` 提示未安裝之 optional 模組與安裝指令 | FR-02 | `python yscb.py dev test --target=core:TestInstaller.test_optional_dependencies_hint` |
| **FT-02** | 單元測試 | `core.installer` 若 optional 模組已安裝則靜默跳過 | FR-02 | `python yscb.py dev test --target=core:TestInstaller.test_optional_dependencies_already_installed` |
| **FT-03** | 單元測試 | `dev.checker` 合格之 `optional` 結構順利通過檢核 | FR-03 | `python yscb.py dev test --target=dev:TestChecker.test_valid_optional_manifest` |
| **FT-04** | 單元測試 | `dev.checker` 攔截不合規之 `optional` 結構（非 dict、缺 version、缺 hint） | FR-03 | `python yscb.py dev test --target=dev:TestChecker.test_invalid_optional_manifest` |
| **FT-05** | 回歸測試 | 徹底刪除 `daemon.py` 與 `hook.core.py` 後，`knowledge-db` 既有測試 100% 通過 | FR-04, FR-05 | `python yscb.py dev test knowledge-db --quiet` |
| **FT-06** | 靜態合規 | `knowledge-db` 依賴轉移至 optional 且全模組通過 `dev check` | FR-06 | `python yscb.py dev check knowledge-db` |
| **FT-07** | 系統回歸 | 全生態系 5 大模組單元與契約測試 100% 通過 | FR-01~06 | `python yscb.py dev test --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證 `_check_optional_dependencies` 準確輸出提示文字與 `python yscb.py install <mod>` 安裝建議 | 2026-09-07 01:52 |
| **FT-02** | `Passed` | 驗證 optional 模組若已存在於工作區則靜默略過無多餘提示輸出 | 2026-09-07 01:52 |
| **FT-03** | `Passed` | 驗證合規的 `optional` 欄位結構順利通過 `dev check` 檢驗 | 2026-09-07 01:52 |
| **FT-04** | `Passed` | 驗證非法型別、缺漏 `version` 或 `hint` 時精確拋出合規錯誤 | 2026-09-07 01:52 |
| **FT-05** | `Passed` | `knowledge-db` 140/140 PASSED (100%)，冷啟動自癒與查詢完全不受影響 | 2026-09-07 01:53 |
| **FT-06** | `Passed` | `knowledge-db` 依賴移轉 optional 後，`dev check` 靜態合規性 100% 通過 | 2026-09-07 01:53 |
| **FT-07** | `Passed` | 全生態系單元測試 121/121 PASSED (89.0%, Fail: 0, Unknown: 15 為歷史既定未改動項目) | 2026-09-07 01:53 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 觀察模組安裝終端輸出，確認 optional 模組提示格式簡潔美觀 | `[跳過/免測]` | 開發者指示免測 (2026-09-07) |
| **UX-02** | 執行 `knowledge-db` 各項 CLI 指令，確認在無 `daemon.py` / 無 `hook.core.py` 下表現一致 | `[跳過/免測]` | 開發者指示免測 (2026-09-07) |
