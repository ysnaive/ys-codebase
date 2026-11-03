# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：三方 Issue 回報查核與分級修復 (Issue Triage Remediation)  
> 建立日期：2026-11-03  
> 計畫狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Claude Opus 5.5 (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：依 [R01_issue_triage.md](./R01_issue_triage.md)（BR / Y / PERF 三方回報經 HEAD `7710f368` 源碼查核合併之 40 項 T-01 ~ T-40 分級表）分主題完成根因修復，並修正原報告誤差（降級、錯誤修法建議）。
- **架構邊界**：
  - 範疇：`yscb.py` 與 `ys_codebase/source/{core,server,dev,file-space,ast,knowledge-db,agents-workflow}/` 及對應 `docs/`、CI 組態。
  - 排除：`.modules/`、`.venv/`、`.mirror/`、`.cache/` 黑盒；`[GATED]` 指令（release / install 非 `@build`）須逐次授權。
  - 原報告修法建議**不得直接照抄**，以 R01 修正後之結論為準（如 PERF-15 排序語意、PERF-14 快取須以 mtime 為鍵、PERF-05 保留全掃 fallback）。

### 1.1 已確認之開發者決策 (Confirmed Decisions)

| 編號 | 對應 | 決策 |
|---|---|---|
| UD-01 | T-02 | 啟動失敗時僅印 [BLOCKER] 提示，原指令 exit code 不變，照常冷派發（預設行為） |
| UD-02 | T-02 | ~~採方案 B~~（已由 sub_01 [P00:DR-07] 改為方案 D 實證回收偵測）採方案 B：POSIX 啟發式容器/沙盒偵測使 `can_spawn_background_daemon()` 回傳 False；同時提供 `YSCB_FORCE_DAEMON=1` 強制覆寫 |
| UD-03 | T-02 | `server/scripts/cli.py` readiness 逾時且進程未存活時回傳 1 |
| UD-04 | T-21 | 補實作 `config://server` 之 `require_server_for_agents`（sub_01 [P00:DR-06] 更名 `strict_hot_dispatch`，擋下依據改為 contributes `server_compatible`）（預設 `false`）；為 `true` 時 daemon 不在即印 [BLOCKER] 並回傳非零，不走冷派發；統一文件與程式之 [BLOCKER] 文案 |
| UD-05 | T-13 | 採方案 A：`_cleanup_state` 不再刪除 `daemon.lock`，`lock.py` 對 EEXIST 有限次重試（其他 errno 照拋） |
| UD-06 | 全體 | Umbrella 統籌；P3 項目獨立為一個子計畫 |

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_server_daemon_robustness` | Full Track | `Completed` | P0~P2 server/daemon 生命週期：T-01, T-02, T-05, T-08, T-12, T-13, T-21 |
| **sub_02** | `sub_02_hot_path_performance` | Full Track | `Completed` | P1~P2 熱路徑效能：T-09, T-10, T-11, T-17, T-18, T-19, T-20 |
| **sub_03** | `sub_03_reliability_and_governance` | Full Track | `Completed` | P1~P2 可靠性與工程治理：T-03, T-04, T-06, T-07, T-14, T-15, T-16 |
| **sub_04** | `sub_04_yscb_host_optimization` | Fast Track | `Completed` | 唯一宿主 `yscb.py` 五維度靜態診斷與收斂重構（對外函式 Mode B / 對內函式 Mode A） |
| **sub_05** | `sub_05_p3_polish` | Full Track | `Pending` | 全部 P3：T-22 ~ T-40（T-36 評估後可標記不修）；另含 sub_01 移交之 DEV-01（熱派發逾時重複執行）與 dev test 沙盒舊副本觀察 |

> [!NOTE]
> 建議執行順序：sub_01 → sub_02 → sub_03 → sub_04 → sub_05。T-13 若 sub_01 中 T-02 先完成則維持 P2。

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：sub_01 結案 — P0 dispatch 卡死消除、沙盒 daemon 守門與嚴格模式上線、鎖檔競態根除
- [x] **里程碑 2**：sub_02 結案 — 增量路徑回歸 O(|dirty|)、contributes/file-space 熱路徑記憶化
- [x] **里程碑 3**：sub_03 結案 — 完整性驗證、worker 隔離、CI 測試與 lint 上線
- [x] **里程碑 4**：sub_04 結案 — `yscb.py` 宿主五維度診斷與收斂評估完成
- [ ] **里程碑 5**：sub_05 結案 — P3 打磨完成，Umbrella 轉 `Completed`

