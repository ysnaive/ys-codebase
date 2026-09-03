# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_generate_internal_gitignore` 包含 `/.modules/` 且支援標記區塊軟合併，完整保留宿主自訂與 agents-workflow 規則 | FR-01 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_ft_01_gitignore_soft_merge_and_topology_coexistence` |
| **FT-02** | 單元測試 | 驗證 `module://` 協議精確解析至 `yscb://.modules/` | FR-02 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_ft_02_semantic_uri_resolution_to_dot_modules` |
| **FT-03** | 單元測試 | 驗證 `restore` 命令批量自 provider 還原模組至 `.modules/` | FR-03 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_ft_03_and_04_restore_and_dirty_detection` |
| **FT-04** | 單元測試 | 驗證 JIT 模組同步守門在缺失或版本落後時自動自愈 | FR-04 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_ft_03_and_04_restore_and_dirty_detection` |
| **FT-05** | 規格檢驗 | 驗證 `STANDARDS.md` 空間協議表政策為 `🚫 忽略` 且實體路徑為 `yscb://.modules/` | FR-05 | 檔案結構與關鍵字核驗 |
| **ET-01** | 邊界測試 | 驗證 `installed_modules` 為空時 `restore` 友善安全返回 0 | EC-01 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_et_01_empty_installed_modules_restore` |
| **ET-02** | 邊界測試 | 驗證 provider 缺失時友善提示且安全返回 1，不拋出未捕獲例外 | EC-02 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_et_02_corrupted_provider_restore_handling` |
| **PT-01** | 效能測試 | 驗證 Clean 狀態下 JIT 嗅探守門執行耗時 $\le 2\text{ms}$（實測 $< 0.05\text{ms}$） | NFR-01 | `python yscb.py dev test --target=core:TestRestoreAndJitModules.test_pt_01_clean_state_jit_sniff_latency` |
| **RT-01** | 全量回歸 | 驗證全生態系四大模組 298/298 單元測試 100% 通過 | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASS` | 通過。`test_ft_01_gitignore_soft_merge_and_topology_coexistence`: 成功建立含 `/.modules/` 之標記區塊，並在 `yscb://` == `project://` 拓撲下與自訂規則及 agents-workflow 標記區塊無損軟合併。 | 2026-09-03 10:53 |
| **FT-02** | `PASS` | 通過。`test_ft_02_semantic_uri_resolution_to_dot_modules`: `module://` 與 `module://core` 精確解析至 `yscb://.modules/` 及 `yscb://.modules/core/`。 | 2026-09-03 10:53 |
| **FT-03** | `PASS` | 通過。`test_ft_03_and_04_restore_and_dirty_detection`: 成功自 mock provider 解壓套件並建立鏡像，物化至 `.modules/`。 | 2026-09-03 10:53 |
| **FT-04** | `PASS` | 通過。`test_ft_03_and_04_restore_and_dirty_detection`: 模組缺失時精確標記 Dirty，執行 restore 後自動感知並轉為 Clean。 | 2026-09-03 10:53 |
| **FT-05** | `PASS` | 通過。`docs/_project/STANDARDS.md` 空間協議表第 1 節已更新，Git 政策標記為 `🚫 忽略`。 | 2026-09-03 10:47 |
| **ET-01** | `PASS` | 通過。`test_et_01_empty_installed_modules_restore`: 空清冊時提示「Nothing to restore」並返回代碼 0。 | 2026-09-03 10:53 |
| **ET-02** | `PASS` | 通過。`test_et_02_corrupted_provider_restore_handling`: 缺失 provider 時友好警告「Unable to restore module」並返回代碼 1。 | 2026-09-03 10:53 |
| **PT-01** | `PASS` | 通過。`test_pt_01_clean_state_jit_sniff_latency`: 100 次循環平均嗅探耗時 $< 0.05\text{ms}$，遠低於 2.0ms 上限標準。 | 2026-09-03 10:53 |
| **RT-01** | `PASS` | 通過。`python yscb.py dev test --all` 實機執行：agents-workflow (50/50), core (66/66), dev (52/52), knowledge-db (130/130)，總計 298/298 通過 (4.911s)。 | 2026-09-03 10:54 |

---

## 3. 人工 / UX 驗證 Checkpoint (User Verified)

- [x] **UX-01**：在乾淨環境下執行 `python yscb.py restore`，驗證所有模組順利物化至 `.modules/` 且 CLI 回傳 0。（已驗證通過）
- [x] **UX-02**：手動刪除 `.modules/` 後直接調用任意 CLI 指令（如 `python yscb.py list`），驗證 JIT 自動自愈與順暢執行。（開發者實機驗證通過：觸發 `[yscb:jit-sync]` 自動物化 4 大模組並順暢輸出清單）
