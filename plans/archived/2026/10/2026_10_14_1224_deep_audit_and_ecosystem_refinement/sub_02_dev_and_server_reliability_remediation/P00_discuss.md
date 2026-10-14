# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_dev_and_server_reliability_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 計畫類型：Bug Fix / Architecture Refinement  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  全專案深度體檢與生態系修復（範疇 B：`dev` 與 `server` 模組）。修復開發者工具鏈（scaffold, test, release-check, checker）與伺服器模組（IPC 競態、stderr 死鎖、背景服務託管、日誌歷史）之隱性 Bug、契約失真與可靠性隱患。
- **核心目標**：
  1. **Dev 工具鏈修復**：修正 `dev create` 骨架生成錯誤（`cmd_bags` 合約、`YSCBTestCase` 繼承、四位版號）；修復 `dev test -k` 參數過濾與 `--target` 冒號/非冒號模組判定；補齊 `contributes/core.json` 漏宣告選項；實作 `release-check --all` 批次預檢；完善 `Checker` 具名指令檢查（保留無 `commands.cmd` 時 `process` 單元測試相容）並接線 `custom_checks`。
  2. **Server 並發與可靠性修復**：修正 `MasterSupervisor.dispatch_task` 加鎖序列化保護 Worker IPC 通訊；啟動背景 Daemon 讀取 Worker `stderr` 避免 PIPE 緩衝區滿溢死鎖並修復 FD 洩漏；遵守「Master is pure control plane」鐵律，在 `WarmWorker` 端透過 `ServiceManager` 統一託管動態背景服務並透過 IPC 同步狀態；修正 `HIST_REGEX` 與 `restart_server`。
- **邊界排除 (Explicitly Excluded)**：
  - 不得破壞 `WarmWorker` 與 `MasterSupervisor` 的純控制平面架構邊界（嚴禁將領域背景服務直接塞入 Master）。
  - 不得破壞 `test_checker.py` 中 14 個依賴最小化 `process(args)` 的單元測試。
  - 下游 CLI 視覺橫幅與停機統計總結由 `sub_06` 負責，本子計畫聚焦於服務並發安全、控制平面 IPC 與底層可靠性。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Dev 模組選項取值與指令合約對齊**：
  `dev/scripts/cli.py` 全面淘汰 `get_option()`，統一採用 `get_option_value()`；`dev create` 生成符合微內核標準的現代化模組骨架（`cmd_bags: CmdBags`、`self.mark_passed()`、`"0.1.0.0"`）。
- **[P00:DR-02] Worker 統一服務託管與 IPC 狀態同步**：
  在 `WarmWorker` 初始化時由 `ServiceManager` 自動載入 `contributes/server.json` 之 `services` 列表；背景服務（如 `KnowledgeDBServiceWorker`）由 Worker 生命週期統一啟動與 `stop_all()`，Master 僅透過 IPC 接收服務健康狀態字典並呈現於 `/api/status`。
- **[P00:DR-03] Master 通訊並發安全與 Stderr 排空**：
  以 `self._dispatch_lock` 序列化並發 HTTP 請求至單一 Worker 程序的標準輸入輸出；以背景 Daemon 執行緒持續排空 Worker `stderr` 並寫入系統記錄，徹底杜絕 OS 緩衝區滿溢死鎖。

---

## 3. 開放議題與確認紀錄

- [x] **已確認**：`test_checker.py` 測試案例是否需要修改？不需要，`Checker` 採用條件式分流（有宣告非空 `commands.cmd` 時剛性檢查具名函式；無宣告時允許 `process` 相容）。
- [x] **已確認**：`server` 模組現有單元測試（`test_server.py`, `test_server_logging.py`, `test_server_api.py`）是否相容？是，修復後將全面保持 100% 通過。

