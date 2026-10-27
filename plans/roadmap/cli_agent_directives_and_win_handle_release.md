# 技術路線圖：報錯自癒指令注入、Windows 更新前句柄釋放與 VFS 定位收斂 (Roadmap)

> 主題：報錯自癒指令注入、Windows 更新前句柄釋放與 VFS 定位收斂 (`cli_agent_directives_and_win_handle_release`)  
> 歸檔日期：2026-10-27  
> 狀態：Ready  
> 目標範疇：`core`、`dev`、`server`（`core/validator.py`、`core/installer.py`、`core/vfs/vfs.py`、`dev/checker.py`）  
> 前置解鎖條件：無  
> 模型：Unknown  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **驗證器報錯時 Agent 易盲猜語法重試**：當 AI Agent 修改 `contributes/*.json` 或模組結構觸發 `core/validator.py` 或 `dev/checker.py` 報錯時，若當前 Context 未載入對應 Skill（如 `how-to-config-yscb`、`yscb-module-dev`），Agent 容易陷入憑直覺盲猜欄位格式的無效迴圈。
- **Windows 下常駐 Server 鎖定 `.pyd`/`.dll` 阻礙更新或回滾**：雖然 `.modules/<mod>` 已導入 `.staging_*` 原子目錄交換，但在 Windows 作業系統下，若開發者手動啟動的常駐 `server` 進程（或 `WarmWorker`）已載入 `.modules/` 或 `.venv/` 內的原生擴充檔（如 `tree_sitter` `.pyd`），連 `os.replace` 重命名舊目錄都會因作業系統檔案句柄鎖定而拋出 `PermissionError (WinError 5)`。
- **`core.vfs` 殘留不切實際的 `MemoryBackend` 擴充描述**：`core/vfs/vfs.py` 仍留有 `供未來 MemoryBackend 等擴充插槽使用` 的註解，易使後續開發者誤以為 VFS 可攔截 `subprocess` / C-extension 的 OS 檔案系統呼叫。

### 1.2 現況與影響範圍評估
- `ValidationResult.format_report()` (`core/validator.py`) 與 `Checker` (`dev/checker.py`) 目前僅列出欄位錯誤與單行建議，缺乏統一的 `[Agent Directive]` 技能路由指引。
- `Installer` (`core/installer.py`) 執行 `install`、`update`、`rollback`、`remove` 前，尚未主動通知運行中的本地 `server` 釋放 Worker 句柄。

### 1.3 核心根因
1. 錯誤訊息缺少針對 AI Agent 的行動路由連結（Actionable Skill Directives）。
2. Windows VFS 檔案鎖定機制要求在替換已載入模組目錄前，必須先終止或卸載持有該目錄句柄的常駐進程。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：僅靠重試退避 (`time.sleep`) 等待句柄釋放** | 在 `_atomic_swap_dir` 中延長 `PermissionError` 重試秒數 | 無須跨模組通訊 | 若常駐 Server Idle TTL 為 1800 秒，短時間重試必然失敗 | ⭐️⭐️ |
| **方案 2：安裝前主動通知 Server 停機/卸載 + 報錯尾端注入 `[Agent Directive]`** | 於 `installer.py` 生命周期變異操作前探測 `daemon.json` 並發送優雅停機信號；於 `validator.py` / `checker.py` 失敗報告尾端附加對應 Skill 路徑提示；同步清理 `vfs.py` 註解 | 徹底根絕 Windows 句柄鎖定、引導 Agent 零盲猜載入正確 Skill、零外部依賴 | 需處理 `server` 未安裝或未啟動時的靜默掠過邏輯 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（單純延長重試） | 方案 2（主動釋放句柄 + Agent Directive 注入） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 低（無法解除長駐 Daemon 的 `.pyd` 映射） | 高（直接復用 `.cache/server/daemon.json` 與 `/api/shutdown`） |
| **後續維護難度 (Maintenance)** | 低 | 低（內聚於 `installer.py` 前置 Hook 與 `format_report`） |
| **可靠性 (Reliability)** | 低 | 極高（跨 Windows / POSIX 行為一致） |
| **落地難度 (Implementation)** | 低 | 低 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：於 core/validator.py 與 dev/checker.py 報錯輸出尾端統一追加 [Agent Directive]
# 指引 Agent 查閱 `.agents/skills/how-to-config-yscb/SKILL.md` 或 `.agents/skills/yscb-module-dev/SKILL.md`

# 步驟 2：於 core/installer.py 實作 _ensure_server_handles_released()
# 在 install / update / rollback / remove 進入實體目錄替換前，若探測到活躍 Server 則發送停機請求並等待釋放

# 步驟 3：更新 core/vfs/vfs.py 與 base.py 註解，確立本地實體路徑代理 + guard.py 守衛定位
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 以最小改動閉環補強跨平台安裝穩定度與 ACI（Agent-Computer Interface）報錯自癒能力。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（`[Agent Directive]` 報錯尾端注入）**：升級 `core/validator.py` 與 `dev/checker.py` 錯誤報告格式。
2. **Stage 2（Windows 常駐進程句柄釋放與 VFS 定位收斂）**：於 `core/installer.py` 增補安裝前 Server 停機釋放協定，並對齊 `core/vfs/` 註解。
3. **Stage 3（測試驗證）**：新增單元測試覆蓋報錯指引與安裝前 Server 釋放流程。

