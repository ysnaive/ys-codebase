# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_dev_and_server_reliability_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-09 在 API 規格書與架構設計書中均有具體落實路徑
- [x] **邊界防護**：EC-01 ~ EC-05 涵蓋舊版測試 Mock 相容、無冒號 `--target`、並發請求加鎖、Stderr 大量輸出排空與非數字 TTL 防呆
- [x] **依賴純淨**：嚴格恪守「Master is pure control plane」，維持 Worker 獨立服務生命週期與零外部重型依賴

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 登記 `[DN-DEV-10]` 模組骨架微內核合約對齊、測試模式解析與命令靜態檢查雙軌容錯 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記 `[DN-11]` Master 純控制平面解耦、Worker 服務託管與 IPC 互斥鎖定 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當並發多個 HTTP 請求同時調用 `/api/run` 時，單一 Worker 的 stdio IPC 通訊管線是否會產生交錯讀寫或封包混亂？  
> [*] **防護解法**：在 `MasterSupervisor` 內配置 `self._dispatch_lock = threading.Lock()`。所有對 Worker 存活狀態檢查、stdin 寫入與 stdout 完整讀取的流程皆在該互斥鎖保護下原子化執行，確保 Worker IPC 嚴格序列化。

> [?] **尖銳問題 2**：若 Worker 內部拋出大量未捕獲例外或第三方套件大量印出 stderr，是否會導致 Worker 程序阻塞停擺？  
> [*] **防護解法**：在啟動 Worker 程序後，Master 立即拉起一條背景 Daemon 執行緒，以管線方式持續讀取 `proc.stderr` 並轉發至系統日誌，徹底防止作業系統 Pipe Buffer（通常為 64KB）被填滿而引發 OS 級死鎖。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (Dev 選項與骨架修復)**：修改 `dev/scripts/cli.py` 改用 `get_option_value()`；修改 `dev/scaffold.py` 與 `dev/case.py` 生成微內核標準骨架。
- [x] **TASK-02 (Dev 測試器與發布預檢)**：修改 `dev/tester.py` 支援 `-k` 與修正 `--target`；修改 `dev/releaser.py` 實作 `release-check --all`；修改 `dev/contributes/core.json` 補齊選項。
- [x] **TASK-03 (Dev 檢查器合約升級)**：修改 `dev/checker.py` 剛性校驗非空 `commands.cmd` 的具名葉節點函式（保留無宣告時 `process` 相容），排除 Docstring AST，串接 `custom_checks`。
- [x] **TASK-04 (Server Master 鎖與 Stderr 排空)**：修改 `server/master.py` 導入 `_dispatch_lock`、`stderr` 排空執行緒與管道清理；修改 `server/logger.py` 支援歷史記錄後綴正則。
- [x] **TASK-05 (Server Worker 服務託管與測試對齊)**：修改 `server/worker.py` 透過 `ServiceManager` 託管服務並解析多層指令；修改 `test_server*.py` 補齊 `super().setUp()` / `tearDown()`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零回歸驗收承諾**：
  `dev` 與 `server` 各項修復完成後，必須通過 `dev` (134 tests) 與 `server` (35 tests) 全量單元測試，並在全生態系 550 測試中保持 100% 通過。

