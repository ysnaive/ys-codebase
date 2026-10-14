# Phase 4: 實作計畫與任務編排 (P04 Implementation Plan)

> 功能名稱：sub_06_downstream_cli_ux_and_server_feedback  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 均已在 API 規格書與架構計畫中完成落實
- [x] **邊界防護**：EC-01 ~ EC-02 涵蓋重複啟動橫幅輸出與強行停機降級報告
- [x] **依賴純淨**：零外部新增重型套件依賴，保持微內核高效輕量

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記 `[DN-12]` 啟動參數橫幅、Console 日誌實時回顯與停機總結架構 |
| **微觀日誌** | `plans/.../changelog.md` | Modify | 記錄子計畫完成與結案紀錄 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 Server 遭 kill -9 或強制關閉，停機總結是否會崩潰？  
> [*] **防護解法**：CLI 採防禦性設計，若無法連接 `/api/shutdown`，自動讀取磁碟快照資料降級顯示基礎停機資訊，絕不拋出未捕獲例外。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (ServerLogger 預期歸檔路徑與資訊支援)**：在 `source/server/server/logger.py` 實作 `get_expected_archive_path()` 與相關輔助函式。
- [x] **TASK-02 (MasterSupervisor 運行指標與 API 擴充)**：在 `source/server/server/master.py` 記錄 `start_time`，擴充 `/api/status` 與 `/api/shutdown` 回傳指標資料（Uptime、Tasks、Services、歸檔路徑）。
- [x] **TASK-03 (Server CLI 啟動橫幅與停機報告實作)**：在 `source/server/scripts/cli.py` 實作 `_print_server_banner()` 與 `_print_shutdown_summary()`，整合至 `start()`、`stop()` 與 `status()`。
- [x] **TASK-04 (Server 前台 Console 日誌回顯與橫幅整合)**：確保 `server start --console` 打印啟動橫幅並串流即時日誌。
- [x] **TASK-05 (全生態系 CLI Help 與反饋打磨)**：排查 `core`, `dev`, `knowledge-db`, `agents-workflow` 指令的 Help 與提示一致性。
- [x] **TASK-06 (單元測試與全生態系驗證)**：適配 `test_server_cli.py` 等測試，驗證 550 全生態系回歸通過。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 兼顧可讀性與測試斷言契約**：
  在橫幅與總結中完全保留原有 `Daemon successfully started` 與 `Daemon stopped gracefully.` 關鍵文字，確保既有測試無損相容。

