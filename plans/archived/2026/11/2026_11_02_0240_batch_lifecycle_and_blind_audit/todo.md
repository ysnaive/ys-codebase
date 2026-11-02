# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：2026_11_02_0240_batch_lifecycle_and_blind_audit  
> 建立日期：2026-11-02  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-16] 對 core 中模組生命週期管理系列 CLI 進行升級，支援單次指令批次操作多個模組
- **建立日期**：2026-11-01
- **目標範疇**：`ys_codebase/source/core/`
- **備忘與解法要點**：支援 install/update/remove/rollback 等生命週期指令接受多個模組參數，將依賴解析、uv 虛擬環境同步、install_hooks 觸發與 Server ModulesWatcher 熱重載合併為單次批次交易，避免逐一操作時重複編譯與重載運行環境

### [TODO-17] 於 session-audit 技能引入盲眼子代理 (blind-subagent) 執行客觀審計，防範主代理認知偏差與自我辯護
- **建立日期**：2026-11-01
- **目標範疇**：`ys_codebase/source/agents-workflow/assets/skills/session-audit/`
- **備忘與解法要點**：由無對話歷史包袱之盲眼子代理讀取 session-trace 結構化指標與關鍵 Step 切片執行四象限根因解剖，避免當事主代理因敘事慣性將 Type D 紀律失誤合理化為 Type C
