# 需求規格說明書 (Requirements Specification)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 環境背景守護權限探針 | 於 `core.platform.process` 實作 `can_spawn_background_daemon() -> bool`，精確檢測 Windows Job Object Breakaway 權限或環境限制，並具備模組級記憶體快取。 | P0 | [P00:DR-01] |
| **FR-02** | `auto_spawn` 組態支援 | 於 `ServerConfig` 與 `config/server/config.project.json` 新增 `auto_spawn: bool = True` 欄位（預設為 `true`）。 | P0 | [P00:DR-01] |
| **FR-03** | 自適應冷派發降級與導引 | 當 `auto_spawn == True` 但探針判定無背景常駐權限時，自動跳過背景 spawn 並於 `stderr` 輸出具備排查指引與 IDE Agents 專屬操作之提示。 | P0 | [P00:DR-02] |
| **FR-04** | stderr 防洗頻旗標抑制 | 提示訊息僅導向 `sys.stderr`（嚴禁污染 `stdout` / `--json`），且於進程級維護狀態旗標，單次 CLI 調用內最多警告一次。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 組態顯式設定 `auto_spawn: false` | 靜默跳過背景喚醒與權限探針，不輸出任何 stderr 警告訊息。 |
| **EC-02** | 測試環境 (`YSCB_TESTING=1` / `YSCB_TEST_SANDBOX=1`) | 依既有規則維持不觸發背景喚醒。 |
| **EC-03** | 探針執行異常 (如 ctypes 不可用或平台例外) | 採安全容錯 (Safe Fallback)，視為無背景權限並安全降級。 |
| **EC-04** | 手動前台/背景啟動 (`server start`) | 仍支援使用者/Agent 透過 CLI 顯式啟動 Server（前台 `--console` 或背景 `--daemon`）。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 探針檢測結果於進程內快取，重複調用延遲 $< 0.1\text{ms}$，冷派發整體耗時維持在 sub-100ms。 |
| **NFR-02** | 依賴純淨度 | 100% 使用 Python 標準庫 (`ctypes`, `subprocess`, `os`, `sys`, `json`)，零新增第三方套件依賴。 |
| **NFR-03** | 跨平台相容 | Windows CP950 / UTF-8 終端與 POSIX (Linux / macOS) 均能安全執行。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** Windows Job Object 在 IDE Agent 沙盒環境下若未宣告 `JOB_OBJECT_LIMIT_BREAKAWAY_OK`，使用 `CREATE_BREAKAWAY_FROM_JOB` (0x01000000) 會觸發 WinError 5 (Access Denied)。
- **`[!NOTE]`** 提示訊息必須使用 `sys.stderr.write` + `flush`，避免破壞 CLI `--json` 格式化輸出管線。
