# 專案輕量級待辦與技術債帳本 (TODO Ledger)

> 主題：專案輕量級待辦與技術債帳本  
> 更新日期：2026-10-29  
> 狀態：Active  
> 最後分配編號：6  
> 模型：Gemini 4 Argon (Low)  

---

## 待辦清單 (Active TODOs)

### [TODO-01] dev release 第三方間接依賴鎖定 (constraints.txt)
- **建立日期**：2026-10-28
- **目標範疇**：`dev/releaser.py, core/pip_manager.py`
- **備忘與解法要點**：於 dev release 支援匯出或附帶 constraints.txt，並由 pip_manager.py 安裝時帶入 -c 參數，防止第三方間接依賴次版本漂移

### [TODO-02] 業務模組內部 URI 解析邊界收斂 (DIP 依賴反轉)
- **建立日期**：2026-10-28
- **目標範疇**：`knowledge-db, agents-workflow`
- **備忘與解法要點**：漸進式將 core.uri 解析收斂至各模組最外層 scripts/cli.py 與 hook.*.py 入口，使內部引擎接收純 Path 物件以利獨立單元測試

### [TODO-03] core.vfs 本地實體代理定位與遠端快取邊界文檔化
- **建立日期**：2026-10-28
- **目標範疇**：`docs/core`
- **備忘與解法要點**：於 docs/core/README.md 與 uri_protocols.md 明確記載 core.vfs 為具 guard.py 權限守衛之本地實體檔案代理層，並定義未來雲端來源為本地快取物化解析器

### [TODO-04] knowledge-db 在 agents-workflow 未安裝時，不應輸出特化給 AI Agents 的相關提示資訊
- **建立日期**：2026-10-29
- **目標範疇**：`knowledge-db (scripts/cli.py, knowledge_db/)`
- **備忘與解法要點**：檢查 module://agents-workflow 是否存在或已安裝；若未安裝則省略專供 Agent 閱讀之截斷導引與專屬提示

### [TODO-05] 處理多個 release_target 投影物化至相同實體路徑但對應之專有名詞/語系文本不同時的碰撞與合併策略
- **建立日期**：2026-10-29
- **目標範疇**：`agents-workflow (agents_workflow/publisher.py, compiler.py)`
- **備忘與解法要點**：例如 antigravity 與 codex 皆投影至 .agents/ 時，檢測同路徑不同 Stage 2 渲染結果之衝突告警、並聯顯示 (如 read_file / exec_command) 或回退通用描述

### [TODO-06] 將執行期 CLI 環境變數嗅探與方言對照機制正規化為宣告式規則，以利後續擴充新宿主環境
- **建立日期**：2026-10-29
- **目標範疇**：`core, agents-workflow (core/locale.py, contributes/)`
- **備忘與解法要點**：將 detect_active_host_dialect 硬編碼之環境變數前綴對照表抽離為 contributes 或結構化註冊表，支援新 release_target 宣告式擴充環境嗅探條件
