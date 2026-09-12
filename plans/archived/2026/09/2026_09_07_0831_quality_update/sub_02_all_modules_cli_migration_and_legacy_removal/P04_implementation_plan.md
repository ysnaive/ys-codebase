# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 均在 P03 API 規格書中定義明確之精確函式簽名與派發契約。
- [x] **邊界防護**：EC-01 ~ EC-04 具體對應 OptionResolver 互斥攔截、choice 列舉校驗與 EC-05 (127) 阻斷。
- [x] **依賴純淨**：符合 NFR-01~03 指標約束，100% Python 標準庫，零第三方依賴。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **專題手冊** | [`docs/Core/cli_commands_architecture.md`](file:///workspace/ys-codebase/docs/Core/cli_commands_architecture.md) | Modify | 確立全生態系模組 100% 採用活躍合約與同構遞迴指令樹，標記歷史 process 契約廢除 |
| **微觀代碼** | `source/*/scripts/cli.py` | Modify | 移除歷史 `def process(args)` 殘留，代碼註解對齊 `CmdBags` 契約 |
| **發布日誌** | [`CHANGELOG.md`](file:///workspace/ys-codebase/CHANGELOG.md) | Modify | 記錄全模組遷移完成與向後相容過渡層剛性拔除之高階摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：徹底拔除 `hasattr(mod, 'process')` 過渡層後，若有外部腳本調用未宣告指令會如何？  
> 💡 **防護解法**：`dispatcher` 嚴格輸出 `EC-05` 契約缺失錯誤（退出碼 127），若指令未知則提供 `EC-01` 模糊拼寫建議（退出碼 1），完全終止隱性退化，確保行為可預期。

> ❓ **尖銳問題 2**：`knowledge-db` 在 Server Worker 常駐進程中熱派發時，如何保證進程狀態與記憶體不被污染？  
> 💡 **防護解法**：熱派發透過 Localhost HTTP IPC 進行串流傳輸，標準輸出以 500ms 防抖緩衝回傳終端；Worker 本身單例共享 `KnowledgeEngine`，任務結束回傳 exit_code，不退出 Worker 進程，實現瞬發與隔離雙重保障。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`dev` 模組遷移：更新 `source/dev/contributes/core.json` commands schema，重構 `source/dev/scripts/cli.py` 為精確命令函式並刪除 `process(args)`
- [ ] **TASK-02**：`knowledge-db` 模組遷移：更新 `source/knowledge-db/contributes/core.json` commands schema（查詢類開啟 `server_compatible: true`），重構 `source/knowledge-db/scripts/cli.py` 為精確命令函式並刪除 `process(args)`
- [ ] **TASK-03**：`agents-workflow` 模組遷移：更新 `source/agents-workflow/contributes/agents-workflow.json` commands schema（含 `plan` 巢狀樹），重構 `source/agents-workflow/scripts/cli.py` 為底線平鋪函式並刪除 `process(args)`
- [ ] **TASK-04**：Hard Sunset Gate 剛性守門：自 `source/core/core/commands/dispatcher.py` 徹底刪除雙軌向後相容退化代碼
- [ ] **TASK-05**：更新測試套件（`test_core_commands.py` 升級 FT-08 為嚴格 EC-05 斷言）並執行全生態系回歸跑測

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 嚴格循序實作與單向刪除原則**：TASK-01 ~ TASK-03 依賴完成全模組遷移後，方可進入 TASK-04 刪除過渡層，避免過渡期間任何模組執行斷裂。
- **[P04:DR-02] 守護 Token 與安全邊界保全**：各模組精確函式入口處統一保留 `guard_dispatch(module_name)` 呼叫，確保安全守門機制不因重構而遺失。
