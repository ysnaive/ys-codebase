# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `DEFAULT_PROVIDER_URL` 為官方儲存庫，且 `_resolve_self_update_target_url` 正確將 `.../release` 轉換為 repo 根目錄之 `yscb.py`，支援 `--url` 覆寫 | FR-01 | `test_resolve_self_update_url` |
| **FT-02** | 單元測試 | 驗證 `cmd_self_update` 語法安全防禦（語法錯誤時拒絕覆寫並回退）與標準備份原子替換流程 | FR-01, EC-03, EC-04 | `test_cmd_self_update_atomic_replacement` |
| **FT-03** | 單元測試 | 驗證本地 Provider 包含多個 core 版本壓縮包時，`_discover_latest_core` 正確解算最高 semver 版本 | FR-02 | `test_discover_latest_core_local` |
| **FT-04** | 單元測試 | 驗證遠端 Provider `index.json` 解析與網路異常/404 時之優雅防禦 | FR-02, EC-01 | `test_discover_latest_core_remote` |
| **FT-05** | 單元測試 | 驗證全新 `cmd_init` 未提供 `yscb_root` 參數時，自動預設為 `".yscb"` 並建立組態檔 | FR-03 | `test_cmd_init_default_yscb_root` |
| **FT-06** | 單元測試 | 驗證 `cmd_init --fix` 在設定檔已存在且 `.modules/core` 缺失時觸發自癒修復，重新解壓最新 core 並連鎖調用 reload | FR-03 | `test_cmd_init_fix_heals_and_reloads` |
| **FT-07** | 單元測試 | 驗證 `generate_internal_gitignore` 產出之內容完整包含 `yscb.py.bak` 與 `*.bak` 規則且具備冪等性 | FR-04 | `test_internal_gitignore_includes_bak` |
| **FT-08** | 單元測試 | 驗證 `UpdateChecker.invalidate_cache` 正確清除快取條目，且模組安裝/升級後快取即時更新 | FR-05 | `test_update_checker_invalidation` |
| **FT-09** | 單元測試 | 驗證自舉指令 `init` 與 `self-update` 支援 `-h`/`--help` 獨立幫助渲染（不經 core 轉發） | FR-01, FR-03 | `test_init_and_self_update_help` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_resolve_self_update_url` 驗證 URL 解析與覆寫成功 | 2026-09-13 18:10 |
| **FT-02** | `Passed` | `test_cmd_self_update_atomic_replacement` 語法校驗防禦與備份回滾通過 | 2026-09-13 18:10 |
| **FT-03** | `Passed` | `test_discover_latest_core_local` 本地 semver 探測成功 | 2026-09-13 18:10 |
| **FT-04** | `Passed` | `test_discover_latest_core_remote` 遠端 index.json 解析與 404 容錯通過 | 2026-09-13 18:10 |
| **FT-05** | `Passed` | `test_cmd_init_default_yscb_root` 預設 .yscb 根目錄驗證通過 | 2026-09-13 18:10 |
| **FT-06** | `Passed` | `test_cmd_init_fix_heals_and_reloads` core 缺失自癒並連鎖 reload、core 完好時提示無需修復 (--force 可強制刷新) 驗證通過 | 2026-09-13 18:15 |
| **FT-07** | `Passed` | `test_internal_gitignore_includes_bak` yscb.py.bak 與 *.bak 忽略規則通過 | 2026-09-13 18:10 |
| **FT-08** | `Passed` | `test_update_checker_invalidation` 快取失效與安裝後自動清除通過 | 2026-09-13 18:10 |
| **FT-09** | `Passed` | `test_init_and_self_update_help` 驗證自舉指令 -h/--help 獨立渲染，拒絕 core 前綴轉發通過 | 2026-09-13 18:35 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端執行 `python yscb.py init -h`、`python yscb.py self-update -h`、`python yscb.py init --fix`，驗證宿主獨立自舉幫助渲染與健全度自癒檢查 | `[測試通過]` | 開發者實機驗收通過；確認 init 與 self-update 為唯二不經 core 轉發的宿主自舉指令 |
