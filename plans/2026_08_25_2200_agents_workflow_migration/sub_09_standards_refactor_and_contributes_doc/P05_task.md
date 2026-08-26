# 實作任務清單 (Task Breakdown)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (標準資產拆分)**：
  - 新建 `source/agents-workflow/assets/standards/AgentsStandards.md`（收斂通用核心原則與防呆紀律）。
  - 重構 `source/agents-workflow/assets/standards/DevelopmentStandards.md`（移除第 1 章，保留工作目錄規範、追溯鏈矩陣、模板指針、三大分流與 SOP 0~7 完整流程）。
- [x] **TASK-02 (Contributes 宣告與組態調整)**：
  - 修改 `source/agents-workflow/manifest.json`（註冊 `AgentsStandards.md` export 與 Token）。
  - 修改 `source/agents-workflow/config.project.json`（將 `"release_targets"` 預設改為 `[]`）。
  - 新建 `source/agents-workflow/contributes.format.md`（官方完整規格說明手冊）。
- [x] **TASK-03 (發布引擎重構)**：
  - 修改 `source/agents-workflow/agents_workflow/publisher.py`：
    - `_soft_merge_agents_md` 提取 `AgentsStandards` 替代 `DevelopmentStandards`。
    - 落實 `enable_agents_md: false` 守門跳過邏輯。
    - 支援 `release_targets: []` 安全發布與無 target 時之軟合併支援。
- [x] **TASK-04 (測試案例撰寫與驗證)**：
  - 修改 `source/agents-workflow/tests/test_compiler.py`，擴充單元測試覆蓋 FT-01~05 與 ET-01。
  - 實機跑測 `python yscb.py dev test agents-workflow`（21/21 Passed）與 `python yscb.py dev test --all`（114/114 Passed）。
- [ ] **TASK-05 (知識庫 1:1 交付與 Dogfooding 同步)**：
  - 更新 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。
  - 執行 `agents-workflow release antigravity` 重新生成 `.agents/` 產物，驗證 `AGENTS.md` 精簡效果。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-03 | Minor | 當 `release_targets: []` 但 `enable_agents_md: true` 時，若未經過 target 映射，直接自 Stage 1 resolved_items 提取 `AgentsStandards` 並以空 deployment_map 透過專案級協議安全轉譯注入 `AGENTS.md`。 | 已於 `publisher.py` 實作防護邏輯並通過單元測試驗證。 |
