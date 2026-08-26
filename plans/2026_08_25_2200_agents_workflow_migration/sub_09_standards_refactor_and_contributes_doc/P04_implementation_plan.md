# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P02 架構設計與 P03 API 規格中有明確對應介面與資產路徑。
- [x] **邊界防護**：EC-01 ~ EC-04 在 Publisher 軟合併、空 target 處理與 `enable_agents_md` 守門中有具體防護。
- [x] **依賴純淨**：100% Python 標準庫，符合 NFR-01~03 約束。
- [x] **Test-First 剛性定稿**：`P06_test_plan.md` (FT-01~05, ET-01, RT-01) 已同步剛性定稿 (Confirmed)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | Modify | 更新模組概覽，加入 `contributes.format.md` 索引與雙標準資產說明。 |
| **維度 2** | `docs/agents-workflow/user_guide.md` | Modify | 補充 `config.project.json` 開關說明 (`enable_agents_md`, `enable_project_changelog`) 與空 target 行為。 |
| **維度 4** | `source/agents-workflow/contributes.format.md` | New | 建立官方 Contributes 擴充規範規格手冊（`export`, `token`, `insert`, `release_target`, `uri_schemes`）。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若專案 `config.project.json` 中 `"release_targets"` 為空陣列 `[]`，執行 `agents-workflow release` 會不會因為缺少 target 拓撲而導致崩潰或未定義行為？  
> 💡 **防護解法**：`ReleasePublisher.release_all()` 在 `active_target_names` 為空時，安全略過投影發布循環，輸出 `published_count: 0`；同時若 `enable_agents_md` 為 `True` 且有 `AgentsStandards`，會回退使用專案級相對路徑進行 `AGENTS.md` 軟合併，保證防呆健壯性 (EC-02)。

> ❓ **尖銳問題 2**：若使用者在 `AGENTS.md` 標籤之外自行寫入大量特化工程規範，軟合併時是否可能因為正則不當而誤刪或覆蓋使用者代碼？  
> 💡 **防護解法**：`_soft_merge_agents_md` 使用嚴格的 `re.compile(r'<!-- YSCB_AGENTS_BEGIN -->.*?<!-- YSCB_AGENTS_END -->', re.DOTALL)` 精確替換標籤內部區塊，標籤前置與後置的自定義內容 100% 原樣保留 (EC-01)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (標準資產拆分)**：
  - 新建 `source/agents-workflow/assets/standards/AgentsStandards.md`（收斂通用核心原則與防呆紀律）。
  - 重構 `source/agents-workflow/assets/standards/DevelopmentStandards.md`（移除第 1 章，保留工作目錄規範、追溯鏈矩陣、模板指針、三大分流與 SOP 0~7 完整流程）。
- [ ] **TASK-02 (Contributes 宣告與組態調整)**：
  - 修改 `source/agents-workflow/manifest.json`（註冊 `AgentsStandards.md` export 與 Token）。
  - 修改 `source/agents-workflow/config.project.json`（將 `"release_targets"` 預設改為 `[]`）。
  - 新建 `source/agents-workflow/contributes.format.md`（官方完整規格說明手冊）。
- [ ] **TASK-03 (發布引擎重構)**：
  - 修改 `source/agents-workflow/agents_workflow/publisher.py`：
    - `_soft_merge_agents_md` 提取 `AgentsStandards` 替代 `DevelopmentStandards`。
    - 落實 `enable_agents_md: false` 守門跳過邏輯。
    - 支援 `release_targets: []` 安全發布。
- [ ] **TASK-04 (測試案例撰寫與驗證)**：
  - 修改 `source/agents-workflow/tests/test_publisher.py`，擴充單元測試覆蓋 FT-01~05 與 ET-01。
  - 實機跑測 `python yscb.py dev test agents-workflow` 與 `python yscb.py dev test --all`。
- [ ] **TASK-05 (知識庫 1:1 交付與 Dogfooding 同步)**：
  - 更新 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。
  - 執行 `agents-workflow release antigravity` 重新生成 `.agents/` 產物，驗證 `AGENTS.md` 精簡效果。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 標準規範與開發流程職責徹底解耦：`AgentsStandards.md` 專注於 Agent 行為準則與防呆紀律；`DevelopmentStandards.md` 專注於專案 SOP 流程作業指引。
- **[P04:DR-02]** `AGENTS.md` 自動軟合併僅注入精簡 `AgentsStandards.md`，顯著優化每次交互之 Token 與 Context 負載。
