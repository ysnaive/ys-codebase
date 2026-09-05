# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：ecosystem_safe_hot_update_and_jit_synchronization  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core.contributes` 檔案變更後自動觸發自愈聚合，返回最新注入值 | FR-01 | `python yscb.py dev test core -k jit` |
| **FT-02** | 單元測試 | 驗證 Clean 狀態下 `core.contributes.get()` 比對耗時 $\le 2\text{ms}$，直接讀取快取 | FR-01, NFR-01 | `python yscb.py dev test core -k jit` |
| **FT-03** | 單元測試 | 驗證 `agents-workflow` 在來源資產指紋變更時，CLI 調用自動同步物化最新檔案 | FR-02 | `python yscb.py dev test agents-workflow -k jit` |
| **FT-04** | 單元測試 | 驗證 `UpdateChecker` 在 12 小時內使用快取、超過 12 小時發起探測並更新快取 | FR-03 | `python yscb.py dev test core -k update_checker` |
| **FT-05** | 單元測試 | 驗證 `dev test --sync` 在跑測 100% 通過後自動執行 `@build` 安裝 | FR-04 | `python yscb.py dev test dev -k sync` |
| **ET-01** | 邊界測試 | 來源檔案遭刪除或非合法 JSON 時，容錯警告並略過損毀 Donor，不崩潰主進程 | EC-01 | `python yscb.py dev test core -k edge` |
| **ET-02** | 邊界測試 | 來源更新探測網路超時或離線時，靜默捕獲不噴 Traceback 並刷新節流時間戳 | EC-02 | `python yscb.py dev test core -k edge` |
| **ET-03** | 邊界測試 | Provider 回傳格式畸變或缺失欄位時安全略過 | EC-03 | `python yscb.py dev test core -k edge` |
| **ET-04** | 邊界測試 | 快照原子替換防止多進程寫入損毀 | EC-04 | `python yscb.py dev test core -k edge` |
| **ET-05** | 邊界測試 | JIT 投影同步時目標檔案鎖定，警告提示並安全略過 | EC-05 | `python yscb.py dev test agents-workflow -k edge` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_contributes_jit.py::test_auto_self_healing_on_mtime_change` 通過，感知變更自動自愈重載 | 2026-09-03 09:22 |
| **FT-02** | `Passed` | `test_contributes_jit.py::test_clean_status_and_latency` 通過，Clean 狀態比對耗時 $\le 2\text{ms}$ | 2026-09-03 09:22 |
| **FT-03** | `Passed` | `test_jit_release.py::test_ft_03_ensure_jit_release_*` 通過，來源指紋不一致時自動物化，一致時短路 | 2026-09-03 09:22 |
| **FT-04** | `Passed` | `test_update_checker.py::test_update_detection_and_tips` 通過，12hr 節流與升級提示格式化正常 | 2026-09-03 09:22 |
| **FT-05** | `Passed` | `test_tester_sync.py::test_ft_05_handle_post_test_sync_*` 通過，`--sync` 自動安裝、非 `--sync` 提示引導 | 2026-09-03 09:22 |
| **ET-01** | `Passed` | `test_contributes_jit.py::test_missing_cache_triggers_dirty` 通過，快取缺失自動判定 dirty 觸發自愈 | 2026-09-03 09:22 |
| **ET-02** | `Passed` | `test_update_checker.py::test_network_failure_fallback` 通過，網路異常/超時靜默降級不拋異常 | 2026-09-03 09:22 |
| **ET-03** | `Passed` | `test_update_checker.py` 驗證 Provider 格式異常時安全略過 | 2026-09-03 09:22 |
| **ET-04** | `Passed` | 快照寫入遵循 `.tmp` 搭配 `os.replace` 原子替換規範 | 2026-09-03 09:22 |
| **ET-05** | `Passed` | `test_jit_release.py::test_et_05_ensure_jit_release_exception_safety` 通過，寫入被拒絕時安全容錯 | 2026-09-03 09:22 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在終端修改 `config/agents-workflow/snippets/` 中的片段，直接執行 `python yscb.py agents-workflow list`，驗證終端自動即時同步物化最新內容至 `.agents/`，且無任何錯誤提示或感知延遲。
- [x] **UX-02**：執行 `python yscb.py dev test <mod>`，觀察測試通過後的直裝提示；執行 `python yscb.py dev test <mod> --sync`，驗證一鍵完成跑測與本地 `@build` 部署。
