<!--

Phase 5 執行指引：
1. 目標：嚴格依照 Phase 3 的拓撲順序與 Phase 4 的 TASK 清單逐項編碼實作。
2. 嚴禁空降實作：未經 Phase 1~4 規劃並獲確認前，嚴禁直接編寫原始碼。
3. 實作偏差三級處置：
   - Minor (實作微調)：在 P05 偏差表登記理由後繼續推進。
   - Moderate (內部架構調整)：更新 P02/P03/P05 並向開發者呈遞變更摘要。
   - Major (API/行為變更)：強制停手發起 /Discuss 討論，獲確認後更新相關 Phase。
4. 範疇保護：遇到異常優先排查本體邏輯，嚴禁擅自跨模組修改外部代碼。
5. Checkpoint 等待關卡：完成所有代碼實作後，標記 TASK 清單並由開發者確認推進至 Phase 6。

-->

# 實作任務清單 (Task Breakdown)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `ys_codebase/source/agents-workflow/manifest.json` 宣告 `claude` 與 `codex` 的 release_target 與投影規則。
- [x] **TASK-02**：在 `ys_codebase/source/agents-workflow/tests/test_targets.py` 編寫單元測試，驗證 targets 列表與發布產物目錄結構。
- [x] **TASK-03**：執行虛擬沙盒跑測 `python yscb.py dev test agents-workflow`，確保 100% Passed。
- [x] **TASK-04**：更新 `docs/agents-workflow/user_guide.md` 交付文檔。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
