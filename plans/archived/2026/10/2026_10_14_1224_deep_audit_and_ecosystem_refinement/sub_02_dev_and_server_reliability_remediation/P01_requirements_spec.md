# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_dev_and_server_reliability_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 狀態：Confirmed  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev/scripts/cli.py` 選項取值修正 | `create` (`--desc`) 與 `release-git` (`--msg`/`-m`) 改用 `bags.get_option_value()`，禁止將 `CmdOption` 物件以 `str()` 寫入產物。 | P0 | [P00:DR-01] |
| **FR-02** | `dev test -k` 參數解析支援 | 於 `tester.py` 支援 `("-k=", "--k=", "--pattern=")` 等模式解析，確保 `-k` 測試過濾 pattern 正常生效。 | P0 | [P00:DR-01] |
| **FR-03** | `dev create` 模組骨架標準化 | 更新 `scaffold.py` 與 `case.py`，生成標準 `def hello(cmd_bags: CmdBags) -> int`、`class ...Test(YSCBTestCase): def test_...(self): self.mark_passed()`、版本號預設為 `"0.1.0.0"`。 | P0 | [P00:DR-01] |
| **FR-04** | `dev` CLI 選項補齊與 `release-check --all` | 1. 於 `dev/contributes/core.json` 補齊 `test`（`-j`, `--target`, `--type`, `--sync`, `--keep-sandbox`）、`op-mksb`、`op-test`、`release-check`（`--all`）、`release-git`（`-m`/`--msg`）宣告。<br/>2. 修正 `tester.py` 的 `--target` 冒號與模組解析。<br/>3. 實作 `dev release-check --all` 批次預檢。 | P1 | [P00:DR-01] |
| **FR-05** | `Checker` 具名指令檢查與擴充接線 | 1. 當 `contributes/core.json` 宣告非空 `commands.cmd` 時，強制校驗具名葉節點函式（不以 `process` 豁免）；無 `commands.cmd` 時保留 `process` 相容。<br/>2. `_check_source_files` 排除模組首行 Docstring AST 節點。<br/>3. 接線 `core.contributes.get("dev", "custom_checks")`。 | P1 | [P00:DR-01] |
| **FR-06** | `MasterSupervisor` IPC 執行緒安全 | 以 `self._dispatch_lock` 序列化並發請求對單一 Worker 的存活檢查、stdin 寫入與 stdout 讀取；清理死代碼 `_task_queue`。 | P0 | [P00:DR-03] |
| **FR-07** | Worker `stderr` 排空與 Pipe 資源釋放 | 啟動背景 Daemon 執行緒持續讀取 `proc.stderr` 寫入日誌；於 `_kill_worker_locked` 確實關閉 `stdin`/`stdout`/`stderr` pipes 避免 FD 洩漏與緩衝區滿溢死鎖。 | P0 | [P00:DR-03] |
| **FR-08** | Worker `ServiceManager` 統一託管 | 遵守 Master 純控制平面鐵律，在 `WarmWorker` 內透過 `ServiceManager` 動態載入 `contributes/server.json` 的 `services` 並於結束時清理；透過 IPC 同步服務狀態至 Master；以 `registry.resolve_command_path` 解析多層指令。 | P0 | [P00:DR-02] |
| **FR-09** | `HIST_REGEX` 支援與測試健全化 | `HIST_REGEX` 支援 `(?:_\d{2,})?_log$`；移除 `restart_server` 對 `source/` 違規回退；補齊 `test_server*.py` 之 `super().setUp()` / `tearDown()`；增加 `server start --ttl` 數值防呆。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `test_checker.py` 中 14 個測試使用無 `commands.cmd` 的 minimal mock | `Checker` 檢測若未宣告 `commands.cmd`，平滑回退為允許 `process(args)`，保證 100% 通過。 |
| **EC-02** | `dev test --target=Class.method` 無模組名稱前綴 | `tester.py` 正確識別為當前模組內之指定類別方法，不將 `target_mod` 覆蓋為無效名稱。 |
| **EC-03** | 並發 HTTP 請求同時到達 Master | `_dispatch_lock` 互斥鎖確保對單一 Worker 標準輸入輸出的原子排隊處理，杜絕回應交錯污染。 |
| **EC-04** | Worker 異常拋出大量堆疊追蹤至 `stderr` | 背景 Daemon 執行緒即時吞吐排空，不阻塞 Worker 程序的 stdout 輸出管線。 |
| **EC-05** | `server start --ttl` 傳入非法非整數字串 (如 `--ttl=abc`) | 輸出明確錯誤提示並優雅終止，避免進程在背景崩潰。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構邊界約束 | 嚴格遵守「Master is pure control plane」，背景領域服務一律託管於 Worker 端。 |
| **NFR-02** | 測試與品質 | `dev` 與 `server` 模組全套單元測試 100% 通過，全生態系 550 項測試 0 回歸。 |
| **NFR-03** | 資源管理 | Worker 重啟或 Master 停止時，所有 Pipe FD 與背景服務程序必須 100% 釋放，無殭屍進程。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`**：`test_server.py` 與 `test_server_logging.py` 測試覆寫了 `setUp()`，若未呼叫 `super().setUp()` 會遺失沙盒初始化邏輯。
- **`[!CAUTION]`**：`dev check` 檢查葉節點具名函式時，必須支援 `-` 轉 `_`（例如 `release-check` 對應 `cmd_release_check` 或 `release_check`）。

