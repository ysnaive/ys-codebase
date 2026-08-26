# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `test_clean_build_core` 與 `test_builder_generates_and_updates_index_json` 動態適配版本構建與索引產生 | FR-01 | `python yscb.py dev test dev -k test_builder` |
| **FT-02** | 整合測試 | 驗證 `test_builder_dev_build_and_release_package` 與 `test_release_force_override_behavior` 在動態版本下 3-Gate 守門與強制覆蓋行為 | FR-01 | `python yscb.py dev test dev -k test_release` |
| **FT-03** | 單元測試 | 驗證 `test_builder_preserves_hook_dev` 動態適配版本並確認 `hook.dev.py` 完整保留 | FR-01 | `python yscb.py dev test dev -k test_builder_preserves_hook_dev` |
| **FT-04** | 模組全測 | 驗證 `dev` 模組全部 30 個測試案例 100% 通過 | FR-01 | `python yscb.py dev test dev` |
| **FT-05** | 工具驗證 | 驗證 `PlanVerifier` 正確解析 RXX 調研報告 Header 別名，全部既有計畫合規通過 | FR-02 | `python yscb.py agents-workflow plan verify` |
| **RT-01** | 回歸測試 | 驗證 `core` 與 `agents-workflow` 模組功能不受影響 | NFR-02 | `python yscb.py dev test core`<br/>`python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `python yscb.py dev test dev -k test_builder`: 動態版本解算 build tag 與 index.json 產物驗證通過。 | 2026-08-27 04:16 |
| **FT-02** | `Passed` | `python yscb.py dev test dev -k test_release`: 動態版本 3-Gate 守門與強制覆蓋 release 驗證通過。 | 2026-08-27 04:16 |
| **FT-03** | `Passed` | `python yscb.py dev test dev -k test_builder_preserves_hook_dev`: `hook.dev.py` 保留性驗證通過。 | 2026-08-27 04:16 |
| **FT-04** | `Passed` | `python yscb.py dev test dev`: 30/30 Total Passed (100% Ready, 34.730s)。 | 2026-08-27 04:16 |
| **FT-05** | `Passed` | `PlanVerifier.verify()`: 4 個計畫共 19 個 Markdown 文件稽核通過，0 Error, 0 Warn。 | 2026-08-27 04:16 |
| **RT-01** | `Passed` | `core` (69/69, 13.217s) 與 `agents-workflow` (30/30, 1.447s) 回歸跑測全數 100% Passed。 | 2026-08-27 04:16 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：核對 `docs/README.md` 渲染效果，確認 `agents-workflow` 模組與版本矩陣顯示正確且連結可正常跳轉。
- [x] **UX-02**：確認 CLI 輸出格式整潔、無未捕捉之例外與警告。
