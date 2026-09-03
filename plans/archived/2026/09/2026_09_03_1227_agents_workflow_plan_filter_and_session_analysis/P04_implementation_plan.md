# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書 P03 中均具備明確之實體介面、檔案與宣告契約。
- [x] **邊界防護**：EC-01 ~ EC-04 均有完整對應之異常防禦策略與測試覆蓋。
- [x] **依賴純淨**：符合 NFR-01~03 約束，維持 100% Python 標準庫零第三方依賴。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時追加本計畫之高階架構變更摘要。 |
| **微觀日誌** | `plans/.../changelog.md` | Modify | 記錄各階段轉換與 DR 決策。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若未來 `plans/` 目錄下新增其他輔助資料夾（如 `plans/backlog/`, `plans/experiments/`），是否會再次引發 `plan check` 誤判報錯？  
> 💡 **防護解法**：絕對不會。因為全系統判定規則已自黑名單徹底收斂至「白名單時間戳正則 `r"^\d{4}_\d{2}_\d{2}"`」，只有符合命名契約之實體計畫才會被納入檢驗，其餘任意資源目錄均安全略過。

> ❓ **尖銳問題 2**：重命名 `WORKFLOW_RETRO` ➔ `WORKFLOW_SESSIONANALYSIS` 是否會造成既有編譯快取損毀或投影遺留？  
> 💡 **防護解法**：`ArtifactCompiler` 與 `ReleasePublisher` 在 Stage 1 快取構建時自動感知最新 contributes 宣告；新測試套件 `test_session_analysis_workflow.py` 將嚴格守門 Stage 1 快取與佔位符解算正確性。

> ❓ **尖銳問題 3**：`core` 模組退出注入後，CLI 的調用合規性是否會失去防護？  
> 💡 **防護解法**：CLI 防呆已有 `AGENTS.md` 守門原則與 `yscb-cli-guild` Skill 作為前端第一道防線；在 `SessionAnalysis` 中，CLI 作為四大維度之一進行次數統計與 I/O Token 消耗計量，職責分工更清晰，避免職責交叉重疊。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`core` 模組清理 — 修改 `source/core/contributes/agents-workflow.json` 移除 `RETRO_CHECK_ITEMS`，刪除 `source/core/assets/retro_check.md`。
- [ ] **TASK-02**：`knowledge-db` 模組對齊 — 更新 `source/knowledge-db/contributes/agents-workflow.json` 注入錨點為 `SESSION_ANALYSIS_CHECK_ITEMS`，新增 `source/knowledge-db/assets/session_analysis_check.md`，刪除舊 `retro_check.md`。
- [ ] **TASK-03**：`agents-workflow` Plans 工具鏈正則收斂 — 修改 `verifier.py`, `scanner.py`, `searcher.py` 排除非時間戳目錄。
- [ ] **TASK-04**：`agents-workflow` 工作流與 Token 宣告 — 新增 `SessionAnalysis.md`，刪除 `Retro.md`，更新 `contributes/agents-workflow.json`。
- [ ] **TASK-05**：單元測試編寫與回歸 — 修改 `test_plans_toolchain.py` 增加非時間戳略過測試；新增 `test_session_analysis_workflow.py` 專屬套件。
- [ ] **TASK-06**：本地編譯、打包、安裝與全生態系端到端回歸驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作規劃**：確認依序執行 TASK-01 ~ TASK-06，同步定稿 `P06_test_plan.md` 為 `Confirmed`。
