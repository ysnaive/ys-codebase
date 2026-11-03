# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Server 與 Daemon 生命週期穩健性修復 (sub_01_server_daemon_robustness)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Confirmed  
> 模型：Claude Opus 5.5 (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 [R01_issue_triage.md](../R01_issue_triage.md) 修復 T-01, T-02, T-05, T-08, T-12, T-13, T-21，並遵循 [umbrella_overview.md](../umbrella_overview.md) §1.1 決策 UD-01 ~ UD-05。
- **核心目標**：
  - T-01 (P0)：worker 卡住時 dispatch 與 `restart_worker` 不再因 `_dispatch_lock` + 無逾時 `readline()`（`master.py:494`, `537`, `395`）全面死鎖。
  - T-02 (P1)：POSIX 容器/沙盒啟發式偵測（UD-02）+ `YSCB_FORCE_DAEMON=1` 覆寫；提示不改 exit code（UD-01）；`server start -d` readiness 逾時且進程已死回傳 1（UD-03）。
  - T-05 (P1)：worker 以獨立 session/process group 啟動，`kill_process_tree` 可殺至孫行程；移除會搶 Popen 回收之 `os.waitpid`。
  - T-08 (P1)：worker 就緒等待 `join(3.0)`（`master.py:648`）改為可設定，失敗以明確錯誤回報（非回傳 PID 0 被誤用）。
  - T-12 (P2)：`dispatcher.py:427` `exec_module` 納入例外攔截；`yscb.py:1222-1226` `except ImportError` 範圍收斂至 `from core.commands import dispatch`。
  - T-13 (P2)：`_cleanup_state` 不刪 `daemon.lock`；`lock.py:54` EEXIST 有限重試（UD-05）。
  - T-21 (P2)：`config://server` 新增 `require_server_for_agents`（預設 `false`），為 `true` 時 daemon 不在即印 [BLOCKER] 並回傳非零、不冷派發（UD-04）；統一 [BLOCKER] 文案與 `yscb-cli-guide` 文件。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 組態讀取復用 `dispatcher._read_server_spawn_config`（擴充回傳欄位，不另造讀取器）。
  - 守門提示復用 `_print_agent_daemon_blocker`（參數化 strict / advisory 兩種文案）。
  - daemon 存活判定復用 `_is_server_daemon_active_or_locked`。
  - 程序樹終止復用 `core.platform.process.kill_process_tree`；環境覆寫沿用既有 `YSCB_NO_DAEMON` 讀取模式。
- **邊界排除 (Explicitly Excluded)**：
  - Windows Job Object 程序樹管理（T-05 Windows 分支，Y-04 估 +80 LOC）。
  - T-03 worker 全域 cwd/environ 隔離（歸 sub_03）。
  - T-25 `_tasks_executed`、T-39 streamer flush、T-40 `_try_lock_fd`（歸 sub_04；T-40 若實作中發現與 T-13 同檔強耦合，再提請併入）。
  - `dispatcher` 之 `importlib.invalidate_caches()`（BR 推論未證實，僅在 T-12 例外訊息中保留原始錯誤，不加推測性修補）。
- **架構影響範圍**：`core`（`commands/dispatcher.py`, `platform/process.py`, `platform/lock.py`）、`server`（`master.py`, `scripts/cli.py`, `configurable/config.project.json`）、根目錄 `yscb.py`、`agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`、`docs/server/`、`docs/core/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 沿用主計畫 UD-01 ~ UD-05，不重議。
- **[P00:DR-02]** 本子計畫分流為 Full Track（跨 `core`/`server`/根 `yscb.py`，新增組態鍵，預估 > 100 LOC）。
- **[P00:DR-03]**（Q1 定案）T-01 不設 dispatch 總逾時；`restart_worker` / `stop` 搶占式先強殺卡住之 worker（解除阻塞 `readline()`）再取 `_dispatch_lock` 接手。`server status` 新增回報「目前是否正在執行指令（module / args / 已執行秒數）」；`server status` 之 contributes `server_compatible` 由 `true` 改為 `false`（強制冷派發，不排隊於 `_dispatch_lock` 之後）。
- **[P00:DR-04]**（Q2 定案）嚴格模式之擋下依據為 contributes 指令級 `server_compatible`（`registry.py:158`）：僅 `server_compatible=true` 之指令於熱派發不可用時 [BLOCKER] + 非零；`server_compatible=false`（僅限冷派發）指令一律照常冷派發，不另立豁免清單。對所有呼叫者一律生效。組態鍵更名（取代 `require_server_for_agents`，見 §3 Q2'）。
- **[P00:DR-06]**（Q2' 定案）組態鍵命名為 `strict_hot_dispatch`（bool，預設 `false`），取代文件中之 `require_server_for_agents`。
- **[P00:DR-07]**（Q3 定案，取代主計畫 UD-02 之方案 B）採方案 D 實證回收偵測：「試過才知道」——以上一次 auto-spawn 之 daemon 是否未經正常關閉即消失為依據，同一 `env_fingerprint` 連續 2 次即判不可常駐並改印 [BLOCKER]（exit code 不變）；正常關閉一次即清除判定；保留 `YSCB_FORCE_DAEMON=1` 強制可常駐與 `YSCB_NO_DAEMON` 強制不可常駐。
- **[P00:DR-08]**（Q4 定案）worker 採兩段式握手：`worker_alive`（`worker_alive_timeout_sec` 預設 5.0）→ `warming`（存活即無上限等待 `worker_ready`，`server status` 顯示預熱秒數，派發排隊）。
- **[P00:DR-05]**（Q5 定案）沙盒回合結束殘留之 `daemon.json` 由既有 stale 清理處理，不新增機制。

---

## 3. 開放議題與確認紀錄

- **全部議題已定案**：Q1→DR-03、Q2→DR-04、Q2'→DR-06、Q3→DR-07、Q4→DR-08、Q5→DR-05。以下保留評估紀錄。

- **Q2'（組態鍵命名）**：語意為「`server_compatible` 指令必須走熱派發」。候選：
  - **推薦** `strict_hot_dispatch`（bool，預設 `false`）
  - `require_hot_dispatch`
  - `forbid_cold_fallback`

- **Q3（T-02 重新評估）**：原方案 B（容器特徵偵測）之根本缺陷：「是容器」不等於「會回收背景進程」，devcontainer / Codespaces 誤判、無特徵沙盒漏判，且特徵清單需長期維護。重新評估如下：

  | 方案 | 判定依據 | 誤判 | 漏判 | 代價 |
  |---|---|---|---|---|
  | B 容器特徵（原案） | 環境標記檔 / cgroup | 高（devcontainer 等） | 有 | 零延遲 |
  | **D 實證回收偵測（推薦）** | 上一次 auto-spawn 之 daemon 是否「未經正常關閉即消失」 | 極低 | 首次 1 次 | 首次白 spawn 一次 |
  | E 啟動時存活探針 | spawn 一個哨兵子進程並等它存活 | — | 無法偵測「回合結束才回收」 | 每次延遲 |

  **方案 D 機制**：
  1. auto-spawn 時於 `cache://server/spawn_probe.json` 記錄 `{pid, spawned_at, env_fingerprint}`（`env_fingerprint` = hostname + `sys.platform`，使 Windows Host 與 Linux Guest 共用 virtiofs 時互不污染）。
  2. daemon 正常關閉（`stop` / idle TTL / reload）時寫入 `clean_exit=true`。
  3. 下次 CLI：若記錄之 pid 已死、無 `clean_exit`、且 daemon 不活躍，判定為「被環境回收」，累計次數；連續 **2 次**後將該 `env_fingerprint` 判為「不可常駐」，之後不再 spawn，改印 [BLOCKER]（遵循 UD-01，exit code 不變）。
  4. 任何一次 daemon 存活至正常關閉即清除判定。`YSCB_FORCE_DAEMON=1` 無條件覆寫為可常駐；既有 `YSCB_NO_DAEMON` 維持強制不可常駐。

  > 結論：建議以 D 取代 UD-02 之 B（`YSCB_FORCE_DAEMON=1` 保留）。是否同意？

- **Q4（T-08 澄清）**：是，但分兩段，不再以單一 3 秒定生死：
  - **現況**：worker 必須在 3 秒內完成「載入 contributes + 啟動全部背景服務」才送出 `worker_ready`；重型服務啟動較慢時，即使 worker 健康也會被殺。
  - **推薦：兩段式握手**
    1. worker 一啟動（尚未載入任何服務）立即送 `worker_alive`，master 以短逾時（`worker_alive_timeout_sec`，預設 `5.0`）確認進程確實喚醒；逾時才判定失敗並明確回報。
    2. 收到 alive 後進入 `warming` 狀態，等待 `worker_ready` 不設硬性上限（只要進程存活）；期間 `server status` 顯示 `Worker: warming (已預熱 N 秒)`，派發請求排隊等待預熱完成。
  - 替代：維持單段，僅把 3 秒改為可設定（預設 10 秒）——較簡單，但慢服務仍可能被誤殺。
