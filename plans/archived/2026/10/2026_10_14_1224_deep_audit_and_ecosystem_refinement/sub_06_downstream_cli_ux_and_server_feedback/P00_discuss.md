# Phase 0: 需求討論與邊界釐清 (P00 Discuss)

> 功能名稱：sub_06_downstream_cli_ux_and_server_feedback  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 使用者原始需求與意圖 (User Intent)

在過去的架構演進中，`server` 模組著重於進程隔離、動態 Port 綁定與 IPC 並發安全性，但在下游開發者體驗 (DX / UX) 上存在反饋缺失：
1. **啟動靜默無反饋**：執行 `server start` 時，僅單行印出 `Starting background daemon (PID: ...)...` 與 `Daemon successfully started (PID: ..., Port: ...)`，缺乏核心運行環境資訊（如 Worker PID、監控狀態、託管背景服務、即時 Log 位置等）。
2. **前台 Console 輸出體驗單薄**：使用 `--console` 啟動時，缺乏清晰的結構化啟動橫幅與即時日誌流，使本機除錯者無法一目了然掌握服務健康狀態。
3. **關閉停機無總結**：執行 `server stop` 時僅輸出 `Daemon stopped gracefully.`，未呈現本次運行的總體統計（如運行時間 Uptime、累計處理任務數、停機原因、日誌歸檔檔案路徑等）。
4. **生態系 CLI 指令反饋一致性**：下游各模組指令在錯誤提示與 Help 引導上需進一步校準與打磨。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

| 編號 | 釐清項目與核心疑問 | 定案結論與共識依據 |
| :---: | :--- | :--- |
| **Q1** | 啟動橫幅應在何時呈現？背景模式與前台模式是否皆適用？ | **結論**：背景模式於 readiness probe 成功後直接於 CLI 終端打印啟動橫幅卡片；前台模式 (`--console`) 則於 Supervisor 啟動就緒後打印橫幅，隨後即時輸出 stdout/stderr 串流日誌。 |
| **Q2** | 停機總結資訊應如何收集？若進程已被強制終止（`--force`）如何取得？ | **結論**：優雅停機時由 `/api/shutdown` 回傳完整 Runtime 統計資訊（Uptime、Tasks、Services、歸檔路徑預告）；若為 `--force` 或進程異常終止，則由 CLI 讀取 `daemon.json` 遺留資料推算並呈現安全降級報告。 |
| **Q3** | 是否破壞任何現有單元測試（如 `test_server_cli.py` 或自動合約測試）？ | **結論**：嚴格相容現有測試輸出斷言，保留原有關鍵字標籤，並在此基礎上豐富視覺反饋與細部摘要。 |

---

## 3. 開放議題與確認事項 (Open Issues)

- **[P00:DR-01] 啟動參數橫幅一等公民化 (Server Startup Banner)**：
  整合 Master PID、Worker PID、Port、TTL、Watcher 狀態、託管 Services 清單與 Log 路徑為結構化 ASCII 橫幅卡片。
- **[P00:DR-02] 關閉運行總結與歸檔追溯 (Server Shutdown Summary)**：
  擴充 `/api/shutdown` API 返回本次生命週期之運行總結，CLI `server stop` 格式化輸出報告卡。
- **[P00:DR-03] 零破壞性與向下相容 (Non-breaking DX)**：
  維持既有 CLI 指令傳參與 exit code 契約，提升人類可讀性而不破壞腳本解析。
