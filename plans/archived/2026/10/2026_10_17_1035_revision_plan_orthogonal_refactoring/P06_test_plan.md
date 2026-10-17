# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：修訂計畫 (Revision Plan) 正交化定位重構、留檔強制化與 SOP 邊界純化  
> 建立日期：2026-10-17  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `PlanScanner` 對獨立修訂計畫（含單獨 `revision_log.md` 或搭配前置 `P00_discuss.md`）識別 Track 為 `"Revision"`，且附掛於 Full Track / Fast Track / Umbrella 時不改變原計畫 Track 與狀態 | FR-03, EC-01 | `python yscb.py dev test --target=agents-workflow:TestPlansToolchainInternal.test_plan_scanner_revision_track_and_orthogonal_attachment` |
| **FT-02** | 單元測試 | 驗證 `PlanVerifier` 對 `revision_log.md` 執行標頭模型檢核、章節標題對齊、`[REV-XX]` 條目存在性檢核與 `Completed` 狀態未勾選 Checkbox 阻斷 | FR-01, FR-04, EC-03 | `python yscb.py dev test --target=agents-workflow:TestPlansToolchainInternal.test_plan_verifier_revision_log_compliance` |
| **FT-03** | 單元測試 | 驗證 `PlanArchiver` 支援獨立 `revision_log.md` (`Completed`) 歸檔，且當主計畫或 `sub_*` 子計畫存在未完成 (`In Progress`) 之附掛 `revision_log.md` 時剛性拋出 `PlanIncompleteError` 阻斷歸檔 | FR-05, EC-02 | `python yscb.py dev test --target=agents-workflow:TestPlansToolchainInternal.test_plan_archiver_revision_log_completion_gate` |
| **ET-01** | 邊界測試 | 驗證 `revision_log.md` 缺少任何 `[REV-XX]` 條目或殘留 `[修訂主題簡述]` 模板佔位符時，`PlanVerifier` 正確回報 `FAIL` | FR-04, EC-03 | `python yscb.py dev test --target=agents-workflow:TestPlansToolchainInternal.test_plan_verifier_revision_log_compliance` |
| **FT-04** | 整合驗證 | 驗證 `agents-workflow` 通用模板與 `development-sop` 資產已清除 `@build`、`dev test` 等本專案自引用特化字眼，且 `revision_log.md` 成功透過 `release` 投影至 `.agents/.yscb/templates/revision_log.md` | FR-01, FR-02, FR-06, FR-07, EC-04 | `python yscb.py agents-workflow release && python yscb.py agents-workflow plan verify 2026_10_17_1035_revision_plan_orthogonal_refactoring` |
| **RT-01** | 回歸測試 | 全生態系模組單元測試與靜態合規檢查 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check agents-workflow && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestPlansToolchainInternal.test_plan_scanner_revision_track_and_orthogonal_attachment` 通過，獨立修訂計畫正確識別為 `Revision`，附掛修訂不干擾原 Track 與狀態 | 2026-10-17 11:00 |
| **FT-02** | `Passed` | `TestPlansToolchainInternal.test_plan_verifier_revision_log_compliance` 通過，動態 `### [REV-01]` 標題豁免誤報且標頭模型、佔位符、Checkbox 檢核正常 | 2026-10-17 11:00 |
| **FT-03** | `Passed` | `TestPlansToolchainInternal.test_plan_archiver_revision_log_completion_gate` 通過，獨立 `revision_log.md` (`Completed`) 順利歸檔，子計畫未完成修訂剛性拋出 `PlanIncompleteError` | 2026-10-17 11:00 |
| **ET-01** | `Passed` | 移除 `[REV-01]` 條目時 `PlanVerifier` 準確觸發 `ID_MATRIX` `FAIL` 阻斷 | 2026-10-17 11:00 |
| **FT-04** | `Passed` | `install agents-workflow@build --force` 自動釋出 12 個更新檔案（含 `.agents/.yscb/templates/revision_log.md`），`plan verify` 100% `PASSED` | 2026-10-17 11:00 |
| **RT-01** | `Passed` | `dev check agents-workflow` `PASSED`；`dev test agents-workflow -q` 88/88 (100.0%) 全數通過 | 2026-10-17 11:00 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視物化後之 `.agents/.yscb/templates/revision_log.md`、`.agents/skills/development-sop/references/plan_modes.md` 與 `phase_06_test.md`，並透過 4 組無上下文 Sub-Agents 盲測確認修訂計畫正交定位、去特化表述與 P06 主動詢問引導符合預期 | `[測試通過]` | 開發者確認 4 組盲測與規範實體驗收通過 (2026-10-17) |
