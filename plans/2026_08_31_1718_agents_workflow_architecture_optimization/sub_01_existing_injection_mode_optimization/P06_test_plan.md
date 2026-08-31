# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `antigravity` target 啟用時，`project://AGENTS.md` 成功生成且包含標準區塊。 | FR-01, FR-02 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-02** | 單元測試 | 驗證 `claude` target 啟用時，`project://CLAUDE.md` 成功生成且內容正確。 | FR-01, FR-02 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-03** | 單元測試 | 驗證 `agents_md: ""` 之 Target 啟用時，不產生任何 `AGENTS.md` 且不報錯。 | FR-01, EC-02 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-04** | 單元測試 | 驗證多 Target 共享相同 `agents_md` 時（如 antigravity + codex），軟合併僅執行一次且無衝突。 | FR-02, EC-01 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **FT-05** | 單元測試 | 驗證 Target 停用時（remove target），其專屬 `agents_md` 檔案被安全 Pruning 清理。 | FR-04, EC-01 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **ET-01** | 邊界測試 | 驗證軟合併時既有檔案之非 YSCB 區塊（使用者自訂規則）100% 完整保留。 | FR-02, EC-01 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **ET-02** | 邊界測試 | 驗證所有 Target 的 `agents_md` 皆為空字串時，正常輸出其他資產，Manifest 不包含 rules 檔案。 | EC-04 | `python yscb.py dev test agents-workflow -k test_publisher` |
| **RT-01** | 全模組回歸 | 全生態系 4 大模組全量迴歸測試 100% Passed。 | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_initial_release_persists_fingerprint` 通過，Manifest 記錄 32 檔案清冊。 | 2026-08-31 17:41 |
| **FT-02** | `Passed` | `test_ft_07_custom_agents_md_projection` 通過，`CLAUDE.md` 包含完整 YSCB 標記區塊。 | 2026-08-31 17:41 |
| **FT-03** | `Passed` | `test_ft_08_empty_agents_md_skips_output` 通過，`agents_md: ""` 略過規範檔輸出。 | 2026-08-31 17:41 |
| **FT-04** | `Passed` | `test_ft_09_multi_target_shared_agents_md` 通過，多 Target 共享同檔軟合併冪等。 | 2026-08-31 17:41 |
| **FT-05** | `Passed` | `test_ft_05_local_by_default_and_proj_flag` 通過，Target 停用時精確 Pruning。 | 2026-08-31 17:41 |
| **ET-01** | `Passed` | `test_ft_05_agents_md_soft_merge_diff` 通過，非 YSCB 區塊（使用者自訂規則）100% 保留。 | 2026-08-31 17:41 |
| **ET-02** | `Passed` | `test_ft_08_empty_agents_md_skips_output` 通過，純工作流輸出無 rules 檔案殘留。 | 2026-08-31 17:41 |
| **RT-01** | `Passed` | 全模組迴歸測試 **275/275 Passed (100% Ready, 3.474s)**。 | 2026-08-31 17:41 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：在專案根目錄執行 `python yscb.py agents-workflow release`，檢查 `AGENTS.md` 是否正確生成/更新且格式工整；切換 Target 驗證 `CLAUDE.md` 或無規範檔狀態。
