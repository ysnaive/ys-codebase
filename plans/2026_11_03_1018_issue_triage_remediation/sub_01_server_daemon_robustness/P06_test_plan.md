# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Server 與 Daemon 生命週期穩健性修復  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Passed  
> 模型：Claude Opus 5.5 (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 整合 | 卡住之 dispatch 被 restart 搶占：dispatch 回傳 1 且錯誤為 `Worker terminated by restart/stop`，restart 於時限內返回、無死鎖；status 期間回報 current_task | FR-01, FR-02, EC-01, EC-02 | `dev test server` (`test_server.py`) |
| **FT-02** | 單元 | `get_status_dict` 不取 `_dispatch_lock`、含 `current_task`；`status.server_compatible=false`；儀表板顯示 Current Task 與 WARMING | FR-02, FR-10 | `test_server.py` |
| **FT-03** | 單元 | 實證回收偵測：2 次非正常死亡 → 不可常駐；clean exit 歸零；損壞檔視為無紀錄；fingerprint 隔離；延遲探鎖呼叫次數 | FR-03, EC-03, EC-04, EC-05, NFR-02 | `dev test core` (`test_platform.py`) |
| **FT-04** | 單元 | `can_spawn_background_daemon` 判定順序 FORCE → NO_DAEMON → POSIX 實證 | FR-04 | `test_platform.py` |
| **FT-05** | 單元 | 非嚴格模式不可常駐時印 advisory BLOCKER 一次、照常冷派發 | FR-05, FR-08 | `test_core_commands.py` |
| **FT-06** | CLI | `server start -d` 逾時：pid 已死回 1、仍存活回 0 | FR-06 | `test_server.py` |
| **FT-07** | 單元 | strict：可常駐時 spawn+重試成功；失敗印 strict BLOCKER 回 1；`server_compatible=false` 不受影響；`enable=false` 失效；已送達後失敗不重試 | FR-07, EC-06 | `test_core_commands.py` |
| **FT-08** | 單元 | `_hot_dispatch_attempt` 分類：refused/HTTPError=未送達；timeout/reset/中途中斷/無 task_finish=已送達 | FR-07 | `test_core_commands.py` |
| **FT-09** | 整合 | 兩段式握手：alive 先於 ready、warming 期間 dispatch 等待後成功；alive 逾時拋 `WorkerSpawnError`；warming 中死亡 dispatch 回 1 | FR-09, EC-07, EC-08 | `test_server.py` |
| **FT-10** | 單元 | `terminate_popen_tree` 升級 SIGKILL 並終止孫行程；master 以 `proc.poll()` 判活 | FR-11 | `test_platform.py`, `test_server.py` |
| **FT-11** | 單元 | `exec_module` 拋 SyntaxError → 錯誤訊息、移除半初始化模組、回 1 | FR-12, EC-09 | `test_core_commands.py` |
| **FT-12** | 單元 | `lock.acquire` EEXIST 重試成功 / 3 次後拋原錯 / 其他 errno 不重試 | FR-13, EC-10 | `test_platform.py` |
| **FT-13** | 整合 | stop 後 `daemon.lock` 保留、clean exit 已標記；`stop --force` 與逾時強殺亦標記 | FR-13, FR-03, EC-11 | `test_server.py` |
| **FT-14** | 單元 | `restart_worker` 組態載入失敗 → 不殺不 spawn；`master.start` 瞬態探鎖競爭後成功啟動 | FR-01 | `test_server.py` |
| **RT-01** | 回歸 | core 全量 | NFR-01, NFR-03 | `python yscb.py dev test core -q` |
| **RT-02** | 回歸 | server 全量 | NFR-03 | `python yscb.py dev test server -q` |
| **RT-03** | 靜態 | 合規檢查 core / server / agents-workflow | NFR-01 | `python yscb.py dev check <mod>` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-14** | `Passed` | 涵蓋於 RT-01 / RT-02 全量執行 | 2026-11-03 11:00 |
| **RT-01** | `Passed` | core 236/236（基線 222/222） | 2026-11-03 11:00 |
| **RT-02** | `Passed` | server 51/51（基線 41/41）；主代理獨立複跑 48/48（修正前）通過 | 2026-11-03 11:00 |
| **RT-03** | `Passed` | `dev check` core / server / agents-workflow 全數 PASS | 2026-11-03 11:00 |
| **Pre-UX 盲審** | `Passed` | 首審 FAILED（2 Major + 2 Minor，見 P01-05 §5.2），修正後複審 `REVIEW_STATUS: PASSED` | 2026-11-03 11:01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於 Agent 容器沙盒（非 IsDaemon）連續執行 2~3 次 `python yscb.py status`：前 2 次照常完成，之後應出現 advisory [BLOCKER] 且不再背景 spawn，exit code 不變 | `[測試通過]` | Agent 於 `/workspace/yscb-uat` 代驗：本環境背景 daemon 不會被回收（BR 原始現象未重現），改以 SIGKILL 模擬回收 2 次 → 第 2 次後出現 advisory [BLOCKER]、rc=0、`reaped_count=2`；後續正常 stop 後歸零 `clean_exit=true`。開發者 2026-11-03 確認通過 |
| **UX-02** | `config://server/config.project.json` 設 `strict_hot_dispatch: true`，daemon 未啟動時執行 `server_compatible` 指令（如 `python yscb.py uri list`）→ strict [BLOCKER] + 非零；`server start --console`（IsDaemon）後重試成功 | `[測試通過]` | 代驗：daemon 未起時 `uri list` → strict [BLOCKER] rc=1；`server status` 冷派發照常；IsDaemon 啟動 `server start --console` 後 `uri list` rc=0（熱派發）。開發者 2026-11-03 確認通過 |
| **UX-03** | daemon 運行中執行長指令時另開 `python yscb.py server status`：立即返回並顯示 Current Task；`server reload` 能搶占結束卡住之 worker | `[測試通過]` | 代驗：以臨時 `uatsleep` 模組（40s）熱派發中，`server status` 立即顯示 `Current Task: uatsleep sleep`；`server reload` 搶占成功（新 worker PID）、被搶占任務 rc=1。開發者 2026-11-03 確認通過 |
| **UX-04** | `server stop` 後 `.cache/server/daemon.lock` 仍存在，立即 `server start --console` 無 `[Errno 17]` | `[測試通過]` | 代驗：`server stop` 後僅剩 `daemon.lock`（daemon.json 已刪），立即 `server start --console` 成功、無 `[Errno 17]`（`/workspace` 為 virtiofs 掛載，但僅 Guest 單側操作，未涵蓋 Host↔Guest 交錯競態）。開發者 2026-11-03 確認通過 |

### 3.1 代驗觀察事項 (UAT Observations)

- **OBS-01**：`record_spawn` 記錄的是 `yscb.py server start --daemon` 啟動器 pid（會立即退出），而非 master pid；因判定時先檢查 daemon 活躍而結果正確，但語意不精確。
- **OBS-02**：被搶占之熱派發任務客戶端僅得 rc=1，終端未顯示 `Worker terminated by restart/stop` 錯誤訊息（僅 server log 有）。
