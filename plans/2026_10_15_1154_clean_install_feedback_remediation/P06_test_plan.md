# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `yscb.py` 之 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL` 常數正確，`_resolve_self_update_target_url` 預設直接返回 `DEFAULT_SELF_UPDATE_URL`，指定 `--url` 時正確覆寫 | FR-01 | `python yscb.py dev test core -k test_self_update_url` |
| **FT-02** | 單元測試 | 驗證 `agents-workflow release-target` 支援 `--add claude --proj` 與 `add claude --proj` 雙向語法，且目標名稱正確傳入 | FR-02, FR-03 | `python yscb.py dev test agents-workflow -k test_release_target_cli_syntax` |
| **FT-03** | 單元測試 | 驗證 `agents-workflow release-target` 支援 `--remove claude --proj` 與 `remove claude --proj` 雙向語法 | FR-02, FR-03 | `python yscb.py dev test agents-workflow -k test_release_target_cli_syntax` |
| **FT-04** | 單元測試 | 驗證 `ReleasePublisher._soft_unmerge_agents_text` 正確剝離 YSCB 區塊，並保留使用者自訂規範 | FR-05, EC-03 | `python yscb.py dev test agents-workflow -k test_soft_unmerge` |
| **FT-05** | 整合測試 | 驗證切換 Target 移除 `antigravity` 時，含使用者自訂內容的 `AGENTS.md` 不被刪除，僅 YSCB 區塊被清除 | FR-05, EC-03 | `python yscb.py dev test agents-workflow -k test_prune_stale_agents_md` |
| **FT-06** | 整合測試 | 驗證切換 Target 移除 `antigravity` 時，若 `AGENTS.md` 完全為預設 YSCB 產物，檔案被乾淨清理 | FR-05, EC-04 | `python yscb.py dev test agents-workflow -k test_prune_stale_agents_md` |
| **RT-01** | 回歸測試 | 全生態系現有單元測試 100% 通過（`core`, `dev`, `server`, `knowledge-db`, `agents-workflow`） | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_self_update_url` 通過 (0.12s)；`test_resolve_self_update_url` 通過。解耦常數與覆寫優先權正確 | 2026-10-15 |
| **FT-02** | `Passed` | `test_ft_05_release_target_cli_syntax` 通過 (0.05s)。`--add` 與 `add` 雙向語法正確傳入 Target 名稱與 `--proj` | 2026-10-15 |
| **FT-03** | `Passed` | `test_ft_05_release_target_cli_syntax` 通過 (0.05s)。`--remove` 與 `remove` 雙向語法正確傳入與 `--proj` | 2026-10-15 |
| **FT-04** | `Passed` | `test_ft_15_soft_unmerge_agents_text` 通過 (0.05s)。精準剝離 YSCB 區塊與空樣板，自訂內容完好保留 | 2026-10-15 |
| **FT-05** | `Passed` | `test_ft_16_prune_stale_agents_md` 通過 (0.23s)。切換 Target 時含使用者自訂內容之 `AGENTS.md` 絕不刪檔並寫回乾淨自訂內容 | 2026-10-15 |
| **FT-06** | `Passed` | `test_ft_16_prune_stale_agents_md` 通過 (0.23s)。切換 Target 時若 `AGENTS.md` 純為預設樣板則乾淨刪除 | 2026-10-15 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` 562/562 全庫測試 100% 通過 (16.79s，涵蓋全 5 模組) | 2026-10-15 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端執行 `python yscb.py agents-workflow release-target --add claude --proj`，確認無報錯且提示 Target 已啟用並發布成功 | `[跳過/免測]` | 開發者指示免測 (2026-10-15) |
