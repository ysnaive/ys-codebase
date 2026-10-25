# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全主計畫二次驗收、測試集子系統 1:1 純化、歷史目錄清理與三層文檔收官 (sub_08_final_acceptance_and_suite_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證測試套件純化為 6 大子系統測試檔，無損整併 47 個有效測試案例，物理刪除 7 支碎片/殭屍檔。 | FR-01 | `python yscb.py dev test agents-workflow -q` |
| **FT-02** | 單元測試 | 驗證徹底清除 1 支死測試檔、4 處墓碑斷言、5 處寬鬆條件放行，並補齊 6 處沙盒目錄清理。 | FR-02 | `python yscb.py dev test agents-workflow -q` |
| **FT-03** | 單元測試 | 驗證物理刪除 `scratch/server_test.log` 與 `scripts/scan_native_io.py`，工作區根目錄乾淨無歷史殘留。 | FR-03 | `git status` 與工作區掃描 |
| **FT-04** | 單元測試 | 驗證更新 `FACTORY_PIPELINE.md` 之 `cache://` 快取敘述與 `README.md` 雙軌 CLI 指令與待辦帳本。 | FR-04 | 靜態檢核與三層文檔對齊檢查 |
| **FT-05** | 整合測試 | 驗證全主計畫 `sub_01` ~ `sub_07` 交付物端到端協同正常，全模組與全生態系二次驗收通過。 | FR-05 | `python yscb.py dev check agents-workflow` |
| **ET-01** | 邊界測試 | 驗證跨檔搬遷測試時命名無衝突，重複之 `test_ft_05` 已重命名為 `test_ft_07`。 | EC-01 | `python yscb.py dev test agents-workflow -k test_targets -q` |
| **ET-02** | 邊界測試 | 驗證 `tearDown` 沙盒清理遇到未初始化變數時具備安全防護，不衍生二度例外。 | EC-02 | `python yscb.py dev test agents-workflow -q` |
| **ET-03** | 邊界測試 | 驗證刪除 `scratch` 與 `scripts` 後不被編譯發布管線誤重建。 | EC-03 | `python yscb.py agents-workflow release --force` |
| **ET-04** | 邊界測試 | 驗證測試純化後有效測試案例總數維持 132 項，無漏測與無效測試回歸。 | EC-04 | `python yscb.py dev test agents-workflow -q` |
| **RT-01** | 回歸測試 | 驗證全模組 100% Python 標準庫與零第三方依賴。 | NFR-01 | `python yscb.py dev check agents-workflow` |
| **RT-02** | 回歸測試 | 驗證測試執行總耗時輕量極速 ($\approx 15$ 秒完成 132 項測試案例)。 | NFR-02 | `python yscb.py dev test agents-workflow -q` |
| **RT-03** | 回歸測試 | 驗證三層文檔 SSOT 100% 對齊無漂移。 | NFR-03 | 靜態檢核與發布檔對照 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-05** | `Passed` | 6 大子系統測試檔、工作區歷史孤兒清理、三層文檔對齊與二次驗收全數通過。 | 2026-10-25 |
| **ET-01 ~ ET-04** | `Passed` | 邊界測試全數通過（方法重命名防呆、`tearDown` 防禦、目錄無重建、有效案例完整保留）。 | 2026-10-25 |
| **RT-01 ~ RT-03** | `Passed` | `dev check` 通過，132/132 測試全綠，耗時 15.2s，三層文檔一致。 | 2026-10-25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 請開發者審閱 6 大純化測試檔架構與收官日誌，確認整體收官驗收與套件體檢符合專案標準。 | `[測試通過]` | 開發者實機審閱確認通過，推進 Phase 07 結案 |

