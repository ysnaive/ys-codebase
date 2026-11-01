# 專案輕量級待辦與技術債帳本 (TODO Ledger)

> 主題：專案輕量級待辦與技術債帳本  
> 更新日期：2026-11-01  
> 狀態：Active  
> 最後分配編號：15  
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

### [TODO-07] pip_manager ensure_venv 與 _bootstrap_pip 改拋 PipInstallError 避免無 ensurepip 環境冷啟動連坐崩潰
- **建立日期**：2026-11-01
- **目標範疇**：`core (pip_manager.py, installer.py)`
- **備忘與解法要點**：將 ensure_venv 與 _bootstrap_pip 拋出之 RuntimeError 統一改為 PipInstallError，使 installer.sync_pip_dependencies 能攔截並降級為 Warning，不阻斷零依賴模組冷啟動自舉

### [TODO-08] TopologyLinker 三處靜態消歧邏輯漏洞修復 (委派呼叫自綁定、單一候選幽靈邊、短變數子字串誤配)
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (linker.py)`
- **備忘與解法要點**：1. 移除 if prefix 分支內對 caller_class 的錯誤回退；2. 加固 len(candidates) == 1 的連線門檻（需通過 _score_candidates 或同檔案定義）；3. 收緊 _score_candidates 子字串匹配要求 len(prefix_tail) >= 3

### [TODO-09] KnowledgeDB .watcher_active 寫入時序與異常清理及 .watcher_dirty 前台檢核對齊
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (service.py, pipeline.py)`
- **備忘與解法要點**：1. 將寫入 .watcher_active 移至 observer.start() 成功後並在 except 被動模式清理；2. 對齊 pipeline._is_watcher_active 對 .watcher_dirty 的讀取檢核與 [DN-04] 文檔契約

### [TODO-11] 報錯尾端 [Agent Directive] 技能路由注入、Windows 安裝前主動通知 Server 釋放句柄與 .old_* 延遲清理及 VFS 註解收斂
- **建立日期**：2026-11-01
- **目標範疇**：`core, dev, server (validator.py, installer.py, engine.py, vfs.py, checker.py)`
- **備忘與解法要點**：1. 於 validator.py 與 checker.py 報錯尾端注入 [Agent Directive] 指引查閱對應 Skill；2. 於 installer.py 生命周期變異前主動通知活躍 Server 停機/卸載 Worker 釋放 .pyd/.dll 句柄，並對 .old_* 採非阻塞容錯延遲回收；3. 清理 vfs.py 不切實際之 MemoryBackend 註解

### [TODO-12] cmd_restore 版本號比對修復 (根治跨分支 auto-restore 死迴圈) 與 plan verify 硬編碼絕對路徑可攜性警告
- **建立日期**：2026-11-01
- **目標範疇**：`yscb.py, core (installer.py), agents-workflow (verifier.py)`
- **備忘與解法要點**：1. 修正 yscb.py 與 installer.py 之 cmd_restore 跳過條件，比對已安裝 manifest.json 之 version == ver，版號不符時自動覆寫更新；2. 於 plan verify 掃描計畫 .md 若含 file:/// 或磁碟機代號 (C:/, D:/) 發出可攜性警告

### [TODO-14] knowledge-db SpaceDef 宣告式檢索權重 (weight) 支援與 plan status 已完成計畫歸檔提醒
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (contributes/_format.json, space.py, hybrid.py), agents-workflow (contributes/knowledge-db.json, status.py, cli.py)`
- **備忘與解法要點**：1. 於 knowledge-db SpaceDef 新增選填 weight: float? (預設 1.0) 並於檢索算分乘算，由 agents-workflow 預設賦予 docs 高於 plans 之權重且天然支援下游 project 級 contribute.json 覆寫；2. 於 plan status 對 plans/ 下已 Completed/Concluded 計畫顯示 plan archive 提醒

### [TODO-15] knowledge-db C#/C++ AST 成員修飾詞 visibility 解析與 C# 跨檔案 partial class 符號聚合
- **建立日期**：2026-11-01
- **目標範疇**：`knowledge-db (parsers/treesitter.py, queries/c_sharp.scm, linker.py)`
- **備忘與解法要點**：1. 修正 treesitter.py 從 AST modifier 節點解析 public/private/protected/internal 可見度（僅 Python 回退底線規則）；2. 支援同 Space 同 Namespace 之 C# partial class 符號與成員跨檔聚合
