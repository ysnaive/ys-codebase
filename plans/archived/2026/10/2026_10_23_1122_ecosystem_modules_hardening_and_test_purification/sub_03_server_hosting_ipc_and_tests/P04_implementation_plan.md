# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書中有對應介面與契約
- [x] **邊界防護**：EC-01 ~ EC-05 有具體錯誤處理策略（連字號路徑注入、`auto_start: false` 略過、雜訊自動導向 stderr、逾時兜底強殺、400 攔截）
- [x] **依賴純淨**：符合 NFR-01 運行時剛性隔離（嚴禁注入 `source/`）與 NFR-02 測試套件 3 檔純化收斂且工作區零殘留

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md`、`ys_codebase/source/server/README.md` | Modify | 更新 `services` 範例、3 檔測試集架構與 CLI 說明 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 增補 `[DN-05]` 記錄 Worker IPC 通道隔離與兩階段優雅停機協議 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `service.py`、`worker.py`、`master.py` 介面註解 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本版本發布摘要與 `sub_03` 結案紀錄 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當背景服務在非任務執行期間直接呼叫 `print()`，是否會污染 Master 的 NDJSON 解析？  
> [*] **防護解法**：`worker_main` 啟動時直接將全域 `sys.stdout` 重導向至 `sys.stderr`，專屬 NDJSON 通道改為私有 `_ipc_stdout` 句柄並以 `ipc_lock` 序列化保護，任何背景雜訊 100% 導向 `stderr` 由 Master 安全日誌收錄。

> [?] **尖銳問題 2**：若 Worker 子進程收到 `{"action": "exit"}` 後死鎖不退出，是否會造成 Master 停機卡死？  
> [*] **防護解法**：`MasterSupervisor._kill_worker_locked` 設定第一階段應用層握手等待上限為 `1.5s`，一旦逾時立即降級為第二階段作業系統層級 `kill_process_tree` 強制收割進程樹。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (背景服務託管引擎修復)**：更新 `server/service.py` 補齊 `import os`，接入 `core.contributes.get`，支援 `code.class://`、`.modules/<provider>` 路徑注入與 `auto_start` 控制。
2. **TASK-02 (Worker IPC 硬隔離與優雅停機)**：更新 `server/worker.py` 實作 `_ipc_stdout` 句柄與 `sys.stdout -> sys.stderr` 重導向；更新 `server/master.py` 實作兩階段優雅停機、修正 `_write_state` 的 `start_time`，並移除所有 `source/` 注入與冗餘 `ServiceManager`。
3. **TASK-03 (Contributes 宣告、Reload 熱刷新與 CLI 清理)**：更新 `contributes/core.json` 補齊 `events`；更新 `server/master.py` 於 `restart_worker` 刷新 `ServerConfig`；清理 `scripts/cli.py` 死代碼 `_handle_start` 並加固負數 TTL 阻斷。
4. **TASK-04 (測試集純化收斂 4 檔 $\rightarrow$ 3 檔與高風險路徑補盲)**：物理刪除 `tests/test_basic.py`；重構 `test_server.py`、`test_server_config.py` 與 `test_server_logging.py`，徹底消滅自寫自驗測試並補齊 4 大高風險路徑。
5. **TASK-DOC (文檔與手冊同步)**：更新 `docs/server/README.md`、`docs/server/DESIGN_NOTES.md`、`ys_codebase/source/server/README.md` 與 `CHANGELOG.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** **`P06_test_plan.md` 狀態正式定稿為 `Confirmed`**：所有功能與邊界測試（`FT-01`~`FT-07`、`ET-01`~`EC-05`、`RT-01`）均具備實質斷言與明確對應之測試方法，符合 `testing-sop` 六大鐵律。

