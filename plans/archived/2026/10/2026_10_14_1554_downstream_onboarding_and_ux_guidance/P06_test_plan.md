# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_10_14_1554_downstream_onboarding_and_ux_guidance  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `format_undefined_uri_hint` 與 `UndefinedURIError` 對 `project://`、`workflow.plans://` 及一般模組協議生成正確之 `Quick fix:` CLI 提示 | FR-05 | `python yscb.py dev test core -k test_uri` |
| **FT-02** | 單元測試 | 驗證 `uri check` 在存在 `!undefined` 協議時於輸出中包含 `[Quick Fix]` 修復指令提示 | FR-05 | `python yscb.py dev test core -k test_uri` |
| **FT-03** | 單元測試 | 驗證 `yscb.py init` 全新自舉完成後輸出 `[Next Steps]` 引導卡片，而 `init --fix` 不重複輸出 | FR-03, EC-03 | `python yscb.py dev test core -k test_remote_zip_bootstrap` |
| **FT-04** | 單元測試 | 驗證 `Installer.cmd_install` 安裝含 `onboarding` 之模組後輸出 `[*] Next Steps for '<module>':` 與 `README.md` 提示 | FR-04 | `python yscb.py dev test core -k test_remote_zip_bootstrap` |
| **FT-05** | 單元測試 | 驗證 `dev` 之 `Checker` 能通過合法 `onboarding: List[str]`，並攔截非字串陣列之非法 `onboarding` (EC-02) | FR-04, EC-01, EC-02 | `python yscb.py dev test dev -k test_checker` |
| **RT-01** | 全量回歸 | 驗證 5 大模組 `dev check --all` 與 `dev test --all` 100% 通過（0 Warnings, 0 Failed） | NFR-01, NFR-02 | `python yscb.py dev check --all && python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** ~ **FT-05** | `Passed` | `test_undefined_uri_quick_fix_hints`、`test_installer_onboarding_guide_output`、`test_ft15_manifest_onboarding_validation` 全數通過 | 2026-10-14 16:08 |
| **RT-01** | `Passed` | `dev check --all`: 5/5 PASSED (0 Warnings, 0 Failed)；`dev test --all`: Pass: 555 (100.0%), Fail: 0, Skip: 0 | 2026-10-14 16:08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視根目錄 `README.md`、`docs/README.md` 與 5 大模組 `ys_codebase/source/*/README.md`，確認 5 大模組全景、Quickstart、組態設定與 Agent Pre-flight Check 清晰準確（含零前置 Subagent 盲測補強與純 Online 流程收斂） | `[測試通過]` | 開發者與零前置 Subagent 盲測驗收通過 (2026-10-14 16:24) |
| **UX-02** | 執行 `python yscb.py install agents-workflow@build --force`（或任意模組安裝），確認終端輸出 `[*] Next Steps for 'agents-workflow':` 引導卡片 | `[測試通過]` | 實機安裝 5 大模組 `@build` 驗證輸出通過 (2026-10-14 16:24) |

