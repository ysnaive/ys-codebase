# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **ET-01** | 邊界測試 | 驗證常駐 Server 冷啟動前先執行 `server stop` 清理舊進程，再執行 `server start` 與 `server status` 100% 乾淨拉起 | EC-01 | `python yscb.py server stop` & `python yscb.py server start` |
| **ET-02** | 邊界測試 | 驗證全量沙盒測試與實機指令執行後，`git status` 零未追蹤臨時檔案與零沙盒污染殘留 | EC-02 | `git status --short` |
| **ET-03** | 邊界測試 | 驗證常駐 Server 熱派發狀態下，群組節點未知子命令（如 `python yscb.py config invalid_subcmd`）正確攔截並返回非 0 退出碼 | EC-03 | `python yscb.py config invalid_subcmd` |
| **FT-04** | 整合測試 | 驗證全生態系 `contributes check` 與 `dev check --all` 靜態結構與契約檢驗 0 Error、0 Warning | FR-01 | `python yscb.py contributes check` & `python yscb.py dev check --all` |
| **FT-05** | 整合測試 | 驗證全生態系沙盒回歸測試 `dev test --all -q` 100% Passed、0 Failed、0 Error、0 Unknown | FR-02 | `python yscb.py dev test --all -q` |
| **FT-06** | 整合測試 | 驗證常駐 `server` 啟動後 `ServiceManager` 託管 `knowledge-db-watcher` 為 `running`，多層子命令熱派發與 `server stop` 優雅停機正常 | FR-03 | `python yscb.py server status` / `uri resolve` / `config get` / `knowledge-db status` / `server stop` |
| **FT-07** | 整合測試 | 驗證 `core`、`dev`、`server`、`knowledge-db` 四大模組皆處於最新 `@build` 部署同步狀態 | FR-04 | `python yscb.py list` |
| **FT-08** | 整合測試 | 驗證 8 份已消費 Roadmap 儲備已閉環歸檔於 `sub_01` ~ `sub_04/roadmap.md`，且三層文檔同步對齊 | FR-05 | 檢查 `sub_01`~`sub_04/roadmap.md`、`plans/roadmap/` 與 `docs/` |
| **RT-09** | 回歸測試 | 驗證四大核心模組測試檔收斂總數嚴格為 43 檔（21 + 7 + 3 + 12）且全數通過 | NFR-01 | 統計 `ys_codebase/source/{core,dev,server,knowledge-db}/tests/test_*.py` 檔案數與執行結果 |
| **RT-10** | 回歸測試 | 驗證全模組遵守 `.modules/` 運行時隔離、零 `source/` 路徑注入與 `CmdBags` 契約 | NFR-02 | `python yscb.py dev check --all` & `python yscb.py contributes check` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **ET-01** | `Passed` | `server stop` 確認乾淨狀態後執行 `server start`，Master (PID 170338) 與 Worker (PID 170340, READY) 正常拉起 | 2026-10-24 |
| **ET-02** | `Passed` | `git status --short` 驗證 `cache://dev/sandbox/` 自動清理完畢，工作區零沙盒殘留檔案 | 2026-10-24 |
| **ET-03** | `Passed` | 常駐 Server 運行下執行 `python yscb.py config invalid_subcmd` 返回 `rc: 1` 並輸出 `Unknown subcommand 'invalid_subcmd' for command 'config'` | 2026-10-24 |
| **FT-04** | `Passed` | `contributes check` 驗證 14 份定義檔 100% Valid；`dev check --all` 驗證 5 模組 100% PASSED (0 Warnings, 0 Failed) | 2026-10-24 |
| **FT-05** | `Passed` | 修正 `dev/tester.py` `_run_op_test` 靜默環境變數隔離後，`dev test dev -q --sync` (79/79) 與 `dev test --all --no-build -q` **Pass: 593(100.0%), Fail: 0, Skip: 0** | 2026-10-24 |
| **FT-06** | `Passed` | `server status` 顯示 `[knowledge-db-watcher] : RUNNING`；連續熱派發 6 項多層子命令（`uri resolve`、`config get`、`contributes check`、`knowledge-db status` 等）全數成功；`server stop` 優雅關閉 1 項背景服務並歸檔日誌 | 2026-10-24 |
| **FT-07** | `Passed` | `python yscb.py list` 確認 `core@1.1.0.build`、`dev@1.1.0.build`、`server@1.0.0.build`、`knowledge-db@1.1.0.build`、`agents-workflow@1.1.0.build` 全數處於最新 Installed 狀態 | 2026-10-24 |
| **FT-08** | `Passed` | 確認 `sub_01` ~ `sub_04/roadmap.md` 已完整收錄 8 份已消費路線圖，`plans/roadmap/` 無殘留；清理 `source/server/README.md` 殘留片段，三層文檔 100% 對齊 | 2026-10-24 |
| **RT-09** | `Passed` | 驗證四大模組純化後測試檔共 43 檔（`core`: 21、`dev`: 7、`server`: 3、`knowledge-db`: 12），全數通過 | 2026-10-24 |
| **RT-10** | `Passed` | 全模組通過 `dev check --all` 8 步檢核與 `contributes check`，100% 符合 `.modules/` 隔離與 `CmdBags` 契約 | 2026-10-24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視四大核心模組（`core`、`dev`、`server`、`knowledge-db`）聯合驗收結果（`contributes check` 14 檔全過、`dev check --all` 5 模組全過、`dev test --all -q` 593 項測試 100% 通過、常駐 Server 託管 `knowledge-db-watcher` 與多層子命令熱派發閉環、8 份 Roadmap 歸檔閉環），確認主計畫整體交付符合預期 | `[測試通過]` | 開發者確認通過 (2026-10-24) |
