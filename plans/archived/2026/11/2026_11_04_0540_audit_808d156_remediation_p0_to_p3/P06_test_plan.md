# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_04_0540_audit_808d156_remediation_p0_to_p3  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `InterProcessLock` 檔案描述符設定為不可繼承 (`os.get_inheritable(fd) == False`)、`ServerLogger.read_tail_chunks` 於日誌輪替/截斷時自動歸零偏移量並讀取新內容，以及 `_perform_self_restart` 標準移交序列 | FR-01 | `python yscb.py dev test --target=server:TestServerLogging` |
| **FT-02** | 單元測試 | 驗證 `vscode-support` 之 `strip_jsonc` 正確剝離 `//`、`/* */` 與尾隨逗號並保留字串內 URL，偵測到 JSONC 時自動備份至 `.vscode/settings.json.bak` 後完成軟合併與原子寫入 | FR-02, EC-01 | `python yscb.py dev test --target=vscode-support:TestVSCodeSupport` |
| **FT-03** | 單元測試 | 驗證 `core.vfs` 之 `robust_rmtree`（含唯讀位元自動 `chmod` 重試）、`robust_replace`（含跨分區 `EXDEV` 暫存回退）與成對 `os.path.realpath` 邊界校驗 | FR-03, EC-02, EC-03 | `python yscb.py dev test --target=core:TestVFS` |
| **FT-04** | 單元測試 | 驗證 `PipManager` 與 `GrammarProvisioner` 透過 `InterProcessLock(.pip_install.lock)` 進行跨進程排他保護與獲鎖後 Double-Checked `importlib.import_module` 檢核 | FR-04 | `python yscb.py dev test --target=ast:TestProvisionerAndJIT` |
| **FT-05** | 單元測試 | 驗證同進程跨模組腳本 `_yscb_mod_{mod_pkg}_{stem}` 命名空間隔離、`run_subprocess_with_tree_timeout` 超時進程樹清理、`file-space` `st_ctime_ns` Racy Stat Gate 與 `CallGraphIndex` 孤兒節點移除 | FR-05, EC-04, EC-05 | `python yscb.py dev test core dev file-space ast -q` |
| **FT-06** | 單元測試 | 驗證 `ast_engine.graph` (`networkx`) 與 `knowledge_db.embedding` (`numpy`) 頂層 Lazy Import、`contributes._read_json_cached` 快取、`_trace_parser` 串流單行上限與 `DeterministicSymbolResolver` / `TopologyLinker` 二級倒排雜湊索引 | FR-06, EC-06, NFR-01, NFR-02 | `python yscb.py dev test core ast knowledge-db agents-workflow -q` |
| **ET-01** | 邊界測試 | 驗證 `.vscode/settings.json` 為不可恢復之損毀語法時，自動備份至 `.vscode/settings.json.bak` 並回傳 `False`，絕不以 `{}` 覆寫原檔 | FR-02, EC-01 | `python yscb.py dev test --target=vscode-support:TestVSCodeSupport.test_et_01_jsonc_settings_preserved_and_hook_lifecycle` |
| **ET-02** | 邊界測試 | 驗證同秒級同長度覆寫 (`AAAA\n` $\to$ `BBBB\n`) 觸發 Racy Stat Gate 重新計算雜湊並標記 `modified`，且懸空符號連結不導致掃描崩潰 | FR-05, EC-04, EC-05 | `python yscb.py dev test --target=file-space:TestFingerprintScannerSelfHealing.test_et_02_racy_stat_gate_and_broken_symlink_safety` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestServerLogging` 9 項測試全數通過（含 `test_non_inheritable_lock_fd_and_log_tail_rotation_reset`） | 2026-11-04 06:00 |
| **FT-02** | `Passed` | `TestVSCodeSupport` 全數通過，確認 JSONC 剝離軟合併與 `.bak` 備份運作正常 | 2026-11-04 06:00 |
| **FT-03** | `Passed` | `TestVFS` 11 項測試全數通過（含 `test_robust_replace_exdev_fallback_and_contributes_json_cache`） | 2026-11-04 06:00 |
| **FT-04** | `Passed` | `TestProvisionerAndJIT` 與 `core` 微環境鎖測試全數通過（修復 `install_packages` 呼叫 `ensure_venv` 之同進程鎖重入順序後 `@build` 安裝順暢完成） | 2026-11-04 06:10 |
| **FT-05** | `Passed` | 全倉 8 模組 141 項測試 `Pass: 141(100.0%), Fail: 0, Skip: 0` | 2026-11-04 06:00 |
| **FT-06** | `Passed` | `dev check --all` (8/8 PASSED)、`contributes check` (26 files valid) 與 141 項單元測試 100% 通過 | 2026-11-04 06:10 |
| **ET-01** | `Passed` | `test_et_01_jsonc_settings_preserved_and_hook_lifecycle` 驗證損毀語法不覆寫原檔且產生 `.bak` | 2026-11-04 06:00 |
| **ET-02** | `Passed` | `test_et_02_racy_stat_gate_and_broken_symlink_safety` 驗證同秒同長度改寫檢出 `modified` 且壞連結零崩潰 | 2026-11-04 06:00 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `AUD-01` ~ `AUD-14` 共 14 項審計處方之實作、全倉 8 模組 `@build` 熱部署狀態 (`server status` 與 `vscode-support status`) 及 141 項自動化測試報告 | `[測試通過]` | 開發者指示於臨時兄弟目錄 `/workspace/yscb-uat-audit-808d156` 執行 0-to-1 安裝與涵蓋全修復範圍之實機指令驗證（含 `init`、`@build` 安裝、virtiofs `lib64` venv 相容性、`vscode-support sync/revert` JSONC `.bak` 保護、`ast` 孤兒節點回收、`knowledge-db` 檢索與 `core` 236 項全量回歸），確認「通過」 |

