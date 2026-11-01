# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：sub_03_multi_platform_release_targets  
> 建立日期：2026-11-01  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-05] 處理多個 release_target 投影物化至相同實體路徑但對應之專有名詞/語系文本不同時的碰撞與合併策略
- **建立日期**：2026-10-29
- **目標範疇**：`agents-workflow (agents_workflow/publisher.py, compiler.py)`
- **備忘與解法要點**：例如 antigravity 與 codex 皆投影至 .agents/ 時，檢測同路徑不同 Stage 2 渲染結果之衝突告警、並聯顯示 (如 read_file / exec_command) 或回退通用描述

### [TODO-06] 將執行期 CLI 環境變數嗅探與方言對照機制正規化為宣告式規則，以利後續擴充新宿主環境
- **建立日期**：2026-10-29
- **目標範疇**：`core, agents-workflow (core/locale.py, contributes/)`
- **備忘與解法要點**：將 detect_active_host_dialect 硬編碼之環境變數前綴對照表抽離為 contributes 或結構化註冊表，支援新 release_target 宣告式擴充環境嗅探條件
