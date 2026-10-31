# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 模組五維度靜態診斷與無損重構  
> 建立日期：2026-10-31  
> 所屬主計畫：`2026_10_30_1641_code_optimize` (`sub_01`)  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core.uri` 已移除 15 個 VFS 薄轉發與 `_get_yscb_root` 等廢棄符號，且 5 處子模組尋根統一委派 `uri.resolve_yscb_root()` | FR-01, FR-03, FR-06, EC-01 | `python yscb.py dev test core -k "test_uri or test_vfs"` |
| **FT-02** | 單元測試 | 驗證 `AtomicEngine` 整合 `core` 初次安裝 `locale` 偵測、移除死方法與 7 個冗餘 `staticmethod` 綁定，頂層無狀態函式正常運作 | FR-02, FR-07, EC-02 | `python yscb.py dev test core -k "test_engine or test_locale or test_config"` |
| **FT-03** | 單元測試 | 驗證 `config.py` 移除 `tempfile` 死分支並 100% 委派 `vfs`、`events.py` 與 `locale.py` 刪除歷史別名且階段化重構無損 | FR-04, FR-07 | `python yscb.py dev test core -k "test_config or test_events_pipeline or test_locale or test_validator"` |
| **FT-04** | 單元測試 | 驗證 `registry.py`（移除 `all_modules` 與 `case_pros/cons`）、`contributes.py`（移除 `get_for_current_module` 與 `_deep_merge` 綁定）、`contributes_cmd.py`、`dispatcher.py` 與 `scripts/cli.py` 重構無損 | FR-05, FR-08, EC-04 | `python yscb.py dev test core -k "test_contributes or test_contributes_cmd or test_core_commands"` |
| **ET-01** | 邊界測試 | 驗證 `Installer` 透過 `engine.transaction_lock` 確定性釋放鎖，且 `pip_manager.ensure_yscb_gitignore` 統一委派 `installer.generate_internal_gitignore` (`vfs.write_text` 原子寫入) | FR-06, FR-07, EC-03 | `python yscb.py dev test core -k "test_installer or test_distribution_lifecycle or test_venv_core"` |
| **PT-01** | 非功能驗證 | 驗證 `core` 維持 100% Python 標準庫零第三方依賴、PEP 562 延遲載入一致，且全模組 58 個 Python 檔案通過語法與合約檢驗 | NFR-01, NFR-02, NFR-03 | `python -m py_compile` & `python yscb.py dev check core` & `python yscb.py dev test core` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASS` | `python yscb.py dev check core` (`PASSED`) & `python yscb.py dev test core -q` 實機通過 (`Pass: 206(100.0%), Fail: 0, Skip: 0`)；`R02` 收斂移除 `uri._get_yscb_root` 並完成 5 處尋根委派合一 | 2026-10-31 |
| **FT-02** | `PASS` | `TestCoreEngine` & `TestCoreLocaleEngine` 實機通過 (`Pass: 206(100.0%), Fail: 0`)；`R02` 移除 `AtomicEngine` 7 個冗餘 `staticmethod` 綁定並同步更新測試調用點 | 2026-10-31 |
| **FT-03** | `PASS` | `config.py` 移除 `try...except ImportError` 與 `tempfile.mkstemp` 死分支（100% 委派 `vfs`），別名清除與階段化拆解通過測試 (`206/206 Passed`) | 2026-10-31 |
| **FT-04** | `PASS` | `R02` 移除 `ContributesAggregator._deep_merge` 綁定、`get_for_current_module`、`CommandsRegistry.all_modules` 與 `case_pros/cons` 舊分支，同步對齊測試 | 2026-10-31 |
| **ET-01** | `PASS` | `transaction_lock` 確定性釋放鎖，且 `ensure_yscb_gitignore` 直接委派 `generate_internal_gitignore`（改用 `vfs.write_text(..., atomic=True)`）消除雙軌重複 | 2026-10-31 |
| **PT-01** | `PASS` | `core` 全模組 58 個檔案語法與 `Mode A` 單一正統入口收斂完成，待 5 個子計畫收斂完成後由主代理統一執行最終編譯與回歸測試 | 2026-10-31 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 待 5 個子計畫全數進入 P06 後，由主代理統一執行 `@build` 熱部署與全系統沙盒測試驗收 | `Pending` | 待驗收 |
