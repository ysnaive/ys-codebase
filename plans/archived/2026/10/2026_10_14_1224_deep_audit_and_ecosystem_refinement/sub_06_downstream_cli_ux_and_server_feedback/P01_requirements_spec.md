# Phase 1: 需求規格說明書 (P01 Requirements Spec)

> 功能名稱：sub_06_downstream_cli_ux_and_server_feedback  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

- **FR-01 (Server 啟動參數橫幅反饋)**：
  - 於 `python yscb.py server start` 背景啟動成功後，印出結構化啟動橫幅：
    - Master PID、Worker PID
    - Dynamic Port (`127.0.0.1:<port>`)
    - Workspace Root (`yscb_root`)
    - Idle TTL 倒數設定
    - Modules Watcher 監聽狀態
    - 註冊並運行的背景託管服務清單
    - 即時日誌檔案路徑 (`.cache/server/log`)
- **FR-02 (Server 前台 Console 日誌回顯)**：
  - 於 `python yscb.py server start --console` 啟動時，先印出上述完整啟動橫幅，並在控制台即時回顯 Master 與 Worker 的日誌串流（stdout/stderr）。
- **FR-03 (Server 關閉停機總結報告)**：
  - 於 `python yscb.py server stop` 停止時，透過 `/api/shutdown` 獲取並輸出結構化運行總結：
    - 累計運行時間 (Uptime)
    - 累計處理任務數 (Total Tasks Handled)
    - 停機原因 (Graceful CLI request / Force kill)
    - 託管背景服務正常停止狀態
    - 歷史日誌歸檔路徑 (`.cache/server/<timestamp>_log`)
- **FR-04 (Server Status 狀態資訊細化)**：
  - 於 `python yscb.py server status` 輸出中，同步包含伺服器已運行時長 (Uptime) 與即時日誌路徑資訊。
- **FR-05 (全生態系 CLI 提示與 Help 體驗打磨)**：
  - 排查並優化 `core`、`dev`、`knowledge-db` 與 `agents-workflow` 指令的 Help 與參數防呆提示，確保輸出風格與反饋一致。

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

- **EC-01 (服務已在運行中再次 start)**：輸出伺服器已在運行中之提示，並格式化印出目前運行實例之橫幅狀態，不重複拉起程序。
- **EC-02 (強行殺死時停機報告降級)**：若伺服器無法優雅響應 `/api/shutdown` 走 `--force` 強殺路徑，讀取本地磁碟快照資料呈現降級停機報告。

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01 (零效能衰退)**：啟動橫幅與停機報告的生成不引入額外開銷（$< 5\text{ms}$ 延遲）。
- **NFR-02 (相容性與零回歸)**：所有既有測試（包含斷言 `Daemon successfully started` 與 `Daemon stopped gracefully.`）保持 100% 通過。

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 橫幅文字必須完整包含既有單元測試所依賴之斷言關鍵字，不可隨意更改既有日誌關鍵字以防破壞測試相容性。

