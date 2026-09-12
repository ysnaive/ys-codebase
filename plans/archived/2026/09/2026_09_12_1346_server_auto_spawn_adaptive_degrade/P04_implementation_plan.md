# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中有對應介面
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略與防洗頻抑制
- [x] **依賴純淨**：100% 使用 Python 標準庫，符合 NFR-02 指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 新增 `auto_spawn` 配置說明與 IDE Agent 使用指引 |
| **專題手冊** | `docs/server/daemon_architecture.md` | Modify | 補充環境自適應探針機制與 Job Object 邊界處理說明 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記 `[DN-10]` 自適應降級與 Agent 常駐導引決策 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本功能之特性發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：在 Windows PowerShell 正常終端下，探針是否會產生額外開銷？  
> [*] **防護解法**：正常終端下 `kernel32.IsProcessInJob` 返回 False（耗時 $<0.01\text{ms}$），直接快取 True，完全不啟動任何探針子進程，零效能損耗。  
> [?] **尖銳問題 2**：提示訊息是否會污染 CLI `--json` 格式化輸出或管線？  
> [*] **防護解法**：提示訊息強制輸出至 `sys.stderr`，且受 `_AUTO_SPAWN_WARNED` 單進程旗標保護，單次 CLI 調用內至多輸出一次，絕對不破壞 `sys.stdout`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `core.platform.process.can_spawn_background_daemon` 探針與快取邏輯。
- [ ] **TASK-02**：實作 `server.config.ServerConfig` 之 `auto_spawn` 欄位解析與預設值。
- [ ] **TASK-03**：升級 `core.commands.dispatcher._maybe_auto_spawn_server` 整合 `auto_spawn` 檢核、探針判定與防洗頻 `stderr` 提示。
- [ ] **TASK-04**：編寫 `test_platform_process.py`, `test_dispatcher.py`, `test_config.py` 單元測試並執行 `dev test` 全套驗證。
- [ ] **TASK-DOC**：同步更新 `docs/server/` 相關手冊與 `DESIGN_NOTES.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全功能技術定稿**：確實驗證探針雙軌快取、`auto_spawn` 雙層組態、`stderr` 防洗頻提示與 IDE Agents 操作指南全部規格閉環。
