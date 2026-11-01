# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 建立日期：2026-11-01  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-04] knowledge-db 在 agents-workflow 未安裝時，不應輸出特化給 AI Agents 的相關提示資訊
- **建立日期**：2026-10-29
- **目標範疇**：`knowledge-db (scripts/cli.py, knowledge_db/)`
- **備忘與解法要點**：檢查 module://agents-workflow 是否存在或已安裝；若未安裝則省略專供 Agent 閱讀之截斷導引與專屬提示

### [TODO-08] TopologyLinker 三處靜態消歧邏輯漏洞修復 (委派呼叫自綁定、單一候選幽靈邊、短變數子字串誤配)
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (linker.py)`
- **備忘與解法要點**：1. 移除 if prefix 分支內對 caller_class 的錯誤回退；2. 加固 len(candidates) == 1 的連線門檻（需通過 _score_candidates 或同檔案定義）；3. 收緊 _score_candidates 子字串匹配要求 len(prefix_tail) >= 3

### [TODO-09] KnowledgeDB .watcher_active 寫入時序與異常清理及 .watcher_dirty 前台檢核對齊
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (service.py, pipeline.py)`
- **備忘與解法要點**：1. 將寫入 .watcher_active 移至 observer.start() 成功後並在 except 被動模式清理；2. 對齊 pipeline._is_watcher_active 對 .watcher_dirty 的讀取檢核與 [DN-04] 文檔契約

### [TODO-14] knowledge-db SpaceDef 宣告式檢索權重 (weight) 支援與 plan status 已完成計畫歸檔提醒
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (contributes/_format.json, space.py, hybrid.py), agents-workflow (contributes/knowledge-db.json, status.py, cli.py)`
- **備忘與解法要點**：1. 於 knowledge-db SpaceDef 新增選填 weight: float? (預設 1.0) 並於檢索算分乘算，由 agents-workflow 預設賦予 docs 高於 plans 之權重且天然支援下游 project 級 contribute.json 覆寫；2. 於 plan status 對 plans/ 下已 Completed/Concluded 計畫顯示 plan archive 提醒

### [TODO-15] knowledge-db C#/C++ AST 成員修飾詞 visibility 解析與 C# 跨檔案 partial class 符號聚合
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (parsers/treesitter.py, queries/c_sharp.scm, linker.py)`
- **備忘與解法要點**：1. 修正 treesitter.py 從 AST modifier 節點解析 public/private/protected/internal 可見度（僅 Python 回退底線規則）；2. 支援同 Space 同 Namespace 之 C# partial class 符號與成員跨檔聚合
