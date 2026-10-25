# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：新世代全量複檢收尾與發布前最終打磨 (Global Step 1~13 Pre-Release Polish)  
> 建立日期：2026-10-25  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 整合與回歸測試 | 驗證 `SandboxProvisioner` (`_SANDBOX_LOCK`、子沙盒跳過自動 `prune_sandboxes`、`_project_venv` `realpath` 解析) 與 `tester.py` 平行收尾清理，使 `dev test --all -q` 5 模組平行測試零互刪全綠 | FR-01, EC-01, NFR-01 | `python yscb.py dev test --all -q` |
| **FT-02** | 單元測試 | 驗證 `PlanVerifier._is_header_match` 精準攔截否定前綴（`非功能需求` vs `功能需求`）子字串誤配，且 `test_ft_14` 100% 通過 | FR-02, EC-02 | `TestPlansModelRecord.test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint` |
| **FT-03** | 單元與整合測試 | 驗證 `knowledge-db` `act_callers`/`act_callees`/`act_impact` 支援 `ftypes` 回退定位、降級提示更新為 `config set`、移除舊版 `yscb.config.json` 分支，且 `contributes/core.json` 通過正交選項篩選與 `contributes check` | FR-03, FR-04, EC-03, NFR-01 | `TestCLI.test_cli_options_extraction_and_orthogonal_filter`, `TestCallGraphAndReferenceIndex.test_ft_12_csharp_and_multilang_advanced_call_topology` |
| **FT-04** | 單元測試 | 驗證 `server/tests/test_server.py` 與 `core/tests/test_distribution_lifecycle.py` 合併重複測項並移除靜態字面量檢查後 100% 通過 `dev check --all` 與 `dev test` | FR-05, NFR-01 | `python yscb.py dev check --all` |
| **FT-05** | 文檔與規範檢核 | 驗證 `docs/agents-workflow/DESIGN_NOTES.md`、`docs/dev/DESIGN_NOTES.md`、`docs/core/README.md`、`docs/knowledge-db/README.md` 與 `CHANGELOG.md` 對齊無誤，且遵守不自動觸發發布之邊界約束 | FR-06, NFR-02 | `python yscb.py agents-workflow plan verify --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `python yscb.py dev test --all -q` 實機平行執行 5 大模組：589/589 Passed (100.0%), 0 Failed, 0 Skipped | 2026-10-25 16:56 |
| **FT-02** | `Passed` | `agents-workflow` 133/133 Passed，`test_ft_14` 驗證 `FULL_REWRITE (章節缺失 3/4, 75%)` 與 `FT Done` 100% 通過 | 2026-10-25 16:56 |
| **FT-03** | `Passed` | `knowledge-db` 150/150 Passed，`contributes check` 15 files Valid | 2026-10-25 16:56 |
| **FT-04** | `Passed` | `dev check --all` 5/5 Modules Passed (0 Warnings, 0 Failed) | 2026-10-25 16:57 |
| **FT-05** | `Passed` | 三層文檔同步對齊完畢，全數 5 模組 `@build` 已熱部署同步且未執行版本發布 | 2026-10-25 16:57 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 Global Step 1~13 收尾打磨成果（`contributes check`、`dev check --all`、`dev test --all -q` 589/589 全綠）與三層文檔對齊狀態 | `[跳過/免測]` | 開發者指示免測（已確認全量測試與三層文檔對齊通過） |
