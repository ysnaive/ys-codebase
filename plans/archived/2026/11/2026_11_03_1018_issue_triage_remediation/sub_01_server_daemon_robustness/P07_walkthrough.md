# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Server 與 Daemon 生命週期穩健性修復  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Claude Opus 5.5 (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：修復主計畫 R01 之 T-01 (P0)、T-02、T-05、T-08 (P1)、T-12、T-13、T-21 (P2)：
  - 搶占式 worker 重啟/停止消除 dispatch 死鎖，`server status` 冷派發並回報執行中指令。
  - 兩段式 worker 握手（alive → warming → ready）取代寫死 3 秒就緒等待。
  - 以「試過才知道」之實證回收偵測判定能否背景常駐（`YSCB_FORCE_DAEMON` / `YSCB_NO_DAEMON` 覆寫），不可常駐時提示不改 exit code。
  - `strict_hot_dispatch` 嚴格模式依 contributes `server_compatible` 阻斷，僅對未送達請求重試。
  - `daemon.lock` 不再刪除並加 EEXIST 重試；`exec_module` 例外與 `yscb.py` ImportError 誤報修正；POSIX worker 程序樹完整終止。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | `except ImportError` 僅包匯入 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | strict 分流、`_HotDispatchResult`、blocker 參數化、exec_module 攔截、spawn 紀錄、task_finish 錯誤輸出 |
| `ys_codebase/source/core/core/platform/daemon_probe.py` | New | 實證回收偵測 |
| `ys_codebase/source/core/core/platform/process.py` | Modify | `can_spawn_background_daemon(yscb_root)`、`terminate_popen_tree` |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | EEXIST 有限重試 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出 |
| `ys_codebase/source/server/server/master.py` | Modify | 搶占、兩段握手、current_task、WorkerSpawnError、保留鎖檔、clean exit、bind_master_pid |
| `ys_codebase/source/server/server/worker.py` | Modify | `worker_alive` |
| `ys_codebase/source/server/server/config.py`, `configurable/config.project.json` | Modify | `strict_hot_dispatch`、`worker_alive_timeout_sec` |
| `ys_codebase/source/server/contributes/core.json` | Modify | `status.server_compatible=false` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 儀表板、readiness 回傳值、強制 stop 標記 clean exit |
| `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md` | Modify | 守門處置說明 |
| `ys_codebase/source/core/tests/test_core_commands.py`, `test_platform.py` | Modify | 新增測試 |
| `ys_codebase/source/server/tests/test_server.py`, `test_server_logging.py` | Modify | 新增/對齊測試 |
| `docs/server/{README,daemon_architecture,hot_reload_and_services,DESIGN_NOTES}.md`, `docs/core/platform.md` | Modify | 三層文檔 |
| `CHANGELOG.md` | Modify | 結案摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 238/238（基線 222）、`server` 52/52（基線 41）；`dev check` core / server / agents-workflow PASS。
- **實機 UX / 人工驗證**：於臨時兄弟目錄 `/workspace/yscb-uat`（virtiofs）以 `core@build` / `server@build` 代驗 UX-01 ~ UX-04，開發者確認 `[測試通過]`；代驗觀察 OBS-01 / OBS-02 已於本計畫修正並經盲審通過；臨時目錄已刪除。
- **冷眼盲審**：Pre-UX 首審 FAILED（2 Major）→ 修正後 PASSED；P07 OBS 修正盲審 PASSED。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | sub_01 結案摘要 |
| **中觀 (Meso)** | `docs/server/README.md` | 已交付 | 新組態鍵、指令行為表、POSIX 判定與覆寫環境變數 |
| **中觀 (Meso)** | `docs/server/daemon_architecture.md`, `hot_reload_and_services.md`, `docs/core/platform.md` | 已交付 | 兩段握手、搶占、回收偵測、strict 流程、daemon_probe API |
| **中觀 (Meso)** | `docs/server/DESIGN_NOTES.md` | 已交付 | DN-10 鎖檔不刪、DN-11 strict 不重試已送達請求 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 新增/變更介面 Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

> 遺留事項：DEV-01（非嚴格模式熱派發 120s 逾時後冷派發重複執行）移交 sub_04；`dev test` 沙盒偶發讀到舊 core 副本（實作子代理觀察，重跑即通過）待 sub_04 評估。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(server,core): harden daemon lifecycle with preemptive restart, two-stage worker handshake and strict hot dispatch

- preempt stuck worker on restart/stop; status runs cold and reports current task
- worker_alive -> warming -> worker_ready handshake (worker_alive_timeout_sec)
- empirical reaping detection (daemon_probe) with YSCB_FORCE_DAEMON override
- strict_hot_dispatch blocks server_compatible commands, retries only unaccepted requests
- keep daemon.lock on stop and retry EEXIST; guard exec_module; narrow yscb.py ImportError
- POSIX worker process-group termination via terminate_popen_tree
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

