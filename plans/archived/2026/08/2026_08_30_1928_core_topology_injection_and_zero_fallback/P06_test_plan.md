# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `set_yscb_root()` / `get_yscb_root()` 記憶體注入與還原。 | FR-01, EC-01 | `python yscb.py dev test core -k test_yscb_root_injection` |
| **FT-02** | 單元測試 | 驗證 `yscb_scope()` Context Manager 作用域隔離與異常還原。 | FR-01, EC-03 | `python yscb.py dev test core -k test_yscb_scope` |
| **FT-03** | 單元測試 | 驗證 `YSCB_ROOT_DIR` 環境變數注入與優先順序。 | FR-02, EC-02 | `python yscb.py dev test core -k test_yscb_env_injection` |
| **FT-04** | 整合測試 | 驗證 `ConfigManager._get_yscb_root` 委任 `uri._get_yscb_root`，無 while 迴圈與 CWD 污染。 | FR-03 | `python yscb.py dev test core -k test_config_zero_fallback` |
| **FT-05** | 整合測試 | 驗證 `SandboxProvisioner._dispatch_test_hooks` 在雙重 Scope 下執行，零宿主檔案穿透。 | FR-04, EC-04 | `python yscb.py dev test dev -k test_sandbox_hook_isolation` |
| **RT-01** | 全量回歸 | 全生態系四大模組 248+ 套測試案例 100% 通過。 | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Pending` | - | - |
| **FT-02** | `Pending` | - | - |
| **FT-03** | `Pending` | - | - |
| **FT-04** | `Pending` | - | - |
| **FT-05** | `Pending` | - | - |
| **RT-01** | `Pending` | - | - |
| **FT-01** | `Passed` | `test_yscb_root_injection_and_scope` 記憶體注入與還原驗證通過。 | 2026-08-30 19:33 |
| **FT-02** | `Passed` | `yscb_scope` 巢狀作用域與例外 finally 還原驗證通過。 | 2026-08-30 19:33 |
| **FT-03** | `Passed` | `YSCB_ROOT_DIR` 環境變數優先級階梯求值驗證通過。 | 2026-08-30 19:33 |
| **FT-04** | `Passed` | `ConfigManager._get_yscb_root` 委任 `uri._get_yscb_root`，無 while 迴圈與 CWD 回退。 | 2026-08-30 19:33 |
| **FT-05** | `Passed` | `SandboxProvisioner._dispatch_test_hooks` 在雙重 Scope 下執行，零宿主檔案穿透。 | 2026-08-30 19:33 |
| **RT-01** | `Passed` | 全生態系 4 大模組全量全類別 (`ALL Types`) 回歸測試：**252/252 Passed (100% Ready, 0 Failed, 0 Skipped)**。 | 2026-08-30 19:33 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：在多沙盒並發跑測下（`dev test --all`），驗證 `ys_codebase/config/` 下宿主檔案 mtime 完全未被修改，確認零並發競爭。
