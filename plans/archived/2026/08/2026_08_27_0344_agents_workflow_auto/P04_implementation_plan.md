# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Agents-Workflow 模組新增 Auto 工作流 (Add Auto Workflow to Agents-Workflow)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 依據 P01~P03：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md) / [P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與架構設計中均有對應檔案與契約。
- [x] **邊界防護**：EC-01 ~ EC-06 均在 `Auto.md` 熔斷守門與執行步驟中具體定義防護行為。
- [x] **依賴純淨**：嚴格遵守 Dogfooding 三層空間隔離規範，代碼 100% 位於 `source/agents-workflow/`。
- [x] **測試前置定稿**：`P06_test_plan.md` 已完成與 FR/EC 1:1 映射並定稿為 `Confirmed`。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 4 (工作流指引)** | `docs/agents-workflow/user_guide.md` | Update | 於工作流清冊章節追加 `/Auto` 自動連續推進工作流之定位、適用時機（Phase 01~05）與三大熔斷原則。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若開發者在某計畫剛執行 `/NewPlan` 且處於 Phase 0 討論階段時就輸入 `/Auto`，Agent 是否會自作主張推進到 Phase 5？**  
> 💡 **防護解法**：絕對不會。`Auto.md` 步驟 1 明確規範邊界守門：若目標計畫處於 Phase 0，Agent 必須強制阻斷並提示「Phase 0 討論必須由開發者確認定稿，P00 Confirmed 後方可啟用 `/Auto`」，杜絕臆測。

> ❓ **尖銳問題 2：若在 Phase 5 實作程式碼時，發現既有代碼架構缺陷需要更改 Public API 或外部模組（Major/Critical 偏差），Auto 模式會不會盲目繼續跑測？**  
> 💡 **防護解法**：絕對不會。觸發「偏差熔斷 (Deviation Gate)」與除錯排查範疇保護鐵律，Agent 必須強制停手發起 `/Discuss` 進行根因分析與範疇確認，獲開發者授權後方可繼續。

> ❓ **尖銳問題 3：若 Phase 6 自動化測試 CLI 跑測 100% Passed，Agent 會不會自動跨入 Phase 7 結案？**  
> 💡 **防護解法**：絕對不會。Auto 流程受「P06 手動/UX 驗證絕對阻斷」剛性約束，抵達 Phase 6 測試完成後強制停步，立即 End Turn 等待開發者人工/UX 驗證回覆。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：建立 `source/agents-workflow/assets/workflows/Auto.md` 工作流指引資產文檔。
- [ ] **TASK-02**：增補 `source/agents-workflow/assets/standards/DevelopmentStandards.md` §4.4 自動連續推進模式。
- [ ] **TASK-03**：更新 `source/agents-workflow/manifest.json`，於 `contributes["agents-workflow"]["export"]` 宣告導出 `Auto.md`。
- [ ] **TASK-04**：撰寫 `source/agents-workflow/tests/test_auto_workflow.py` 單元測試套件。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] (實作計畫與文檔交付定稿)**：
  - 定稿 4 大拓撲實作任務與 `docs/agents-workflow/user_guide.md` 文檔交付規劃。
- **[P04:DR-02] (剛性定稿 P06 測試計畫)**：
  - 剛性審查並確認 `P06_test_plan.md` 包含 3 項功能測試、3 項邊界測試、1 項回歸測試與 1 項 UX 驗證。
