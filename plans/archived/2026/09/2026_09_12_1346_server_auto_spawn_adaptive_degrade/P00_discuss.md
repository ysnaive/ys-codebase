# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：使用方案 A + C，並於預設 auto_spawn = true，當自適應環境探針發現無開立背景程序權限時，自動降級並彈出提示，修改 auto_spawn config，或是給予權限，並且專門給 agents 提示 "如果你是 IDE Agents 以 xxx 模式... 手動執行 server start"
- **核心目標**：
  1. 整合方案 A (環境感知自適應降級) 與方案 C (`auto_spawn` 組態與診斷控制)。
  2. 預設 `auto_spawn = true`，維持一般終端使用者開箱即用之自動喚醒體驗。
  3. 當自適應環境探針 (`can_spawn_background_daemon` / Breakaway 偵測) 發現當前環境無開立背景守護程序權限時（如 Windows Job Object 限制或 Agent 沙盒），自動阻斷無效的 `_maybe_auto_spawn_server()`，降級至本地極速冷派發。
  4. 輸出清晰指引提示，引導使用者修改 `config/server/config.project.json` 之 `auto_spawn: false` 或開放權限；並專門為 IDE Agents 提供「以常駐 Daemon 模式 (如 `IsDaemon: true` / Background Task) 執行 `python yscb.py server start --console`」之具體行動指南。
  5. 支援提示防洗頻機制（如單次執行階段或標記抑制），避免污染 Agent 結構化輸出或高頻指令刷屏。
- **邊界排除 (Explicitly Excluded)**：
  - 不使用高風險之 WMI / 系統服務外部逃逸技術（方案 D）。
  - 不破壞既有 Hot-IPC 與本地冷派發之核心派發邏輯與微內核效能。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 方案 A + C 融合架構**：
  - 於 `core.platform.process` 或 `core.commands.dispatcher` 實作環境權限自適應探針。
  - 於 `server.config` 與 `config/server/config.project.json` 支援 `auto_spawn: bool = true` 組態。
- **[P00:DR-02] 自適應降級與雙向引導提示**：
  - 當 `auto_spawn == True` 但環境無開立背景守護程序權限時，自動跳過背景拉起，防止無效進程抖動。
  - 輸出終端提示，包含：
    1. 環境限制說明（無法脫離目前進程樹/Job Object）。
    2. 組態優化指引（建議設定 `auto_spawn: false`）。
    3. IDE Agents 專用指引（建議透過 IDE 背景常駐模式 `python yscb.py server start --console` / `IsDaemon: true` 啟動以享受 Hot-IPC）。
- **[P00:DR-03] 輸出純度與防洗頻約束**：
  - 提示訊息統一輸出至 `stderr`，嚴禁污染 `stdout`（保障 `--json` 與管線輸出）。
  - 於當前進程內維持提示旗標（Process-level Notice Flag），單次進程派發中最多提示一次，避免高頻重複警告。

---

## 3. 開放議題與確認紀錄

- [x] 預設值確認：`auto_spawn` 預設為 `true`。
- [x] 降級行為確認：偵測無背景權限時自動平滑退化至本地冷派發。
- [x] Agent 引導確認：包含 IDE Agent 常駐模式操作指南。
